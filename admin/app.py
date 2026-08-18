#!/usr/bin/env python3
"""
Admin 后端服务 - 昇腾服务器大模型适配清单管理系统
提供数据管理、爬虫控制、模型编辑等功能
"""

import json
import os
import sys
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, render_template_string, send_from_directory

# ============ 配置 ============
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
SCRIPTS_DIR = BASE_DIR / 'scripts'
ADMIN_DIR = BASE_DIR / 'admin'

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()

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
    """加载 JSON 文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_json(filepath, data):
    """保存 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
        'data_size_mb': round(sum(
            os.path.getsize(DATA_DIR / f) for f in os.listdir(DATA_DIR)
            if os.path.isfile(DATA_DIR / f)
        ) / 1024 / 1024, 2)
    }


# ============ 路由 ============

@app.route('/')
def admin_index():
    """Admin 首页"""
    stats = get_data_stats()
    return render_template_string(ADMIN_HTML, stats=stats, crawler=crawler_status)


@app.route('/api/stats')
def api_stats():
    """获取数据统计 API"""
    return jsonify(get_data_stats())


@app.route('/api/models')
def api_models():
    """获取模型列表 API（支持搜索和分页）"""
    models = load_json(DATA_DIR / 'models-lite.json') or []
    search = request.args.get('search', '').lower()
    source = request.args.get('source', '')
    category = request.args.get('category', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))

    # 筛选
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

    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size,
        'models': models[start:end]
    })


@app.route('/api/models/<model_id>', methods=['GET'])
def api_model_get(model_id):
    """获取单个模型详情"""
    models = load_json(DATA_DIR / 'models-lite.json') or []
    detail = load_json(DATA_DIR / 'models-detail.json') or []

    m = next((x for x in models if x.get('id') == model_id), None)
    d = next((x for x in detail if x.get('id') == model_id), None)

    if not m:
        return jsonify({'error': '模型不存在'}), 404

    return jsonify({'model': m, 'detail': d})


@app.route('/api/models/<model_id>', methods=['PUT'])
def api_model_update(model_id):
    """更新模型数据"""
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


@app.route('/api/models/<model_id>', methods=['DELETE'])
def api_model_delete(model_id):
    """删除模型"""
    models = load_json(DATA_DIR / 'models-lite.json') or []
    new_models = [m for m in models if m.get('id') != model_id]

    if len(new_models) == len(models):
        return jsonify({'error': '模型不存在'}), 404

    save_json(DATA_DIR / 'models-lite.json', new_models)

    # 同步更新 models.json
    full_models = load_json(DATA_DIR / 'models.json') or []
    full_models = [m for m in full_models if m.get('id') != model_id]
    save_json(DATA_DIR / 'models.json', full_models)

    return jsonify({'success': True, 'deleted': model_id})


@app.route('/api/models/batch', methods=['POST'])
def api_models_batch():
    """批量操作模型"""
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


@app.route('/api/crawler/status')
def api_crawler_status():
    """获取爬虫状态"""
    return jsonify(crawler_status)


@app.route('/api/crawler/run', methods=['POST'])
def api_crawler_run():
    """运行爬虫"""
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


@app.route('/api/data/export')
def api_data_export():
    """导出数据"""
    format_type = request.args.get('format', 'json')
    data_type = request.args.get('type', 'models')

    if data_type == 'models':
        data = load_json(DATA_DIR / 'models-lite.json') or []
    elif data_type == 'train':
        data = load_json(DATA_DIR / 'train-models.json') or {}
    elif data_type == 'hardware':
        data = load_json(DATA_DIR / 'hardware.json') or []
    else:
        return jsonify({'error': '未知数据类型'}), 400

    if format_type == 'json':
        return jsonify(data)
    else:
        return jsonify({'error': '不支持的导出格式'}), 400


