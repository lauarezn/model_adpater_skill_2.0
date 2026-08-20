#!/usr/bin/env python3
"""
统一服务入口 - 同时托管静态网站和 Admin 后端
- 首页 (/) : 昇腾大模型适配清单
- Admin (/admin) : 管理后台
"""

import os
import sys
import json
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

# ============ 配置 ============
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
SCRIPTS_DIR = BASE_DIR / 'scripts'

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path='')

# 爬虫运行状态
crawler_status = {
    'running': False,
    'last_run': None,
    'last_status': None,
    'progress': '',
    'pid': None
}


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
        crawler_status['progress'] = '正在启动爬虫...'
        crawler_status['last_run'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / 'crawler.py')],
                capture_output=True, text=True, timeout=600,
                cwd=str(BASE_DIR)
            )
            if result.returncode == 0:
                crawler_status['last_status'] = 'success'
                crawler_status['progress'] = result.stdout[-500:] if result.stdout else '爬取完成'
            else:
                crawler_status['last_status'] = 'failed'
                crawler_status['progress'] = (result.stderr or '')[-500:]
        except subprocess.TimeoutExpired:
            crawler_status['last_status'] = 'failed'
            crawler_status['progress'] = '爬虫执行超时（>10分钟）'
        except Exception as e:
            crawler_status['last_status'] = 'failed'
            crawler_status['progress'] = f'爬虫执行失败: {str(e)}'
        finally:
            crawler_status['running'] = False

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
              'train-models.json', 'hardware.json', 'crawl-status.json']:
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
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"🚀 服务启动于 http://localhost:{port}")
    print(f"   📋 首页: http://localhost:{port}/")
    print(f"   ⚙️  Admin: http://localhost:{port}/admin")
    app.run(host='0.0.0.0', port=port, debug=False)
