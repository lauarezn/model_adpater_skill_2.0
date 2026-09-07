#!/usr/bin/env python3
"""
统一服务入口 - 同时托管静态网站和 Admin 后端
- 首页 (/) : 昇腾大模型适配清单
- Admin (/admin) : 管理后台
"""

import os
import sys
import re
import json
import shutil
import subprocess
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, Response

# ============ 配置 ============
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
SCRIPTS_DIR = BASE_DIR / 'scripts'

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path='')

# 爬虫运行状态（含实时过程日志，跨进程持久化到 data/crawler-status.json）
CRAWLER_STATUS_FILE = DATA_DIR / 'crawler-status.json'
crawler_status = {
    'running': False,
    'last_run': None,
    'last_status': None,
    'progress': '',
    'pid': None,
    'log': [],
    'history': []
}


def _load_crawler_status():
    """从磁盘加载爬虫历史状态（last_run/last_status/log/history），供进程重启后保留历史日志"""
    data = load_json(CRAWLER_STATUS_FILE) or {}
    if isinstance(data, dict):
        crawler_status['last_run'] = data.get('last_run')
        crawler_status['last_status'] = data.get('last_status')
        crawler_status['log'] = data.get('log', [])
        crawler_status['history'] = data.get('history', [])
    return crawler_status


def _save_crawler_status():
    """将爬虫状态（含历史日志）持久化到磁盘，保证服务重启后仍可查看历史记录"""
    try:
        save_json(CRAWLER_STATUS_FILE, crawler_status)
    except Exception:
        pass


# ============ 辅助函数 ============

def load_json(filepath):
    """加载 JSON 文件，文件不存在或解析失败时返回 None"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_json(filepath, data):
    """保存 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_data_size_mb():
    """计算 data 目录下所有文件的总大小（MB）"""
    total_bytes = sum(
        os.path.getsize(DATA_DIR / f) for f in os.listdir(DATA_DIR)
        if os.path.isfile(DATA_DIR / f)
    )
    return round(total_bytes / 1024 / 1024, 2)


def get_data_stats():
    """获取数据统计信息"""
    models = load_json(DATA_DIR / 'models-lite.json') or []
    detail = load_json(DATA_DIR / 'models-detail.json') or []
    train = load_json(DATA_DIR / 'train-models.json') or {}
    hardware = load_json(DATA_DIR / 'hardware.json') or []
    status = load_json(DATA_DIR / 'crawl-status.json') or {}

    categories = {}
    for m in models:
        cat = m.get('category', '其他')
        categories[cat] = categories.get(cat, 0) + 1

    sources = {}
    for m in models:
        src = m.get('source', '未知')
        sources[src] = sources.get(src, 0) + 1

    return {
        'total_models': len(models),
        'total_detail': len(detail),
        'total_train': len(train.get('models', [])),
        'total_hardware': len(hardware),
        'categories': categories,
        'sources': sources,
        'crawl_status': status,
        'data_size_mb': get_data_size_mb()
    }


def filter_models(models, search='', source='', category=''):
    """通用模型筛选函数"""
    if search:
        search = search.lower()
        models = [m for m in models if search in m.get('name', '').lower()
                  or search in m.get('developer', '').lower()
                  or search in m.get('id', '').lower()]
    if source:
        models = [m for m in models if m.get('source') == source]
    if category:
        models = [m for m in models if m.get('category') == category]
    return models


def paginate(items, page, page_size):
    """通用分页函数"""
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total, max(1, (total + page_size - 1) // page_size)


def get_all_sources():
    """获取所有数据来源"""
    models = load_json(DATA_DIR / 'models-lite.json') or []
    return sorted(list(set(m.get('source', '未知') for m in models)))


def get_all_categories():
    """获取所有分类"""
    models = load_json(DATA_DIR / 'models-lite.json') or []
    return sorted(list(set(m.get('category', '其他') for m in models)))


# ============ 静态文件路由 ============

@app.route('/')
def index():
    return send_from_directory(str(BASE_DIR), 'index.html')


# ============ Admin 路由 ============

@app.route('/admin')
@app.route('/admin/')
def admin_index():
    return send_from_directory(str(BASE_DIR / 'admin'), 'index.html')


@app.route('/admin/css/<path:filename>')
def admin_css(filename):
    return send_from_directory(str(BASE_DIR / 'admin' / 'css'), filename)


@app.route('/admin/js/<path:filename>')
def admin_js(filename):
    return send_from_directory(str(BASE_DIR / 'admin' / 'js'), filename)


@app.route('/admin/api/stats')
def api_stats():
    return jsonify(get_data_stats())


@app.route('/admin/api/models')
def api_models():
    models = load_json(DATA_DIR / 'models-lite.json') or []
    search = request.args.get('search', '')
    source = request.args.get('source', '')
    category = request.args.get('category', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))

    filtered = filter_models(models, search, source, category)
    page_items, total, total_pages = paginate(filtered, page, page_size)

    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'models': page_items,
        'sources': get_all_sources(),
        'categories': get_all_categories()
    })


@app.route('/admin/api/models/<model_id>', methods=['GET'])
def api_model_get(model_id):
    models = load_json(DATA_DIR / 'models-lite.json') or []
    detail = load_json(DATA_DIR / 'models-detail.json') or []
    m = next((x for x in models if x.get('id') == model_id), None)
    d = next((x for x in detail if x.get('id') == model_id), None)
    if not m:
        return jsonify({'error': '模型不存在'}), 404
    return jsonify({'model': m, 'detail': d})


@app.route('/admin/api/models/<model_id>', methods=['PUT'])
def api_model_update(model_id):
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    models = load_json(DATA_DIR / 'models-lite.json') or []
    for i, m in enumerate(models):
        if m.get('id') == model_id:
            models[i].update(data)
            save_json(DATA_DIR / 'models-lite.json', models)
            return jsonify({'success': True, 'model': models[i]})
    return jsonify({'error': '模型不存在'}), 404


@app.route('/admin/api/models/<model_id>', methods=['DELETE'])
def api_model_delete(model_id):
    models = load_json(DATA_DIR / 'models-lite.json') or []
    new_models = [m for m in models if m.get('id') != model_id]
    if len(new_models) == len(models):
        return jsonify({'error': '模型不存在'}), 404
    save_json(DATA_DIR / 'models-lite.json', new_models)
    full_models = load_json(DATA_DIR / 'models.json') or []
    full_models = [m for m in full_models if m.get('id') != model_id]
    save_json(DATA_DIR / 'models.json', full_models)
    return jsonify({'success': True, 'deleted': model_id})


@app.route('/admin/api/models/batch', methods=['POST'])
def api_models_batch():
    action = request.json.get('action')
    ids = request.json.get('ids', [])
    if not ids:
        return jsonify({'error': '请选择模型'}), 400
    models = load_json(DATA_DIR / 'models-lite.json') or []
    if action == 'delete':
        new_models = [m for m in models if m.get('id') not in ids]
        save_json(DATA_DIR / 'models-lite.json', new_models)
        full_models = load_json(DATA_DIR / 'models.json') or []
        full_models = [m for m in full_models if m.get('id') not in ids]
        save_json(DATA_DIR / 'models.json', full_models)
        return jsonify({'success': True, 'deleted': len(ids), 'remaining': len(new_models)})
    elif action == 'export':
        selected = [m for m in models if m.get('id') in ids]
        return jsonify({'success': True, 'models': selected, 'count': len(selected)})
    return jsonify({'error': '未知操作'}), 400


@app.route('/admin/api/crawler/status')
def api_crawler_status():
    return jsonify(crawler_status)