@app.route('/api/data/backup', methods=['POST'])
def api_data_backup():
    """备份数据"""
    backup_dir = DATA_DIR / 'backups'
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_info = []

    for f in ['models.json', 'models-lite.json', 'models-detail.json',
              'train-models.json', 'hardware.json', 'crawl-status.json']:
        src = DATA_DIR / f
        if src.exists():
            dst = backup_dir / f'{timestamp}_{f}'
            import shutil
            shutil.copy2(src, dst)
            backup_info.append(f)

    return jsonify({
        'success': True,
        'backup_time': timestamp,
        'backup_dir': str(backup_dir),
        'files': backup_info
    })


@app.route('/api/data/restore', methods=['POST'])
def api_data_restore():
    """恢复备份"""
    filename = request.json.get('filename')
    if not filename:
        return jsonify({'error': '请指定备份文件'}), 400

    backup_path = DATA_DIR / 'backups' / filename
    if not backup_path.exists():
        return jsonify({'error': '备份文件不存在'}), 404

    # 根据备份文件名确定目标文件
    target_name = filename.split('_', 1)[1] if '_' in filename else filename
    target_path = DATA_DIR / target_name

    import shutil
    shutil.copy2(backup_path, target_path)

    return jsonify({'success': True, 'restored': target_name})


@app.route('/api/data/backups')
def api_data_backups():
    """列出备份文件"""
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


