#!/usr/bin/env python3
"""
HuggingFace (hf-mirror.com) 模型命名比对脚本

把本地 models-lite.json 的模型比对到 HuggingFace 的权威组织/仓库命名，
输出 Excel 比对报告。

比对策略（三级）：
  1. developer → HF 候选组织映射表，拉取该组织的全量模型清单建索引
  2. 本地模型名规范化后在索引中匹配
  3. 匹配不到的用 HF 搜索接口兜底

数据源：hf-mirror.com（huggingface.co 在当前网络不可达，hf-mirror 可访问）
说明：本脚本只读数据、只输出报告，不修改任何 JSON 数据。
"""

import json
import os
import re
import socket
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

# 设置全局 socket 默认超时，避免任何请求无限挂起
socket.setdefaulttimeout(12)

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    raise SystemExit('缺少 openpyxl，请先执行: pip install openpyxl')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
REPORT_DIR = os.path.join(DATA_DIR, 'reports')
os.makedirs(REPORT_DIR, exist_ok=True)

API_BASE = 'https://hf-mirror.com/api/models'
HEADERS = {'User-Agent': 'Mozilla/5.0 (model-adapater compare script)'}
REQUEST_INTERVAL = 0.3  # 秒，控制请求频率
CACHE_DIR = os.path.join(DATA_DIR, 'reports', 'hf_cache')
os.makedirs(CACHE_DIR, exist_ok=True)


def log(msg):
    """实时输出（flush 避免缓冲导致看不到进度）"""
    print(msg, flush=True)

# ============ developer → HF 候选组织映射 ============
# 值为候选 HF 组织名列表，按优先级排序；脚本会验证哪个存在
DEVELOPER_TO_ORG = {
    '深度求索': ['deepseek-ai'],
    '阿里云': ['Qwen', 'aliyun-qwen', 'tongyi'],
    '智谱AI': ['zhipuai', 'THUDM'],
    'Meta': ['meta-llama'],
    '月之暗面': ['moonshotai'],
    'MiniMax': ['MiniMaxAI'],
    'Mistral AI': ['mistralai'],
    '面壁智能': ['openbmb'],
    'Google': ['google'],
    'NVIDIA': ['nvidia'],
    '零一万物': ['01-ai'],
    '百度': ['baidu'],
    '上海AI实验室': ['internlm', 'ShanghaiAILaboratory'],
    '腾讯': ['tencent'],
    'Microsoft': ['microsoft'],
    '小米': ['XiaomiMiMo', 'xiaomi'],
    '百川智能': ['baichuan-inc'],
    '字节跳动': ['bytedance'],
    'OpenMOSS': ['OpenMOSS'],
    'OpenBMB': ['openbmb'],
    'FunAudioLLM': ['FunAudioLLM'],
    'Black Forest Labs': ['black-forest-labs'],
    'Stability AI': ['stabilityai'],
    '商汤': ['sensetime'],
    '阶跃星辰': ['stepfun'],
    'k2-fsa': ['k2-fsa'],
    'Fish Audio': ['fishaudio'],
    '美团': ['meituan'],
    'Lightricks': ['Lightricks'],
    'HiDream': ['HiDream-ai'],
    'Rhymes AI': ['rhymes-ai'],
    'OvisAI': ['AIDC-AI'],
    'Boson AI': ['boson-ai'],
    'Wan AI': ['Wan-AI', 'wan-ai'],
    'IndexTeam': ['IndexTeam'],
    'Krea': ['krea'],
    'OmniGen': ['FoundationAgents'],
    'BestWishYsh': [],
    'Soul AI Lab': [],
    'k2-fsa': ['k2-fsa'],
}

# ============ 名称规范化 ============
def normalize_hf_name(name):
    """把本地模型名转成用于匹配的规范化形式（小写、去特殊字符/常见变体后缀）。"""
    n = name.lower()
    n = re.sub(r'\(.*?\)', '', n)          # 去括号说明
    n = re.sub(r'\s+', '-', n)             # 空格转横杠
    # 去掉 -npu / 日期 / 量化 / 部署 等变体标记
    n = re.sub(r'-npu\b|npu-deployment|_npu\b', '', n)
    n = re.sub(r'(20\d{6})', '', n)
    n = re.sub(r'-(w4a8|w8a8|mxfp8|fp8|bf16|awq|gptq|quantized|int8|int4)\b.*$', '', n)
    n = re.sub(r'-(vllm|mindspeed|ascend|a2|a3|atlas[a-z0-9-]*|deployment|model)\b.*$', '', n)
    n = re.sub(r'[^a-z0-9]', '', n)        # 去所有非字母数字
    return n


def normalize_index(idstr):
    """HF 仓库 id 的规范化（org/repo → 只保留 repo 部分并规范化）。"""
    repo = idstr.split('/')[-1] if '/' in idstr else idstr
    n = repo.lower()
    n = re.sub(r'\(.*?\)', '', n)
    n = re.sub(r'\s+', '-', n)
    n = re.sub(r'[^a-z0-9]', '', n)
    return n