@app.route('/admin/api/crawler/run', methods=['POST'])
def api_crawler_run():
    if crawler_status['running']:
        return jsonify({'error': '爬虫正在运行中'}), 400

    def run_crawler():
        crawler_status['running'] = True
        crawler_status['last_run'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        crawler_status['last_status'] = None
        crawler_status['log'] = []
        crawler_status['progress'] = '正在启动爬虫...'
        _save_crawler_status()

        def append_log(line):
            line = line.rstrip('\n')
            if line:
                crawler_status['log'].append(line)
                # 保留最近 200 行，避免内存与传输过大
                if len(crawler_status['log']) > 200:
                    crawler_status['log'] = crawler_status['log'][-200:]
                crawler_status['progress'] = line
                _save_crawler_status()

        append_log(f"[{crawler_status['last_run']}] 开始运行爬虫...")
        try:
            # 使用 Popen 实时逐行读取输出；-u 关闭子进程 stdout 块缓冲，确保 print 实时到达管道
            proc = subprocess.Popen(
                [sys.executable, '-u', str(SCRIPTS_DIR / 'crawler.py')],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=str(BASE_DIR)
            )
            crawler_status['pid'] = proc.pid
            _save_crawler_status()

            import select
            try:
                while True:
                    # 非阻塞读取一行，以便检测 running 被停止等外部状态
                    rlist, _, _ = select.select([proc.stdout], [], [], 0.5)
                    if rlist:
                        line = proc.stdout.readline()
                        if line:
                            append_log(line)
                            continue
                        # readline 返回空且进程已结束 -> 退出
                        if proc.poll() is not None:
                            break
                    else:
                        if proc.poll() is not None:
                            # 进程结束，清空剩余输出
                            for rest in proc.stdout:
                                append_log(rest)
                            break
                proc.wait(timeout=1)
            except Exception:
                pass

            if proc.returncode == 0:
                crawler_status['last_status'] = 'success'
                append_log('爬取完成')
            else:
                crawler_status['last_status'] = 'failed'
                append_log(f'爬虫异常退出，退出码: {proc.returncode}')
        except subprocess.TimeoutExpired:
            crawler_status['last_status'] = 'failed'
            append_log('爬虫执行超时（>10分钟）')
        except Exception as e:
            crawler_status['last_status'] = 'failed'
            append_log(f'爬虫执行失败: {str(e)}')
        finally:
            crawler_status['running'] = False
            crawler_status['pid'] = None
            # 写入历史记录（最近 20 条）
            crawler_status['history'].append({
                'time': crawler_status['last_run'],
                'status': crawler_status['last_status'],
                'summary': crawler_status['log'][-1] if crawler_status['log'] else ''
            })
            if len(crawler_status['history']) > 20:
                crawler_status['history'] = crawler_status['history'][-20:]
            append_log(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 爬虫执行结束（状态: {crawler_status['last_status']}）")
            _save_crawler_status()

    thread = threading.Thread(target=run_crawler, daemon=True)
    thread.start()
    return jsonify({'success': True, 'message': '爬虫已启动'})


@app.route('/admin/api/data/backup', methods=['POST'])
def api_data_backup():
    backup_dir = DATA_DIR / 'backups'
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_info = []
    for f in ['models.json', 'models-lite.json', 'models-detail.json',
              'train-models.json', 'hardware.json', 'crawl-status.json',
              'acl-pytorch-models.json', 'pytorch-models.json', 'mindie-models.json',
              'global-models.json', 'benchmarks.json', 'model-params.json']:
        src = DATA_DIR / f
        if src.exists():
            dst = backup_dir / f'{timestamp}_{f}'
            shutil.copy2(src, dst)
            backup_info.append(f)
    return jsonify({
        'success': True,
        'backup_time': timestamp,
        'backup_dir': str(backup_dir),
        'files': backup_info
    })


@app.route('/admin/api/data/restore', methods=['POST'])
def api_data_restore():
    filename = request.json.get('filename')
    if not filename:
        return jsonify({'error': '请指定备份文件'}), 400
    backup_path = DATA_DIR / 'backups' / filename
    if not backup_path.exists():
        return jsonify({'error': '备份文件不存在'}), 404
    target_name = filename.split('_', 1)[1] if '_' in filename else filename
    target_path = DATA_DIR / target_name
    shutil.copy2(backup_path, target_path)
    return jsonify({'success': True, 'restored': target_name})


@app.route('/admin/api/data/backups')
def api_data_backups():
    backup_dir = DATA_DIR / 'backups'
    if not backup_dir.exists():
        return jsonify({'backups': []})
    backups = []
    for f in sorted(backup_dir.iterdir(), reverse=True):
        if f.is_file():
            size_kb = round(f.stat().st_size / 1024, 1)
            backups.append({
                'name': f.name,
                'size_kb': size_kb,
                'modified': datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
    return jsonify({'backups': backups})


# ============ 首页 API 端点（前后端分离）============

@app.route('/admin/api/homepage/stats')
def api_homepage_stats():
    """首页头部统计数据"""
    models = load_json(DATA_DIR / 'models-lite.json') or []
    hardware = load_json(DATA_DIR / 'hardware.json') or []
    categories = list(set(m.get('category', '其他') for m in models))
    return jsonify({
        'modelCount': len(models),
        'hardwareCount': len(hardware),
        'categoryCount': len(categories),
        'dataDate': datetime.now().strftime('%Y-%m-%d %H:%M')
    })


@app.route('/admin/api/homepage/models')
def api_homepage_models():
    """首页模型清单数据（支持搜索/筛选/分页）"""
    models = load_json(DATA_DIR / 'models-lite.json') or []
    search = request.args.get('search', '').lower()
    category = request.args.get('category', '')
    tag = request.args.get('tag', '')
    support = request.args.get('support', '')
    hardware = request.args.get('hardware', '')
    sort = request.args.get('sort', 'default')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))

    filtered = models
    if search:
        filtered = [m for m in filtered if search in m.get('name', '').lower()
                    or search in m.get('developer', '').lower()
                    or any(search in t.lower() for t in m.get('tags', []))]
    if category and category != 'all':
        filtered = [m for m in filtered if m.get('category') == category]
    if tag and tag != 'all':
        filtered = [m for m in filtered if tag in m.get('tags', [])]
    if support and support != 'all':
        filtered = [m for m in filtered if m.get('supportLevel') == support]
    if hardware and hardware != 'all':
        filtered = [m for m in filtered if hardware in m.get('minHardware', '') or hardware in m.get('recommendedHardware', '')]

    # 排序
    if sort in ('popular', 'newest', 'updated'):
        filtered.sort(key=lambda m: -(int(m.get('id', '0')) if m.get('id', '0').isdigit() else 0))
    else:
        filtered.sort(key=lambda m: m.get('name', ''))

    page_items, total, total_pages = paginate(filtered, page, page_size)

    all_tags = sorted(list(set(
        t for m in models for t in m.get('tags', [])
    )))
    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'models': page_items,
        'categories': get_all_categories(),
        'tags': all_tags,
        'hardwareOptions': sorted(list(set(
            m.get('minHardware', '') for m in models if m.get('minHardware')
        ) | set(
            m.get('recommendedHardware', '') for m in models if m.get('recommendedHardware')
        )))
    })


# ============ 全球AI大模型列表（datalearner）============

def load_global_models():
    """加载全球AI大模型数据"""
    data = load_json(DATA_DIR / 'global-models.json') or {}
    return data.get('models', []), data.get('pagination'), data.get('fetched_at')


@app.route('/admin/api/global-models')
def api_global_models():
    """全球AI大模型列表数据（支持搜索/筛选/分页）
    筛选维度：类型(type)、机构(publisher)、商业用途(commercial)、规模(scale)
    """
    models, pagination, fetched_at = load_global_models()
    search = request.args.get('search', '').lower()
    mtype = request.args.get('type', '')
    publisher = request.args.get('publisher', '')
    commercial = request.args.get('commercial', '')
    scale = request.args.get('scale', '')
    lifecycle = request.args.get('lifecycle', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 24))

    filtered = models
    if search:
        filtered = [m for m in filtered
                    if search in m.get('model_abbr_name', '').lower()
                    or search in m.get('orgName', '').lower()
                    or search in (m.get('model_code') or '').lower()]
    if mtype and mtype != 'all':
        filtered = [m for m in filtered if m.get('model_TYPE_NAME') == mtype]
    if publisher and publisher != 'all':
        filtered = [m for m in filtered if m.get('orgName') == publisher]
    if commercial and commercial != 'all':
        filtered = [m for m in filtered if (m.get('commercial_usage') or '') == commercial]
    if scale and scale != 'all':
        filtered = [m for m in filtered if (m.get('scaleBucket') or '') == scale]
    if lifecycle and lifecycle != 'all':
        filtered = [m for m in filtered if (m.get('lifecycleStatus') or '') == lifecycle]

    page_items, total, total_pages = paginate(filtered, page, page_size)

    # 汇总筛选项
    types = sorted(list(set(m.get('model_TYPE_NAME', '') for m in models if m.get('model_TYPE_NAME'))))
    publishers = sorted(list(set(m.get('orgName', '') for m in models if m.get('orgName'))))
    commercials = sorted(list(set(m.get('commercial_usage', '') for m in models if m.get('commercial_usage'))))
    scales = sorted(list(set(m.get('scaleBucket', '') for m in models if m.get('scaleBucket'))))

    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'models': page_items,
        'filters': {
            'types': types,
            'publishers': publishers,
            'commercials': commercials,
            'scales': scales,
        },
        'meta': {
            'fetched_at': fetched_at,
            'total_all': len(models),
        }
    })


@app.route('/admin/api/global-models/<model_id>', methods=['PUT'])
def api_global_model_update(model_id):
    """Admin：保存编辑后的全球AI大模型数据"""
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    payload = load_json(DATA_DIR / 'global-models.json') or {}
    models = payload.get('models', [])
    for i, m in enumerate(models):
        if str(m.get('model_id')) == str(model_id):
            models[i].update(data)
            payload['models'] = models
            save_json(DATA_DIR / 'global-models.json', payload)
            return jsonify({'success': True, 'model': models[i]})
    return jsonify({'error': '模型不存在'}), 404


# ============ 最热模型排行榜（实时抓取 hf-mirror）============

HOT_MODELS_CACHE = {'data': None, 'fetched_at': None}
HOT_MODELS_CACHE_TTL = 600  # 缓存 10 分钟，避免频繁请求外部接口
HOT_MODELS_LOCK = threading.Lock()

# 任务类型中文映射
HOT_MODELS_PIPELINE_ZH = {
    'text-generation': '文本生成',
    'image-text-to-text': '多模态图文',
    'image-to-text': '图生文',
    'text-to-image': '文生图',
    'text-to-video': '文生视频',
    'image-to-video': '图生视频',
    'image-text-to-video': '图文生视频',
    'text-to-speech': '语音合成',
    'automatic-speech-recognition': '语音识别',
    'fill-mask': '填空',
    'sentence-similarity': '句向量',
    'zero-shot-image-classification': '零样本图像分类',
    'image-classification': '图像分类',
    'object-detection': '目标检测',
    'image-segmentation': '图像分割',
    'mask-generation': '掩码分割',
    'time-series-forecasting': '时序预测',
    'feature-extraction': '特征提取',
    'text-classification': '文本分类',
    'token-classification': '词元分类',
    'question-answering': '问答',
    'summarization': '摘要',
    'translation': '翻译',
    'text2text-generation': '文本到文本生成',
    'conversational': '对话',
    'audio-classification': '音频分类',
    'image-feature-extraction': '图像特征提取',
}


def _pipeline_zh(tag):
    """将 HF pipeline_tag 映射为中文，未知返回原值"""
    if not tag:
        return '未分类'
    return HOT_MODELS_PIPELINE_ZH.get(tag, tag)


def _fmt_size(num):
    """将数字格式化为易读的 K/M/B 形式"""
    if num is None:
        return '0'
    try:
        num = float(num)
    except (TypeError, ValueError):
        return str(num or 0)
    if num >= 1e9:
        return f'{num/1e9:.1f}B'
    if num >= 1e6:
        return f'{num/1e6:.1f}M'
    if num >= 1e3:
        return f'{num/1e3:.1f}K'
    return f'{int(num)}'


