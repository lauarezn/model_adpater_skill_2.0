#!/usr/bin/env python3
"""
统一爬取脚本：从所有所需链接爬取Markdown/HTML内容，
解析模型名称和备注，输出JSON数据文件。
每天定时执行一次。
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:
    os.system(f'{sys.executable} -m pip install requests -q')
    import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    os.system(f'{sys.executable} -m pip install beautifulsoup4 -q')
    from bs4 import BeautifulSoup

# ============ 配置 ============
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

TIMEOUT = 30
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ============ 爬取链接 ============
URLS = {
    'vllm_ascend': 'https://docs.vllm.ai/projects/ascend/zh-cn/latest/user_guide/support_matrix/supported_models.html',
    'vllm_omni': 'https://docs.vllm.ai/projects/vllm-omni/en/latest/models/supported_models/',
    'sglang_ascend': 'https://docs.sglang.io/docs/hardware-platforms/ascend-npus/ascend_npu_support_models',
    'gitcode_ai': 'https://ai.gitcode.com/models?ascendNative=true',
    'ascend_sact': 'https://gitcode.com/org/Ascend-SACT/repos',
    'mindspeed_mm': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/docs/zh/pytorch/supported_models.md',
    'mindspeed_llm': 'https://gitcode.com/Ascend/MindSpeed-LLM/blob/master/docs/zh/pytorch/models/supported_models.md',
}


def fetch_url(url, timeout=TIMEOUT):
    """获取URL内容，支持重试"""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            print(f"  [尝试{attempt+1}] HTTP {resp.status_code}: {url}")
        except Exception as e:
            print(f"  [尝试{attempt+1}] 失败: {e}")
        time.sleep(2)
    return None


# ============ 解析函数 ============

def parse_vllm_ascend(html):
    """解析 vLLM Ascend 支持矩阵页面"""
    models = []
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')

    for table in tables:
        prev_text = ''
        prev_el = table.find_previous_sibling()
        if prev_el:
            prev_text = prev_el.get_text(strip=True)

        category = 'LLM'
        if '多模态' in prev_text:
            category = '多模态'
        elif '池化' in prev_text:
            category = '嵌入/排序'

        rows = table.find_all('tr')
        headers = [th.get_text(strip=True) for th in rows[0].find_all('th')] if rows else []

        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            model_cell = cells[0]
            model_link = model_cell.find('a')
            model_name = model_link.get_text(strip=True) if model_link else model_cell.get_text(strip=True)
            if not model_name:
                continue

            doc_href = model_link.get('href', '') if model_link else ''
            support_text = cells[1].get_text(strip=True) if len(cells) > 1 else ''

            support_level = '扩展兼容'
            if '✅' in support_text:
                support_level = '✅ 已支持'
            elif '🔵' in support_text:
                support_level = '🔵 实验性'
            elif '❌' in support_text:
                continue

            supported_hardware = 'A2/A3'
            doc_url = ''
            max_len = ''

            for i, header in enumerate(headers):
                if i >= len(cells):
                    continue
                h = header.strip()
                if '硬件' in h:
                    supported_hardware = cells[i].get_text(strip=True) or 'A2/A3'
                elif '文档' in h:
                    link = cells[i].find('a')
                    if link:
                        href = link.get('href', '')
                        if href and not href.startswith('http'):
                            href = 'https://docs.vllm.ai' + href
                        doc_url = href
                elif '长度' in h:
                    max_len = cells[i].get_text(strip=True)

            if not doc_url and doc_href:
                doc_url = doc_href if doc_href.startswith('http') else 'https://docs.vllm.ai' + doc_href

            developer = _detect_developer(model_name)
            architecture = _detect_architecture(model_name)
            tags = _detect_tags(model_name, category, architecture)

            model_id = re.sub(r'[^a-z0-9]', '-', model_name.lower()).strip('-')
            model_id = re.sub(r'-+', '-', model_id)

            models.append({
                'id': model_id,
                'name': model_name,
                'category': category,
                'developer': developer,
                'parameters': f'支持 {max_len} 上下文' if max_len else '多尺寸',
                'architecture': architecture,
                'supportLevel': support_level,
                'framework': 'PyTorch',
                'minHardware': 'Atlas 800I A3' if 'A2' in supported_hardware else 'Atlas 800T A3',
                'recommendedHardware': 'Atlas 800T A3' if 'A3' in supported_hardware else 'Atlas 800I A3',
                'inferencePerf': '优' if support_level == '✅ 已支持' else '良',
                'trainingPerf': '良',
                'mindsporeSupport': '支持' if developer in ['阿里云', '智谱AI', '百川智能', '上海AI实验室', '面壁智能', '深度求索'] else '需迁移',
                'cannVersion': '7.0+',
                'notes': f'vLLM Ascend {support_level} · 硬件: {supported_hardware}',
                'tags': tags,
                'docUrl': doc_url,
                'source': 'vLLM Ascend'
            })

    return models


def parse_vllm_omni(html):
    """解析 vLLM Omni 支持模型页面"""
    models = []
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')

    for table in tables:
        rows = table.find_all('tr')
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) < 4:
                continue

            arch_name = cells[0].get_text(strip=True)
            model_name = cells[1].get_text(strip=True)
            ascend_support = cells[3].get_text(strip=True) if len(cells) > 3 else ''

            if '✅' not in ascend_support:
                continue

            names = [n.strip() for n in model_name.split(',') if n.strip()]
            for name in names:
                clean_name = re.sub(r'\(.*?\)', '', name).strip()
                if not clean_name:
                    clean_name = name

                category = '多模态'
                if any(k in clean_name for k in ['TTS', 'Audio', 'Voice', 'Speech', 'Singer', 'SVC']):
                    category = '语音'
                elif any(k in clean_name for k in ['Video', 'T2V', 'I2V', 'V2V', 'S2V']):
                    category = '视频生成'
                elif any(k in clean_name for k in ['Image', 'Edit', 'DiT', 'Diffusion', 'SD', 'FLUX', 'Pipeline']):
                    category = '图像生成'
                elif any(k in clean_name for k in ['Robot', 'VLA', 'GR00T']):
                    category = '具身智能'

                developer = _detect_developer(clean_name)
                architecture = _detect_architecture(clean_name)
                tags = _detect_tags(clean_name, category, architecture)

                model_id = re.sub(r'[^a-z0-9]', '-', clean_name.lower()).strip('-')
                model_id = re.sub(r'-+', '-', model_id)

                hf_link = ''
                hf_link_el = cells[2].find('a') if len(cells) > 2 else None
                if hf_link_el:
                    hf_link = hf_link_el.get('href', '')

                models.append({
                    'id': model_id,
                    'name': clean_name,
                    'category': category,
                    'developer': developer,
                    'parameters': '多尺寸',
                    'architecture': architecture,
                    'supportLevel': '✅ 已支持',
                    'framework': 'PyTorch',
                    'minHardware': 'Atlas 800I A3',
                    'recommendedHardware': 'Atlas 800T A3',
                    'inferencePerf': '良',
                    'trainingPerf': '良',
                    'mindsporeSupport': '需迁移',
                    'cannVersion': '7.0+',
                    'notes': f'vLLM Omni 支持 · 架构: {arch_name}',
                    'tags': tags,
                    'docUrl': hf_link,
                    'source': 'vLLM Omni',
                    'archName': arch_name
                })

    return models


def parse_sglang_ascend(html):
    """解析 SGLang Ascend 支持模型页面"""
    models = []
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')

    for table in tables:
        rows = table.find_all('tr')
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            model_name = cells[0].get_text(strip=True)
            if not model_name:
                continue

            category = 'LLM'
            if any(k in model_name for k in ['VL', 'Vision', 'Omni']):
                category = '多模态'
            elif any(k in model_name for k in ['Coder', 'Code']):
                category = '代码'
            elif any(k in model_name for k in ['Audio', 'Voice', 'Speech']):
                category = '语音'
            elif any(k in model_name for k in ['Embedding', 'Reranker']):
                category = '嵌入/排序'

            developer = _detect_developer(model_name)
            architecture = _detect_architecture(model_name)
            tags = _detect_tags(model_name, category, architecture)

            support_level = '✅ 已支持'
            if 'experimental' in model_name.lower():
                support_level = '🔵 实验性'

            model_id = re.sub(r'[^a-z0-9]', '-', model_name.lower()).strip('-')
            model_id = re.sub(r'-+', '-', model_id)

            models.append({
                'id': model_id,
                'name': model_name,
                'category': category,
                'developer': developer,
                'parameters': '多尺寸',
                'architecture': architecture,
                'supportLevel': support_level,
                'framework': 'PyTorch',
                'minHardware': 'Atlas 800I A3',
                'recommendedHardware': 'Atlas 800T A3',
                'inferencePerf': '良',
                'trainingPerf': '良',
                'mindsporeSupport': '需迁移',
                'cannVersion': '7.0+',
                'notes': 'SGLang Ascend 支持',
                'tags': tags,
                'docUrl': '',
                'source': 'SGLang Ascend'
            })

    return models


def parse_gitcode_ai(html):
    """解析 GitCode AI 昇腾原生模型页面（支持翻页）"""
    models = []

    def extract_models_from_html(html_text):
        """从 HTML 中提取 Next.js 脱水数据中的模型"""
        result = []
        push_matches = list(re.finditer(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html_text))

        for match in push_matches:
            decoded = match.group(1)
            decoded = decoded.replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\').replace('\\"', '"')

            if '"content":[' not in decoded:
                continue

            content_match = re.search(r'"content":\[(.*?)\]', decoded)
            if not content_match:
                continue

            content_str = content_match.group(1)
            try:
                content_data = json.loads('[' + content_str + ']')
                result.extend(content_data)
            except json.JSONDecodeError:
                continue

        return result

    # 提取第一页数据
    first_page_models = extract_models_from_html(html)
    models.extend(first_page_models)

    # 提取 total 和 page_count
    total_match = re.search(r'"total":"?(\d+)"?', html)
    page_count_match = re.search(r'"page_count":(\d+)', html)
    total = int(total_match.group(1)) if total_match else 0
    page_count = int(page_count_match.group(1)) if page_count_match else 1

    print(f"  GitCode AI: 第1页 {len(first_page_models)} 个模型, 总计 {total} 个, 共 {page_count} 页")

    # 翻页获取剩余数据
    if page_count > 1:
        for page in range(2, min(page_count + 1, 50)):
            page_url = f'https://ai.gitcode.com/models?ascendNative=true&page={page}'
            page_html = fetch_url(page_url, timeout=20)
            if page_html:
                page_models = extract_models_from_html(page_html)
                models.extend(page_models)
                print(f"  GitCode AI: 第{page}页 {len(page_models)} 个模型")
            else:
                print(f"  GitCode AI: 第{page}页 获取失败")
            time.sleep(1)

    # 转换为标准格式
    parsed_models = []
    for m in models:
        name = m.get('name', '')
        if not name:
            continue

        web_url = m.get('web_url', '')
        description = m.get('description', '')
        task = m.get('task', [])
        task_name = ''
        if task and isinstance(task, list) and len(task) > 0:
            task_name = task[0].get('name_en', '') if isinstance(task[0], dict) else ''
        elif isinstance(task, dict):
            task_name = task.get('name_en', '')
        download_count = m.get('download_count', 0)
        org_name = m.get('namespace_info', {}).get('name', '')

        category = 'LLM'
        if any(k in task_name for k in ['Audio', 'Speech', 'Voice']):
            category = '语音'
        elif any(k in task_name for k in ['Image', 'Visual', 'Video']):
            category = '多模态'
        elif any(k in task_name for k in ['Feature', 'Embedding']):
            category = '嵌入/排序'
        elif any(k in name for k in ['VL', 'Vision', 'Omni', 'Image', 'Diffusion']):
            category = '多模态'
        elif any(k in name for k in ['Audio', 'Voice', 'Speech', 'ASR', 'TTS']):
            category = '语音'
        elif any(k in name for k in ['Embedding', 'Reranker']):
            category = '嵌入/排序'
        elif any(k in name for k in ['Coder', 'Code']):
            category = '代码'

        developer = _detect_developer(name)
        if developer == '社区' and ('Ascend' in org_name or 'ascend' in org_name or 'atomgit' in org_name):
            developer = '华为'

        architecture = _detect_architecture(name)
        tags = _detect_tags(name, category, architecture)

        model_id = re.sub(r'[^a-z0-9]', '-', name.lower()).strip('-')
        model_id = re.sub(r'-+', '-', model_id)

        parsed_models.append({
            'id': model_id,
            'name': name,
            'category': category,
            'developer': developer,
            'parameters': f'下载 {(download_count/1000):.1f}k' if download_count > 1000 else f'下载 {download_count}',
            'architecture': architecture,
            'supportLevel': '✅ 已支持',
            'framework': 'PyTorch',
            'minHardware': 'Atlas 800I A3',
            'recommendedHardware': 'Atlas 800T A3',
            'inferencePerf': '良',
            'trainingPerf': '良',
            'mindsporeSupport': '支持' if developer in ['华为', '阿里云', '智谱AI', '百川智能', '上海AI实验室', '面壁智能', '深度求索'] else '需迁移',
            'cannVersion': '7.0+',
            'notes': f'GitCode AI · 昇腾原生 · {web_url}',
            'tags': tags,
            'docUrl': web_url,
            'source': 'GitCode AI'
        })

    return parsed_models


def parse_ascend_sact(html):
    """解析 Ascend-SACT 组织仓库页面（支持翻页）"""
    models = []

    total_match = re.search(r'总计:\s*(\d+)', html)
    total_count = int(total_match.group(1)) if total_match else 0

    page_size = 20
    total_pages = max(1, (total_count + page_size - 1) // page_size) if total_count > 0 else 1

    print(f"  Ascend-SACT: 总计 {total_count} 个仓库, 共 {total_pages} 页")

    all_htmls = [html]

    if total_pages > 1:
        for page in range(2, total_pages + 1):
            page_url = f'https://gitcode.com/org/Ascend-SACT/repos?page={page}'
            page_html = fetch_url(page_url, timeout=20)
            if page_html:
                all_htmls.append(page_html)
                print(f"  Ascend-SACT: 第{page}页 获取成功")
            else:
                print(f"  Ascend-SACT: 第{page}页 获取失败")
            time.sleep(1)

    seen_names = set()
    for page_html in all_htmls:
        repo_matches = re.finditer(r'<a[^>]*href="/Ascend-SACT/([^"/]+)"[^>]*>([^<]+)</a>', page_html)

        for match in repo_matches:
            repo_name = match.group(1).strip()
            if not repo_name or repo_name in seen_names:
                continue
            seen_names.add(repo_name)

            if repo_name in ['Ascend-SACT-README', '.github'] or 'docker' in repo_name or 'benchmark' in repo_name:
                continue

            name = repo_name.replace('-', ' ').replace('_', ' ')

            category = 'LLM'
            if any(k in name for k in ['VL', 'Vision', 'Image', 'OCR', 'Diffusion', 'SD']):
                category = '多模态'
            elif any(k in name for k in ['Audio', 'Voice', 'Speech', 'ASR', 'TTS']):
                category = '语音'
            elif any(k in name for k in ['Embedding', 'Reranker']):
                category = '嵌入/排序'
            elif any(k in name for k in ['Coder', 'Code']):
                category = '代码'
            elif any(k in name for k in ['Timer', 'Forecast', 'Time']):
                category = '时序'
            elif any(k in name for k in ['Fold', 'Science', 'Chem']):
                category = '科学计算'

            developer = _detect_developer(name)
            if developer == '社区':
                developer = '华为'

            architecture = _detect_architecture(name)
            tags = _detect_tags(name, category, architecture)

            model_id = re.sub(r'[^a-z0-9]', '-', repo_name.lower()).strip('-')
            model_id = re.sub(r'-+', '-', model_id)

            doc_url = f'https://gitcode.com/Ascend-SACT/{repo_name}'

            models.append({
                'id': model_id,
                'name': repo_name,
                'category': category,
                'developer': developer,
                'parameters': '',
                'architecture': architecture,
                'supportLevel': '✅ 已支持',
                'framework': 'PyTorch',
                'minHardware': 'Atlas 800I A3',
                'recommendedHardware': 'Atlas 800T A3',
                'inferencePerf': '良',
                'trainingPerf': '良',
                'mindsporeSupport': '支持',
                'cannVersion': '7.0+',
                'notes': f'Ascend-SACT · {doc_url}',
                'tags': tags,
                'docUrl': doc_url,
                'source': 'Ascend-SACT'
            })

    return models


def parse_mindspeed_mm(html):
    """解析 MindSpeed-MM 支持模型列表（从 HTML 表格解析）"""
    models = []
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')

    for table in tables:
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue

        headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]
        current_category = '多模态生成'

        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            cell_texts = [c.get_text(strip=True) for c in cells]

            if len(cells) == 1:
                cat = cell_texts[0]
                if cat in ['多模态生成', '多模态理解', '语音识别', '语音生成']:
                    current_category = cat
                continue

            if len(cells) < 5:
                continue

            model_name = cell_texts[0]
            params = cell_texts[1] if len(cell_texts) > 1 else ''
            task = cell_texts[2] if len(cell_texts) > 2 else ''
            cluster = cell_texts[3] if len(cell_texts) > 3 else ''
            precision = cell_texts[4] if len(cell_texts) > 4 else 'BF16'

            if not model_name or model_name.startswith('---'):
                continue

            desc_map = {
                'Lumina-mGPT': '多模态生成模型',
                'OpenSoraPlan': '视频生成模型',
                'Wan2.2-T2V': '文生视频模型',
                'Wan2.2-TI2V': '图文生视频模型',
                'Wan2.2-I2V': '图生视频模型',
                'Wan2.1-T2V': '文生视频模型',
                'Wan2.1-I2V': '图生视频模型',
                'Self-Forcing': '视频生成蒸馏模型',
                'HunyuanVideo': '视频生成模型',
                'OpenSora': '视频生成模型',
                'WFVAE': '视频VAE模型',
                'CogVideoX': '视频生成模型',
                'Qihoo-T2X': '文生图/视频模型',
                'SDXL': '文生图模型',
                'SD3.5': '文生图模型',
                'Flux': '文生图模型',
                'Flux2-T2I': '文生图模型',
                'Flux2-I2I': '图生图模型',
                'Flux-Kontext': '文生图模型',
                'Qwen-Image': '文生图模型',
                'Qwen-Image-Edit': '图编辑模型',
                'GLM-4.1V': '多模态理解模型',
                'DeepSeek-OCR': 'OCR识别模型',
                'LLaVA': '多模态理解模型',
                'InternVL': '多模态理解模型',
                'Qwen2-VL': '多模态理解模型',
                'Qwen2.5-VL': '多模态理解模型',
                'Qwen3-VL': '多模态理解模型',
                'Qwen3.5': '多模态理解模型',
                'Qwen2.5-Omni': '全模态理解模型',
                'Qwen3-Omni': '全模态理解模型',
                'Magistral': '多模态理解模型',
                'Whisper': '语音识别模型',
                'CosyVoice': '语音生成模型',
            }

            desc = '多模态模型'
            for key, val in desc_map.items():
                if key in model_name:
                    desc = val
                    break

            models.append({
                'name': model_name,
                'params': params,
                'task': task,
                'cluster': cluster,
                'precision': precision,
                'framework': 'MM',
                'status': '已支持',
                'category': current_category,
                'desc': desc
            })

    return models


def parse_mindspeed_llm(html):
    """解析 MindSpeed-LLM 支持模型列表（从 HTML 表格解析）"""
    models = []
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')

    current_category = '稠密模型'

    for table in tables:
        for prev in table.find_all_previous(['h2', 'h3', 'h4']):
            t = prev.get_text(strip=True)
            if t in ['稠密模型', '稀疏模型', '状态空间模型', '多模态模型']:
                current_category = t
                break

        if current_category == '多模态模型':
            continue

        rows = table.find_all('tr')
        if len(rows) < 2:
            continue

        headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]

        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                continue

            model_name = cells[0].get_text(strip=True) if len(cells) > 0 else ''
            if not model_name or model_name.startswith('---'):
                continue

            params = cells[1].get_text(strip=True) if len(cells) > 1 else ''

            cluster = ''
            for i, h in enumerate(headers):
                if '集群' in h and i < len(cells):
                    cluster = cells[i].get_text(strip=True)
                    break

            status = '已支持'
            for i, h in enumerate(headers):
                if '认证' in h and i < len(cells):
                    cert = cells[i].get_text(strip=True)
                    if 'Test' in cert or '测试' in cert:
                        status = '测试中'
                    break

            desc_map = {
                'Aquila': '语言模型', 'Baichuan': '语言模型', 'Bloom': '多语言语言模型',
                'ChatGLM': '对话语言模型', 'GLM4': '对话语言模型', 'CodeLlama': '代码语言模型',
                'InternLM': '语言模型', 'LLaMA': '基础语言模型', 'LLaMA2': '语言模型',
                'LLaMA3': '语言模型', 'LLaMA3.1': '语言模型', 'LLaMA3.2': '轻量语言模型',
                'LLaMA3.3': '语言模型', 'Qwen': '语言模型', 'Qwen1.5': '语言模型',
                'Qwen2': '语言模型', 'Qwen2.5': '语言模型', 'Qwen3': '语言模型',
                'QwQ': '推理模型', 'Qwen2.5-Math': '数学推理模型', 'CodeQwen': '代码语言模型',
                'Yi': '语言模型', 'Yi1.5': '语言模型', 'Mistral': '语言模型',
                'Gemma': '语言模型', 'Gemma2': '语言模型', 'MiniCPM': '轻量语言模型',
                'MiniCPM3': '轻量语言模型', 'Phi3.5': '轻量语言模型',
                'DeepSeek-Math': '数学推理模型', 'DeepSeek-R1-Distill': '蒸馏推理模型',
                'Seed-OSS': '语言模型', 'Magistral': '语言模型', 'PLM': '语言模型',
                'Grok-1': 'MoE语言模型', 'Mixtral': 'MoE语言模型',
                'DeepSeek-V2': 'MoE语言模型', 'DeepSeek-V3': 'MoE语言模型',
                'DeepSeek-V4': 'MoE语言模型', 'Hunyuan': 'MoE语言模型',
                'GPT4': 'MoE语言模型', 'GLM4.5': 'MoE语言模型', 'GLM5': 'MoE语言模型',
                'Step3.5': 'MoE语言模型', 'LongCat': 'MoE语言模型',
                'MiniMax': 'MoE语言模型', 'Mamba2': 'SSM语言模型', 'Mamba3': 'SSM语言模型',
                'Ring': 'MoE语言模型', 'Ling-mini': 'MoE语言模型',
            }

            desc = '语言模型'
            for key, val in desc_map.items():
                if key in model_name:
                    desc = val
                    break

            models.append({
                'name': model_name,
                'params': params,
                'task': '预训练/微调',
                'cluster': cluster,
                'precision': 'BF16',
                'framework': 'LLM',
                'status': status,
                'category': current_category,
                'desc': desc
            })

    return models


# ============ 辅助函数 ============

def _detect_developer(name):
    """根据模型名称检测开发者"""
    dev_map = {
        'DeepSeek': '深度求索', 'Qwen': '阿里云', 'GLM': '智谱AI', 'ChatGLM': '智谱AI',
        'CodeGeeX': '智谱AI', 'Baichuan': '百川智能', 'LLaMA': 'Meta', 'Llama': 'Meta',
        'Yi': '零一万物', 'Intern': '上海AI实验室', 'Mistral': 'Mistral AI', 'Mixtral': 'Mistral AI',
        'MiniCPM': '面壁智能', 'Phi': 'Microsoft', 'Gemma': 'Google', 'Kimi': '月之暗面',
        'MiniMax': 'MiniMax', 'MINIMAX': 'MiniMax', 'Ernie': '百度', 'ERNIE': '百度',
        'Stable': 'Stability AI', 'Whisper': 'OpenAI', 'Pangu': '华为', 'openPangu': '华为',
        'Hunyuan': '腾讯', 'FireRed': '华为', 'BAGEL': '字节跳动', 'ByteDance': '字节跳动',
        'Mammoth': '字节跳动', 'Helios': 'BestWishYsh', 'MagiHuman': 'SII-GAIR',
        'Ovis': 'OvisAI', 'LongCat': '美团', 'CosyVoice': 'FunAudioLLM', 'FunAudio': 'FunAudioLLM',
        'OmniVoice': 'k2-fsa', 'VoxCPM': 'OpenBMB', 'MOSS': 'OpenMOSS', 'Higgs': 'Boson AI',
        'IndexTTS': 'IndexTeam', 'NextStep': '阶跃星辰', 'stepfun': '阶跃星辰',
        'MiMo': '小米', 'Xiaomi': '小米', 'Fish': 'Fish Audio', 'fishaudio': 'Fish Audio',
        'SenseNova': '商汤', 'Lance': '字节跳动', 'HiDream': 'HiDream', 'Krea': 'Krea',
        'OmniGen': 'OmniGen', 'SoulX': 'Soul AI Lab', 'AudioX': 'zhangj1an',
        'GR00T': 'NVIDIA', 'nvidia': 'NVIDIA', 'Cosmos': 'NVIDIA', 'FLUX': 'Black Forest Labs',
        'Wan': 'Wan AI', 'LTX': 'Lightricks', 'Aria': 'Rhymes AI', 'Florence': 'Microsoft',
        'PaddleOCR': '百度', 'QVQ': '阿里云', 'Molmo': 'Allen AI', 'Bert': 'Google',
        'RoBERTa': 'Google',
    }
    for key, val in dev_map.items():
        if key in name:
            return val
    return '社区'


def _detect_architecture(name):
    """根据模型名称检测架构"""
    if any(k in name for k in ['MoE', 'A3B', 'A22B', 'W8A8', 'W4A8']):
        return 'MoE'
    if any(k in name for k in ['VL', 'Vision', 'Omni']):
        return 'Vision-Language'
    if any(k in name for k in ['Diffusion', 'SD']):
        return 'Diffusion'
    if any(k in name for k in ['Embedding', 'Reranker']):
        return 'Embedding'
    if any(k in name for k in ['Reward', 'RM']):
        return 'Reward Model'
    if any(k in name for k in ['TTS', 'Voice', 'Speech', 'Singer', 'Audio']):
        return '语音模型'
    if any(k in name for k in ['VLA']):
        return 'VLA'
    return 'Transformer'


def _detect_tags(name, category, architecture):
    """根据模型名称检测标签"""
    tags = [category]
    if architecture == 'MoE':
        tags.append('MoE')
    if any(k in name for k in ['VL', 'Vision', 'Omni', 'Image']):
        tags.append('视觉')
    if any(k in name for k in ['Video', 'T2V', 'I2V']):
        tags.append('视频')
    if any(k in name for k in ['Coder', 'Code']):
        tags.append('代码')
    if any(k in name for k in ['Embedding', 'Reranker']):
        tags.append('嵌入')
    if any(k in name for k in ['Reranker']):
        tags.append('排序')
    if any(k in name for k in ['Audio', 'Voice', 'Speech', 'ASR']):
        tags.append('音频')
    if any(k in name for k in ['TTS', 'Voice', 'Speech']):
        tags.append('语音合成')
    if any(k in name for k in ['Thinking', 'R1']):
        tags.append('推理')
    if any(k in name for k in ['Math']):
        tags.append('数学')
    if any(k in name for k in ['Diffusion', 'DiT']):
        tags.append('扩散模型')
    if any(k in name for k in ['Robot', 'VLA']):
        tags.append('具身智能')
    if any(k in name for k in ['Singer', 'SVC']):
        tags.append('歌声合成')
    if any(k in name for k in ['Edit']):
        tags.append('编辑')
    if any(k in name for k in ['OCR']):
        tags.append('OCR')
    return tags


def merge_models(all_source_models):
    """合并多个来源的模型，去重"""
    merged = []
    seen = set()

    for models in all_source_models:
        for m in models:
            key = m.get('name', '').lower().replace(' ', '').replace('/', '').replace('-', '')
            if not key:
                continue
            if key not in seen:
                seen.add(key)
                merged.append(m)

    return merged


# ============ 主函数 ============

def crawl_all():
    """爬取所有链接并保存数据"""
    crawl_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    results = {}

    print(f"=== 开始爬取 ({crawl_time}) ===")

    # 1. 爬取 vLLM Ascend
    print("\n[1/7] 爬取 vLLM Ascend 支持矩阵...")
    html = fetch_url(URLS['vllm_ascend'])
    if html:
        models = parse_vllm_ascend(html)
        results['vllm_ascend'] = models
        print(f"  ✓ 解析到 {len(models)} 个模型")
    else:
        results['vllm_ascend'] = []
        print("  ✗ 爬取失败")

    # 2. 爬取 vLLM Omni
    print("\n[2/7] 爬取 vLLM Omni 支持模型...")
    html = fetch_url(URLS['vllm_omni'])
    if html:
        models = parse_vllm_omni(html)
        results['vllm_omni'] = models
        print(f"  ✓ 解析到 {len(models)} 个模型")
    else:
        results['vllm_omni'] = []
        print("  ✗ 爬取失败")

    # 3. 爬取 SGLang Ascend
    print("\n[3/7] 爬取 SGLang Ascend 支持模型...")
    html = fetch_url(URLS['sglang_ascend'])
    if html:
        models = parse_sglang_ascend(html)
        results['sglang_ascend'] = models
        print(f"  ✓ 解析到 {len(models)} 个模型")
    else:
        results['sglang_ascend'] = []
        print("  ✗ 爬取失败")

    # 4. 爬取 GitCode AI
    print("\n[4/7] 爬取 GitCode AI 昇腾原生模型...")
    html = fetch_url(URLS['gitcode_ai'])
    if html:
        models = parse_gitcode_ai(html)
        results['gitcode_ai'] = models
        print(f"  ✓ 解析到 {len(models)} 个模型")
    else:
        results['gitcode_ai'] = []
        print("  ✗ 爬取失败")

    # 5. 爬取 Ascend-SACT
    print("\n[5/7] 爬取 Ascend-SACT 组织仓库...")
    html = fetch_url(URLS['ascend_sact'])
    if html:
        models = parse_ascend_sact(html)
        results['ascend_sact'] = models
        print(f"  ✓ 解析到 {len(models)} 个模型")
    else:
        results['ascend_sact'] = []
        print("  ✗ 爬取失败")

    # 6. 爬取 MindSpeed-MM
    print("\n[6/7] 爬取 MindSpeed-MM 训练模型...")
    html = fetch_url(URLS['mindspeed_mm'])
    if html:
        models = parse_mindspeed_mm(html)
        results['mindspeed_mm'] = models
        print(f"  ✓ 解析到 {len(models)} 个模型")
    else:
        results['mindspeed_mm'] = []
        print("  ✗ 爬取失败")

    # 7. 爬取 MindSpeed-LLM
    print("\n[7/7] 爬取 MindSpeed-LLM 训练模型...")
    html = fetch_url(URLS['mindspeed_llm'])
    if html:
        models = parse_mindspeed_llm(html)
        results['mindspeed_llm'] = models
        print(f"  ✓ 解析到 {len(models)} 个模型")
    else:
        results['mindspeed_llm'] = []
        print("  ✗ 爬取失败")

    # 合并模型清单数据
    print("\n=== 合并数据 ===")
    all_model_sources = [
        results['vllm_ascend'],
        results['vllm_omni'],
        results['sglang_ascend'],
        results['gitcode_ai'],
        results['ascend_sact'],
    ]
    merged_models = merge_models(all_model_sources)
    print(f"模型清单合并后: {len(merged_models)} 个模型")

    # 保存模型清单数据
    models_file = os.path.join(DATA_DIR, 'models.json')
    with open(models_file, 'w', encoding='utf-8') as f:
        json.dump(merged_models, f, ensure_ascii=False, indent=2)
    print(f"已保存: {models_file}")

    # 保存轻量版
    lite_models = []
    for m in merged_models:
        lite_models.append({
            'id': m.get('id', ''),
            'name': m.get('name', ''),
            'category': m.get('category', ''),
            'developer': m.get('developer', ''),
            'parameters': m.get('parameters', ''),
            'architecture': m.get('architecture', ''),
            'supportLevel': m.get('supportLevel', ''),
            'framework': m.get('framework', ''),
            'minHardware': m.get('minHardware', ''),
            'recommendedHardware': m.get('recommendedHardware', ''),
            'inferencePerf': m.get('inferencePerf', ''),
            'trainingPerf': m.get('trainingPerf', ''),
            'mindsporeSupport': m.get('mindsporeSupport', ''),
            'cannVersion': m.get('cannVersion', ''),
            'notes': m.get('notes', ''),
            'tags': m.get('tags', []),
            'docUrl': m.get('docUrl', ''),
            'source': m.get('source', '')
        })

    lite_file = os.path.join(DATA_DIR, 'models-lite.json')
    with open(lite_file, 'w', encoding='utf-8') as f:
        json.dump(lite_models, f, ensure_ascii=False, indent=2)
    print(f"已保存: {lite_file}")

    # 保存训练模型清单数据
    train_models = results['mindspeed_mm'] + results['mindspeed_llm']
    train_file = os.path.join(DATA_DIR, 'train-models.json')
    with open(train_file, 'w', encoding='utf-8') as f:
        json.dump({
            'models': train_models,
            'crawl_time': crawl_time,
            'total': len(train_models),
            'mm_count': len(results['mindspeed_mm']),
            'llm_count': len(results['mindspeed_llm'])
        }, f, ensure_ascii=False, indent=2)
    print(f"已保存: {train_file} ({len(train_models)} 个训练模型)")

    # 保存爬取状态
    status = {
        'crawl_time': crawl_time,
        'sources': {
            'vllm_ascend': len(results['vllm_ascend']),
            'vllm_omni': len(results['vllm_omni']),
            'sglang_ascend': len(results['sglang_ascend']),
            'gitcode_ai': len(results['gitcode_ai']),
            'ascend_sact': len(results['ascend_sact']),
            'mindspeed_mm': len(results['mindspeed_mm']),
            'mindspeed_llm': len(results['mindspeed_llm']),
        },
        'total_models': len(merged_models),
        'total_train_models': len(train_models)
    }

    status_file = os.path.join(DATA_DIR, 'crawl-status.json')
    with open(status_file, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    print(f"已保存: {status_file}")

    print(f"\n=== 爬取完成 ({crawl_time}) ===")
    print(f"模型清单: {len(merged_models)} 个模型")
    print(f"训练模型清单: {len(train_models)} 个模型")

    return status


if __name__ == '__main__':
    crawl_all()
