#!/usr/bin/env python3
"""
系列对比分组报告生成器

输入：data/models-lite.json（或 models.json）
输出：Excel 报告（.xlsx），包含三个工作表：
  1. 系列分组汇总 —— 每个 family 系列的变体数量、代表模型、属性分布
  2. 变体明细     —— 每个模型的归一化结果、拆出的属性（NPU/日期/量化/参数量/变体）
  3. 命名规则统计 —— 各种变体后缀在全量数据中的占比

归一化逻辑（提取 family 系列名）：
  从 name 中依次剥掉常见变体后缀，得到基础系列名 family。
  变体属性则单独拆出：isNpu、hasDate、precision、params、variant 等。
"""

import json
import os
import re
from collections import Counter, defaultdict

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except ImportError:
    raise SystemExit('缺少 openpyxl，请先执行: pip install openpyxl')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUT_DIR = os.path.join(BASE_DIR, 'data', 'reports')
os.makedirs(OUT_DIR, exist_ok=True)

# 已知的模型系列名（大小写不敏感匹配），用于把变体归到统一系列
KNOWN_FAMILY = [
    'qwen3-next', 'qwen3-omni', 'qwen3-vl', 'qwen3.6', 'qwen3.5', 'qwen3',
    'qwen2.5', 'qwen2-vl', 'qwen2-audio', 'qwen2-moe', 'qwen2', 'qwen1.5', 'qwen',
    'glm-4', 'glm-4.5', 'glm-4.6', 'glm-5', 'glm4', 'glm', 'chatglm',
    'deepseek-v3', 'deepseek-r1', 'deepseek-vl', 'deepseek-coder', 'deepseek',
    'llama-4', 'llama-3', 'llama-2', 'llama', 'mini-cpm', 'minicpm',
    'internvl', 'internlm', 'mistral', 'mixtral', 'gemma',
    'phi-4', 'phi-3', 'phi', 'baichuan', 'yi-1.5', 'yi', 'kimi',
    'minimax', 'ernie', 'pangu', 'hunyuan', 'step', 'mixtral',
]

# 参数量模式：-7B / -0.5B / -70b 等（只匹配参数量本身，不含后续架构标记）
PARAMS_RE = re.compile(r'-(\d+(?:\.\d+)?[kKmMbB])\b')

# 量化/精度标记
PRECISION_MARKERS = ['w4a8', 'w8a8', 'w4a16', 'mxfp8', 'fp8', 'bf16', 'fp16',
                     'int8', 'int4', 'quantized', 'awq', 'gptq']

# 变体后缀（Instruct/Base/Chat 等）
VARIANT_MARKERS = ['instruct', 'base', 'chat', 'sft', 'rl', 'dpo', 'thinking',
                   'grpo', 'pruning', 'pruned', 'mtp', 'finetune', 'ft', 'lora',
                   'eagle', 'posttrain', 'reasoner', 'coder', 'omni', 'vl']


def _canon_params(p):
    """统一参数量大小写展示，如 0.5b -> 0.5B、7b -> 7B、300m -> 300M"""
    m = re.match(r'^(\d+(?:\.\d+)?)([kKmMbB])$', p)
    if m:
        return m.group(1) + m.group(2).upper()
    return p


def normalize(name):
    """把模型名归一化为 family（系列名）+ 拆出的属性。

    系列名采用「家族 + 参数量」两级，如 Qwen3-30B / Qwen3-235B；
    无参数量时退到家族名，如 DeepSeek-V3。
    """
    raw = name.strip()
    n = raw
    attrs = {
        'isNpu': bool(re.search(r'-npu\b|npu-|npu-deployment|_npu\b', raw, re.I)),
        'hasDate': bool(re.search(r'(?:^|[^0-9])(20\d{6})(?:[^0-9]|$)', raw)),
        'date': '',
        'precision': '',
        'params': '',
        'variant': '',
    }

    # 提取日期
    dm = re.search(r'(20\d{6})', raw)
    if dm:
        attrs['date'] = dm.group(1)
        n = n.replace(dm.group(1), '')

    # 提取参数量并统一大小写
    pm = PARAMS_RE.search(raw)
    if pm:
        attrs['params'] = _canon_params(pm.group(1))
        # 只删参数量本身，保留后面的架构标记（如 A3B），供系列名拼接
        n = re.sub(r'-\d+(?:\.\d+)?[kKmMbB]\b', '', n)

    # 提取精度
    for p in PRECISION_MARKERS:
        if re.search(re.escape(p), raw, re.I):
            attrs['precision'] = p.lower()
            n = re.sub(re.escape(p), '', n, flags=re.I)
            break

    # 提取变体后缀
    for v in VARIANT_MARKERS:
        if re.search(r'(?<![a-z])' + v + r'\b', raw, re.I):
            attrs['variant'] = v.lower()
            break

    # 去掉 -npu / -a3 / -a2 等硬件标记
    n = re.sub(r'-(npu|a2|a3|atlas[a-z0-9-]*|deployment|model)\b', '', n, flags=re.I)
    # 去掉纯日期/数字尾巴
    n = re.sub(r'[._-]?\d{4,8}$', '', n)
    n = re.sub(r'[._-]*(v?\d+(\.\d+)*)$', '', n)
    # 清理残留分隔符
    n = re.sub(r'[_\-\.]+', '-', n).strip('-_-. ')

    # 匹配已知家族名
    family = ''
    lower = n.lower()
    for f in KNOWN_FAMILY:
        if re.search(r'(^|[-_.]|(?<=\d))' + re.escape(f) + r'(?=$|[-_.]|\d)', lower):
            family = _canonical(f)
            break
    if not family:
        # 取前两个"-"分段作为 family 兜底
        parts = [p for p in n.split('-') if p]
        family = '-'.join(parts[:2]) if parts else n
        family = family or raw

    # 家族名 + 参数量 拼接成系列名（若有参数量）
    if attrs['params']:
        family = f"{family}-{attrs['params']}"

    return raw, family, attrs