def _fetch_hf_hot_models(limit=50):
    """实时抓取 hf-mirror /api/models（默认按热度 trending 排序），返回模型排行榜列表。

    返回字段：rank、developer(开发商)、model_name、model_id、pipeline_tag(中文)、
    downloads(原始)、downloads_display、likes、trending_score、created_at、hf_url。
    """
    url = f'{HF_MIRROR_BASE}/api/models?limit={int(limit)}'
    raw = _http_get(url, timeout=30)
    arr = json.loads(raw)
    if not isinstance(arr, list):
        return []

    out = []
    for idx, m in enumerate(arr, start=1):
        mid = m.get('id') or m.get('modelId') or ''
        # id 形如 "org/ModelName"，斜杠前为开发商/作者
        if '/' in mid:
            developer, model_name = mid.split('/', 1)
        else:
            developer, model_name = '', mid
        pipeline = m.get('pipeline_tag') or ''
        downloads = m.get('downloads') or 0
        likes = m.get('likes') or 0
        out.append({
            'rank': idx,
            'developer': developer,
            'model_name': model_name,
            'model_id': mid,
            'pipeline_tag': pipeline,
            'pipeline_zh': _pipeline_zh(pipeline),
            'downloads': downloads,
            'downloads_display': _fmt_size(downloads),
            'likes': likes,
            'trending_score': m.get('trendingScore') or 0,
            'created_at': m.get('createdAt') or '',
            'hf_url': f'{HF_MIRROR_BASE}/{mid}',
        })
    return out


@app.route('/admin/api/hot-models')
def api_hot_models():
    """最热模型排行榜：实时抓取 hf-mirror，带 10 分钟缓存。

    参数：limit（默认 30，最大 100）、sort（trending/downloads/likes，默认 trending）
    """
    try:
        limit = int(request.args.get('limit', 30))
    except (TypeError, ValueError):
        limit = 30
    limit = max(1, min(limit, 100))
    sort_key = request.args.get('sort', 'trending')

    now = datetime.utcnow()
    # 命中缓存则直接返回（缓存存 limit=100 的完整数据，前端再按需裁剪）
    with HOT_MODELS_LOCK:
        cache_valid = (
            HOT_MODELS_CACHE['data'] is not None
            and HOT_MODELS_CACHE['fetched_at'] is not None
            and (now - HOT_MODELS_CACHE['fetched_at']).total_seconds() < HOT_MODELS_CACHE_TTL
        )
        if cache_valid:
            items = HOT_MODELS_CACHE['data']
            fetched_at = HOT_MODELS_CACHE['fetched_at']
        else:
            fetched_at = None
            items = None

    if items is None:
        try:
            items = _fetch_hf_hot_models(limit=100)
        except Exception as e:
            # 抓取失败时返回错误，前端展示失败提示
            return jsonify({'success': False, 'error': f'抓取 hf-mirror 失败：{e}'}), 502
        with HOT_MODELS_LOCK:
            HOT_MODELS_CACHE['data'] = items
            HOT_MODELS_CACHE['fetched_at'] = now
        fetched_at = now

    # 排序
    if sort_key == 'downloads':
        items = sorted(items, key=lambda x: x['downloads'], reverse=True)
        for i, it in enumerate(items, start=1):
            it['rank'] = i
    elif sort_key == 'likes':
        items = sorted(items, key=lambda x: x['likes'], reverse=True)
        for i, it in enumerate(items, start=1):
            it['rank'] = i
    # trending 为默认顺序，rank 已按返回顺序编号

    page_items = items[:limit]
    fetched_iso = fetched_at.isoformat() if fetched_at else None
    return jsonify({
        'success': True,
        'total': len(items),
        'limit': limit,
        'sort': sort_key,
        'fetched_at': fetched_iso,
        'models': page_items,
    })


# ============ 全球AI大模型详情代理（抓取 DataLearner 详情页）============

DATALEARNER_DETAIL_BASE = 'https://www.datalearner.com/ai-models/pretrained-models'
DATALEARNER_ORIGIN = 'https://www.datalearner.com'


def _extract_thinking_modes(full_html):
    """从 DataLearner 完整详情页 HTML 解析该模型实际支持的思考模式细分选项。

    DataLearner 在页面 RSC 数据中通过 "thinkingModes":[...] 声明每个模型支持的
    细分模式（如 GLM-5.3 为 low/high/max），并附 thinkingModeCatalog 作为完整目录。
    这里只取该模型实际支持的 modes，返回 [(modeKey, displayNameZh, isDefault), ...]，
    解析失败时返回空列表（调用方回退到默认细分选项）。
    """
    start_marker = 'thinkingModes\\":['
    end_marker = 'thinkingModeCatalog'
    s = full_html.find(start_marker)
    if s == -1:
        return []
    s += len(start_marker)
    e = full_html.find(end_marker, s)
    if e == -1:
        return []
    raw = full_html[s:e]
    lb = raw.rfind(']')
    if lb == -1:
        return []
    elems = raw[:lb].rstrip().rstrip(',')
    try:
        unescaped = elems.replace('\\"', '"').replace('\\\\', '\\')
        arr = json.loads('[' + unescaped + ']')
        return [(it.get('modeKey'), it.get('displayNameZh'), it.get('isDefault', 0)) for it in arr]
    except Exception:
        return []


