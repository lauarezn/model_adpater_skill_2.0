#!/usr/bin/env python3
"""
昇腾大模型推理性能数据解析脚本

数据来源：data_preformce_data/ 目录下的 7 份 Excel 性能基线
- 25.1.rc2性能指标.xlsx
- A300I A2性能基线（32GB&64GB）-10312220.xlsx
- DeepSeek-V4基线0605.xlsx
- vLLM Ascend v0.13.0解决方案出口性能.xlsx
- vllm-ascend 0.17.0rc1性能基线.xlsx
- 昇腾大模型推理性能基线--vLLM_Ascend（0.11.0）-25.1124-刷新1125.xlsx
- 昇腾推理25.2.RC1大模型推理性能基线-MindIE 2.2.RC1-25.1124.xlsx

实现原理：
- 逐 sheet 定位表头行（同时包含“模型名称/模型”与“吞吐/TTFT”关键字的行）
- 通过列别名映射将各文件不同的表头统一为标准化字段
- 数值字段做单位归一化（ms / TPS），并清洗“未测试 / / / -”等占位
- 汇总写入 data/performance.json，作为模型性能查询页面的权威数据源

用法：
    python3 scripts/parse_performance.py [--dir data_preformce_data] [--out data/performance.json]
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    os.system(f'{sys.executable} -m pip install pandas openpyxl -q')
    import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
SRC_DIR = DATA_DIR / 'data_preformce_data'
OUT_FILE = DATA_DIR / 'performance.json'

# 数据目录兜底：默认相对项目根目录
if not SRC_DIR.exists():
    SRC_DIR = BASE_DIR / 'data_preformce_data'

# ============ 列别名映射（各 Excel 表头 -> 标准化字段） ============
# 匹配时去除空白/换行/星号/下划线，并转小写
COLUMN_ALIASES = {
    'model':       ['模型名称', '模型'],
    'framework':   ['推理框架'],
    'product':     ['产品组合'],
    'scenario':    ['场景'],
    'hardware':    ['设备信息', '硬件环境'],
    'topology':    ['组网形态'],
    'total_cards': ['总卡数', '卡数'],
    'data_format': ['数据格式', '数据类型'],
    'avg_input':   ['平均输入', '输入长度'],
    'avg_output':  ['平均输出', '输出长度'],
    'prefix_cache':['prefixcache命中率', '数据集前缀占比'],
    'concurrency': ['系统并发数', '实际并发', '实测并发数'],
    'max_concurrency': ['最大并发数'],
    'ttft_ms':     ['ttft平均', 'ttft'],
    'ttft_p90':    ['ttftp90'],
    'tpot_ms':     ['tpot平均', 'tpot', 'topt卡时延要求'],
    'tpot_p90':    ['tpotslo_p90', 'tpotslo'],
    'e2e_s':       ['e2e时间', 'e2e'],
    'output_tps':  ['输出吞吐', '卡100ms单卡输出吞吐'],
    'per_card_output_tps': ['单卡输出吞吐'],
    'e2e_tps':     ['e2e吞吐', '总token吞吐', '卡100ms单卡e2e吞吐'],
    'per_card_e2e_tps': ['单卡e2e吞吐', '每卡总token吞吐', '每卡输出吞吐'],
    'qps':         ['qps', '系统qps'],
    'qpm':         ['qpm', '系统qpm'],
    'req_rate':    ['请求频率'],
    'version':     ['软件版本', '版本'],
    'parallel':    ['并行策略'],
    'params':      ['参数配置', 'vllm服务化参数配置'],
    'note':        ['备注'],
}


def _norm_header(s):
    """表头归一化：去空白/换行/星号/下划线/括号，转小写"""
    if s is None:
        return ''
    s = str(s)
    s = re.sub(r'\s+', '', s)
    s = s.replace('*', '').replace('_', '').replace('（', '').replace('）', '')
    s = s.replace('(', '').replace(')', '').replace('，', '').replace(',', '')
    return s.lower()


def _to_float(v):
    """数值清洗：容忍 '未测试 / / - None nan' 等占位，返回 float 或 None"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s.lower() in ('nan', 'none', 'null'):
        return None
    if s in ('/', '-', '--', '未测试', '无', '—'):
        return None
    # 去千分位逗号与百分号
    s = s.replace(',', '').replace('%', '').replace('，', '')
    try:
        return float(s)
    except ValueError:
        m = re.search(r'-?\d+(?:\.\d+)?', s)
        return float(m.group()) if m else None


