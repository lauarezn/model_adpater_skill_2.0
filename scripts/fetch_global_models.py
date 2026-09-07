#!/usr/bin/env python3
"""
全球AI大模型数据抓取脚本
数据来源：DataLearner AI 大模型列表 (https://www.datalearner.com/ai-models/pretrained-models)

实现原理：
- 目标站为 Next.js 应用，模型数据通过服务端渲染嵌入在 HTML 的 RSC payload（__next_f）中
- 分页通过 URL 查询参数 ?page=N 实现，共 20 页、913 个模型
- 本脚本逐页抓取 HTML，解析 RSC payload 中的 initialBootstrap 数据，汇总后写入 data/global-models.json

用法：
    python3 scripts/fetch_global_models.py
"""

import urllib.request
import re
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
OUTPUT = DATA_DIR / 'global-models.json'

PAGE_URL = 'https://www.datalearner.com/ai-models/pretrained-models'
TOTAL_PAGES = 20
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
}


def extract_models_from_html(html):
    """从列表页 HTML 的 RSC payload 中提取模型数据"""
    pattern = re.compile(r'__next_f\.push\(\[1,(".*?")\]\)', re.S)
    chunks = pattern.findall(html)
    parts = []
    for c in chunks:
        try:
            parts.append(json.loads(c))  # 反转义 JSON 字符串
        except Exception:
            pass
    full = ''.join(parts)
    i = full.find('initialBootstrap')
    if i < 0:
        return None, None
    j = full.find('{', i)
    dec = json.JSONDecoder()
    obj, _ = dec.raw_decode(full[j:])
    return obj.get('models', []), obj.get('pagination')


def fetch_page(page):
    url = f'{PAGE_URL}?page={page}' if page > 1 else PAGE_URL
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', errors='replace')


def main():
    all_models = []
    pagination = None
    for page in range(1, TOTAL_PAGES + 1):
        for attempt in range(3):
            try:
                html = fetch_page(page)
                models, pag = extract_models_from_html(html)
                if models is None:
                    raise RuntimeError('未找到 initialBootstrap 数据')
                all_models.extend(models)
                if pag:
                    pagination = pag
                print(f'第 {page}/{TOTAL_PAGES} 页: +{len(models)} 个模型 (累计 {len(all_models)})', flush=True)
                break
            except Exception as e:
                print(f'第 {page} 页第 {attempt + 1} 次尝试失败: {e}', flush=True)
                if attempt == 2:
                    print(f'  -> 第 {page} 页抓取失败，跳过', flush=True)
                time.sleep(2)
        time.sleep(0.5)

    # 按 model_id 去重
    seen = {}
    for m in all_models:
        seen[m.get('model_id')] = m
    unique = list(seen.values())

    output = {
        'source': 'datalearner.com/ai-models/pretrained-models',
        'fetched_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'pagination': pagination,
        'total': len(unique),
        'models': unique,
    }

    DATA_DIR.mkdir(exist_ok=True)
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\n✅ 抓取完成，共 {len(unique)} 个模型，已写入 {OUTPUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