@app.route('/admin/api/global-models/detail/<model_code>')
def api_global_model_detail_proxy(model_code):
    """代理抓取 DataLearner 对应模型的详情页 HTML 并返回，
    使前端 iframe 能可靠显示"链接跳转后的实际内容"（避免浏览器第三方/跨域限制）。
    """
    # 安全校验 model_code，仅允许字母数字与中划线
    if not re.fullmatch(r'[A-Za-z0-9\-_]+', model_code or ''):
        return jsonify({'error': '无效的模型标识'}), 400

    # 接收测评筛选参数（思考模式 / 思考模式细分 / 工具使用），转发给 DataLearner 使其按对应模式抓取数据
    bm_thinking = (request.args.get('bm_thinking') or '').strip()
    bm_tool = (request.args.get('bm_tool') or '').strip()
    bm_mode = (request.args.get('bm_mode') or '').strip()
    name = (request.args.get('name') or '').strip()

    url = f'{DATALEARNER_DETAIL_BASE}/{model_code}'
    _bm_qs = []
    if bm_thinking:
        _bm_qs.append('bm_thinking=' + urllib.parse.quote(bm_thinking))
    if bm_tool:
        _bm_qs.append('bm_tool=' + urllib.parse.quote(bm_tool))
    if bm_mode:
        _bm_qs.append('bm_mode=' + urllib.parse.quote(bm_mode))
    if _bm_qs:
        url += '?' + '&'.join(_bm_qs)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return jsonify({'error': f'抓取详情失败: {str(e)}'}), 502

    # 解析该模型实际支持的思考模式细分选项（须在丢弃 <main> 之前从完整 HTML 提取）
    thinking_modes = _extract_thinking_modes(html)

    # 只保留页面的主要内容（<main> 主体），丢弃导航栏、页脚等外围元素
    main_match = re.search(r'<main[^>]*>(.*?)</main>', html, re.S)
    main_html = main_match.group(1) if main_match else html

    # 提取原页面 head 中的样式表链接，保证主体内容样式正常
    css_links = re.findall(r'<link[^>]+rel=["\']stylesheet["\'][^>]*>', html)
    if not css_links:
        css_links = re.findall(r'<link[^>]+stylesheet[^>]*>', html)
    css_links_abs = [re.sub(r'(href=)(["\'])/([^"\']*)', rf'\1\2{DATALEARNER_ORIGIN}/\3', l) for l in css_links]

    # 将主体内容中的相对资源路径改写为 DataLearner 绝对路径
    main_html = re.sub(r'(src|href)=(["\'])/([^"\']*)', rf'\1=\2{DATALEARNER_ORIGIN}/\3', main_html)

    # 去掉主体内容里的 SEO JSON-LD 脚本（不影响显示）
    main_html = re.sub(r'<script type="application/ld\+json">.*?</script>', '', main_html, flags=re.S)

    # 移除页面级辅助元素：面包屑导航（Breadcrumb）
    main_html = re.sub(r'<nav[^>]*aria-label="Breadcrumb"[^>]*>.*?</nav>', '', main_html, flags=re.S)

    # 删除 DataLearner 官方微信宣传块（含微信二维码）
    wechat_pos = main_html.find('DataLearner 官方微信')
    if wechat_pos != -1:
        sec_start = main_html.rfind('<section', 0, wechat_pos)
        sec_end = main_html.find('</section>', wechat_pos)
        if sec_start != -1 and sec_end != -1:
            main_html = main_html[:sec_start] + main_html[sec_end + len('</section>'):]

    # 需求1：删除 "查看评测深度分析" 和 "与其他模型对比" 两个跳转按钮
    def _remove_btn(h, text):
        while True:
            i = h.find(text)
            if i == -1:
                break
            a_start = h.rfind('<a', 0, i)
            a_end = h.find('</a>', i)
            if a_start == -1 or a_end == -1:
                break
            h = h[:a_start] + h[a_end + len('</a>'):]
        return h
    main_html = _remove_btn(main_html, '查看评测深度分析')
    main_html = _remove_btn(main_html, '与其他模型对比')

    # 删除 "和其他模型对比" 字段及其内容（id=common-comparisons 的整个 section）
    main_html = re.sub(
        r'<section[^>]*id=["\']common-comparisons["\'][^>]*>.*?</section>',
        '',
        main_html,
        count=1,
        flags=re.S
    )

    # 需求3：取消链接按钮组（在线体验/GitHub/Hugging Face/对比）中 "对比" 按钮的跳转链接
    # （保留按钮，移除 href 并改为禁用态，与 GitHub/Hugging Face 的"暂无"按钮样式一致）
    def _disable_compare_btn(m):
        tag = m.group(0)
        # 移除 href 跳转
        tag = re.sub(r'\s+href="[^"]*"', '', tag)
        # 加禁用标识与样式
        tag = re.sub(r'<a\b', '<a aria-disabled="true"', tag)
        tag = re.sub(r'class="([^"]*)"', r'class="\1 cursor-not-allowed opacity-40"', tag, count=1)
        return tag
    main_html = re.sub(
        r'<a[^>]*title="与其他模型进行规格对比"[^>]*>.*?</a>',
        _disable_compare_btn,
        main_html,
        flags=re.S
    )

    # 需求2：将模型详情链接改写为本项目 AI 大模型对应详情页（顶层跳转，而非 DataLearner）
    def _rewrite_model_link(match):
        prefix = match.group(1)
        code = match.group(2)
        suffix = match.group(3)
        # 从链接 title 属性提取模型名（如 title="查看模型详情: GLM-4.7-Flash"）
        title_m = re.search(r'title="[^"]*[:：]\s*([^"]+)"', prefix)
        if title_m:
            name = urllib.parse.quote(title_m.group(1).strip())
            return f'{prefix}href="/model_detail.html?code={code}&name={name}" target="_top"{suffix}'
        return f'{prefix}href="/model_detail.html?code={code}" target="_top"{suffix}'
    main_html = re.sub(
        r'(<a[^>]*?)href="https://www\.datalearner\.com/ai-models/pretrained-models/([a-z0-9\-]+)"([^>]*?)>',
        _rewrite_model_link,
        main_html
    )

    # 需求4：将评测结果中对应基准的跳转链接改写为本项目评测基准详情页
    # （DataLearner 详情页 /benchmarks/<code> -> 本站 benchmark_detail.html?code=<code>）
    main_html = re.sub(
        r'href="https://www\.datalearner\.com/benchmarks/([a-z0-9\-]+)"',
        r'href="/benchmark_detail.html?code=\1"',
        main_html
    )

    # 需求5：修复测评结果筛选按钮（思考模式 / 思考模式细分 / 工具使用）无法跳转的问题。
    # DataLearner 的这些按钮是 React 客户端组件（点击行为由打包 JS 提供），代理抓取丢弃了 JS，
    # 导致按钮成为纯静态 <button>、点击无反应。这里整体重建筛选工具栏，把按钮改写为带
    # 查询参数（bm_thinking / bm_tool / bm_mode）的 <a> 链接，使点击后能按对应模式重新抓取数据。
    def _rewrite_benchmark_toolbar(h, code, name, cur_thinking, cur_tool, cur_mode, thinking_modes):
        t_start = h.find('benchmark-toolbar')
        if t_start == -1:
            return h
        # 工具栏结束边界：优先取数据区（benchmark-category）；无数据时为空状态提示（py-7 文案块）。
        # 注意必须回退到对应 <div ...> 标签的起点，避免截断标签前缀产生残留字符。
        t_end = h.find('benchmark-category', t_start)
        if t_end == -1:
            t_end = h.find('class="py-7', t_start)
        if t_end == -1:
            return h
        div_back = h.rfind('<div', 0, t_end)
        if div_back == -1:
            return h
        # 回退到 toolbar 起始标签对应的 <div> 起点
        div_start = h.rfind('<div', 0, t_start)
        if div_start == -1:
            return h
        t_end = div_back

        def _href(override):
            p = {'code': code}
            if name:
                p['name'] = name
            th = override.get('bm_thinking', cur_thinking)
            tl = override.get('bm_tool', cur_tool)
            md = override.get('bm_mode', cur_mode)
            if th:
                p['bm_thinking'] = th
                # 思考模式细分仅对"思考"模式生效，其余情况下细分不参与
                if th == 'thinking' and md:
                    p['bm_mode'] = md
            if tl:
                p['bm_tool'] = tl
            return '/model_detail.html?' + '&'.join(f'{k}={urllib.parse.quote(str(v))}' for k, v in p.items())

        def _chip(label, active, override):
            cls = 'benchmark-filter-chip' + (' is-active' if active else '')
            aria = 'true' if active else 'false'
            return (f'<a href="{_href(override)}" '
                    f'class="{cls}" aria-pressed="{aria}" role="button">{label}</a>')

        def _group(label, items):
            # items: list of (显示名, 参数名, 参数值或None表示"全部")
            opts = []
            for disp, pname, pval in items:
                cur = {'bm_thinking': cur_thinking, 'bm_tool': cur_tool, 'bm_mode': cur_mode}.get(pname)
                active = (pval is None and not cur) or (pval is not None and cur == pval)
                opts.append(_chip(disp, active, {pname: pval}))
            return (f'<div class="benchmark-mode-filter">'
                    f'<span class="benchmark-filter-label">{label}</span>'
                    f'<div class="benchmark-filter-options">' + ''.join(opts) + '</div></div>')

        thinking_items = [
            ('全部', 'bm_thinking', None),
            ('常规', 'bm_thinking', 'normal'),
            ('思考', 'bm_thinking', 'thinking'),
        ]
        # 思考模式细分选项：优先取该模型实际支持的 modes（thinkingModes），
        # 解析失败时回退到通用档位（低/中/高/最高）
        mode_items = [('全部', 'bm_mode', None)]
        if thinking_modes:
            for _mk, _zh, _is_def in thinking_modes:
                if _mk:
                    mode_items.append((_zh, 'bm_mode', _mk))
        else:
            mode_items.extend([
                ('低', 'bm_mode', 'low'),
                ('中', 'bm_mode', 'medium'),
                ('高', 'bm_mode', 'high'),
                ('最高', 'bm_mode', 'max'),
            ])
        tool_items = [
            ('全部', 'bm_tool', None),
            ('使用工具', 'bm_tool', 'with'),
            ('不使用工具', 'bm_tool', 'without'),
        ]
        toolbar = ('<div class="benchmark-toolbar">'
                   + _group('思考模式', thinking_items)
                   # 与 DataLearner 原站交互一致：思考模式细分仅在选中"思考"模式时显示，
                   # 常规模式及未选择思考模式时不显示
                   + ('' if cur_thinking != 'thinking' else _group('思考模式细分', mode_items))
                   + _group('工具使用', tool_items)
                   + '</div>')
        return h[:div_start] + toolbar + h[t_end:]

    main_html = _rewrite_benchmark_toolbar(
        main_html, model_code, name, bm_thinking, bm_tool, bm_mode, thinking_modes
    )

    # 需求6：删除 API 定价区域中的"了解不同定价模式详解"链接及其外层容器
    # （该链接指向 DataLearner 外部页面，在本站无对应目标，删除以保持页面纯净）
    _pm_key = main_html.find('了解不同定价模式详解')
    if _pm_key != -1:
        # 向前定位包裹该链接的外层 div（flex items-center justify-end，仅含此链接）
        _pm_start = main_html.rfind('<div class="flex items-center justify-end">', 0, _pm_key)
        _pm_a_end = main_html.find('</a>', _pm_key)
        if _pm_start != -1 and _pm_a_end != -1:
            _pm_div_end = main_html.find('</div>', _pm_a_end)
            if _pm_div_end != -1:
                main_html = main_html[:_pm_start] + main_html[_pm_div_end + len('</div>'):]

    # 需求7：删除"了解数据收集方法"链接（指向 DataLearner 外部页面，本站无对应目标）
    main_html = _remove_btn(main_html, '了解数据收集方法')

    doc = (
        '<!DOCTYPE html><html lang="zh-CN"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        + ''.join(css_links_abs) +
        '</head><body>' + main_html + '</body></html>'
    )

    resp = Response(doc, content_type='text/html; charset=utf-8')
    # 禁止浏览器缓存代理抓取的详情页，避免切换筛选/刷新后显示旧内容
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


# ============ 模型详情规格解析（供对比页逐项对比使用）============
# 从 DataLearner 模型详情页纯文本中提取核心规格项，返回结构化 JSON
_MODEL_SPEC_LABELS = [
    '上下文长度', '模型参数', '最大输出长度', '模型类型', '输入/输出模态',
    '发布时间', '模型文件大小', 'MoE架构', '总参数 / 激活参数', '知识截止',
    '代码开源状态', '预训练权重开源', '推理能力', '多语言支持',
]
_MODEL_SPEC_STOP = [
    ' 更新于', ' 浏览量', ' 在线体验', ' GitHub', ' Hugging', ' DeepSeek',
    ' 开源', ' 官方', ' 评测', ' 常见', ' 发布', ' 模型解读', ' 推理过程',
    ' 思考模式', ' 上下文长度', ' 最大输出', ' 模型类型', ' 输入/输出',
    ' 模型文件', ' MoE架构', ' 总参数', ' 知识截止', ' 代码开源',
    ' 预训练权重', ' 推理能力', ' 多语言', ' 模型参数',
]