# ============ HF API 封装 ============
def _get(url, retries=2, timeout=12):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            if i == retries - 1:
                return None
            time.sleep(0.5)
    return None


def fetch_org_models(org, max_pages=30):
    """拉取一个 HF 组织的全部模型清单（分页）。返回 [{'id','pipeline_tag','downloads'}...]"""
    models = []
    page = 0
    while page < max_pages:
        url = (f'{API_BASE}?author={urllib.parse.quote(org)}'
               f'&limit=100&offset={page*100}&sort=downloads&direction=-1')
        data = _get(url)
        if data is None:
            break
        if not isinstance(data, list) or len(data) == 0:
            break
        models.extend(data)
        if len(data) < 100:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL)
    return models


def search_models(query, limit=20):
    """HF 搜索接口"""
    url = f'{API_BASE}?search={urllib.parse.quote(query)}&limit={limit}'
    data = _get(url)
    if not isinstance(data, list):
        return []
    return data


def org_exists(org):
    """检查组织是否存在"""
    url = f'{API_BASE}?author={urllib.parse.quote(org)}&limit=1'
    data = _get(url)
    return isinstance(data, list) and len(data) > 0


# ============ 主流程 ============
def _load_org_cache(org):
    """从磁盘缓存加载组织清单，无则返回 None。"""
    path = os.path.join(CACHE_DIR, f'{org}.json')
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _save_org_cache(org, models):
    path = os.path.join(CACHE_DIR, f'{org}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(models, f, ensure_ascii=False)


def build_org_index(orgs_to_fetch):
    """按组织拉取清单（带磁盘缓存），建立 repo规范化名 -> [(id, pipeline, downloads)] 索引。"""
    index = defaultdict(list)
    org_meta = {}
    for i, org in enumerate(orgs_to_fetch, 1):
        models = _load_org_cache(org)
        if models is None:
            log(f'  [{i}/{len(orgs_to_fetch)}] 拉取组织 {org} ...')
            models = fetch_org_models(org)
            if models:
                _save_org_cache(org, models)
            time.sleep(REQUEST_INTERVAL)
        else:
            log(f'  [{i}/{len(orgs_to_fetch)}] 使用缓存 {org} ({len(models)} 个)')
        if not models:
            org_meta[org] = 0
            continue
        org_meta[org] = len(models)
        for m in models:
            mid = m.get('id', '')
            if not mid:
                continue
            key = normalize_index(mid)
            index[key].append({
                'id': mid,
                'pipeline': m.get('pipeline_tag', ''),
                'downloads': m.get('downloads', 0),
            })
    return index, org_meta


def match_in_index(name_norm, index):
    """在索引中按规范化名精确匹配，返回最优候选。"""
    if name_norm in index:
        cands = sorted(index[name_norm], key=lambda x: -x['downloads'])
        return cands[0], 'exact'
    return None, ''


def match_by_search(local_name, developer_orgs):
    """用搜索接口找最佳匹配。优先限定在已知组织内。"""
    results = search_models(local_name)
    if not results:
        return None, ''
    # 优先选官方组织（候选组织里的）
    for m in results:
        mid = m.get('id', '')
        author = mid.split('/')[0] if '/' in mid else ''
        if author in developer_orgs:
            return {'id': mid, 'pipeline': m.get('pipeline_tag', ''),
                    'downloads': m.get('downloads', 0)}, 'search-official'
    # 否则取下载量最高的
    best = max(results, key=lambda x: x.get('downloads', 0))
    return {'id': best.get('id', ''), 'pipeline': best.get('pipeline_tag', ''),
            'downloads': best.get('downloads', 0)}, 'search'


def main():
    import sys
    only_orgs = set()
    args = sys.argv[1:]
    if args:
        # 支持 --orgs=org1,org2 只处理指定组织（用于分阶段运行）
        for a in args:
            if a.startswith('--orgs='):
                only_orgs = {x.strip() for x in a.split('=', 1)[1].split(',') if x.strip()}

    with open(os.path.join(DATA_DIR, 'models-lite.json'), encoding='utf-8') as f:
        models = json.load(f)

    # 需要拉取的组织（去重）
    orgs_to_fetch = set()
    for m in models:
        dev = m.get('developer', '')
        orgs_to_fetch.update(DEVELOPER_TO_ORG.get(dev, []))
    if only_orgs:
        orgs_to_fetch = orgs_to_fetch & only_orgs
    orgs_to_fetch = sorted(orgs_to_fetch)

    log(f'本地模型: {len(models)} 个')
    log(f'待拉取 HF 组织: {len(orgs_to_fetch)} 个 -> {orgs_to_fetch}')

    index, org_meta = build_org_index(orgs_to_fetch)
    log('组织拉取完成:')
    for org, cnt in sorted(org_meta.items(), key=lambda x: -x[1]):
        log(f'  {org}: {cnt} 个模型')

    # 逐模型比对
    rows = []
    stats = Counter()
    total = len(models)
    for idx, m in enumerate(models, 1):
        name = m.get('name', '')
        dev = m.get('developer', '')
        name_norm = normalize_hf_name(name)
        cand_orgs = [o for o in DEVELOPER_TO_ORG.get(dev, []) if o in orgs_to_fetch]

        # 1) 精确匹配索引
        match, how = match_in_index(name_norm, index)
        # 2) 搜索兜底（仅对 developer 已知的模型，避免社区模型请求过多触发限流）
        if not match and dev != '社区' and cand_orgs:
            stats['searched'] += 1
            if stats['searched'] % 20 == 0:
                log(f'    搜索兜底已发起 {stats["searched"]} 次')
            match, how = match_by_search(name, cand_orgs)
        hf_id = match['id'] if match else ''
        stats['matched'] += 1 if match else 0
        stats['total'] += 1
        if not match:
            stats['unmatched'] += 1
        else:
            stats[f'how_{how}'] += 1
            hf_author = hf_id.split('/')[0] if '/' in hf_id else ''
            if hf_author in cand_orgs or dev == '社区':
                stats['org_consistent'] += 1
            else:
                stats['org_diff'] += 1

        rows.append({
            '本地模型名': name,
            '本地developer': dev,
            '本地分类': m.get('category', ''),
            'HF权威ID': hf_id,
            'HF链接': f'https://hf-mirror.com/{hf_id}' if hf_id else '',
            'pipeline': match['pipeline'] if match else '',
            '下载量': match['downloads'] if match else '',
            '匹配方式': {'exact': '索引精确', 'search-official': '搜索(官方组织)',
                       'search': '搜索(最佳)'}.get(how, how) if match else '未匹配',
            '组织一致性': ('一致' if (match and (hf_id.split('/')[0] in cand_orgs or dev == '社区'))
                        else ('不一致' if match else '未匹配')),
        })
        if idx % 500 == 0:
            log(f'  已比对 {idx}/{total}，命中 {stats["matched"]}')

    # 写 Excel
    ts = '20260911'
    out_path = os.path.join(REPORT_DIR, f'HF模型命名比对报告_{ts}.xlsx')
    write_excel(rows, stats, out_path)

    log('\n===== 比对统计 =====')
    log(f'总模型: {stats["total"]}, 匹配到: {stats["matched"]}, 未匹配: {stats["unmatched"]}')
    log(f'匹配方式: 索引精确 {stats["how_exact"]}, 搜索官方 {stats["how_search-official"]}, 搜索最佳 {stats["how_search"]}')
    log(f'组织一致性: 一致 {stats["org_consistent"]}, 不一致 {stats["org_diff"]}')
    log(f'输出: {out_path}')


def write_excel(rows, stats, out_path):
    wb = openpyxl.Workbook()
    header_fill = PatternFill('solid', fgColor='4472C4')
    header_font = Font(color='FFFFFF', bold=True)
    match_fill = PatternFill('solid', fgColor='E2EFDA')     # 匹配
    diff_fill = PatternFill('solid', fgColor='FCE4EC')      # 组织不一致
    none_fill = PatternFill('solid', fgColor='FFF2CC')      # 未匹配

    # 表1：比对明细
    ws = wb.active
    ws.title = '比对明细'
    headers = ['本地模型名', '本地developer', '本地分类', 'HF权威ID', 'HF链接',
               'pipeline', '下载量', '匹配方式', '组织一致性']
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    for r in rows:
        ws.append([r[h] for h in headers])
    # 条件着色
    for row in ws.iter_rows(min_row=2):
        how = row[7].value
        orgc = row[8].value
        fill = None
        if how == '未匹配':
            fill = none_fill
        elif orgc == '不一致':
            fill = diff_fill
        elif how in ('索引精确', '搜索(官方组织)'):
            fill = match_fill
        if fill:
            for cell in row:
                cell.fill = fill
    for i, h in enumerate(headers, start=1):
        ws.column_dimensions[chr(64 + i)].width = min(max(len(str(h)) * 2 + 4, 14), 45)
    ws.freeze_panes = 'A2'

    # 表2：统计
    ws2 = wb.create_sheet('统计')
    s_headers = ['指标', '数量']
    ws2.append(s_headers)
    for c in range(1, 3):
        cell = ws2.cell(row=1, column=c)
        cell.fill = header_fill
        cell.font = header_font
    stat_items = [
        ('总模型数', stats['total']),
        ('匹配到 HF', stats['matched']),
        ('未匹配', stats['unmatched']),
        ('  - 索引精确匹配', stats['how_exact']),
        ('  - 搜索命中官方组织', stats['how_search-official']),
        ('  - 搜索命中最佳', stats['how_search']),
        ('组织与本地一致', stats['org_consistent']),
        ('组织与本地不一致', stats['org_diff']),
        ('数据源', 'hf-mirror.com API'),
    ]
    for k, v in stat_items:
        ws2.append([k, v])
    ws2.column_dimensions['A'].width = 34
    ws2.column_dimensions['B'].width = 14

    wb.save(out_path)


if __name__ == '__main__':
    main()