def _canonical(f):
    """把已知系列名转成展示用的大小写形式"""
    mapping = {
        'qwen3-next': 'Qwen3-Next', 'qwen3-omni': 'Qwen3-Omni', 'qwen3-vl': 'Qwen3-VL',
        'qwen3.6': 'Qwen3.6', 'qwen3.5': 'Qwen3.5', 'qwen3': 'Qwen3',
        'qwen2.5': 'Qwen2.5', 'qwen2-vl': 'Qwen2-VL', 'qwen2-audio': 'Qwen2-Audio',
        'qwen2-moe': 'Qwen2-MoE', 'qwen2': 'Qwen2', 'qwen1.5': 'Qwen1.5', 'qwen': 'Qwen',
        'glm-4.5': 'GLM-4.5', 'glm-4.6': 'GLM-4.6', 'glm-5': 'GLM-5', 'glm-4': 'GLM-4',
        'glm4': 'GLM4', 'glm': 'GLM', 'chatglm': 'ChatGLM',
        'deepseek-v3': 'DeepSeek-V3', 'deepseek-r1': 'DeepSeek-R1', 'deepseek-vl': 'DeepSeek-VL',
        'deepseek-coder': 'DeepSeek-Coder', 'deepseek': 'DeepSeek',
        'llama-4': 'LLaMA-4', 'llama-3': 'LLaMA-3', 'llama-2': 'LLaMA-2', 'llama': 'LLaMA',
        'mini-cpm': 'MiniCPM', 'minicpm': 'MiniCPM', 'internvl': 'InternVL',
        'internlm': 'InternLM', 'mistral': 'Mistral', 'mixtral': 'Mixtral', 'gemma': 'Gemma',
        'phi-4': 'Phi-4', 'phi-3': 'Phi-3', 'phi': 'Phi', 'baichuan': 'Baichuan',
        'yi-1.5': 'Yi-1.5', 'yi': 'Yi', 'kimi': 'Kimi', 'minimax': 'MiniMax',
        'ernie': 'ERNIE', 'pangu': 'Pangu', 'hunyuan': 'Hunyuan', 'step': 'Step',
    }
    return mapping.get(f, f)