@app.route('/admin/api/global-models/detail-spec/<model_code>')
def api_global_model_detail_spec(model_code):
    """抓取 DataLearner 模型详情页并提取核心规格项，返回 JSON 供对比页逐项对比。"""
    if not re.fullmatch(r'[A-Za-z0-9\-_]+', model_code or ''):
        return jsonify({'error': '无效的模型标识'}), 400

    url = f'{DATALEARNER_DETAIL_BASE}/{model_code}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return jsonify({'error': f'抓取详情失败: {str(e)}'}), 502

    # 转为纯文本，便于按「标签 值」模式提取
    text = re.sub(r'<script.*?</script>', ' ', html, flags=re.S)
    text = re.sub(r'<style.*?</style>', ' ', text, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    specs = {}
    for label in _MODEL_SPEC_LABELS:
        idx = text.find(label)
        if idx == -1:
            specs[label] = ''
            continue
        after = text[idx + len(label):]
        nextpos = len(after)
        # 截断到下一个已知标签
        for other in _MODEL_SPEC_LABELS:
            if other != label:
                p = after.find(other)
                if p != -1 and p < nextpos:
                    nextpos = p
        # 截断到常见边界词
        for sep in _MODEL_SPEC_STOP:
            p = after.find(sep)
            if p != -1 and p < nextpos and p < 200:
                nextpos = p
        val = after[:nextpos].strip().lstrip(': ').strip()
        specs[label] = val[:120]

    return jsonify({'model_code': model_code, 'specs': specs})


@app.route('/admin/api/homepage/models/<model_id>')
def api_homepage_model_detail(model_id):
    """首页模型详情"""
    models = load_json(DATA_DIR / 'models-lite.json') or []
    detail = load_json(DATA_DIR / 'models-detail.json') or []
    m = next((x for x in models if x.get('id') == model_id), None)
    d = next((x for x in detail if x.get('id') == model_id), None)
    if not m:
        return jsonify({'error': '模型不存在'}), 404
    return jsonify({'model': m, 'detail': d})


@app.route('/admin/api/homepage/hardware')
def api_homepage_hardware():
    """首页硬件数据"""
    hardware = load_json(DATA_DIR / 'hardware.json') or []
    search = request.args.get('search', '').lower()
    hw_type = request.args.get('type', '')
    chip = request.args.get('chip', '')

    filtered = hardware
    if search:
        filtered = [h for h in filtered if search in h.get('name', '').lower()
                    or search in h.get('type', '').lower()
                    or search in h.get('chip', '').lower()
                    or search in h.get('scenario', '').lower()]
    if hw_type and hw_type != 'all':
        filtered = [h for h in filtered if h.get('type') == hw_type]
    if chip and chip != 'all':
        filtered = [h for h in filtered if chip in h.get('chip', '')]

    chips = sorted(list(set(h.get('chip', '') for h in hardware if h.get('chip'))))
    return jsonify({
        'hardware': filtered,
        'chips': chips
    })


@app.route('/admin/api/homepage/nv-hardware')
def api_homepage_nv_hardware():
    """首页 NV（NVIDIA）产品数据"""
    hardware = load_json(DATA_DIR / 'nv-hardware.json') or []
    search = request.args.get('search', '').lower()
    chip = request.args.get('chip', '')

    filtered = hardware
    if search:
        filtered = [h for h in filtered if search in h.get('name', '').lower()
                    or search in h.get('type', '').lower()
                    or search in h.get('chip', '').lower()
                    or search in h.get('scenario', '').lower()]
    if chip and chip != 'all':
        filtered = [h for h in filtered if chip in h.get('chip', '')]

    chips = sorted(list(set(h.get('chip', '') for h in hardware if h.get('chip'))))
    return jsonify({
        'hardware': filtered,
        'chips': chips
    })


# ============ 全球硬件参数管理（Admin 增删改查）============

HARDWARE_SOURCES = {
    'ascend': DATA_DIR / 'hardware.json',
    'nv': DATA_DIR / 'nv-hardware.json',
}


def load_hardware_source(source):
    """按来源加载硬件列表"""
    fp = HARDWARE_SOURCES.get(source)
    if not fp:
        return None
    return load_json(fp) or []


def save_hardware_source(source, items):
    """保存硬件列表到对应来源文件"""
    fp = HARDWARE_SOURCES[source]
    save_json(fp, items)


@app.route('/admin/api/hardware-params')
def api_hardware_params():
    """全球硬件参数列表（hardware.json + nv-hardware.json 合并，带 source 标识）"""
    source = request.args.get('source', '')
    search = request.args.get('search', '').lower()
    hw_type = request.args.get('type', '')

    all_items = []
    for src in HARDWARE_SOURCES:
        for h in load_hardware_source(src):
            item = dict(h)
            item['_source'] = src
            all_items.append(item)

    filtered = all_items
    if source and source != 'all':
        filtered = [h for h in filtered if h.get('_source') == source]
    if search:
        filtered = [h for h in filtered
                    if search in h.get('name', '').lower()
                    or search in h.get('chip', '').lower()
                    or search in h.get('type', '').lower()
                    or search in h.get('id', '').lower()]
    if hw_type and hw_type != 'all':
        filtered = [h for h in filtered if h.get('type') == hw_type]

    # 汇总类型
    types = sorted(list(set(h.get('type', '') for h in all_items if h.get('type'))))
    return jsonify({
        'total': len(filtered),
        'total_all': len(all_items),
        'hardware': filtered,
        'filters': {'types': types}
    })


@app.route('/admin/api/hardware-params', methods=['POST'])
def api_hardware_param_create():
    """Admin：新增全球硬件参数"""
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    source = data.pop('_source', 'ascend')
    if source not in HARDWARE_SOURCES:
        return jsonify({'error': '无效的数据来源'}), 400
    # 自动生成 id（若未提供）
    if not data.get('id'):
        base = data.get('name', 'hardware')
        data['id'] = re.sub(r'[^a-zA-Z0-9]+', '-', base).strip('-').lower() or 'hardware'
    items = load_hardware_source(source)
    items.append(data)
    save_hardware_source(source, items)
    return jsonify({'success': True, 'hardware': data})


@app.route('/admin/api/hardware-params/<source>/<hw_id>', methods=['PUT'])
def api_hardware_param_update(source, hw_id):
    """Admin：更新全球硬件参数"""
    if source not in HARDWARE_SOURCES:
        return jsonify({'error': '无效的数据来源'}), 400
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    data.pop('_source', None)
    items = load_hardware_source(source)
    for i, h in enumerate(items):
        if str(h.get('id')) == str(hw_id):
            items[i].update(data)
            save_hardware_source(source, items)
            return jsonify({'success': True, 'hardware': items[i]})
    return jsonify({'error': '硬件不存在'}), 404


@app.route('/admin/api/hardware-params/<source>/<hw_id>', methods=['DELETE'])
def api_hardware_param_delete(source, hw_id):
    """Admin：删除全球硬件参数"""
    if source not in HARDWARE_SOURCES:
        return jsonify({'error': '无效的数据来源'}), 400
    items = load_hardware_source(source)
    new_items = [h for h in items if str(h.get('id')) != str(hw_id)]
    if len(new_items) == len(items):
        return jsonify({'error': '硬件不存在'}), 404
    save_hardware_source(source, new_items)
    return jsonify({'success': True})


# ============ GPU_LIB 参数库（LLM Token 计算器与 Admin 共用数据源 data/gpu_lib.json） ============
GPU_LIB_FILE = DATA_DIR / 'gpu_lib.json'
# GPU_LIB 字段：GPU型号、显存带宽、FP16算力、FP8算力、显存容量、显存类型、互联带宽、参考价格
GPU_LIB_FIELDS = ['name', 'bw', 'fp16', 'fp8', 'vram', 'memType', 'ic', 'price']


def load_gpu_lib():
    return load_json(GPU_LIB_FILE) or []


def save_gpu_lib(items):
    save_json(GPU_LIB_FILE, items)


@app.route('/admin/api/gpu-lib')
def api_gpu_lib_list():
    """Admin/计算器：GPU_LIB 参数库列表（支持搜索、来源过滤）"""
    search = request.args.get('search', '').lower()
    source = request.args.get('source', '')
    items = load_gpu_lib()

    # 来源过滤：original=原始内置，global=由全球硬件提取补充（名称含"（整机）"或"推理卡/加速卡"等）
    if source == 'original':
        items = [g for g in items if not g.get('_fromGlobal')]
    elif source == 'global':
        items = [g for g in items if g.get('_fromGlobal')]
    if search:
        items = [g for g in items if search in g.get('name', '').lower()
                 or search in g.get('memType', '').lower()]

    return jsonify({
        'total': len(items),
        'total_all': len(load_gpu_lib()),
        'hardware': items
    })


@app.route('/admin/api/gpu-lib', methods=['POST'])
def api_gpu_lib_create():
    """Admin：新增 GPU_LIB 条目"""
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'GPU型号不能为空'}), 400
    items = load_gpu_lib()
    if any(g.get('name') == name for g in items):
        return jsonify({'error': '该 GPU 型号已存在'}), 400
    # 仅保留 GPU_LIB 字段
    item = {f: data.get(f) for f in GPU_LIB_FIELDS}
    items.append(item)
    save_gpu_lib(items)
    return jsonify({'success': True, 'hardware': item})


@app.route('/admin/api/gpu-lib/<path:gpu_name>', methods=['PUT'])
def api_gpu_lib_update(gpu_name):
    """Admin：更新 GPU_LIB 条目（按名称匹配）"""
    from urllib.parse import unquote
    gpu_name = unquote(gpu_name)
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    items = load_gpu_lib()
    for i, g in enumerate(items):
        if g.get('name') == gpu_name:
            new_name = (data.get('name') or '').strip()
            if new_name and new_name != gpu_name:
                if any(x.get('name') == new_name for x in items):
                    return jsonify({'error': '该 GPU 型号已存在'}), 400
                items[i]['name'] = new_name
            for f in GPU_LIB_FIELDS:
                if f != 'name' and f in data:
                    items[i][f] = data[f]
            save_gpu_lib(items)
            return jsonify({'success': True, 'hardware': items[i]})
    return jsonify({'error': 'GPU 型号不存在'}), 404


@app.route('/admin/api/gpu-lib/<path:gpu_name>', methods=['DELETE'])
def api_gpu_lib_delete(gpu_name):
    """Admin：删除 GPU_LIB 条目（按名称匹配）"""
    from urllib.parse import unquote
    gpu_name = unquote(gpu_name)
    items = load_gpu_lib()
    new_items = [g for g in items if g.get('name') != gpu_name]
    if len(new_items) == len(items):
        return jsonify({'error': 'GPU 型号不存在'}), 404
    save_gpu_lib(new_items)
    return jsonify({'success': True})


# ============ 全球AI模型参数库（Admin 管理数据源 data/model-params.json） ============
MODEL_PARAMS_FILE = DATA_DIR / 'model-params.json'
# 字段：名称、总参、激活、层数、注意力头数、KV头数、头维度、上下文、架构、是否MoE
MODEL_PARAMS_FIELDS = ['modelCode', 'name', 'totalParams', 'activeParams', 'layers',
                       'attentionHeads', 'kvHeads', 'headDim', 'context', 'architecture', 'isMoE']


def load_model_params():
    return load_json(MODEL_PARAMS_FILE) or []


def save_model_params(items):
    save_json(MODEL_PARAMS_FILE, items)


@app.route('/admin/api/model-params')
def api_model_params_list():
    """全球AI模型参数列表（支持搜索/分页）"""
    search = request.args.get('search', '').lower()
    has_params = request.args.get('hasParams', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))

    items = load_model_params()
    filtered = items
    if search:
        filtered = [m for m in filtered
                    if search in m.get('name', '').lower()
                    or search in m.get('modelCode', '').lower()]
    if has_params == 'yes':
        filtered = [m for m in filtered if m.get('totalParams') is not None]
    elif has_params == 'no':
        filtered = [m for m in filtered if m.get('totalParams') is None]

    page_items, total, total_pages = paginate(filtered, page, page_size)
    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'total_all': len(items),
        'models': page_items
    })


@app.route('/admin/api/model-params', methods=['POST'])
def api_model_params_create():
    """Admin：新增全球AI模型参数"""
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    code = (data.get('modelCode') or '').strip() or (data.get('name') or '').strip()
    if not code:
        return jsonify({'error': '模型标识不能为空'}), 400
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': '模型名称不能为空'}), 400
    items = load_model_params()
    if any(m.get('modelCode') == code for m in items):
        return jsonify({'error': '该模型已存在'}), 400
    item = {f: data.get(f) for f in MODEL_PARAMS_FIELDS}
    item['modelCode'] = code
    item['name'] = name
    items.append(item)
    save_model_params(items)
    return jsonify({'success': True, 'model': item})


