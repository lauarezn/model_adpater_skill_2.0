#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPU 硬件对比与选型引擎
=======================
本模块将仓库的硬件对比/选型能力沉淀为独立 Python 引擎，口径与既有实现保持一致：
  - 多 GPU 对比  对齐 token_calculator.html 的「不同 GPU 对比」表
  - 卡型推荐     对齐 ascend-presales-recommend 的 hw_estimate()（显存三约束 → 卡数 + TCO）

数据源复用仓库 data/ 目录：
  - GPU 参数库   data/gpu_lib.json（与 Admin「GPU 硬件参数」共用）
  - 模型参数库   data/model-params.json（与 Admin「全球AI模型参数」共用）

仅依赖 Python 标准库，无第三方依赖。只读数据文件，不修改任何数据。
"""
import json
import argparse
import os
import datetime

# 与 ascend-presales-recommend / hardware-estimation.js 口径一致
BYTES = {'fp16': 2, 'int8': 1, 'int4': 0.5, 'fp32': 4}
KV_BYTES = {'fp16': 2, 'int8': 1, 'int4': 0.5, 'fp32': 4}
EFFICIENCY = 0.65
# KV 经验比例（无模型结构时用）：权重 3%，按 4096 seq 归一
KV_RATIO = 0.03
KV_BASE_SEQ = 4096
# 额外运行时开销（权重 8% + 2GB 固定）
OVERHEAD_RATIO = 0.08
OVERHEAD_FIXED = 2
# 单集群可部署上限
MAX_CARDS = 512

DEFAULT_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class HwError(Exception):
    pass


def _num(v, name, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        raise HwError('参数 %s 非法: %r' % (name, v))


# ============ 数据加载 ============

def load_gpu_lib(repo=None):
    repo = repo or DEFAULT_REPO
    path = os.path.join(repo, 'data', 'gpu_lib.json')
    if not os.path.exists(path):
        raise HwError('未找到 GPU 参数库: %s' % path)
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    hw = data['hardware'] if isinstance(data, dict) and 'hardware' in data else data
    return list(hw)


def load_model_lib(repo=None):
    repo = repo or DEFAULT_REPO
    path = os.path.join(repo, 'data', 'model-params.json')
    if not os.path.exists(path):
        raise HwError('未找到模型参数库: %s' % path)
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
            'kvHeads': m.get('kvHeads'),
            'headDim': m.get('headDim'),
            'ctx': m.get('context'),
            'moe': 'Yes' if is_moe else 'No',
            'arch': m.get('architecture') or ('MoE' if is_moe else 'Dense'),
        }
    return lib


def resolve_model(model_lib, name):
    m = model_lib.get(name)
    if m is None:
        low = (name or '').lower()
        for k, v in model_lib.items():
            if k.lower() == low or v['modelCode'].lower() == low:
                return v
    return m


# ============ 核心计算 ============

def model_vram_est(active_b, precision, in_len, out_len, model=None):
    """
    估算总显存占用（GB）。有模型结构时按真实 KV Cache 公式，否则用经验比例。
    返回 (weight_gb, kv_gb, total_gb)
    """
    prec = (precision or 'fp16').lower()
    bytes_p = BYTES.get(prec, 2)
    kv_bytes = KV_BYTES.get(prec, 2)
    weight_gb = active_b * bytes_p
    if model and model.get('layers') and model.get('kvHeads') and model.get('headDim'):
        seq = max((in_len or 0) + (out_len or 0), 1)
        kv_gb = 2 * model['layers'] * model['kvHeads'] * model['headDim'] * seq * kv_bytes / 1e9
    else:
        total_seq = max((in_len or 0) + (out_len or 0), 1)
        kv_gb = weight_gb * KV_RATIO * (total_seq / KV_BASE_SEQ)
    total_gb = weight_gb + kv_gb + (weight_gb * OVERHEAD_RATIO + OVERHEAD_FIXED)
    return weight_gb, kv_gb, total_gb


def gpu_compare(model, precision='fp16', in_len=512, out_len=512, gpu_names=None, repo=None):
    """
    多 GPU 对比：给定模型 + 精度 + 输入/输出长度，计算每款 GPU 的
    权重体积、理论/实际 Decode、Prefill 时间、单卡是否放得下、性价比(tok/s per 万元)。
    gpu_names 为 None 时对比全部卡型。
    """
    gpu_lib = load_gpu_lib(repo)
    if gpu_names:
        gpu_lib = [g for g in gpu_lib if g.get('name') in gpu_names]
        if not gpu_lib:
            raise HwError('指定的 GPU 型号在参数库中不存在: %s' % gpu_names)

    weight_gb, kv_gb, total_gb = model_vram_est(model['active'], precision, in_len, out_len, model)

    rows = []
    for g in gpu_lib:
        name = g.get('name')
        bw = g.get('bw') or 0
        fp16 = g.get('fp16') or 0
        vram = g.get('vram') or 0
        price = g.get('price') or 0
        # Decode：带宽 ÷ (权重+KV) × 效率；理论速度 = 带宽 ÷ 权重
        denom = weight_gb + kv_gb
        theo = bw / weight_gb if (bw and weight_gb) else 0
        actual = (bw / denom) * EFFICIENCY if (bw and denom) else 0
        # Prefill ms
        prefill_ms = 2 * model['total'] * in_len / fp16 * 1000 if fp16 else 0
        # 单卡是否放得下
        enough = (weight_gb + kv_gb) <= vram
        # 性价比：每万元可获得的实际吞吐 (tok/s / 万元)
        cost_wan = price / 10000 if price else 0
        perf_per_wan = actual / cost_wan if cost_wan > 0 else 0
        rows.append({
            'gpu': name,
            'bandwidth': bw,
            'fp16_tflops': fp16,
            'vram': vram,
            'weight_gb': round(weight_gb, 1),
            'kv_gb': round(kv_gb, 2),
            'theo_decode_toks': theo,
            'actual_decode_toks': actual,
            'prefill_ms': prefill_ms,
            'enough_single_gpu': enough,
            'price_cny': price,
            'perf_per_wan': perf_per_wan,
        })
    # 默认按实际吞吐降序；性价比仅供参考
    rows.sort(key=lambda r: r['actual_decode_toks'], reverse=True)
    return rows


def recommend_cards(model, precision='fp16', in_len=512, out_len=512, qps=1.0, repo=None):
    """
    卡型推荐：给定模型 + 精度 + 输入/输出长度 + 目标 QPS，
    按「显存三约束」为每款 GPU 求所需卡数 + TCO，按成本升序取前 3。
    对齐 ascend-presales-recommend 的 hw_estimate() 口径。
    """
    in_len = in_len or 0
    out_len = out_len or 0
    qps = qps or 0
    weight_gb, kv_gb, total_gb = model_vram_est(model['active'], precision, in_len, out_len, model)

    gpu_lib = load_gpu_lib(repo)
    plans = []
    over_capacity = False
    for g in gpu_lib:
        if not g.get('vram') or not g.get('name') or not (g.get('price') or 0):
            continue
        vram = g['vram']
        bw = g.get('bw') or 0
        fp16 = g.get('fp16') or 0
        price = g.get('price') or 0

        # 约束1：显存（单卡可用按 90%）
        cards_vram = -(-total_gb // (vram * 0.9))
        # 约束2：Decode（单卡聚合，大显存 batch=16，否则 8）
        batch_per_gpu = 16 if vram >= 60 else 8
        denom = weight_gb + kv_gb
        per_seq = (bw / denom) * EFFICIENCY if (bw and denom) else 0
        dec_per_card = per_seq * batch_per_gpu
        needed_dec = qps * out_len
        cards_dec = -(-needed_dec // dec_per_card) if dec_per_card > 0 else 10**9
        # 约束3：Prefill
        pre_per_card = (fp16 * 1e12) / (2 * model['active'] * 1e9) if (fp16 and model['active']) else 0
        needed_pre = qps * in_len
        cards_pre = -(-needed_pre // pre_per_card) if pre_per_card > 0 else 10**9

        cards = max(cards_vram, cards_dec, cards_pre)
        if cards > MAX_CARDS:
            over_capacity = True
            continue
        plans.append({
            'gpu': g['name'],
            'vram': vram,
            'cards': cards,
            'total_vram_gb': vram * cards,
            'cost_cny': price * cards,
        })
    plans.sort(key=lambda x: x['cost_cny'])

    result = {'total_vram_gb': round(total_gb, 1), 'plans': plans[:3]}

    # 全部卡型超限：返回所需卡数最少的卡型，标注 over_capacity
    if not plans and over_capacity:
        best = None
        for g in gpu_lib:
            if not g.get('vram') or not g.get('name') or not (g.get('price') or 0):
                continue
            vram = g['vram']
            bw = g.get('bw') or 0
            fp16 = g.get('fp16') or 0
            cards_vram = -(-total_gb // (vram * 0.9))
            batch_per_gpu = 16 if vram >= 60 else 8
            denom = weight_gb + kv_gb
            per_seq = (bw / denom) * EFFICIENCY if (bw and denom) else 0
            dec_per_card = per_seq * batch_per_gpu
            cards_dec = -(-(qps * out_len) // dec_per_card) if dec_per_card > 0 else 10**9
            pre_per_card = (fp16 * 1e12) / (2 * model['active'] * 1e9) if (fp16 and model['active']) else 0
            cards_pre = -(-(qps * in_len) // pre_per_card) if pre_per_card > 0 else 10**9
            cards = max(cards_vram, cards_dec, cards_pre)
            if best is None or cards < best['cards']:
                best = {'gpu': g['name'], 'vram': vram, 'cards': cards,
                        'total_vram_gb': vram * cards,
                        'cost_cny': (g.get('price') or 0) * cards}
        if best:
            best['over_capacity'] = True
            result['plans'] = [best]
    return result


# ============ 输出辅助 ============

def fmt(n, digits=None):
    if n is None or (isinstance(n, float) and n != n):
        return '-'
    if digits is None:
        digits = 2 if abs(n) >= 1000 else 4
    v = round(n, digits)
    if v == int(v):
        v = int(v)
    return '{:,}'.format(v)


def render_compare(model, rows):
    lines = []
    lines.append('=' * 76)
    lines.append('GPU 对比  ·  %s (%s)  总参 %sB 激活 %sB' % (model['name'], model['modelCode'], fmt(model['total']), fmt(model['active'])))
    lines.append('=' * 76)
    lines.append('%-22s %9s %10s %9s %9s %6s %9s %10s' % (
        'GPU', '带宽GB/s', '实际tok/s', 'Prefill ms', '显存GB', '够', '价格万', 'tok/s/万元'))
    lines.append('-' * 76)
    for r in rows:
        lines.append('%-22s %9s %10s %9s %9s %6s %9s %10s' % (
            r['gpu'][:22], fmt(r['bandwidth']), fmt(r['actual_decode_toks']),
            fmt(r['prefill_ms']), fmt(r['vram']),
            '✅' if r['enough_single_gpu'] else '❌',
            fmt(r['price_cny'] / 10000), fmt(r['perf_per_wan'])))
    lines.append('=' * 76)
    return '\n'.join(lines)


def render_plans(model, result):
    lines = []
    lines.append('=' * 76)
    lines.append('卡型推荐  ·  %s (%s)  激活 %sB  总显存需求约 %s GB' % (
        model['name'], model['modelCode'], fmt(model['active']), fmt(result['total_vram_gb'])))
    lines.append('=' * 76)
    for p in result['plans']:
        tag = '  (超出单集群上限)' if p.get('over_capacity') else ''
        lines.append('  %s × %s 卡   总显存 %s GB   成本 %s 万%s' % (
            p['gpu'], p['cards'], fmt(p['total_vram_gb']), fmt(p['cost_cny'] / 10000), tag))
    lines.append('=' * 76)
    return '\n'.join(lines)


# ============ CLI ============

def main():
    ap = argparse.ArgumentParser(description='GPU 硬件对比与选型引擎')
    ap.add_argument('--repo', default=DEFAULT_REPO, help='仓库根目录（含 data/），默认自动探测')
    ap.add_argument('--model', required=True, help='模型名称（如 DeepSeek-V3 / Qwen2.5-72B）')
    ap.add_argument('--precision', default='fp16', choices=['fp16', 'int8', 'int4', 'fp32'],
                    help='量化精度（默认 fp16）')
    ap.add_argument('--in-len', type=float, default=512, help='输入长度 tokens（默认 512）')
    ap.add_argument('--out-len', type=float, default=512, help='输出长度 tokens（默认 512）')
    ap.add_argument('--gpus', nargs='*', default=None,
                    help='参与对比的 GPU 型号列表（不指定则全部）')
    ap.add_argument('--qps', type=float, default=1.0, help='目标 QPS（用于卡型推荐，默认 1）')
    ap.add_argument('--mode', choices=['compare', 'recommend', 'all'], default='all',
                    help='compare=多GPU对比 / recommend=卡型推荐 / all=两者')
    ap.add_argument('--out', help='输出 JSON 文件路径（可选）')
    ap.add_argument('--json', action='store_true', help='仅输出 JSON')
    args = ap.parse_args()

    model_lib = load_model_lib(args.repo)
    model = resolve_model(model_lib, args.model)
    if model is None:
        raise HwError('未找到模型: %s' % args.model)

    report = {
        'meta': {
            'model': model['name'],
            'model_code': model['modelCode'],
            'arch': model['arch'],
            'moe': model['moe'],
            'precision': args.precision,
            'in_len': args.in_len,
            'out_len': args.out_len,
            'qps': args.qps,
            'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'model': {k: model[k] for k in ('name', 'modelCode', 'total', 'active', 'layers', 'kvHeads', 'headDim', 'ctx', 'arch', 'moe')},
    }
    if args.mode in ('compare', 'all'):
        report['compare'] = gpu_compare(model, args.precision, args.in_len, args.out_len, args.gpus, args.repo)
    if args.mode in ('recommend', 'all'):
        report['recommend'] = recommend_cards(model, args.precision, args.in_len, args.out_len, args.qps, args.repo)

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if 'compare' in report:
            print(render_compare(model, report['compare']))
            print()
        if 'recommend' in report:
            print(render_plans(model, report['recommend']))


if __name__ == '__main__':
    main()