def build_report(models):
    """构建系列分组数据。返回 (family 汇总行, 变体明细行, 命名规则统计)。"""
    groups = defaultdict(list)
    for m in models:
        raw, family, attrs = normalize(m.get('name', ''))
        groups[family].append({
            'id': m.get('id', ''),
            'name': raw,
            'category': m.get('category', ''),
            'developer': m.get('developer', ''),
            'framework': m.get('framework', ''),
            'supportLevel': m.get('supportLevel', ''),
            **attrs,
        })

    # 1. 系列分组汇总
    summary_rows = []
    for family, items in groups.items():
        cats = Counter(i['category'] for i in items)
        npu_n = sum(1 for i in items if i['isNpu'])
        date_n = sum(1 for i in items if i['hasDate'])
        precisions = sorted({i['precision'] for i in items if i['precision']})
        variants = sorted({i['variant'] for i in items if i['variant']})
        params = sorted({i['params'] for i in items if i['params']})
        summary_rows.append({
            'family': family,
            '变体数': len(items),
            '是否多变体': '是' if len(items) > 1 else '否',
            'NPU版数': npu_n,
            '日期版数': date_n,
            '参数量(种)': '、'.join(params) if params else '',
            '精度(种)': '、'.join(precisions) if precisions else '',
            '变体后缀(种)': '、'.join(variants) if variants else '',
            '分类分布': '、'.join(f'{k}({v})' for k, v in cats.most_common()),
            '代表模型': items[0]['name'],
        })

    # 2. 变体明细
    detail_rows = []
    for family, items in sorted(groups.items(), key=lambda x: -len(x[1])):
        for i in sorted(items, key=lambda x: x['name'].lower()):
            detail_rows.append({
                'family': family,
                'name': i['name'],
                'category': i['category'],
                'developer': i['developer'],
                'framework': i['framework'],
                'supportLevel': i['supportLevel'],
                'isNpu': '是' if i['isNpu'] else '',
                'date': i['date'],
                'precision': i['precision'],
                'params': i['params'],
                'variant': i['variant'],
            })

    # 3. 命名规则统计
    rule_stats = {
        '含 -npu / NPU 标记': sum(1 for m in models if re.search(r'-npu\b|npu-|_npu\b', m.get('name', ''), re.I)),
        '含日期(20xxxxxx)': sum(1 for m in models if re.search(r'(20\d{6})', m.get('name', ''))),
        '含量化/精度标记': sum(1 for m in models if re.search(r'w4a8|w8a8|mxfp8|fp8|quant', m.get('name', ''), re.I)),
        '含变体后缀(Instruct/Base等)': sum(1 for m in models if re.search(r'-(instruct|base|chat|sft|rl|dpo|thinking|grpo|finetune|lora)\b', m.get('name', ''), re.I)),
    }
    rule_rows = [
        {'指标': k, '数量': v, '占比': f'{v/len(models)*100:.1f}%'}
        for k, v in rule_stats.items()
    ]
    return summary_rows, detail_rows, rule_rows, groups


def write_excel(summary_rows, detail_rows, rule_rows, groups, out_path):
    wb = openpyxl.Workbook()

    header_fill = PatternFill('solid', fgColor='4F81BD')
    header_font = Font(color='FFFFFF', bold=True)
    multi_fill = PatternFill('solid', fgColor='FFF2CC')  # 多变体系列高亮

    def write_sheet(ws, headers, rows, highlight_col=None):
        ws.append(headers)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=c)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
        for r in rows:
            ws.append([r.get(h, '') for h in headers])
        # 高亮多变体行
        if highlight_col and highlight_col in headers:
            col = headers.index(highlight_col) + 1
            for row in ws.iter_rows(min_row=2):
                if row[col - 1].value == '是':
                    for cell in row:
                        cell.fill = multi_fill
        # 列宽
        for i, h in enumerate(headers, start=1):
            width = min(max(len(str(h)) * 2 + 4, 12), 40)
            ws.column_dimensions[get_column_letter(i)].width = width
        ws.freeze_panes = 'A2'

    # 表1：系列分组汇总
    ws1 = wb.active
    ws1.title = '系列分组汇总'
    s_headers = ['family', '变体数', '是否多变体', 'NPU版数', '日期版数', '参数量(种)',
                 '精度(种)', '变体后缀(种)', '分类分布', '代表模型']
    s_rows = sorted(summary_rows, key=lambda x: -x['变体数'])
    write_sheet(ws1, s_headers, s_rows, highlight_col='是否多变体')

    # 表2：变体明细
    ws2 = wb.create_sheet('变体明细')
    d_headers = ['family', 'name', 'category', 'developer', 'framework', 'supportLevel',
                 'isNpu', 'date', 'precision', 'params', 'variant']
    write_sheet(ws2, d_headers, detail_rows)

    # 表3：命名规则统计
    ws3 = wb.create_sheet('命名规则统计')
    r_headers = ['指标', '数量', '占比']
    write_sheet(ws3, r_headers, rule_rows)

    wb.save(out_path)
    return len(groups)


def main():
    src = os.path.join(DATA_DIR, 'models-lite.json')
    if not os.path.exists(src):
        src = os.path.join(DATA_DIR, 'models.json')
    with open(src, encoding='utf-8') as f:
        models = json.load(f)

    summary_rows, detail_rows, rule_rows, groups = build_report(models)

    ts = '20260911'
    out_path = os.path.join(OUT_DIR, f'模型系列对比分组报告_{ts}.xlsx')
    n_groups = write_excel(summary_rows, detail_rows, rule_rows, groups, out_path)

    multi = sum(1 for r in summary_rows if r['是否多变体'] == '是')
    print(f'输入: {src} ({len(models)} 个模型)')
    print(f'归一化出 {n_groups} 个系列，其中 {multi} 个系列含多个变体')
    print(f'输出: {out_path}')


if __name__ == '__main__':
    main()