@app.route('/admin/api/model-params/<path:mp_code>', methods=['PUT'])
def api_model_params_update(mp_code):
    """Admin：更新全球AI模型参数（按 modelCode 匹配）"""
    from urllib.parse import unquote
    mp_code = unquote(mp_code)
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    items = load_model_params()
    for i, m in enumerate(items):
        if m.get('modelCode') == mp_code:
            new_code = (data.get('modelCode') or '').strip()
            if new_code and new_code != mp_code:
                if any(x.get('modelCode') == new_code for x in items):
                    return jsonify({'error': '模型标识已存在'}), 400
                items[i]['modelCode'] = new_code
            for f in MODEL_PARAMS_FIELDS:
                if f != 'modelCode' and f in data:
                    items[i][f] = data[f]
            save_model_params(items)
            return jsonify({'success': True, 'model': items[i]})
    return jsonify({'error': '模型不存在'}), 404


@app.route('/admin/api/model-params/<path:mp_code>', methods=['DELETE'])
def api_model_params_delete(mp_code):
    """Admin：删除全球AI模型参数（按 modelCode 匹配）"""
    from urllib.parse import unquote
    mp_code = unquote(mp_code)
    items = load_model_params()
    new_items = [m for m in items if m.get('modelCode') != mp_code]
    if len(new_items) == len(items):
        return jsonify({'error': '模型不存在'}), 404
    save_model_params(new_items)
    return jsonify({'success': True})


# ---------- HF（hf-mirror）架构字段补全 ----------
HF_MIRROR_BASE = 'https://hf-mirror.com'


def _http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', errors='replace')


def _extract_hf_link(detail_html):
    """从 DataLearner 详情页提取 Hugging Face 仓库链接"""
    m = re.search(r'href=["\'](https?://(?:huggingface\.co|hf-mirror\.com)/[^"\']+)["\']', detail_html, re.I)
    if not m:
        return None
    url = m.group(1)
    # 归一化为 repo 路径（org/name）
    url = re.sub(r'^https?://(?:huggingface\.co|hf-mirror\.com)/', '', url)
    url = url.rstrip('/')
    # 去掉 /blob/... /tree/... /resolve/... 等后缀
    url = re.split(r'/(blob|tree|resolve|raw|commit)/', url)[0]
    return url


def _deep_find(cfg, key):
    """递归在嵌套 dict 中查找指定 key 的第一个非空值。
    多模态模型（如 GLM5、Qwen-VL、Omni 等）的架构字段常嵌套在 text_config/vision_config 等子对象中。
    优先返回 text_config（文本部分），其次顶层，再其它子对象。
    """
    if not isinstance(cfg, dict):
        return None
    # 优先 text_config
    if 'text_config' in cfg and isinstance(cfg.get('text_config'), dict):
        v = cfg['text_config'].get(key)
        if v is not None and v != 0:
            return v
    # 顶层
    if key in cfg:
        v = cfg[key]
        if v is not None and v != 0:
            return v
    # 其它子对象深度查找
    for k, v in cfg.items():
        if k == 'text_config':
            continue
        if isinstance(v, dict):
            r = _deep_find(v, key)
            if r is not None:
                return r
    return None


def _fetch_hf_config(hf_repo):
    """抓取 hf-mirror 的 config.json 并解析架构字段（支持多模态嵌套结构）"""
    config_url = f'{HF_MIRROR_BASE}/{hf_repo}/raw/main/config.json'
    cfg_text = _http_get(config_url)
    cfg = json.loads(cfg_text)

    # 若存在 text_config，以其为文本部分主配置（多模态模型架构字段在其内）
    base = cfg.get('text_config') if isinstance(cfg.get('text_config'), dict) else cfg

    layers = _deep_find(cfg, 'num_hidden_layers')
    if layers is None:
        # ChatGLM 等模型用 num_layers 表示层数
        layers = _deep_find(cfg, 'num_layers')
    heads = _deep_find(cfg, 'num_attention_heads')
    # KV 头数字段名不统一：多数模型用 num_key_value_heads，Falcon 等用 num_kv_heads
    kv_heads = _deep_find(cfg, 'num_key_value_heads')
    if kv_heads is None:
        kv_heads = _deep_find(cfg, 'num_kv_heads')
    # 缺少 KV 头数字段时，默认等于注意力头数
    if kv_heads is None:
        kv_heads = heads
    hidden = _deep_find(cfg, 'hidden_size')
    head_dim = _deep_find(cfg, 'head_dim')
    qk_head_dim = _deep_find(cfg, 'qk_head_dim')
    v_head_dim = _deep_find(cfg, 'v_head_dim')
    context = _deep_find(cfg, 'max_position_embeddings')
    if context is None:
        # ChatGLM 等模型用 seq_length 表示上下文长度
        context = _deep_find(cfg, 'seq_length')
    if context is None:
        # 部分模型（如 Falcon）config.json 无 max_position_embeddings，
        # 回退到 tokenizer_config.json 的 model_max_length 获取上下文长度
        try:
            tok_cfg = json.loads(_http_get(f'{HF_MIRROR_BASE}/{hf_repo}/raw/main/tokenizer_config.json', timeout=15))
            context = tok_cfg.get('model_max_length')
        except Exception:
            context = None
    model_type = (base or {}).get('model_type') or cfg.get('model_type')

    out = {}
    if layers is not None:
        out['layers'] = layers
    if heads is not None:
        out['attentionHeads'] = heads
    if kv_heads is not None:
        out['kvHeads'] = kv_heads
    # head_dim=0 或缺失时，用 hidden_size/attention_heads 或 qk_head_dim 推算
    if head_dim not in (None, 0):
        out['headDim'] = head_dim
    elif qk_head_dim not in (None, 0):
        out['headDim'] = qk_head_dim
    elif hidden is not None and heads:
        out['headDim'] = int(hidden / heads)
    if context is not None:
        out['context'] = context
    if model_type:
        out['modelType'] = model_type

    # MoE 判断：检查各类专家字段或 model_type
    is_moe = bool(_deep_find(cfg, 'num_experts_per_tok')
                  or _deep_find(cfg, 'num_local_experts')
                  or _deep_find(cfg, 'n_routed_experts')
                  or _deep_find(cfg, 'num_experts')
                  or 'moe' in str(model_type or '').lower())
    if is_moe:
        out['isMoE'] = '是'
        out['architecture'] = 'MoE'
    elif out:
        out['isMoE'] = '否'
        out['architecture'] = 'Dense'
    return out


@app.route('/admin/api/model-params/fetch-hf', methods=['POST'])
def api_model_params_fetch_hf():
    """从 HF（hf-mirror）抓取模型 config 补全架构字段。
    请求体：{"code": "glm-5-3"} 或 {"codes": ["glm-5-3", ...]}，或 {"repo": "zai-org/GLM-5.3"} 指定 HF 仓库
    """
    data = request.json or {}
    codes = data.get('codes') or ([data['code']] if data.get('code') else [])
    explicit_repo = data.get('repo') or ''
    results = []
    for code in codes:
        items = load_model_params()
        rec = next((m for m in items if m.get('modelCode') == code), None)
        if not rec:
            results.append({'code': code, 'success': False, 'error': '模型不存在'})
            continue
        try:
            hf_repo = explicit_repo
            if not hf_repo:
                # 抓取 datalearner 详情页提取 HF 链接
                detail_url = f'{DATALEARNER_DETAIL_BASE}/{code}'
                detail_html = _http_get(detail_url)
                hf_repo = _extract_hf_link(detail_html)
            if not hf_repo:
                results.append({'code': code, 'success': False, 'error': '未找到对应 HF 仓库（可能为闭源模型）'})
                continue
            fields = _fetch_hf_config(hf_repo)
            if not fields:
                results.append({'code': code, 'success': False, 'error': 'config.json 无架构字段'})
                continue
            # 回填
            for k, v in fields.items():
                if k in ('layers', 'attentionHeads', 'kvHeads', 'headDim', 'context', 'architecture', 'isMoE'):
                    rec[k] = v
            rec['hfRepo'] = hf_repo
            save_model_params(items)
            results.append({'code': code, 'success': True, 'hfRepo': hf_repo,
                            'model': {k: rec.get(k) for k in MODEL_PARAMS_FIELDS}})
        except Exception as e:
            results.append({'code': code, 'success': False, 'error': str(e)})
    return jsonify({'results': results, 'success_count': sum(1 for r in results if r['success'])})


# 训练模型部署链接映射（模型名 → 部署指南 URL）
TRAIN_MODEL_URLS = {
    # Wan2.2 系列
    'Wan2.2-T2V-5B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/wan2.2/README.md',
    'Wan2.2-T2V-A14B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/wan2.2/README.md',
    'Wan2.2-TI2V-5B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/wan2.2/README.md',
    'Wan2.2-I2V-A14B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/wan2.2/README.md',
    # Wan2.1 系列
    'Wan2.1-T2V-1.3B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/wan2.1/README.md',
    'Wan2.1-T2V-14B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/wan2.1/README.md',
    'Wan2.1-I2V-1.3B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/wan2.1/README.md',
    'Wan2.1-I2V-14B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/wan2.1/README.md',
    # 其他多模态生成
    'Self-Forcing-1.3B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/self-forcing/README.md',
    'HunyuanVideo1.5-T2V-8B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/hunyuanvideo_1.5/README.md',
    'Qihoo-T2X-1.1B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qihoo_t2x/README.md',
    'SD3.5-8.1B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/diffusers/sd3.5/README.md',
    'Flux-12B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/diffusers/flux/README.md',
    'Flux2-T2I-32B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/diffusers/flux2/README.md',
    'Flux2-I2I-32B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/diffusers/flux2/README.md',
    'Flux-Kontext-12B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/diffusers/flux_kontext/README.md',
    'Qwen-Image-27B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen_image/README.md',
    'Qwen-Image-Edit-27B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen_image/README.md',
    # 多模态理解
    'LLaVA 1.5-7B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/llava1.5/README.md',
    'InternVL 3.5-30B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/internvl3.5/README.md',
    'Qwen2.5-VL-3B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen2.5_vl/README.md',
    'Qwen2.5-VL-7B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen2.5_vl/README.md',
    'Qwen2.5-VL-32B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen2.5_vl/README.md',
    'Qwen2.5-VL-72B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen2.5_vl/README.md',
    'Qwen3-VL-8B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen3vl/README.md',
    'Qwen3-VL-30B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen3vl/README.md',
    'Qwen3-VL-235B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen3vl/README.md',
    'Qwen3.5-27B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen3_5/README.md',
    'Qwen3.5-35B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen3_5/README.md',
    'Qwen3.5-397B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen3_5/README.md',
    'Qwen2.5-Omni-7B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen2.5_omni/README.md',
    'Qwen3-Omni-30B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/qwen3omni/README.md',
    'Magistral-Small-2509-24B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/magistral-2509/README.md',
    # 语音
    'Whisper-1.5B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/whisper/README.md',
    'CosyVoice3-0.5B': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/examples/cosyvoice3/README.md',
}


