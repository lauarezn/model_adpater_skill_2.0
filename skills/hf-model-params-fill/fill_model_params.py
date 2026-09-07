#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HF 模型参数补全与架构校正脚本（仓库专有）
==========================================
用于维护 data/model-params.json（全球AI模型参数）。

功能：
  1. 抓取 HF(hf-mirror) config.json 补全模型参数（layers/attentionHeads/kvHeads/headDim/context）
  2. 按 config.json 键值判断架构（Dense/MoE）
  3. 应用「Dense 架构 总参=激活参」规则
  4. 修改前自动备份，修改后自动验证一致性

用法：
  python3 fill_model_params.py --code tencent-hy3-preview --repo tencent/Hy3-preview
  python3 fill_model_params.py --repo tencent/Hy3-preview --code tencent-hy3-preview
  python3 fill_model_params.py --all-dense-fix     # 全量校正 Dense 激活=总参

依赖：复用仓库 server.py 的 _http_get / _fetch_hf_config（或独立 urllib 实现）。
"""
import json
import os
import sys
import time
import argparse
import urllib.request
from datetime import datetime

# 仓库根目录（脚本位于 skills/hf-model-params-fill/）
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_FILE = os.path.join(REPO_ROOT, 'data', 'model-params.json')
BACKUP_DIR = os.path.join(REPO_ROOT, 'data', 'backups')
HF_MIRROR_BASE = 'https://hf-mirror.com'

# 架构判断依据（用户规定 + 增强）
MOE_TOP_KEYS = ['n_routed_experts', 'num_local_experts']   # 存在且>0 → MoE
MOE_SECOND_KEYS = ['num_experts_per_tok', 'top_k']          # 存在 → MoE
MOE_EXTRA_KEYS = ['num_experts', 'moe_num_experts', 'use_moe', 'moe_top_k',
                  'moe_intermediate_size', 'moe_layers_enum']


def http_get(url, timeout=30, retries=4):
    """抓取 URL，带重试（hf-mirror DNS 间歇失败）。"""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'
    })
    last_err = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', errors='replace')
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise last_err


def deep_find(cfg, key):
    """递归查找嵌套 dict 中的 key（优先 text_config）。"""
    if not isinstance(cfg, dict):
        return None
    if 'text_config' in cfg and isinstance(cfg.get('text_config'), dict):
        v = cfg['text_config'].get(key)
        if v is not None and v != 0:
            return v
    if key in cfg:
        v = cfg[key]
        if v is not None and v != 0:
            return v
    for k, v in cfg.items():
        if k == 'text_config':
            continue
        if isinstance(v, dict):
            r = deep_find(v, key)
            if r is not None:
                return r
    return None


def judge_architecture(cfg):
    """按用户规定的流程判断架构，返回 'MoE' 或 'Dense'。"""
    # 1. n_routed_experts / num_local_experts 存在且>0 → MoE
    for key in MOE_TOP_KEYS:
        v = deep_find(cfg, key)
        if v is not None and v > 0:
            return 'MoE'
    # 2. num_experts_per_tok / top_k 存在 → MoE
    for key in MOE_SECOND_KEYS:
        if deep_find(cfg, key) is not None:
            return 'MoE'
    # 增强判据
    for key in MOE_EXTRA_KEYS:
        if deep_find(cfg, key) not in (None, False, 0, ''):
            return 'MoE'
    # model_type 含 moe
    mt = str((cfg.get('text_config') or {}).get('model_type') or cfg.get('model_type') or '').lower()
    if 'moe' in mt:
        return 'MoE'
    return 'Dense'


def fetch_params(hf_repo):
    """抓取 config.json 并解析字段 + 判断架构。"""
    url = f'{HF_MIRROR_BASE}/{hf_repo}/resolve/main/config.json'
    cfg = json.loads(http_get(url))
    arch = judge_architecture(cfg)

    layers = deep_find(cfg, 'num_hidden_layers')
    if layers is None:
        layers = deep_find(cfg, 'num_layers')
    heads = deep_find(cfg, 'num_attention_heads')
    kv = deep_find(cfg, 'num_key_value_heads')
    if kv is None:
        kv = deep_find(cfg, 'num_kv_heads')
    if kv is None:
        kv = heads
    hidden = deep_find(cfg, 'hidden_size')
    # DeepSeek MLA 特例：headDim = qk_nope_head_dim + qk_rope_head_dim（如 128+64=192）
    qk_nope = deep_find(cfg, 'qk_nope_head_dim')
    qk_rope = deep_find(cfg, 'qk_rope_head_dim')
    if qk_nope is not None and qk_rope is not None:
        hd = qk_nope + qk_rope
    else:
        hd = deep_find(cfg, 'head_dim')
        if hd is None:
            hd = deep_find(cfg, 'qk_head_dim')
        if hd is None and hidden is not None and heads:
            hd = int(hidden / heads)
    ctx = deep_find(cfg, 'max_position_embeddings')
    if ctx is None:
        ctx = deep_find(cfg, 'seq_length')
    if ctx is None:
        try:
            tok = json.loads(http_get(f'{HF_MIRROR_BASE}/{hf_repo}/resolve/main/tokenizer_config.json', timeout=15))
            ctx = tok.get('model_max_length')
        except Exception:
            ctx = None

    return {
        'architecture': arch,
        'isMoE': '是' if arch == 'MoE' else '否',
        'layers': layers, 'attentionHeads': heads, 'kvHeads': kv,
        'headDim': hd, 'context': ctx,
    }


def backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(BACKUP_DIR, f'model-params-backup-{ts}.json')
    with open(DATA_FILE) as f:
        data = f.read()
    with open(dst, 'w') as f:
        f.write(data)
    return dst


def load():
    with open(DATA_FILE) as f:
        return json.load(f)


def save(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fill_one(data, code, params, hf_repo):
    """应用抓取结果到指定 modelCode 记录。返回变更描述或 None。"""
    target = next((m for m in data if (m.get('modelCode') or '').lower() == code.lower()), None)
    if target is None:
        return f'未找到 modelCode={code}'
    changes = []
    # 架构与 isMoE
    if params.get('architecture') and target.get('architecture') != params['architecture']:
        changes.append(f"arch {target.get('architecture')}->{params['architecture']}")
        target['architecture'] = params['architecture']
    if params.get('isMoE') and target.get('isMoE') != params['isMoE']:
        changes.append(f"isMoE {target.get('isMoE')}->{params['isMoE']}")
        target['isMoE'] = params['isMoE']
    # 数值字段
    for fld, val in [('layers', 'layers'), ('attentionHeads', 'attentionHeads'),
                     ('kvHeads', 'kvHeads'), ('headDim', 'headDim'), ('context', 'context')]:
        v = params.get(fld)
        if v is not None and target.get(fld) != v:
            changes.append(f"{fld} {target.get(fld)}->{v}")
            target[fld] = v
    # hfRepo
    if hf_repo and target.get('hfRepo') != hf_repo:
        changes.append(f"hfRepo {target.get('hfRepo')}->{hf_repo}")
        target['hfRepo'] = hf_repo
    # Dense：激活=总参
    if params.get('architecture') == 'Dense':
        tp = target.get('totalParams')
        if tp is not None and target.get('activeParams') != tp:
            changes.append(f"activeParams {target.get('activeParams')}->{tp} (Dense=总参)")
            target['activeParams'] = tp
    return '; '.join(changes) if changes else '(无变化)'


def verify_dense_rule(data):
    """验证所有 Dense 模型：totalParams 有值时 activeParams 必须等于它。"""
    bad = []
    for m in data:
        if m.get('architecture') == 'Dense':
            tp = m.get('totalParams')
            ap = m.get('activeParams')
            if tp is not None and (ap is None or ap == '' or ap != tp):
                bad.append(m.get('modelCode'))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', help='modelCode，如 tencent-hy3-preview')
    ap.add_argument('--repo', help='HF 仓库，如 tencent/Hy3-preview')
    ap.add_argument('--all-dense-fix', action='store_true', help='全量校正所有 Dense 激活=总参')
    args = ap.parse_args()

    data = load()
    bak = backup()
    print(f'已备份 -> {bak}')

    if args.all_dense_fix:
        fixed = 0
        for m in data:
            if m.get('architecture') == 'Dense' and m.get('totalParams') is not None:
                if m.get('activeParams') != m['totalParams']:
                    m['activeParams'] = m['totalParams']
                    fixed += 1
        save(data)
        print(f'Dense 全量校正：{fixed} 个模型 activeParams 设为 = totalParams')
    elif args.code and args.repo:
        params = fetch_params(args.repo)
        print(f'抓取 {args.repo}: arch={params["architecture"]}, layers={params["layers"]}, '
              f'heads={params["attentionHeads"]}, kv={params["kvHeads"]}, '
              f'headDim={params["headDim"]}, ctx={params["context"]}')
        desc = fill_one(data, args.code, params, args.repo)
        save(data)
        print(f'{args.code}: {desc}')
    else:
        print('请提供 --code 与 --repo，或 --all-dense-fix')
        sys.exit(1)

    # 验证
    bad = verify_dense_rule(load())
    if bad:
        print(f'⚠️ 验证：仍有 {len(bad)} 个 Dense 模型 active≠total: {bad}')
    else:
        print('✅ 验证通过：所有 Dense 模型（totalParams 有值）均满足 总参=激活参')


if __name__ == '__main__':
    main()