def _clean_text(v):
    if v is None:
        return ''
    s = str(v).strip()
    if s.lower() in ('nan', 'none', 'null'):
        return ''
    return s


def _clean_raw(v):
    """保留原始输入/输出长度内容（如 '8K'、'1K'），无值或占位时返回空字符串。

    与 _to_float 不同：不做数值提取，保留 Excel 中的实际单位/写法，供表格原样展示。
    """
    if v is None:
        return ''
    s = str(v).strip()
    if not s or s.lower() in ('nan', 'none', 'null', '/', '-', '--', '未测试', '无', '—'):
        return ''
    return s


# 会被误判为模型名的表头/备注行（合并单元格导致表头重复出现）
_HEADER_LIKE = {
    '*模型名称', '*产品组合', '*场景', '推理框架', '模型', '合计',
    'pd混部测试数据', '数据说明', '版本性能总览',
}


def _is_header_like(model):
    m = model.strip().lower()
    if m in _HEADER_LIKE:
        return True
    # 含“测试数据”备注行
    if '测试数据' in m or '混部测试' in m:
        return True
    # 形如“800I A3单机 W8A8 服务化性能”的章节标题行（模型名不应含“服务化性能/性能”等描述）
    if ('服务化性能' in m or '性能' in m) and len(m) > 12:
        return True
    return False


def _detect_header_row(rows):
    """定位表头行：该行同时含“模型”与“吞吐/TTFT”关键字"""
    for i, row in enumerate(rows):
        if not row or not any(c is not None for c in row):
            continue
        joined = ' '.join(_norm_header(c) for c in row)
        has_model = ('模型名称' in joined) or ('模型' in joined and '模型数量' not in joined)
        has_metric = ('吞吐' in joined) or ('ttft' in joined) or ('tpot' in joined) or ('输出' in joined)
        if has_model and has_metric:
            return i
    return None


def _build_column_map(header_row):
    """返回 {standard_field: col_index}"""
    col_map = {}
    norm_headers = [_norm_header(c) for c in header_row]
    for field, aliases in COLUMN_ALIASES.items():
        for idx, h in enumerate(norm_headers):
            for alias in aliases:
                a = _norm_header(alias)
                if h and (h == a or h.startswith(a)):
                    col_map[field] = idx
                    break
            if field in col_map:
                break
    return col_map


