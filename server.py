#!/usr/bin/env python3
"""
统一服务入口 - 同时托管静态网站和 Admin 后端
- 首页 (/) : 昇腾大模型适配清单
- Admin (/admin) : 管理后台
"""

import os
import sys
import json
import subprocess
import threading
import shutil
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
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_data_stats():
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

    data_size = sum(
        os.path.getsize(DATA_DIR / f) for f in os.listdir(DATA_DIR)
        if os.path.isfile(DATA_DIR / f)
    ) / 1024 / 1024

    return {
        'total_models': len(models),
        'total_detail': len(detail),
        'total_train': len(train.get('models', [])),
        'total_hardware': len(hardware),
        'categories': categories,
        'sources': sources,
        'crawl_status': status,
        'data_size_mb': round(data_size, 2)
    }


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
    search = request.args.get('search', '').lower()
    source = request.args.get('source', '')
    category = request.args.get('category', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))

    if search:
        models = [m for m in models if search in m.get('name', '').lower()
                  or search in m.get('developer', '').lower()
                  or search in m.get('id', '').lower()]
    if source:
        models = [m for m in models if m.get('source') == source]
    if category:
        models = [m for m in models if m.get('category') == category]

    total = len(models)
    start = (page - 1) * page_size
    end = start + page_size

    all_sources = sorted(list(set(m.get('source', '未知') for m in load_json(DATA_DIR / 'models-lite.json') or [])))
    all_categories = sorted(list(set(m.get('category', '其他') for m in load_json(DATA_DIR / 'models-lite.json') or [])))

    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size),
        'models': models[start:end],
        'sources': all_sources,
        'categories': all_categories
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
    if sort == 'popular':
        filtered.sort(key=lambda m: -(int(m.get('id', '0')) if m.get('id', '0').isdigit() else 0))
    elif sort == 'newest':
        filtered.sort(key=lambda m: -(int(m.get('id', '0')) if m.get('id', '0').isdigit() else 0))
    elif sort == 'updated':
        filtered.sort(key=lambda m: -(int(m.get('id', '0')) if m.get('id', '0').isdigit() else 0))
    else:
        filtered.sort(key=lambda m: m.get('name', ''))

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size

    all_tags = sorted(list(set(
        t for m in models for t in m.get('tags', [])
    )))
    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size),
        'models': filtered[start:end],
        'categories': sorted(list(set(m.get('category', '其他') for m in models))),
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

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size

    categories = sorted(list(set(m.get('category', '') for m in train_models if m.get('category'))))
    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size),
        'models': filtered[start:end],
        'categories': categories
    })


@app.route('/admin/api/sources')
def api_sources():
    models = load_json(DATA_DIR / 'models-lite.json') or []
    sources = {}
    for m in models:
        src = m.get('source', '未知')
        if src not in sources:
            sources[src] = {'count': 0, 'supported': 0, 'experimental': 0}
        sources[src]['count'] += 1
        if m.get('supportLevel') == '✅ 已支持':
            sources[src]['supported'] += 1
        elif m.get('supportLevel') == '🔵 实验性':
            sources[src]['experimental'] += 1
    return jsonify(sources)


# ============ Admin 前端页面 ============
# Admin 前端已分离为独立文件: admin/index.html, admin/css/admin.css, admin/js/admin.js


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
