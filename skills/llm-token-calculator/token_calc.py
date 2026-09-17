#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Token 计算器（独立计算引擎）
=================================
本模块从 token_calculator.html 的 recalc() 逻辑抽离为独立 Python 引擎，保持算法口径完全一致。
数据源复用仓库 data/ 目录：
  - GPU 参数库   data/gpu_lib.json     （与 Admin「GPU 硬件参数」共用）
  - 模型参数库   data/model-params.json（与 Admin「全球AI模型参数」共用）

仅依赖 Python 标准库，无第三方依赖。只读数据文件，不修改任何数据。
"""
import json
import argparse
import os
import datetime
from collections import OrderedDict

# 量化精度 -> 每参数字节数（与页面 QUANT_BYTES 一致）
QUANT_BYTES = {'FP32': 4, 'FP16': 2, 'INT8': 1, 'INT4': 0.5, 'INT2': 0.25}
# KV Cache 精度 -> 每元素字节数（与页面 KV_BYTES 一致，无 INT2）
KV_BYTES = {'FP32': 4, 'FP16': 2, 'INT8': 1, 'INT4': 0.5}

DEFAULT_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CalcError(Exception):
    pass


# ============ 数据加载 ============

def load_gpu_lib(repo=None):
    """加载 GPU 参数库，返回 {name: {bw, fp16, fp8, vram, memType, ic, price}}"""
    repo = repo or DEFAULT_REPO
    path = os.path.join(repo, 'data', 'gpu_lib.json')
    if not os.path.exists(path):
        raise CalcError('未找到 GPU 参数库: %s' % path)
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    hw = data['hardware'] if isinstance(data, dict) and 'hardware' in data else data
    lib = {}
    for g in hw:
        lib[g['name']] = {
            'bw': g.get('bw'),
            'fp16': g.get('fp16'),
            'fp8': g.get('fp8'),
            'vram': g.get('vram'),
            'memType': g.get('memType'),
            'ic': g.get('ic'),
            'price': g.get('price'),
        }
    return lib


def load_model_lib(repo=None):
    """加载模型参数库，返回 {name: {...}}。仅保留可计算模型（总参/层数/KV头数/头维度齐全）。"""
    repo = repo or DEFAULT_REPO
    path = os.path.join(repo, 'data', 'model-params.json')
    if not os.path.exists(path):
        raise CalcError('未找到模型参数库: %s' % path)
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    items = data['models'] if isinstance(data, dict) and 'models' in data else data
    lib = {}
    for m in items:
        if not m:
            continue
        if m.get('totalParams') is None or m.get('layers') is None or \
           m.get('kvHeads') is None or m.get('headDim') is None:
            continue
        is_moe = m.get('isMoE') in ('是', 'Yes', True)
        name = (m.get('name') or m.get('modelCode') or '').strip() or m.get('modelCode')
        lib[name] = {
            'name': name,
            'modelCode': m.get('modelCode') or name,
            'total': m.get('totalParams'),
            'active': m.get('activeParams') if m.get('activeParams') is not None else m.get('totalParams'),
            'layers': m.get('layers'),
            'heads': m.get('attentionHeads'),
            'kvHeads': m.get('kvHeads'),
            'headDim': m.get('headDim'),
            'ctx': m.get('context'),
            'arch': m.get('architecture') or ('MoE' if is_moe else 'Dense'),
            'moe': 'Yes' if is_moe else 'No',
        }
    return lib


# ============ 计算核心（与 token_calculator.html recalc() 口径一致） ============

def calc(params):
    """
    核心计算。params 为 dict，键：
      gpu_name, model_name,
      gpu_count, bandwidth, fp16, vram,           # 显存带宽/FP16算力/显存容量（通常由 gpu 联动）
      quant_prec, kv_prec,                          # 量化精度 / KV 精度
      prompt_len, gen_len, efficiency, tp_coef, seq # 提示/生成长度、效率系数、TP通信系数、实际上下文
    返回结构化计算结果 dict。
    """
    bw = _num(params.get('bandwidth'), 'bandwidth')
    fp16 = _num(params.get('fp16'), 'fp16')
    vram = _num(params.get('vram'), 'vram')
    gpu_count = max(1, int(_num(params.get('gpu_count'), 'gpu_count') or 1))

    m = params['model']
    total = m['total']
    active = m['active']
    layers = m['layers']
    kv_heads = m['kvHeads']
    head_dim = m['headDim']

    quant = params.get('quant_prec', 'INT8').upper()
    kvp = params.get('kv_prec', 'FP16').upper()
    if quant not in QUANT_BYTES:
        raise CalcError('未知量化精度: %s' % quant)
    if kvp not in KV_BYTES:
        raise CalcError('未知 KV 精度: %s' % kvp)
    bytes_per_param = QUANT_BYTES[quant]
    kv_bytes = KV_BYTES[kvp]

    prompt_len = _num(params.get('prompt_len'), 'prompt_len')
    gen_len = _num(params.get('gen_len'), 'gen_len')
    efficiency = _num(params.get('efficiency'), 'efficiency')
    tp_coef = _num(params.get('tp_coef'), 'tp_coef')
    seq = _num(params.get('seq'), 'seq')

    # 模型权重体积 GB
    weight = active * bytes_per_param
    # KV Cache 体积 GB：2×层数×KV头数×头维度×seq×字节/1e9
    kv = 2 * layers * kv_heads * head_dim * seq * kv_bytes / 1e9
    total_vram = weight + kv
    # 理论 Decode（只按权重）
    theo_decode = bw / weight if weight > 0 else 0
    # 考虑 KV 的理论速度
    theo_kv = bw / (weight + kv) if (weight + kv) > 0 else 0
    # 实际 Decode（单卡）
    actual_decode = theo_kv * efficiency
    # 多卡张量并行速度
    tp_speed = (bw * gpu_count) / weight * efficiency * tp_coef if weight > 0 else 0
    # 多卡每卡显存占用
    per_gpu_vram = total_vram / gpu_count if gpu_count > 0 else 0
    # Prefill 时间 ms
    prefill_ms = 2 * total * prompt_len / (fp16 * gpu_count) * 1000 if fp16 > 0 and gpu_count > 0 else 0
    ttft = prefill_ms
    # 生成总耗时 秒
    gen_time = gen_len / actual_decode if actual_decode > 0 else 0
    # 用户感知吞吐
    total_sec = prefill_ms / 1000 + gen_time
    user_thru = gen_len / total_sec if total_sec > 0 else 0
    # 每 Token 算力 GFLOPs
    per_token = 2 * total
    # 每日可生成 Token
    daily = actual_decode * 86400
    # 每百万 Token 显存读取量
    per_million = weight * 1e6

    enough = total_vram <= vram

    return {
        'bytes_per_param': bytes_per_param,
        'kv_bytes': kv_bytes,
        'weight_gb': weight,
        'kv_gb': kv,
        'total_vram_gb': total_vram,
        'per_gpu_vram_gb': per_gpu_vram,
        'enough_single_gpu': enough,
        'theo_decode_toks': theo_decode,
        'theo_with_kv_toks': theo_kv,
        'actual_decode_toks': actual_decode,
        'tp_speed_toks': tp_speed,
        'prefill_ms': prefill_ms,
        'ttft_ms': ttft,
        'gen_time_sec': gen_time,
        'user_thru_toks': user_thru,
        'per_token_gflops': per_token,
        'daily_tokens': daily,
        'per_million_read_gb': per_million,
    }


def _num(v, name):
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        raise CalcError('参数 %s 非法: %r' % (name, v))


# ============ 输出辅助 ============

def fmt(n, digits=None):
    if n is None or (isinstance(n, float) and (n != n)):
        return '-'
    if digits is None:
        digits = 2 if abs(n) >= 1000 else 4
    v = round(n, digits)
    if v == int(v):
        v = int(v)
    return '{:,}'.format(v)


# ============ CLI ============

def build_report(args):
    gpu_lib = load_gpu_lib(args.repo)
    model_lib = load_model_lib(args.repo)

    if args.gpu not in gpu_lib:
        raise CalcError('未找到 GPU 型号: %s（可用: %s…）' % (args.gpu, list(gpu_lib)[:5]))
    gpu = gpu_lib[args.gpu]

    # 模型名支持大小写不敏感匹配
    model_name = args.model
    m = model_lib.get(model_name)
    if m is None:
        low = model_name.lower()
        for k, v in model_lib.items():
            if k.lower() == low or v['modelCode'].lower() == low:
                m = v
                model_name = k
                break
    if m is None:
        raise CalcError('未找到模型: %s' % args.model)

    params = {
        'gpu_name': args.gpu,
        'model_name': model_name,
        'gpu_count': args.gpu_count,
        'bandwidth': gpu['bw'],
        'fp16': gpu['fp16'],
        'vram': gpu['vram'],
        'quant_prec': args.quant,
        'kv_prec': args.kv_prec,
        'prompt_len': args.prompt_len,
        'gen_len': args.gen_len,
        'efficiency': args.efficiency,
        'tp_coef': args.tp_coef,
        'seq': args.seq,
        'model': m,
    }
    r = calc(params)

    report = {
        'meta': {
            'gpu': args.gpu,
            'model': model_name,
            'model_code': m['modelCode'],
            'is_moe': m['moe'],
            'arch': m['arch'],
            'quant': args.quant,
            'kv_prec': args.kv_prec,
            'gpu_count': args.gpu_count,
            'prompt_len': args.prompt_len,
            'gen_len': args.gen_len,
            'efficiency': args.efficiency,
            'tp_coef': args.tp_coef,
            'seq': args.seq,
            'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'gpu': gpu,
        'model': {k: m[k] for k in ('name', 'modelCode', 'total', 'active', 'layers', 'kvHeads', 'headDim', 'ctx', 'arch', 'moe')},
        'result': r,
    }
    return report


def render_text(report):
    meta = report['meta']
    gpu = report['gpu']
    m = report['model']
    r = report['result']
    lines = []
    lines.append('=' * 62)
    lines.append('LLM Token 计算')
    lines.append('=' * 62)
    lines.append('GPU: %s  (带宽 %s GB/s · FP16 %s TFLOPS · 显存 %s GB · %s 卡)' % (
        meta['gpu'], fmt(gpu['bw']), fmt(gpu['fp16']), fmt(gpu['vram']), meta['gpu_count']))
    lines.append('模型: %s (%s)  架构 %s  总参 %sB  激活 %sB' % (
        meta['model'], m['modelCode'], m['arch'], fmt(m['total']), fmt(m['active'])))
    lines.append('精度: %s (每参 %sB) · KV %s (每元素 %sB) · seq %s · 提示 %s / 生成 %s' % (
        meta['quant'], r['bytes_per_param'], meta['kv_prec'], r['kv_bytes'],
        fmt(meta['seq']), fmt(meta['prompt_len']), fmt(meta['gen_len'])))
    lines.append('-' * 62)
    lines.append('模型权重体积       %s GB' % fmt(r['weight_gb']))
    lines.append('KV Cache 体积      %s GB' % fmt(r['kv_gb']))
    lines.append('总显存占用         %s GB  (单卡每卡 %s GB)' % (fmt(r['total_vram_gb']), fmt(r['per_gpu_vram_gb'])))
    lines.append('单卡是否放得下     %s' % ('✅ 足够' if r['enough_single_gpu'] else '❌ 不足，需多卡或更低精度'))
    lines.append('理论 Decode 速度   %s tok/s' % fmt(r['theo_decode_toks']))
    lines.append('考虑 KV 理论速度   %s tok/s' % fmt(r['theo_with_kv_toks']))
    lines.append('实际 Decode 单卡   %s tok/s  (效率 %s)' % (fmt(r['actual_decode_toks']), meta['efficiency']))
    lines.append('多卡 TP 速度       %s tok/s  (通信系数 %s)' % (fmt(r['tp_speed_toks']), meta['tp_coef']))
    lines.append('Prefill 时间       %s ms' % fmt(r['prefill_ms']))
    lines.append('首 Token TTFT      %s ms' % fmt(r['ttft_ms']))
    lines.append('生成总耗时         %s 秒' % fmt(r['gen_time_sec']))
    lines.append('用户感知吞吐       %s tok/s' % fmt(r['user_thru_toks']))
    lines.append('每 Token 算力      %s GFLOPs' % fmt(r['per_token_gflops']))
    lines.append('每日可生成 Token   %s' % fmt(r['daily_tokens']))
    lines.append('每百万Token读取    %s GB' % fmt(r['per_million_read_gb']))
    lines.append('=' * 62)
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description='LLM Token 计算器（独立引擎）')
    ap.add_argument('--repo', default=DEFAULT_REPO, help='仓库根目录（含 data/），默认自动探测')
    ap.add_argument('--gpu', required=True, help='GPU 型号（如 华为昇腾910C / NVIDIA H100 SXM5）')
    ap.add_argument('--model', required=True, help='模型名称（如 DeepSeek-V3）')
    ap.add_argument('--gpu-count', type=int, default=8, help='GPU 数量（默认 8）')
    ap.add_argument('--quant', default='INT8', choices=list(QUANT_BYTES), help='量化精度（默认 INT8）')
    ap.add_argument('--kv-prec', default='FP16', choices=list(KV_BYTES), help='KV Cache 精度（默认 FP16）')
    ap.add_argument('--prompt-len', type=float, default=512, help='提示长度 tokens（默认 512）')
    ap.add_argument('--gen-len', type=float, default=128000, help='生成长度 tokens（默认 128000）')
    ap.add_argument('--efficiency', type=float, default=0.65, help='效率系数（默认 0.65）')
    ap.add_argument('--tp-coef', type=float, default=0.92, help='张量并行通信系数（默认 0.92）')
    ap.add_argument('--seq', type=float, default=8192, help='实际上下文长度 seq（默认 8192）')
    ap.add_argument('--out', help='输出 JSON 文件路径（可选）')
    ap.add_argument('--json', action='store_true', help='仅输出 JSON（不打印文本）')
    args = ap.parse_args()

    report = build_report(args)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))


if __name__ == '__main__':
    main()