def parse_sheet(ws_rows, file_name, sheet_name):
    """解析单个数据 sheet，返回记录列表（dict）"""
    rows = [list(r) for r in ws_rows]
    if not rows:
        return []
    header_idx = _detect_header_row(rows)
    if header_idx is None:
        return []
    col_map = _build_column_map(rows[header_idx])
    if 'model' not in col_map:
        return []
    records = []
    for r in rows[header_idx + 1:]:
        if not r or not any(c is not None and str(c).strip() for c in r):
            continue
        def g(field):
            idx = col_map.get(field)
            if idx is None or idx >= len(r):
                return None
            return r[idx]
        # 模型名称为空的行跳过（如版本对比行、汇总行）
        model = _clean_text(g('model'))
        if not model or _is_header_like(model):
            continue
        # 跳过错位/重复的表头行（product/scenario/hardware 等单元格仍为表头标签）
        if _clean_text(g('product')) in ('*产品组合', '产品组合') or \
           _clean_text(g('scenario')) in ('*场景', '场景') or \
           _clean_text(g('hardware')) in ('*设备信息', '设备信息'):
            continue
        # 模型名归一化：Qwen3- 235B -> Qwen3-235B（去除连字符后的空格）
        model = re.sub(r'-\s+', '-', model).strip()
        # 只有参数配置、没有实际指标的行跳过（A300I 表头的配置列）
        ttft = _to_float(g('ttft_ms'))
        tpot = _to_float(g('tpot_ms'))
        out_tps = _to_float(g('output_tps'))
        if ttft is None and tpot is None and out_tps is None and 'avg_input' not in col_map:
            # 无任何指标且无输入列（如纯配置清单）跳过
            if not col_map.get('avg_input') is not None:
                continue
        rec = {
            'model': model,
            'framework': _clean_text(g('framework')).replace('VLLM-Ascend', 'vLLM Ascend') or '昇腾',
            'product': re.sub(r'[\n\r]+', ' ', _clean_text(g('product'))).strip(),
            'scenario': _clean_text(g('scenario')),
            'hardware': _clean_text(g('hardware')),
            'topology': _clean_text(g('topology')),
            'total_cards': _to_float(g('total_cards')),
            'data_format': _clean_text(g('data_format')),
            'avg_input': _to_float(g('avg_input')),
            'avg_output': _to_float(g('avg_output')),
            'avg_input_raw': _clean_raw(g('avg_input')),
            'avg_output_raw': _clean_raw(g('avg_output')),
            'prefix_cache': _to_float(g('prefix_cache')),
            'concurrency': _to_float(g('concurrency')),
            'max_concurrency': _to_float(g('max_concurrency')),
            'ttft_ms': ttft,
            'ttft_p90': _to_float(g('ttft_p90')),
            'tpot_ms': tpot,
            'tpot_p90': _to_float(g('tpot_p90')),
            'e2e_s': _to_float(g('e2e_s')),
            'output_tps': out_tps,
            'per_card_output_tps': _to_float(g('per_card_output_tps')),
            'e2e_tps': _to_float(g('e2e_tps')),
            'per_card_e2e_tps': _to_float(g('per_card_e2e_tps')),
            'qps': _to_float(g('qps')),
            'qpm': _to_float(g('qpm')),
            'req_rate': _to_float(g('req_rate')),
            'version': _clean_text(g('version')),
            'parallel': _clean_text(g('parallel')),
            'source_file': file_name,
            'source_sheet': sheet_name,
        }
        # 清洗 NaN -> None（保证 JSON 合法）
        rec = {k: (None if (isinstance(v, float) and v != v) else v) for k, v in rec.items()}
        records.append(rec)
    return records


def parse_file(file_path):
    """解析单个 Excel 文件的所有 sheet，返回记录列表"""
    all_records = []
    try:
        xls = pd.ExcelFile(file_path)
    except Exception as e:
        print(f'  ⚠ 无法读取 {file_path.name}: {e}')
        return []
    for sheet_name in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=object)
            rows = df.values.tolist()
        except Exception as e:
            print(f'  ⚠ sheet {sheet_name} 解析失败: {e}')
            continue
        recs = parse_sheet(rows, file_path.name, sheet_name)
        if recs:
            print(f'  · {sheet_name}: {len(recs)} 条')
            all_records.extend(recs)
    return all_records


def main():
    import argparse
    parser = argparse.ArgumentParser(description='解析昇腾推理性能 Excel 数据')
    parser.add_argument('--dir', default=str(SRC_DIR), help='Excel 数据目录')
    parser.add_argument('--out', default=str(OUT_FILE), help='输出 JSON 路径')
    args = parser.parse_args()

    src_dir = Path(args.dir)
    if not src_dir.is_dir():
        print(f'❌ 目录不存在: {src_dir}')
        sys.exit(1)

    files = sorted(src_dir.glob('*.xlsx'))
    if not files:
        print(f'❌ 目录下没有 xlsx 文件: {src_dir}')
        sys.exit(1)

    print(f'解析目录: {src_dir}')
    all_records = []
    for f in files:
        print(f'\n📄 {f.name}')
        all_records.extend(parse_file(f))

    # 去重：同一 (model, product, scenario, input, output, source) 视为重复
    seen = set()
    uniq = []
    for rec in all_records:
        key = (rec['model'], rec['product'], rec['scenario'],
               rec['avg_input'], rec['avg_output'], rec['source_file'], rec['source_sheet'])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(rec)

    # 分配 id
    for i, rec in enumerate(uniq, 1):
        rec['id'] = f'perf-{i}'

    data = {
        'source': '昇腾推理性能基线合集',
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(uniq),
        'items': uniq,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'\n✅ 完成：共 {len(all_records)} 条原始记录，去重后 {len(uniq)} 条')
    print(f'   输出文件: {out}')


if __name__ == '__main__':
    main()