def enrich_train_model(m):
    """为训练模型补充部署链接等额外信息"""
    m = dict(m)  # 不修改原始数据
    # 补充稳定 id（训练模型原始数据不含 id，前端详情弹窗依赖 id 定位）
    if not m.get('id'):
        import re as _re
        _id = _re.sub(r'[^a-z0-9]', '-', m.get('name', '').lower()).strip('-')
        m['id'] = _re.sub(r'-+', '-', _id)
    # 优先使用精确匹配，否则根据 source 生成通用链接
    name = m.get('name', '')
    if name in TRAIN_MODEL_URLS:
        m['model_url'] = TRAIN_MODEL_URLS[name]
    elif m.get('source') == 'MindSpeed-MM':
        m['model_url'] = 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/docs/zh/pytorch/supported_models.md'
    elif m.get('source') == 'MindSpeed-LLM':
        m['model_url'] = 'https://gitcode.com/Ascend/MindSpeed-LLM/blob/master/docs/zh/pytorch/models/supported_models.md'
    return m


@app.route('/admin/api/homepage/train-models')
def api_homepage_train_models():
    """首页训练模型数据"""
    train = load_json(DATA_DIR / 'train-models.json') or {}
    train_models = train.get('models', [])
    search = request.args.get('search', '').lower()
    framework = request.args.get('framework', '')
    category = request.args.get('category', '')
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 30))

    filtered = train_models
    if search:
        filtered = [m for m in filtered if search in m.get('name', '').lower()
                    or search in m.get('framework', '').lower()]
    if framework and framework != 'all':
        filtered = [m for m in filtered if m.get('framework') == framework]
    if category and category != 'all':
        filtered = [m for m in filtered if m.get('category') == category]
    if status and status != 'all':
        filtered = [m for m in filtered if m.get('status') == status]

    page_items, total, total_pages = paginate(filtered, page, page_size)

    # 为每个模型补充部署链接
    page_items = [enrich_train_model(m) for m in page_items]

    categories = sorted(list(set(m.get('category', '') for m in train_models if m.get('category'))))
    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'models': page_items,
        'categories': categories
    })


# 预定义数据源列表（含 URL）
PREDEFINED_SOURCES = [
    {'name': 'vLLM Ascend', 'url': 'https://docs.vllm.ai/projects/ascend/en/latest/user_guide/support_matrix/supported_models.html'},
    {'name': 'vLLM Omni', 'url': 'https://docs.vllm.ai/projects/vllm-omni/en/latest/models/supported_models/'},
    {'name': 'SGLang Ascend', 'url': 'https://docs.sglang.io/docs/hardware-platforms/ascend-npus/ascend_npu_support_models'},
    {'name': 'GitCode AI', 'url': 'https://ai.gitcode.com/models?ascendNative=true'},
    {'name': 'Ascend-SACT', 'url': 'https://gitcode.com/org/Ascend-SACT/repos'},
    {'name': 'MindSpeed-LLM', 'url': 'https://gitcode.com/Ascend/MindSpeed-LLM/blob/master/docs/zh/pytorch/models/supported_models.md'},
    {'name': 'MindSpeed-MM', 'url': 'https://gitcode.com/Ascend/MindSpeed-MM/blob/master/docs/zh/pytorch/supported_models.md'},
]


@app.route('/admin/api/sources')
def api_sources():
    models = load_json(DATA_DIR / 'models-lite.json') or []
    train = load_json(DATA_DIR / 'train-models.json') or {}
    train_models = train.get('models', [])

    # 统计各来源的模型数据（含推理模型和训练模型）
    stats = {}
    for m in models:
        src = m.get('source', '未知')
        if src not in stats:
            stats[src] = {'count': 0, 'supported': 0, 'experimental': 0}
        stats[src]['count'] += 1
        if m.get('supportLevel') == '✅ 已支持':
            stats[src]['supported'] += 1
        elif m.get('supportLevel') == '🔵 实验性':
            stats[src]['experimental'] += 1

    for m in train_models:
        src = m.get('source', '未知')
        if src not in stats:
            stats[src] = {'count': 0, 'supported': 0, 'experimental': 0}
        stats[src]['count'] += 1
        if m.get('status') == '已支持':
            stats[src]['supported'] += 1

    # 合并预定义数据源（确保所有数据源都展示，包括暂无模型数据的）
    result = {}
    for src in PREDEFINED_SOURCES:
        name = src['name']
        s = stats.get(name, {'count': 0, 'supported': 0, 'experimental': 0})
        s['url'] = src['url']
        result[name] = s

    # 补充不在预定义列表中的其他来源
    for name, s in stats.items():
        if name not in result:
            result[name] = s

    return jsonify(result)


# 小模型部署链接映射（基于 GitCode ModelZoo-PyTorch 仓库路径）
ACL_MODEL_BASE_URL = 'https://gitcode.com/Ascend/ModelZoo-PyTorch/tree/master'

# ACL_PyTorch 分类 → 子目录映射（built-in）
ACL_BUILTIN_CATEGORY_DIRS = {
    '语音': 'audio',
    '计算机视觉': 'cv',
    '嵌入': 'embedding',
    '具身智能': 'embodied_ai',
    '基础模型': 'foundation_models',
    'NLP': 'nlp',
    'OCR': 'ocr',
}

# ACL_PyTorch 分类 → 子目录映射（contrib）
ACL_CONTRIB_CATEGORY_DIRS = {
    '语音': 'audio',
    '计算机视觉': 'cv',
    '知识图谱': 'knowledge',
    'NLP': 'nlp',
    '强化学习': 'rl',
}

# PyTorch 分类 → 子目录映射（built-in）
PYTORCH_BUILTIN_CATEGORY_DIRS = {
    '语音': 'audio',
    '计算机视觉': 'cv',
    '自动驾驶': 'autonoumous_driving',
    '扩散模型': 'diffusion',
    '基础模型': 'foundation',
    'NLP': 'nlp',
    '多模态': 'multimodal',
    '强化学习': 'rl',
}

# PyTorch 分类 → 子目录映射（contrib）
PYTORCH_CONTRIB_CATEGORY_DIRS = {
    '语音': 'audio',
    '计算机视觉': 'cv',
    '自动驾驶': 'autonoumous_driving',
    '扩散模型': 'diffusion',
    '基础模型': 'foundation',
    'NLP': 'nlp',
    '多模态': 'multimodal',
    '强化学习': 'rl',
}


def enrich_acl_model(m):
    """为小模型补充部署链接"""
    m = dict(m)  # 不修改原始数据
    data_dir = m.get('data_dir', '')
    folder = m.get('folder', '')
    source = m.get('source', '')
    category = m.get('category', '')

    if data_dir == 'ACL_PyTorch' and folder:
        # ACL_PyTorch: {source}/{category_en}/{folder}/README.md
        sub_dir_map = ACL_BUILTIN_CATEGORY_DIRS if source == 'built-in' else ACL_CONTRIB_CATEGORY_DIRS
        sub_dir = sub_dir_map.get(category, '')
        if sub_dir:
            m['model_url'] = f'{ACL_MODEL_BASE_URL}/{data_dir}/{source}/{sub_dir}/{folder}/README.md'
        else:
            m['model_url'] = f'{ACL_MODEL_BASE_URL}/{data_dir}/ModeList.md'
    elif data_dir == 'PyTorch' and folder:
        # PyTorch: {source}/{category_en}/{folder}/README.md
        sub_dir_map = PYTORCH_BUILTIN_CATEGORY_DIRS if source == 'built-in' else PYTORCH_CONTRIB_CATEGORY_DIRS
        sub_dir = sub_dir_map.get(category, '')
        if sub_dir:
            m['model_url'] = f'{ACL_MODEL_BASE_URL}/{data_dir}/{source}/{sub_dir}/{folder}/README.md'
        else:
            m['model_url'] = f'{ACL_MODEL_BASE_URL}/{data_dir}'
    return m


@app.route('/admin/api/acl-models')
def api_acl_models():
    """小模型数据（合并 ACL_PyTorch + PyTorch 两个目录）"""
    acl_models = load_json(DATA_DIR / 'acl-pytorch-models.json') or []
    pytorch_models = load_json(DATA_DIR / 'pytorch-models.json') or []

    # 为每个模型标记数据源目录
    for m in acl_models:
        m['data_dir'] = 'ACL_PyTorch'
    for m in pytorch_models:
        m['data_dir'] = 'PyTorch'

    models = acl_models + pytorch_models

    search = request.args.get('search', '').lower()
    category = request.args.get('category', '')
    source = request.args.get('source', '')
    data_dir = request.args.get('data_dir', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))

    filtered = models
    if search:
        filtered = [m for m in filtered if search in m.get('name', '').lower()
                    or search in m.get('folder', '').lower()
                    or search in m.get('description', '').lower()]
    if category and category != 'all':
        filtered = [m for m in filtered if m.get('category') == category]
    if source and source != 'all':
        filtered = [m for m in filtered if m.get('source') == source]
    if data_dir and data_dir != 'all':
        filtered = [m for m in filtered if m.get('data_dir') == data_dir]

    page_items, total, total_pages = paginate(filtered, page, page_size)

    # 为每个模型补充部署链接
    page_items = [enrich_acl_model(m) for m in page_items]

    categories = sorted(list(set(m.get('category', '') for m in models if m.get('category'))))
    sources = sorted(list(set(m.get('source', '') for m in models if m.get('source'))))
    data_dirs = sorted(list(set(m.get('data_dir', '') for m in models if m.get('data_dir'))))

    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'models': page_items,
        'categories': categories,
        'sources': sources,
        'data_dirs': data_dirs,
        'acl_total': len(acl_models),
        'pytorch_total': len(pytorch_models)
    })