@app.route('/api/sources')
def api_sources():
    """获取数据来源统计"""
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

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Admin - 昇腾大模型适配清单管理</title>
  <style>
    :root {
      --bg: #0F172A;
      --bg-card: #1E293B;
      --bg-hover: #334155;
      --text: #E2E8F0;
      --text-secondary: #94A3B8;
      --primary: #3B82F6;
      --primary-hover: #2563EB;
      --success: #22C55E;
      --warning: #F59E0B;
      --danger: #EF4444;
      --border: #334155;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }
    .sidebar {
      position: fixed;
      left: 0; top: 0; bottom: 0;
      width: 220px;
      background: var(--bg-card);
      border-right: 1px solid var(--border);
      padding: 20px 0;
      z-index: 100;
    }
    .sidebar h2 {
      padding: 0 20px 20px;
      font-size: 1rem;
      color: var(--primary);
      border-bottom: 1px solid var(--border);
    }
    .sidebar nav { padding: 10px 0; }
    .sidebar a {
      display: block;
      padding: 10px 20px;
      color: var(--text-secondary);
      text-decoration: none;
      font-size: 0.9rem;
      transition: all 0.2s;
      cursor: pointer;
    }
    .sidebar a:hover, .sidebar a.active {
      background: var(--bg-hover);
      color: var(--text);
      border-left: 3px solid var(--primary);
    }
    .main {
      margin-left: 220px;
      padding: 24px;
      max-width: 1400px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
    }
    .header h1 { font-size: 1.5rem; }
    .header .subtitle { color: var(--text-secondary); font-size: 0.85rem; margin-top: 4px; }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .stat-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
    }
    .stat-card .value {
      font-size: 2rem;
      font-weight: 700;
      color: var(--primary);
    }
    .stat-card .label {
      font-size: 0.8rem;
      color: var(--text-secondary);
      margin-top: 4px;
    }
    .card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
    }
    .card h3 {
      font-size: 1rem;
      margin-bottom: 16px;
      color: var(--text);
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      border: none;
      border-radius: 8px;
      font-size: 0.85rem;
      cursor: pointer;
      transition: all 0.2s;
      font-weight: 500;
    }
    .btn-primary { background: var(--primary); color: white; }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-success { background: var(--success); color: white; }
    .btn-success:hover { opacity: 0.9; }
    .btn-danger { background: var(--danger); color: white; }
    .btn-danger:hover { opacity: 0.9; }
    .btn-warning { background: var(--warning); color: #1E293B; }
    .btn-warning:hover { opacity: 0.9; }
    .btn-sm { padding: 4px 10px; font-size: 0.8rem; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }
    th, td {
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    th {
      color: var(--text-secondary);
      font-weight: 600;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    tr:hover { background: var(--bg-hover); }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 500;
    }
    .badge-success { background: rgba(34,197,94,0.2); color: var(--success); }
    .badge-warning { background: rgba(245,158,11,0.2); color: var(--warning); }
    .badge-danger { background: rgba(239,68,68,0.2); color: var(--danger); }
    .badge-info { background: rgba(59,130,246,0.2); color: var(--primary); }
    .search-bar {
      display: flex;
      gap: 12px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    .search-bar input, .search-bar select {
      padding: 8px 12px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      font-size: 0.85rem;
    }
    .search-bar input { flex: 1; min-width: 200px; }
    .search-bar select { min-width: 120px; }
    .pagination {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 16px;
      justify-content: center;
    }
    .pagination span { color: var(--text-secondary); font-size: 0.85rem; }
    .modal-overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.6);
      z-index: 1000;
      align-items: center;
      justify-content: center;
    }
    .modal-overlay.active { display: flex; }
    .modal {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      max-width: 700px;
      width: 90%;
      max-height: 80vh;
      overflow-y: auto;
    }
    .modal h2 { margin-bottom: 16px; }
    .modal .form-group {
      margin-bottom: 12px;
    }
    .modal .form-group label {
      display: block;
      font-size: 0.8rem;
      color: var(--text-secondary);
      margin-bottom: 4px;
    }
    .modal .form-group input, .modal .form-group select, .modal .form-group textarea {
      width: 100%;
      padding: 8px 12px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      font-size: 0.85rem;
    }
    .modal .form-group textarea { min-height: 80px; resize: vertical; }
    .modal .form-actions {
      display: flex;
      gap: 8px;
      justify-content: flex-end;
      margin-top: 16px;
    }
    .toast {
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 12px 20px;
      border-radius: 8px;
      color: white;
      font-size: 0.85rem;
      z-index: 2000;
      animation: slideIn 0.3s ease;
    }
    .toast-success { background: var(--success); }
    .toast-error { background: var(--danger); }
    .toast-info { background: var(--primary); }
    @keyframes slideIn {
      from { transform: translateX(100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    .section { display: none; }
    .section.active { display: block; }
    .crawler-status {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px 16px;
      border-radius: 8px;
      margin-bottom: 16px;
    }
    .crawler-status.running { background: rgba(59,130,246,0.1); border: 1px solid var(--primary); }
    .crawler-status.idle { background: rgba(34,197,94,0.1); border: 1px solid var(--success); }
    .crawler-status.failed { background: rgba(239,68,68,0.1); border: 1px solid var(--danger); }
    .status-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      display: inline-block;
    }
    .status-dot.running { background: var(--primary); animation: pulse 1s infinite; }
    .status-dot.idle { background: var(--success); }
    .status-dot.failed { background: var(--danger); }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }
    .progress-box {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      font-family: monospace;
      font-size: 0.8rem;
      white-space: pre-wrap;
      max-height: 300px;
      overflow-y: auto;
      margin-top: 12px;
    }
    .checkbox-col { width: 36px; }
    .tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.7rem; background: var(--bg-hover); margin: 1px; }
    .empty-state { text-align: center; padding: 40px; color: var(--text-secondary); }
    .backup-list { max-height: 300px; overflow-y: auto; }
    .backup-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 12px;
      border-bottom: 1px solid var(--border);
    }
    .backup-item:hover { background: var(--bg-hover); }
    .backup-item .name { font-size: 0.85rem; }
    .backup-item .meta { font-size: 0.75rem; color: var(--text-secondary); }
  </style>
