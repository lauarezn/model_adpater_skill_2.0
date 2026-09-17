#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
昇腾售前三级推荐编排器 (ascend-presales-recommend)

① 全球大模型推荐  : global-models.json(913) + model-params.json(913) → 硬过滤 + 能力打分
② 昇腾适配筛选    : mindie-models.json(43,生产级) + acl-pytorch/pytorch(迁移级) → 系列→型号映射 + 等级标注
③ 硬件推荐        : performance.json(700 实测) 优先 + hardware-estimation 口径估算兜底 + TCO

输出: report 对象 (JSON, 可写文件), 同时打印可读 Markdown 报告。
只读 data/*.json, 不修改任何数据文件。纯标准库, 无第三方依赖。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

# ---------- 常量：与 selection-engine.js / hardware-estimation.js 对齐 ----------
# 场景 → 模型类型映射 (selection-engine SCENE_TO_TYPE)
SCENE_TO_TYPE = {
    '智能问答': ['聊天大模型', '基础大模型', '推理大模型'],
    '内容生成': ['基础大模型', '聊天大模型'],
    '代码辅助': ['编程大模型', '基础大模型'],
    '文档处理': ['基础大模型', '聊天大模型'],
    '知识抽取': ['基础大模型', '聊天大模型'],
    '翻译': ['翻译大模型', '基础大模型'],
    '多模态': ['多模态大模型', '视觉大模型'],
    '语音': ['语音大模型'],
    '推理': ['推理大模型'],
    # —— 实时交互类（SCENE_PRESETS 预设场景，同样参与打分）——
    '多轮客服': ['聊天大模型', '基础大模型'],
    '行业助手': ['聊天大模型', '基础大模型'],
    'Code Agent 短链': ['编程大模型', '基础大模型'],
    'Code Agent 中链': ['编程大模型', '基础大模型'],
    '全仓库': ['编程大模型', '基础大模型'],
    '中文档 RAG': ['基础大模型', '聊天大模型'],
    '全文档 QA': ['基础大模型', '聊天大模型'],
    '整本书 QA': ['基础大模型', '聊天大模型'],
}
# 实时交互类场景预设：场景 → 推荐输入/输出长度(tokens)。未显式指定 in_len/out_len 时自动套用。
SCENE_PRESETS = {
    '多轮客服': {'in_len': 2048, 'out_len': 512},
    '行业助手': {'in_len': 16000, 'out_len': 1024},
    'Code Agent 短链': {'in_len': 32000, 'out_len': 800},
    'Code Agent 中链': {'in_len': 100000, 'out_len': 800},
    '全仓库': {'in_len': 500000, 'out_len': 2000},
    '中文档 RAG': {'in_len': 32000, 'out_len': 1000},
    '全文档 QA': {'in_len': 300000, 'out_len': 2000},
    '整本书 QA': {'in_len': 800000, 'out_len': 2000},
}
# 精度 → 参数规模档 (selection-engine PRECISION_BUCKET)
PRECISION_BUCKET = {
    '极高': ['xlarge', 'large'],
    '较高': ['large', 'medium', 'xlarge'],
    '一般': ['medium', 'small', 'tiny'],
    'fp16': ['xlarge', 'large', 'medium'],
    'int8': ['large', 'medium', 'small'],
    'int4': ['medium', 'small', 'tiny'],
}
# 开源/可私有化授权 (selection-engine OPEN_SOURCE_USAGE)
OPEN_SOURCE_USAGE = ['免费商用授权', '有条件免费商用授权']
# 每精度每参数字节数 / KV 字节 (hardware-estimation BYTES/KV_BYTES)
BYTES = {'fp16': 2, 'int8': 1, 'int4': 0.5}
KV_BYTES = {'fp16': 2, 'int8': 1, 'int4': 0.5}
EFFICIENCY = 0.65
TP_COEF = 0.92
# 昇腾适配文件
MINDIE_FILE = 'data/mindie-models.json'
ACL_FILE = 'data/acl-pytorch-models.json'
PYTORCH_FILE = 'data/pytorch-models.json'
ASCEND_FILE = 'data/models.json'   # 昇腾适配清单主源(998条)
# models.json supportLevel → 适配等级
SUPPORT_LEVEL_MAP = {
    '✅ 已支持': 'production',
    '🔵 实验性': 'experimental',
    '扩展兼容': 'compatible',
}


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def norm(s):
    return re.sub(r'[\s\-_.]+', '', str(s or '').lower())


# ---------- 数据加载 ----------
class Data:
    def __init__(self, repo):
        self.repo = repo
        self.global_models = []
        self.model_params = {}
        self.mindie = []       # 生产级适配系列
        self.acl = []          # 迁移级适配
        self.pytorch = []      # 迁移级适配
        self.ascend = []       # 昇腾适配清单主源(models.json)
        self.performance = []
        self.gpu_lib = []

    def path(self, rel):
        return os.path.join(self.repo, rel)

    def load(self):
        gm = load_json(self.path('data/global-models.json'))
        self.global_models = gm.get('models', gm) if isinstance(gm, dict) else gm
        mp = load_json(self.path('data/model-params.json'))
        self.model_params = mp if isinstance(mp, dict) else {'models': mp}
        self.ascend = load_json(self.path(ASCEND_FILE))
        self.mindie = load_json(self.path(MINDIE_FILE))
        self.acl = load_json(self.path(ACL_FILE))
        self.pytorch = load_json(self.path(PYTORCH_FILE))
        pf = load_json(self.path('data/performance.json'))
        self.performance = pf.get('items', pf) if isinstance(pf, dict) else pf
        gl = load_json(self.path('data/gpu_lib.json'))
        self.gpu_lib = gl.get('hardware', gl) if isinstance(gl, dict) else gl

    def find_param(self, code):
        """按 modelCode 或 name 找 model-params 条目"""
        c = norm(code)
        for m in self.model_params.get('models', self.model_params):
            if norm(m.get('modelCode', '')) == c or norm(m.get('name', '')) == c:
                return m
        return None


# ---------- Step 1: 全球大模型推荐 ----------
def step1_global(data, args):
    require_open = args.require_open
    scenes = [args.scene] if args.scene else []
    precision = args.precision

    # 硬性过滤
    pool = []
    for m in data.global_models:
        cu = str(m.get('commercial_usage', '') or '')
        t = m.get('model_TYPE_NAME', '') or ''
        if require_open and cu not in OPEN_SOURCE_USAGE:
            continue
        if t == 'embedding模型':
            continue
        if cu == '不可以商用':
            continue
        pool.append(m)

    # 打分
    scored = []
    for m in pool:
        score = 0
        pos, neg = [], []
        t = m.get('model_TYPE_NAME', '') or ''
        need_types = set()
        for s in scenes:
            need_types.update(SCENE_TO_TYPE.get(s, []))
        if t in need_types:
            score += 40
            pos.append('场景类型匹配：%s' % t)
        elif need_types:
            neg.append('场景类型不匹配：%s' % (t or '未分类'))

        if ('推理' in scenes or '智能问答' in scenes) and m.get('reasoningModel'):
            score += 15
            pos.append('推理模型，适合深度推理/复杂问答')

        bucket = m.get('scaleBucket')
        want_bucket = PRECISION_BUCKET.get(precision, [])
        if bucket in want_bucket:
            score += 20
            pos.append('参数规模匹配精度档：%s' % bucket)
        elif bucket:
            neg.append('参数规模与精度档不符：%s' % bucket)

        param = data.find_param(m.get('model_code', ''))
        ctx = param.get('context') if param else None
        if ctx is not None:
            if ctx >= 32000:
                score += 12
                pos.append('上下文≥32K：%s' % ctx)
            else:
                neg.append('上下文不足32K：%s' % ctx)

        if cu in OPEN_SOURCE_USAGE:
            score += 5
            pos.append('可商用开源：%s' % cu)
        else:
            neg.append('非开源：%s' % (cu or '未知'))

        scored.append({'m': m, 'score': score, 'pos': pos, 'neg': neg, 'ctx': ctx})

    scored.sort(key=lambda x: x['score'], reverse=True)
    top = [x for x in scored[:args.top] if x['score'] > 0]
    candidates = top if top else scored[:args.top]

    return {
        'pool_total': len(data.global_models),
        'pool_after_filter': len(pool),
        'candidates': [
            {
                'code': c['m'].get('model_code', ''),
                'name': c['m'].get('model_abbr_name') or c['m'].get('model_code', ''),
                'org': c['m'].get('orgName', ''),
                'type': c['m'].get('model_TYPE_NAME', ''),
                'scale': c['m'].get('scaleBucket', ''),
                'commercial': c['m'].get('commercial_usage', ''),
                'reasoning': bool(c['m'].get('reasoningModel')),
                'ctx': c['ctx'],
                'score': c['score'],
                'reasons': {'pos': c['pos'], 'neg': c['neg']},
            }
            for c in candidates
        ],
    }


# ---------- Step 2: 昇腾适配筛选 ----------
def build_series_index(data):
    """构建昇腾适配索引。

    主源为 models.json(998条,昇腾适配清单)：按 supportLevel 细分等级，并保留推荐硬件/性能评级。
    补充源：mindie-models(生产级 MindIE)、acl/pytorch(迁移级)。
    返回 (ascend_entries, mindie_series, mig_series)
    """
    # models.json 条目：每条记录 norm(id)/norm(name)/supportLevel/推荐硬件/性能评级
    ascend_entries = []
    for m in data.ascend:
        ident = norm(m.get('id', ''))
        nm = norm(m.get('name', ''))
        if not ident and not nm:
            continue
        ascend_entries.append({
            'id': ident,
            'name': nm,
            'raw_name': m.get('name', ''),
            'support_level': m.get('supportLevel', ''),
            'level': SUPPORT_LEVEL_MAP.get(m.get('supportLevel', ''), 'compatible'),
            'recommended_hw': m.get('recommendedHardware', ''),
            'inference_perf': m.get('inferencePerf', ''),
            'training_perf': m.get('trainingPerf', ''),
        })

    mindie_series = set()
    for s in data.mindie:
        n = s.get('name', '')
        if n:
            mindie_series.add(norm(n))
    mig_series = set()
    for lst in (data.acl, data.pytorch):
        for s in lst:
            n = s.get('name', '')
            if n:
                mig_series.add(norm(n))
    return ascend_entries, mindie_series, mig_series


def series_match(model_code, model_name, ascend_entries, mindie_series, mig_series):
    """返回 (等级, 命中明细)。

    等级: production / experimental / compatible / migration / none
    匹配优先级：① models.json(昇腾适配清单主源) → ② mindie(生产级) → ③ acl/pytorch(迁移级)。
    models.json 内匹配：norm(id) 精确 → norm(name) 精确 → 归一化前缀（长条目优先，避免 Qwen2 误吞 Qwen2.5）。
    """
    code = norm(model_code)
    name = norm(model_name)

    # ① 昇腾适配清单主源
    # 先精确匹配 id / name
    for e in ascend_entries:
        if e['id'] and e['id'] == code:
            return e['level'], [{'series': e['raw_name'], 'recommended_hw': e['recommended_hw'],
                                 'inference_perf': e['inference_perf'], 'training_perf': e['training_perf']}], 'ascend'
    for e in ascend_entries:
        if e['name'] and e['name'] == name:
            return e['level'], [{'series': e['raw_name'], 'recommended_hw': e['recommended_hw'],
                                 'inference_perf': e['inference_perf'], 'training_perf': e['training_perf']}], 'ascend'
    # 归一化前缀匹配（长条目优先，避免 Qwen2 误吞 Qwen2.5）
    # 第一优先级：候选名以条目名开头（系列→型号，如 Qwen3.5→Qwen3）
    # 第二优先级：条目名以候选名开头（型号前缀→完整条目，如 hy4-preview→hy4-preview-experimental，
    #             候选名需足够长，防止 qwen 过短误吞大量条目）
    best = None
    for e in ascend_entries:
        if not e['name']:
            continue
        if name.startswith(e['name']):
            if best is None or len(e['name']) > len(best['name']):
                best = e
    if best is None:
        for e in ascend_entries:
            if not e['name'] or len(name) < 6:
                continue
            if e['name'].startswith(name):
                if best is None or len(e['name']) > len(best['name']):
                    best = e
    if best:
        return best['level'], [{'series': best['raw_name'], 'recommended_hw': best['recommended_hw'],
                                'inference_perf': best['inference_perf'], 'training_perf': best['training_perf']}], 'ascend'

    # ② MindIE 生产级
    hit_mindie = _match_series(code, name, mindie_series)
    if hit_mindie:
        return 'production', [{'series': s, 'recommended_hw': '', 'inference_perf': '', 'training_perf': ''} for s in hit_mindie], 'mindie'

    # ③ 迁移级
    hit_mig = _match_series(code, name, mig_series)
    if hit_mig:
        return 'migration', [{'series': s, 'recommended_hw': '', 'inference_perf': '', 'training_perf': ''} for s in hit_mig], 'acl'

    return 'none', [], ''


def _match_series(code, name, series_set):
    """按归一化后长度降序遍历系列，命中 = 精确相等 或 模型名以系列名开头（前缀）。"""
    hits = []
    for series in sorted(series_set, key=len, reverse=True):
        if not series:
            continue
        if code == series or name == series or name.startswith(series):
            hits.append(series)
    return hits


def step2_ascend(data, candidates):
    ascend_entries, mindie_series, mig_series = build_series_index(data)
    per = {}
    for c in candidates:
        code = c['code']
        level, matched, source = series_match(code, c['name'], ascend_entries, mindie_series, mig_series)
        frameworks = []
        if source == 'mindie':
            frameworks.append('MindIE')
        elif source == 'acl':
            frameworks.append('ACL/PyTorch')
        elif source == 'ascend':
            frameworks.append('PyTorch')
        per[code] = {
            'adapt_level': level,
            'matched_series': [m['series'] for m in matched],
            'recommended_hw': matched[0]['recommended_hw'] if matched else '',
            'inference_perf': matched[0]['inference_perf'] if matched else '',
            'training_perf': matched[0]['training_perf'] if matched else '',
            'adapt_source': source,
            'frameworks': frameworks,
        }
    return {'per_candidate': per}


# ---------- Step 3: 硬件推荐 ----------
def perf_for_model(data, model_code, model_name):
    """在 performance.json 找该模型实测，返回最优(按 per_card_output_tps 降序)或 None。

    区分两类命中并标注来源，避免把不同型号的实测误当成目标模型本身：
      - exact (精确)：实测模型名与目标模型名完全一致（归一化后相等）
      - series(同系列)：仅通过前缀/系列匹配命中（如 Flash-Vision-Exp 命中 Flash），
        此时结果标注 source_model（来源实测模型名）与 match_type='series'，
        由前端提示"该配置来源于同系列实测"。
    精确命中优先，无精确命中才降级用同系列。
    """
    c = norm(model_code)
    n = norm(model_name)
    exact, series = [], []
    for it in data.performance:
        mn = norm(it.get('model', ''))
        if mn == c or mn == n:
            exact.append(it)
        elif c and (c.startswith(mn) or mn.startswith(c)):
            series.append(it)
    def key(it):
        return it.get('per_card_output_tps') or it.get('output_tps') or 0
    if exact:
        exact.sort(key=key, reverse=True)
        best, match_type = exact[0], 'exact'
    elif series:
        series.sort(key=key, reverse=True)
        best, match_type = series[0], 'series'
    else:
        return None
    return {
        'framework': best.get('framework'),
        'hardware': best.get('hardware'),
        'topology': best.get('topology'),
        'total_cards': best.get('total_cards'),
        'data_format': best.get('data_format'),
        'ttft_ms': best.get('ttft_ms'),
        'output_tps': best.get('output_tps'),
        'per_card_output_tps': best.get('per_card_output_tps'),
        'concurrency': best.get('concurrency'),
        'source_model': best.get('model'),
        'match_type': match_type,
    }

def hw_estimate(data, active_params_b, precision, in_len, out_len, qps):
    """硬件估算：显存三约束 → 各卡型所需卡数 + TCO。

    统一复用 gpu-hardware-compare 引擎的 recommend_cards()（单一来源），
    与 llm-token-calculator / gpu-hardware-compare 共用同一口径。
    无模型结构时按经验比例估算 KV，行为与旧实现一致。
    """
    import importlib.util
    hw_path = os.path.join(data.repo, 'skills', 'gpu-hardware-compare', 'hw_compare.py')
    spec = importlib.util.spec_from_file_location('_hw_engine', hw_path)
    eng = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eng)

    # 仅提供激活参数（无结构 → model_vram_est 走经验 KV 比例，与旧口径一致）
    model = {'active': active_params_b}
    try:
        result = eng.recommend_cards(
            model, precision or 'fp16', in_len or 0, out_len or 0, qps or 0, data.repo)
    except Exception:  # noqa: BLE001 - 引擎异常时回退为空结果，不阻断编排
        return {'total_vram_gb': 0, 'plans': []}
    return result


def step3_hardware(data, candidates, args):
    per = {}
    for c in candidates:
        code = c['code']
        param = data.find_param(code)
        active = (param.get('activeParams') if param and param.get('activeParams') is not None
                  else (param.get('totalParams') if param else None) or c.get('active') or c.get('scale'))
        if not active:
            # 从 scaleBucket 给个量级(避免除零/空)
            active = {'tiny': 3, 'small': 8, 'medium': 30, 'large': 70, 'xlarge': 300}.get(c.get('scale'), None)
        bench = perf_for_model(data, code, c['name'])
        est = hw_estimate(data, active or 1, args.precision, args.in_len, args.out_len, args.qps) if active else None
        per[code] = {
            'active_params_b': active,
            'has_bench': bench is not None,
            'bench': bench,
            'hw_estimate': est,
        }
    return {'per_candidate': per}


# ---------- 综合排序 ----------
def rank(data, candidates, step2, step3):
    rank_map = {'production': 3, 'migration': 2, 'none': 1}
    ranked = []
    for c in candidates:
        code = c['code']
        level = step2['per_candidate'][code]['adapt_level']
        has_bench = step3['per_candidate'][code]['has_bench']
        # 综合分 = 能力分 + 适配等级加分 + 实测加分
        overall = c['score'] + rank_map.get(level, 1) * 5 + (8 if has_bench else 0)
        ranked.append({
            'code': code, 'name': c['name'], 'score': c['score'],
            'adapt_level': level, 'has_bench': has_bench, 'overall': overall,
        })
    ranked.sort(key=lambda x: x['overall'], reverse=True)
    return ranked


# ---------- 输出 ----------
def build_report(data, args):
    # 场景预设：未显式指定 in_len/out_len 时，套用 SCENE_PRESETS 推荐值
    if (args.in_len is None or args.out_len is None) and args.scene in SCENE_PRESETS:
        p = SCENE_PRESETS[args.scene]
        if args.in_len is None:
            args.in_len = p['in_len']
        if args.out_len is None:
            args.out_len = p['out_len']
    s1 = step1_global(data, args)
    s2 = step2_ascend(data, s1['candidates'])
    s3 = step3_hardware(data, s1['candidates'], args)
    ranked = rank(data, s1['candidates'], s2, s3)
    report = {
        'meta': {
            'scene': args.scene, 'precision': args.precision, 'qps': args.qps,
            'in_len': args.in_len, 'out_len': args.out_len,
            'require_open': args.require_open, 'top': args.top,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'step1': s1,
        'step2': s2,
        'step3': s3,
        'ranked': ranked,
    }
    return report


LEVEL_CN = {'production': '⭐生产级', 'experimental': '🔵实验级', 'compatible': '🔄兼容级', 'migration': '🔧迁移级(ACL/PyTorch)', 'none': '⚠️无适配记录'}


def print_markdown(report):
    m = report['meta']
    print('=' * 72)
    print('昇腾售前三级推荐报告  场景=%s  精度=%s  QPS=%s  len(in/out)=%s/%s  开源=%s'
          % (m['scene'], m['precision'], m['qps'], m['in_len'], m['out_len'], '是' if m['require_open'] else '否'))
    print('=' * 72)

    print('\n【① 全球大模型推荐】 池 %s → 过滤后 %s 个候选：'
          % (report['step1']['pool_total'], report['step1']['pool_after_filter']))
    for i, c in enumerate(report['step1']['candidates'], 1):
        print('  %d. %s (%s)  %s 分  [%s | %s]'
              % (i, c['name'], c['org'], c['score'], c['type'], c['commercial']))
        for p in c['reasons']['pos']:
            print('       ✔ %s' % p)
        for n in c['reasons']['neg'][:2]:
            print('       ✘ %s' % n)

    print('\n【② 昇腾适配筛选】')
    for c in report['step1']['candidates']:
        code = c['code']
        a = report['step2']['per_candidate'][code]
        series = '、'.join(a['matched_series']) if a['matched_series'] else '-'
        hw = ('  推荐卡:%s' % a['recommended_hw']) if a['recommended_hw'] else ''
        print('  %s : %s  命中系列[%s]%s' % (c['name'], LEVEL_CN.get(a['adapt_level'], a['adapt_level']), series, hw))

    print('\n【③ 硬件推荐】')
    for c in report['step1']['candidates']:
        code = c['code']
        h = report['step3']['per_candidate'][code]
        print('  - %s (激活参数 %sB)' % (c['name'], h['active_params_b']))
        if h['has_bench']:
            b = h['bench']
            print('      实测[%s]: 硬件=%s 卡数=%s 精度=%s TTFT=%sms 单卡输出吞吐=%s tok/s'
                  % (b.get('framework'), b.get('hardware', '').split('\n')[0][:40],
                     b.get('total_cards'), b.get('data_format'), b.get('ttft_ms'),
                     b.get('per_card_output_tps')))
        else:
            print('      无昇腾实测，用估算兜底')
        if h['hw_estimate'] and h['hw_estimate'].get('plans'):
            for p in h['hw_estimate']['plans'][:2]:
                print('      估算: %s × %s卡 (总显存约%sGB, 成本约%s万)'
                      % (p['gpu'], p['cards'], p['total_vram_gb'], round(p['cost_cny'] / 10000, 1)))

    print('\n【综合排序】')
    for i, r in enumerate(report['ranked'], 1):
        print('  %d. %s  综合分%s  [%s | %s]' % (
            i, r['name'], r['overall'],
            LEVEL_CN.get(r['adapt_level'], r['adapt_level']),
            '有实测' if r['has_bench'] else '无实测'))
    print('=' * 72)


def main():
    ap = argparse.ArgumentParser(description='昇腾售前三级推荐编排器')
    ap.add_argument('--repo', default=os.getcwd(), help='仓库根目录(默认当前目录)')
    ap.add_argument('--scene', default='智能问答', help='业务场景(智能问答/内容生成/代码辅助/文档处理/知识抽取/翻译/多模态/语音/推理)')
    ap.add_argument('--precision', default='fp16', choices=['fp16', 'int8', 'int4', '极高', '较高', '一般'],
                    help='精度档位(默认 fp16)')
    ap.add_argument('--qps', type=float, default=30, help='并发 QPS')
    ap.add_argument('--in-len', type=int, default=None, help='平均输入长度(tokens)，缺省按场景预设(SCENE_PRESETS)')
    ap.add_argument('--out-len', type=int, default=None, help='平均输出长度(tokens)，缺省按场景预设(SCENE_PRESETS)')
    ap.add_argument('--require-open', action='store_true', help='仅推荐开源/可私有化模型')
    ap.add_argument('--top', type=int, default=5, help='候选模型数量(默认5)')
    ap.add_argument('--adapt-only', action='store_true', help='只跑①②(适配等级)，不做硬件估算')
    ap.add_argument('--out', help='输出 JSON 报告文件路径')
    args = ap.parse_args()

    data = Data(args.repo)
    data.load()
    report = build_report(data, args)

    if args.adapt_only:
        # 只保留①②
        report.pop('step3', None)
        report['ranked'] = [r for r in report['ranked']]

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('报告已写入: %s' % args.out)
    else:
        print_markdown(report)


if __name__ == '__main__':
    main()