def enrich_mindie_model(m):
    """为 MindIE 模型补充部署链接"""
    m = dict(m)  # 不修改原始数据
    data_dir = m.get('data_dir', '')
    folder = m.get('folder', '')
    if data_dir and folder:
        m['model_url'] = f'{ACL_MODEL_BASE_URL}/{data_dir}/{folder}/README.md'
    return m


@app.route('/admin/api/mindie-models')
def api_mindie_models():
    """MindIE 模型数据"""
    mindie_models = load_json(DATA_DIR / 'mindie-models.json') or []

    search = request.args.get('search', '').lower()
    category = request.args.get('category', '')
    source = request.args.get('source', '')
    data_dir = request.args.get('data_dir', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))

    filtered = mindie_models
    if search:
        filtered = [m for m in filtered if search in m.get('name', '').lower()
                    or search in m.get('folder', '').lower()
                    or search in m.get('description', '').lower()]
    if category and category != 'all':
        filtered = [m for m in filtered if m.get('category') == category]
    if source and source != 'all':
        filtered = [m for m in filtered if m.get('source') == source]
    if data_dir and data_dir != 'all':
        filtered = [m for m in filtered if m.get('data_dir') == data_dir]

    page_items, total, total_pages = paginate(filtered, page, page_size)

    # 为每个 MindIE 模型补充部署链接
    page_items = [enrich_mindie_model(m) for m in page_items]

    categories = sorted(list(set(m.get('category', '') for m in mindie_models if m.get('category'))))
    sources = sorted(list(set(m.get('source', '') for m in mindie_models if m.get('source'))))
    data_dirs = sorted(list(set(m.get('data_dir', '') for m in mindie_models if m.get('data_dir'))))

    # 按目录统计
    dir_stats = {}
    for m in mindie_models:
        d = m.get('data_dir', '未知')
        dir_stats[d] = dir_stats.get(d, 0) + 1

    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'models': page_items,
        'categories': categories,
        'sources': sources,
        'data_dirs': data_dirs,
        'dir_stats': dir_stats
    })


# ============ 大模型评测基准（datalearner）============

def load_benchmarks():
    """加载大模型评测基准数据"""
    data = load_json(DATA_DIR / 'benchmarks.json') or {}
    return data.get('benchmarks', []), data.get('fetched_at')


@app.route('/admin/api/benchmarks')
def api_benchmarks():
    """大模型评测基准列表数据（支持搜索/筛选/分页）
    筛选维度：类别(category)、语言(language)、难度(difficulty)、机构(institution)
    """
    benchmarks, fetched_at = load_benchmarks()
    search = request.args.get('search', '').lower()
    category = request.args.get('category', '')
    language = request.args.get('language', '')
    difficulty = request.args.get('difficulty', '')
    institution = request.args.get('institution', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 24))

    filtered = benchmarks
    if search:
        filtered = [b for b in filtered
                    if search in b.get('shortName', '').lower()
                    or search in b.get('fullName', '').lower()
                    or search in b.get('description', '').lower()
                    or search in b.get('category', '').lower()]
    if category and category != 'all':
        filtered = [b for b in filtered if b.get('category') == category]
    if language and language != 'all':
        filtered = [b for b in filtered if b.get('language') == language]
    if difficulty and difficulty != 'all':
        filtered = [b for b in filtered if (b.get('difficultyLevel') or '') == difficulty]
    if institution and institution != 'all':
        filtered = [b for b in filtered if b.get('institution') == institution]

    page_items, total, total_pages = paginate(filtered, page, page_size)

    # 汇总筛选项
    categories = sorted(list(set(b.get('category', '') for b in benchmarks if b.get('category'))))
    languages = sorted(list(set(b.get('language', '') for b in benchmarks if b.get('language'))))
    difficulties = sorted(list(set(b.get('difficultyLevel', '') for b in benchmarks if b.get('difficultyLevel'))))
    institutions = sorted(list(set(b.get('institution', '') for b in benchmarks if b.get('institution'))))

    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'benchmarks': page_items,
        'filters': {
            'categories': categories,
            'languages': languages,
            'difficulties': difficulties,
            'institutions': institutions,
        },
        'meta': {
            'fetched_at': fetched_at,
            'total_all': len(benchmarks),
        }
    })


@app.route('/admin/api/benchmarks/<benchmark_id>', methods=['PUT'])
def api_benchmark_update(benchmark_id):
    """Admin：保存编辑后的评测基准数据"""
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    payload = load_json(DATA_DIR / 'benchmarks.json') or {}
    benchmarks = payload.get('benchmarks', [])
    for i, b in enumerate(benchmarks):
        if str(b.get('id')) == str(benchmark_id):
            benchmarks[i].update(data)
            payload['benchmarks'] = benchmarks
            save_json(DATA_DIR / 'benchmarks.json', payload)
            return jsonify({'success': True, 'benchmark': benchmarks[i]})
    return jsonify({'error': '评测基准不存在'}), 404


# ============ 大模型评测基准详情（抓取 DataLearner 详情页数据）============

DATALEARNER_BENCHMARK_BASE = 'https://www.datalearner.com/benchmarks'


def extract_benchmark_initial_data(html):
    """从 DataLearner 基准详情页的 Next.js flight data 中提取 initialData JSON。
    返回 (benchmark, results, totalCount, offset, limit)，解析失败返回 (None, [], 0, 0, 0)。
    """
    # initialData 出现在某个 self.__next_f.push([1,"..."] ) 的 flight 字符串中
    i = html.find('initialData')
    if i == -1:
        return None, [], 0, 0, 0
    start = html.rfind('self.__next_f.push([1,"', 0, i)
    if start == -1:
        return None, [], 0, 0, 0
    paren = html.find('(', start)
    if paren == -1:
        return None, [], 0, 0, 0
    # 兼容两种 push 闭合格式：旧式带分号 "])；"，新式直接 "])"
    closing = html.find(');', paren)
    if closing == -1:
        closing = html.find('])', paren) + 1
    if closing == 0:
        return None, [], 0, 0, 0
    push_inner = html[paren + 1:closing]
    try:
        arr, _ = json.JSONDecoder().raw_decode(push_inner)
        inner = arr[1]  # 解码后的 flight 字符串
        ki = inner.find('initialData')
        colon = inner.find(':', ki)
        astart = inner.find('{', colon)
        obj, _ = json.JSONDecoder().raw_decode(inner[astart:])
        return (
            obj.get('benchmark'),
            obj.get('results') or [],
            obj.get('totalCount') or 0,
            obj.get('offset') or 0,
            obj.get('limit') or 0,
        )
    except Exception:
        return None, [], 0, 0, 0


@app.route('/admin/api/benchmarks/detail/<benchmark_code>')
def api_benchmark_detail(benchmark_code):
    """代理抓取 DataLearner 对应评测基准详情页，解析其 initialData（基准信息 + 模型榜单），
    以 JSON 返回，供前端 benchmark_detail.html 渲染，避免跳转到 DataLearner 页面。
    """
    if not re.fullmatch(r'[A-Za-z0-9\-_]+', benchmark_code or ''):
        return jsonify({'error': '无效的基准标识'}), 400

    url = f'{DATALEARNER_BENCHMARK_BASE}/{benchmark_code}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return jsonify({'error': f'抓取详情失败: {str(e)}'}), 502

    benchmark, results, total_count, offset, limit = extract_benchmark_initial_data(html)
    if benchmark is None:
        return jsonify({'error': '未能解析该基准的详情数据'}), 502

    # 补充基准详情页链接
    benchmark['datalearnerUrl'] = url
    return jsonify({
        'benchmark': benchmark,
        'results': results,
        'totalCount': total_count,
        'offset': offset,
        'limit': limit,
    })


# ============ 定时备份任务 ============

def scheduled_backup():
    """每天晚上 23:00 自动备份数据"""
    backup_dir = DATA_DIR / 'backups'
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_files = ['models.json', 'models-lite.json', 'models-detail.json',
                    'train-models.json', 'hardware.json', 'crawl-status.json',
                    'acl-pytorch-models.json', 'pytorch-models.json', 'mindie-models.json',
                    'global-models.json', 'benchmarks.json']
    backed_up = []
    for f in backup_files:
        src = DATA_DIR / f
        if src.exists():
            dst = backup_dir / f'{timestamp}_{f}'
            shutil.copy2(src, dst)
            backed_up.append(f)
    print(f"[{timestamp}] ⏰ 定时备份完成: {len(backed_up)} 个文件 ({', '.join(backed_up)})")


def run_daily_backup():
    """定时线程：每天 23:00 执行备份"""
    while True:
        now = datetime.now()
        # 计算到下一次 23:00 的秒数
        target = now.replace(hour=23, minute=0, second=0, microsecond=0)
        if now >= target:
            # 如果已经过了今天的 23:00，则计算到明天
            from datetime import timedelta
            target = target + timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        threading.Event().wait(wait_seconds)
        try:
            scheduled_backup()
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y%m%d_%H%M%S')}] ⏰ 定时备份失败: {e}")


# ============ 首页静态文件路由（放在 Admin 路由之后）============

@app.route('/<path:path>')
def static_files(path):
    # 排除 admin 路由（让 Flask 匹配更具体的 admin 路由）
    if path.startswith('admin/'):
        return admin_index()
    file_path = BASE_DIR / path
    if file_path.exists() and file_path.is_file():
        return send_from_directory(str(BASE_DIR), path)
    return send_from_directory(str(BASE_DIR), 'index.html')


# ============ 启动 ============
if __name__ == '__main__':
    # 加载爬虫历史状态（重启后保留历史日志）
    _load_crawler_status()
    # 启动定时备份线程（每天 23:00 自动备份）
    backup_thread = threading.Thread(target=run_daily_backup, daemon=True)
    backup_thread.start()
    print("⏰ 定时备份已启动（每天 23:00 自动备份）")

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"🚀 服务启动于 http://localhost:{port}")
    print(f"   📋 首页: http://localhost:{port}/")
    print(f"   ⚙️  Admin: http://localhost:{port}/admin")
    app.run(host='0.0.0.0', port=port, debug=False)