</head>
<body>
  <div class="sidebar">
    <h2>⚙️ Admin Panel</h2>
    <nav>
      <a class="active" onclick="switchTab('dashboard')">📊 仪表盘</a>
      <a onclick="switchTab('models')">📋 模型管理</a>
      <a onclick="switchTab('crawler')">🕷️ 爬虫控制</a>
      <a onclick="switchTab('backup')">💾 数据备份</a>
      <a onclick="switchTab('sources')">📡 数据来源</a>
    </nav>
    <div style="padding: 20px; border-top: 1px solid var(--border); margin-top: 20px;">
      <a href="/" target="_blank" style="color: var(--primary); text-decoration: none; font-size: 0.85rem;">← 返回首页</a>
    </div>
  </div>

  <div class="main">
    <div class="header">
      <div>
        <h1>Admin 管理后台</h1>
        <div class="subtitle">昇腾服务器大模型适配清单 · 数据管理系统</div>
      </div>
      <div>
        <button class="btn btn-primary" onclick="refreshStats()">🔄 刷新数据</button>
      </div>
    </div>

    <!-- 仪表盘 -->
    <div class="section active" id="section-dashboard">
      <div class="stats-grid" id="statsGrid">
        <div class="stat-card">
          <div class="value" id="statModels">-</div>
          <div class="label">模型总数</div>
        </div>
        <div class="stat-card">
          <div class="value" id="statDetail">-</div>
          <div class="label">详细模型</div>
        </div>
        <div class="stat-card">
          <div class="value" id="statTrain">-</div>
          <div class="label">训练模型</div>
        </div>
        <div class="stat-card">
          <div class="value" id="statHardware">-</div>
          <div class="label">硬件型号</div>
        </div>
        <div class="stat-card">
          <div class="value" id="statDataSize">-</div>
          <div class="label">数据大小</div>
        </div>
      </div>

      <div class="card">
        <h3>📊 分类分布</h3>
        <div id="categoryChart"></div>
      </div>

      <div class="card">
        <h3>📡 数据来源分布</h3>
        <div id="sourceChart"></div>
      </div>
    </div>

    <!-- 模型管理 -->
    <div class="section" id="section-models">
      <div class="card">
        <div class="search-bar">
          <input type="text" id="modelSearch" placeholder="🔍 搜索模型名称、ID、开发者..." oninput="searchModels()">
          <select id="sourceFilter" onchange="searchModels()">
            <option value="">全部来源</option>
          </select>
          <select id="categoryFilter2" onchange="searchModels()">
            <option value="">全部分类</option>
          </select>
          <button class="btn btn-danger btn-sm" onclick="batchDelete()">🗑️ 批量删除</button>
          <button class="btn btn-primary btn-sm" onclick="exportSelected()">📥 导出选中</button>
        </div>
        <div style="overflow-x: auto;">
          <table>
            <thead>
              <tr>
                <th class="checkbox-col"><input type="checkbox" id="selectAll" onchange="toggleSelectAll()"></th>
                <th>模型名称</th>
                <th>开发者</th>
                <th>分类</th>
                <th>状态</th>
                <th>来源</th>
                <th>硬件</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="modelTableBody"></tbody>
          </table>
        </div>
        <div class="pagination" id="modelPagination"></div>
      </div>
    </div>

    <!-- 爬虫控制 -->
    <div class="section" id="section-crawler">
      <div class="card">
        <h3>🕷️ 爬虫状态</h3>
        <div class="crawler-status" id="crawlerStatus">
          <span class="status-dot idle"></span>
          <span id="crawlerStatusText">就绪</span>
        </div>
        <div style="display: flex; gap: 12px; margin-bottom: 16px;">
          <button class="btn btn-success" id="runCrawlerBtn" onclick="runCrawler()">▶️ 运行爬虫</button>
          <button class="btn btn-primary" onclick="refreshCrawlerStatus()">🔄 刷新状态</button>
        </div>
        <div class="progress-box" id="crawlerProgress">暂无爬虫日志</div>
      </div>

      <div class="card">
        <h3>📋 爬取配置</h3>
        <table>
          <thead>
            <tr><th>数据源</th><th>URL</th></tr>
          </thead>
          <tbody>
            <tr><td>vLLM Ascend</td><td style="font-size:0.75rem;word-break:break-all">https://docs.vllm.ai/projects/ascend/zh-cn/latest/user_guide/support_matrix/supported_models.html</td></tr>
            <tr><td>vLLM Omni</td><td style="font-size:0.75rem;word-break:break-all">https://docs.vllm.ai/projects/vllm-omni/en/latest/models/supported_models/</td></tr>
            <tr><td>SGLang Ascend</td><td style="font-size:0.75rem;word-break:break-all">https://docs.sglang.io/docs/hardware-platforms/ascend-npus/ascend_npu_support_models</td></tr>
            <tr><td>GitCode AI</td><td style="font-size:0.75rem;word-break:break-all">https://ai.gitcode.com/models?ascendNative=true</td></tr>
            <tr><td>Ascend-SACT</td><td style="font-size:0.75rem;word-break:break-all">https://gitcode.com/org/Ascend-SACT/repos</td></tr>
            <tr><td>MindSpeed-MM</td><td style="font-size:0.75rem;word-break:break-all">https://gitcode.com/Ascend/MindSpeed-MM/blob/master/docs/zh/pytorch/supported_models.md</td></tr>
            <tr><td>MindSpeed-LLM</td><td style="font-size:0.75rem;word-break:break-all">https://gitcode.com/Ascend/MindSpeed-LLM/blob/master/docs/zh/pytorch/models/supported_models.md</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 数据备份 -->
    <div class="section" id="section-backup">
      <div class="card">
        <h3>💾 数据备份</h3>
        <div style="display: flex; gap: 12px; margin-bottom: 16px;">
          <button class="btn btn-primary" onclick="createBackup()">📦 创建备份</button>
          <button class="btn btn-warning" onclick="listBackups()">🔄 刷新列表</button>
        </div>
        <div id="backupResult"></div>
        <div class="backup-list" id="backupList">
          <div class="empty-state">暂无备份数据</div>
        </div>
      </div>
    </div>

    <!-- 数据来源 -->
    <div class="section" id="section-sources">
      <div class="card">
        <h3>📡 数据来源统计</h3>
        <div id="sourceStats"></div>
      </div>
    </div>
  </div>

  <!-- 编辑模型弹窗 -->
  <div class="modal-overlay" id="editModal">
    <div class="modal">
      <h2>✏️ 编辑模型</h2>
      <div id="editForm"></div>
      <div class="form-actions">
        <button class="btn btn-primary" onclick="saveModel()">💾 保存</button>
        <button class="btn" style="background:var(--bg-hover);color:var(--text)" onclick="closeEditModal()">取消</button>
      </div>
    </div>
  </div>

  <script>
    let currentPage = 1;
    let selectedIds = new Set();
    let editingModelId = null;

    // ============ Tab 切换 ============
    function switchTab(tab) {
      document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
      document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
      document.getElementById('section-' + tab).classList.add('active');
      document.querySelector(`.sidebar a[onclick*="'${tab}'"]`).classList.add('active');

      if (tab === 'models') searchModels();
      if (tab === 'crawler') refreshCrawlerStatus();
      if (tab === 'backup') listBackups();
      if (tab === 'sources') loadSourceStats();
    }

    // ============ Toast 通知 ============
    function showToast(message, type = 'info') {
      const toast = document.createElement('div');
      toast.className = `toast toast-${type}`;
      toast.textContent = message;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 3000);
    }

    // ============ 仪表盘 ============
    async function refreshStats() {
      try {
        const res = await fetch('/api/stats');
        const stats = await res.json();

        document.getElementById('statModels').textContent = stats.total_models;
        document.getElementById('statDetail').textContent = stats.total_detail;
        document.getElementById('statTrain').textContent = stats.total_train;
        document.getElementById('statHardware').textContent = stats.total_hardware;
        document.getElementById('statDataSize').textContent = stats.data_size_mb + ' MB';

        // 分类分布
        const catHtml = Object.entries(stats.categories)
          .map(([k, v]) => `<span class="badge badge-info" style="margin:4px;font-size:0.85rem">${k}: ${v}</span>`)
          .join('');
        document.getElementById('categoryChart').innerHTML = catHtml || '<span class="empty-state">暂无数据</span>';

        // 来源分布
        const srcHtml = Object.entries(stats.sources)
          .map(([k, v]) => `<span class="badge badge-success" style="margin:4px;font-size:0.85rem">${k}: ${v}</span>`)
          .join('');
        document.getElementById('sourceChart').innerHTML = srcHtml || '<span class="empty-state">暂无数据</span>';
      } catch (e) {
        showToast('加载统计数据失败', 'error');
      }
    }

    // ============ 模型管理 ============
    async function searchModels() {
      const search = document.getElementById('modelSearch').value;
      const source = document.getElementById('sourceFilter').value;
      const category = document.getElementById('categoryFilter2').value;

      try {
        const res = await fetch(`/api/models?search=${encodeURIComponent(search)}&source=${source}&category=${category}&page=${currentPage}&page_size=50`);
        const data = await res.json();

        const tbody = document.getElementById('modelTableBody');
        tbody.innerHTML = data.models.map(m => `
          <tr>
            <td><input type="checkbox" class="model-checkbox" value="${m.id}" onchange="updateSelected()"></td>
            <td><strong>${m.name}</strong><br><span style="font-size:0.75rem;color:var(--text-secondary)">${m.id}</span></td>
            <td>${m.developer}</td>
            <td><span class="badge badge-info">${m.category}</span></td>
            <td><span class="badge ${m.supportLevel === '✅ 已支持' ? 'badge-success' : m.supportLevel === '🔵 实验性' ? 'badge-warning' : 'badge-danger'}">${m.supportLevel}</span></td>
            <td><span class="badge badge-info">${m.source}</span></td>
            <td style="font-size:0.75rem">${m.minHardware}</td>
            <td>
              <button class="btn btn-primary btn-sm" onclick="editModel('${m.id}')">✏️</button>
              <button class="btn btn-danger btn-sm" onclick="deleteModel('${m.id}')">🗑️</button>
            </td>
          </tr>
        `).join('');

        // 分页
        const pagination = document.getElementById('modelPagination');
        pagination.innerHTML = `
          <button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="changePage(${currentPage - 1})" ${currentPage <= 1 ? 'disabled' : ''}>上一页</button>
          <span>第 ${data.page}/${data.total_pages} 页 · 共 ${data.total} 条</span>
          <button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="changePage(${currentPage + 1})" ${currentPage >= data.total_pages ? 'disabled' : ''}>下一页</button>
        `;

        // 更新筛选器选项
        updateFilters(data);
      } catch (e) {
        showToast('加载模型列表失败', 'error');
      }
    }

    function changePage(page) {
      currentPage = page;
      searchModels();
    }

    async function updateFilters(data) {
      // 只在首次加载时更新筛选器选项
      const sourceSelect = document.getElementById('sourceFilter');
      if (sourceSelect.options.length <= 1) {
        const sources = [...new Set(data.models.map(m => m.source))];
        sources.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s; opt.textContent = s;
          sourceSelect.appendChild(opt);
        });
      }
      const catSelect = document.getElementById('categoryFilter2');
      if (catSelect.options.length <= 1) {
        const cats = [...new Set(data.models.map(m => m.category))];
        cats.forEach(c => {
          const opt = document.createElement('option');
          opt.value = c; opt.textContent = c;
          catSelect.appendChild(opt);
        });
      }
    }

    function toggleSelectAll() {
      const checked = document.getElementById('selectAll').checked;
      document.querySelectorAll('.model-checkbox').forEach(cb => cb.checked = checked);
      updateSelected();
    }

    function updateSelected() {
      selectedIds = new Set();
      document.querySelectorAll('.model-checkbox:checked').forEach(cb => selectedIds.add(cb.value));
    }

    async function batchDelete() {
      if (selectedIds.size === 0) {
        showToast('请先选择要删除的模型', 'error');
        return;
      }
      if (!confirm(`确定删除选中的 ${selectedIds.size} 个模型？`)) return;

      try {
        const res = await fetch('/api/models/batch', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({action: 'delete', ids: [...selectedIds]})
        });
        const data = await res.json();
        showToast(`已删除 ${data.deleted} 个模型，剩余 ${data.remaining} 个`, 'success');
        searchModels();
        refreshStats();
      } catch (e) {
        showToast('批量删除失败', 'error');
      }
    }

    async function exportSelected() {
      if (selectedIds.size === 0) {
        showToast('请先选择要导出的模型', 'error');
        return;
      }
      try {
        const res = await fetch('/api/models/batch', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({action: 'export', ids: [...selectedIds]})
        });
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data.models, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `exported_models_${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showToast(`已导出 ${data.count} 个模型`, 'success');
      } catch (e) {
        showToast('导出失败', 'error');
      }
    }

    async function editModel(id) {
      try {
        const res = await fetch(`/api/models/${id}`);
        const data = await res.json();
        const m = data.model;
        editingModelId = id;

        const fields = ['name', 'developer', 'category', 'supportLevel', 'framework',
          'minHardware', 'recommendedHardware', 'architecture', 'parameters',
          'inferencePerf', 'trainingPerf', 'mindsporeSupport', 'cannVersion', 'notes'];

        document.getElementById('editForm').innerHTML = fields.map(f => `
          <div class="form-group">
            <label>${f}</label>
            <input type="text" id="edit_${f}" value="${(m[f] || '').replace(/"/g, '&quot;')}">
          </div>
        `).join('');

        document.getElementById('editModal').classList.add('active');
      } catch (e) {
        showToast('加载模型详情失败', 'error');
      }
    }

    async function saveModel() {
      if (!editingModelId) return;
      const data = {};
      document.querySelectorAll('#editForm input').forEach(input => {
        data[input.id.replace('edit_', '')] = input.value;
      });

      try {
        const res = await fetch(`/api/models/${editingModelId}`, {
          method: 'PUT',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(data)
        });
        if (res.ok) {
          showToast('模型已更新', 'success');
          closeEditModal();
          searchModels();
        } else {
          showToast('更新失败', 'error');
        }
      } catch (e) {
        showToast('更新失败', 'error');
      }
    }

    function closeEditModal() {
      document.getElementById('editModal').classList.remove('active');
      editingModelId = null;
    }

    async function deleteModel(id) {
      if (!confirm(`确定删除模型 ${id}？`)) return;
      try {
        const res = await fetch(`/api/models/${id}`, {method: 'DELETE'});
        if (res.ok) {
          showToast('模型已删除', 'success');
          searchModels();
          refreshStats();
        }
      } catch (e) {
        showToast('删除失败', 'error');
      }
    }

    // ============ 爬虫控制 ============
    async function refreshCrawlerStatus() {
      try {
        const res = await fetch('/api/crawler/status');
        const status = await res.json();
        const el = document.getElementById('crawlerStatus');
        const textEl = document.getElementById('crawlerStatusText');

        if (status.running) {
          el.className = 'crawler-status running';
          el.querySelector('.status-dot').className = 'status-dot running';
          textEl.textContent = '爬虫运行中...';
          document.getElementById('runCrawlerBtn').disabled = true;
        } else {
          el.className = 'crawler-status idle';
          el.querySelector('.status-dot').className = 'status-dot idle';
          textEl.textContent = status.last_status === 'failed' ? '上次运行失败' : (status.last_run ? `上次运行: ${status.last_run} · 状态: ${status.last_status}` : '就绪');
          document.getElementById('runCrawlerBtn').disabled = false;
        }

        if (status.progress) {
          document.getElementById('crawlerProgress').textContent = status.progress;
        }
      } catch (e) {
        showToast('获取爬虫状态失败', 'error');
      }
    }

    async function runCrawler() {
      try {
        const res = await fetch('/api/crawler/run', {method: 'POST'});
        const data = await res.json();
        if (data.success) {
          showToast('爬虫已启动', 'success');
          refreshCrawlerStatus();
          // 轮询状态
          const interval = setInterval(async () => {
            await refreshCrawlerStatus();
            const statusRes = await fetch('/api/crawler/status');
            const status = await statusRes.json();
            if (!status.running) {
              clearInterval(interval);
              showToast('爬虫执行完成', 'success');
              refreshStats();
            }
          }, 3000);
        } else {
          showToast(data.error, 'error');
        }
      } catch (e) {
        showToast('启动爬虫失败', 'error');
      }
    }

    // ============ 数据备份 ============
    async function createBackup() {
      try {
        const res = await fetch('/api/data/backup', {method: 'POST'});
        const data = await res.json();
        if (data.success) {
          showToast(`备份已创建: ${data.files.length} 个文件`, 'success');
          listBackups();
        }
      } catch (e) {
        showToast('创建备份失败', 'error');
      }
    }

    async function listBackups() {
      try {
        const res = await fetch('/api/data/backups');
        const data = await res.json();
        const list = document.getElementById('backupList');

        if (data.backups.length === 0) {
          list.innerHTML = '<div class="empty-state">暂无备份数据</div>';
          return;
        }

        list.innerHTML = data.backups.map(b => `
          <div class="backup-item">
            <div>
              <div class="name">${b.name}</div>
              <div class="meta">${b.size_kb} KB · ${b.modified}</div>
            </div>
            <button class="btn btn-primary btn-sm" onclick="restoreBackup('${b.name}')">🔄 恢复</button>
          </div>
        `).join('');
      } catch (e) {
        showToast('加载备份列表失败', 'error');
      }
    }

    async function restoreBackup(filename) {
      if (!confirm(`确定从 ${filename} 恢复数据？当前数据将被覆盖！`)) return;
      try {
        const res = await fetch('/api/data/restore', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({filename})
        });
        const data = await res.json();
        if (data.success) {
          showToast(`已恢复: ${data.restored}`, 'success');
          refreshStats();
        }
      } catch (e) {
        showToast('恢复失败', 'error');
      }
    }

    // ============ 数据来源 ============
    async function loadSourceStats() {
      try {
        const res = await fetch('/api/sources');
        const sources = await res.json();
        const container = document.getElementById('sourceStats');

        container.innerHTML = Object.entries(sources).map(([name, stats]) => `
          <div style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px">
            <h4 style="margin-bottom:8px">${name}</h4>
            <div style="display:flex;gap:16px;font-size:0.85rem">
              <span>总数: <strong>${stats.count}</strong></span>
              <span style="color:var(--success)">✅ 已支持: ${stats.supported}</span>
              <span style="color:var(--warning)">🔵 实验性: ${stats.experimental}</span>
            </div>
          </div>
        `).join('');
      } catch (e) {
        showToast('加载来源统计失败', 'error');
      }
    }

    // ============ 初始化 ============
    refreshStats();
    refreshCrawlerStatus();
    setInterval(refreshCrawlerStatus, 10000);
  </script>
</body>
</html>
"""


# ============ 启动 ============
if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"Admin 后端服务启动于 http://localhost:{port}")
    print(f"Admin 页面: http://localhost:{port}/")
    app.run(host='0.0.0.0', port=port, debug=False)
