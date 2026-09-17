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
import time
import hmac
import base64
import hashlib
import shutil
import subprocess
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, Response

# ============ 配置 ============
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
SCRIPTS_DIR = BASE_DIR / 'scripts'

# 需纳入备份的 JSON 数据文件清单（手动备份与每日定时备份共用，避免两份清单不同步）
BACKUP_FILES = [
    'models.json', 'models-lite.json', 'models-detail.json',
    'train-models.json', 'hardware.json', 'nv-hardware.json', 'crawl-status.json',
    'acl-pytorch-models.json', 'pytorch-models.json', 'mindie-models.json',
    'global-models.json', 'benchmarks.json', 'model-params.json',
    'gpu_lib.json', 'performance.json', 'users.json',
]

# 注意：不要用 static_url_path='' 把整个项目根目录挂载为静态目录，
# 否则 Flask 内置静态路由 /<path> 会优先于 static_files 白名单，
# 导致 server.py 源码、data/*.json 数据/凭据、日志等被匿名直接下载。
# 静态资源统一由下方 static_files 路由（含扩展名/目录白名单）处理。
app = Flask(__name__)

# 爬虫运行状态（含实时过程日志，跨进程持久化到 data/crawler-status.json）
CRAWLER_STATUS_FILE = DATA_DIR / 'crawler-status.json'

# Admin 后台写操作鉴权：设置环境变量 ADMIN_TOKEN 后，所有 /admin/api/* 的
# POST/PUT/DELETE 请求必须携带匹配的 X-Admin-Token 请求头，否则返回 401。
# 未配置时保持向后兼容（放行），并在启动时打印安全提示。
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', '').strip()


@app.before_request
def _admin_api_auth():
    """保护 Admin 后台的写操作，防止匿名篡改数据/执行爬虫/恢复备份。

    仅对 /admin/api/* 的写方法校验；GET 等只读接口保持开放（首页数据需公开展示）。
    配置了 ADMIN_TOKEN 才启用校验，未配置则放行。
    """
    if not ADMIN_TOKEN:
        return None
    if request.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
        return None
    if not request.path.startswith('/admin/api/'):
        return None
    # 只读接口豁免：普通用户功能页（模型性能查询、AI使能服务报价器）里
    # 以 POST 承载的只读计算接口，无需管理员令牌
    READONLY_POST = {
        '/admin/api/performance/llm-advice',              # AI 选型建议（只读解读）
        '/admin/api/performance/recommend-by-requirement', # 按需求智能选型（只读推荐）
        '/admin/api/quote/generate',                      # 报价器生成报价（只读计算）
    }
    if request.path.rstrip('/') in READONLY_POST:
        return None
    supplied = request.headers.get('X-Admin-Token', '')
    if supplied != ADMIN_TOKEN:
        return jsonify({'error': '未授权：管理员令牌无效或缺失'}), 401
    return None


# ============ 用户认证与权限体系 ============
# 数据模型：data/users.json 存用户（密码仅存 PBKDF2 哈希，绝不存明文）。
# 角色为累积式等级：viewer(1) < member(2) < editor(3) < admin(4)，
# 更高角色拥有更低角色的全部权限。注册默认 viewer（仅可见大模型），
# 由 admin 后台升级到 member 后可见硬件/报价/性能等敏感数据。
from werkzeug.security import generate_password_hash, check_password_hash

USERS_FILE = DATA_DIR / 'users.json'
AUTH_SECRET = os.environ.get('AUTH_SECRET', '').strip() or 'jiuwenswarm-default-auth-secret'
AUTH_TOKEN_TTL = 12 * 3600  # token 有效期 12 小时

# 角色等级映射（数值越大权限越高）
ROLE_LEVEL = {'viewer': 1, 'member': 2, 'editor': 3, 'admin': 4}
# 认证接口自身的路径，不参与权限拦截
AUTH_PUBLIC_PATHS = (
    '/api/auth/login', '/api/auth/register', '/api/auth/me', '/api/auth/logout',
    '/api/auth/change-password',
)

# 敏感数据接口前缀：仅 member(2) 及以上角色可访问（viewer 只能看大模型）。
# 覆盖硬件、报价、性能、评测基准、模型参数等内部价值数据。
SENSITIVE_API_PREFIXES = (
    '/admin/api/homepage/hardware', '/admin/api/homepage/nv-hardware',
    '/admin/api/hardware-params', '/admin/api/quote/', '/admin/api/benchmarks',
    '/admin/api/performance/', '/admin/api/model-params', '/api/calc/hw',
    '/admin/api/homepage/nv',
)
# 数据维护写操作：所有 /admin/api/* 的 POST/PUT/DELETE/PATCH 默认需 editor(3)+。
# 只读计算接口（READONLY_POST_PATHS）除外；admin 专属接口由 ADMIN_ONLY 优先判定。
EDITOR_WRITE_PREFIXES = ('/admin/api/',)
# 需 admin(4) 才能执行的接口前缀（爬虫/备份恢复/用户管理）
ADMIN_ONLY_PREFIXES = (
    '/admin/api/crawler/', '/admin/api/data/backup', '/admin/api/data/restore',
    '/admin/api/data/backups', '/admin/api/admin/users',
)

# 以 POST 承载的只读计算接口（无数据写副作用），不要求编辑角色，member 即可用
READONLY_POST_PATHS = {
    '/admin/api/quote/generate',                # 报价器生成报价（只读计算）
    '/admin/api/quote/parse-requirement',       # 需求解析（只读计算）
    '/admin/api/performance/llm-advice',        # AI 选型建议（只读解读）
    '/admin/api/performance/recommend-by-requirement',  # 按需求智能选型（只读推荐）
    '/api/presales-extract', '/api/presales-recommend',
}


def load_users():
    data = load_json(USERS_FILE) or {}
    return data.get('users', [])


def save_users(users):
    save_json(USERS_FILE, {'users': users})


def find_user(username=None, uid=None):
    users = load_users()
    if username is not None:
        return next((u for u in users if u.get('username') == username), None)
    return next((u for u in users if u.get('id') == uid), None)


def _b64e(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _b64d(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def make_token(user):
    """签发 HS256 风格 JWT（自签，不依赖第三方库）。"""
    header = _b64e(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
    payload = _b64e(json.dumps({
        'uid': user['id'], 'username': user['username'], 'role': user['role'],
        'exp': int(time.time()) + AUTH_TOKEN_TTL,
    }).encode())
    signing = f'{header}.{payload}'.encode()
    sig = hmac.new(AUTH_SECRET.encode(), signing, hashlib.sha256).digest()
    return f'{header}.{payload}.{_b64e(sig)}'


def verify_token(token):
    """校验并解析 token，成功返回用户 dict，失败返回 None。"""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        expected = hmac.new(AUTH_SECRET.encode(), f'{header}.{payload}'.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(sig), expected):
            return None
        data = json.loads(_b64d(payload))
        if data.get('exp', 0) < time.time():
            return None
        user = find_user(uid=data.get('uid'))
        if not user or user.get('status') != 'active':
            return None
        # 以库中最新角色为准，避免 token 里角色过期后仍沿用旧权限
        data['role'] = user['role']
        return data
    except Exception:
        return None


def current_user():
    """从请求头 Authorization: Bearer <token> 解析当前用户，未登录返回 None。"""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    return verify_token(auth[len('Bearer '):].strip())


def role_level(role):
    return ROLE_LEVEL.get(role, 0)


@app.before_request
def _auth_permission_gate():
    """统一权限拦截：所有 /api/auth/* 之外的接口按需校验登录角色。

    - /api/auth/* 认证接口本身始终开放（除 me/change-password 需登录）；
    - 敏感数据接口要求 member(2)+；
    - 数据维护写操作要求 editor(3)+；
    - 爬虫/备份/用户管理要求 admin(4)+。
    未登录访问受保护接口返回 401，角色不足返回 403。
    """
    path = request.path.rstrip('/')
    # 认证接口自身放行（其中需登录的接口在各自函数内校验）
    if path.startswith('/api/auth/'):
        return None

    # 判定所需最低角色
    need = None
    if any(path.startswith(p) for p in SENSITIVE_API_PREFIXES):
        need = 'member'
    if any(path.startswith(p) for p in ADMIN_ONLY_PREFIXES):
        need = 'admin'
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        # 只读计算接口（以 POST 承载的计算/推荐，无数据写副作用）不视为编辑写操作
        if path.rstrip('/') not in READONLY_POST_PATHS:
            if any(path.startswith(p) for p in EDITOR_WRITE_PREFIXES):
                need = max(need or 'member', 'editor', key=role_level) or 'editor'
    if need is None:
        return None

    user = current_user()
    if user is None:
        return jsonify({'error': '未登录或登录已过期，请先登录'}), 401
    if role_level(user.get('role')) < role_level(need):
        return jsonify({'error': f'权限不足：需要 {need} 及以上角色'}), 403
    return None


# ============ 用户认证 API ============

@app.route('/api/auth/register', methods=['POST'])
def api_auth_register():
    """自助注册。默认角色 viewer（仅可见大模型），需 admin 升级后才可见硬件等敏感数据。"""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    email = (data.get('email') or '').strip()

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if not re.fullmatch(r'[A-Za-z0-9_\-]{3,32}', username):
        return jsonify({'error': '用户名需为 3-32 位字母、数字、下划线或中划线'}), 400
    if len(password) < 6:
        return jsonify({'error': '密码长度不能少于 6 位'}), 400
    if find_user(username=username):
        return jsonify({'error': '用户名已存在'}), 409

    users = load_users()
    user = {
        'id': f"u_{int(time.time())}_{len(users) + 1}",
        'username': username,
        'password_hash': generate_password_hash(password),
        'email': email,
        'role': 'viewer',
        'status': 'active',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'last_login': None,
    }
    users.append(user)
    save_users(users)
    return jsonify({'success': True, 'message': '注册成功，默认权限为查看大模型；如需查看硬件等数据请联系管理员升级权限',
                    'user': {'id': user['id'], 'username': username, 'role': user['role']}}), 201


@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    """登录，返回 token 与用户信息。"""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    user = find_user(username=username)
    if not user or not check_password_hash(user.get('password_hash', ''), password):
        return jsonify({'error': '用户名或密码错误'}), 401
    if user.get('status') != 'active':
        return jsonify({'error': '账号已被禁用，请联系管理员'}), 403

    users = load_users()
    for u in users:
        if u.get('id') == user['id']:
            u['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_users(users)

    token = make_token(user)
    return jsonify({'success': True, 'token': token, 'user': {
        'id': user['id'], 'username': user['username'], 'role': user['role'],
    }})


@app.route('/api/auth/me', methods=['GET'])
def api_auth_me():
    """获取当前登录用户信息（用于前端恢复会话）。"""
    user = current_user()
    if not user:
        return jsonify({'error': '未登录'}), 401
    return jsonify({'user': {
        'id': user['uid'], 'username': user['username'], 'role': user['role'],
    }})


@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    """登出。无状态 JWT 无法服务端强制失效，此处由前端清除本地 token 即可。"""
    return jsonify({'success': True})


@app.route('/api/auth/change-password', methods=['POST'])
def api_auth_change_password():
    """修改密码（需登录）。"""
    user = current_user()
    if not user:
        return jsonify({'error': '未登录'}), 401
    data = request.json or {}
    old_pw = data.get('old_password') or ''
    new_pw = data.get('new_password') or ''
    if len(new_pw) < 6:
        return jsonify({'error': '新密码长度不能少于 6 位'}), 400
    users = load_users()
    for u in users:
        if u.get('id') == user['uid']:
            if not check_password_hash(u.get('password_hash', ''), old_pw):
                return jsonify({'error': '原密码错误'}), 400
            u['password_hash'] = generate_password_hash(new_pw)
            save_users(users)
            return jsonify({'success': True, 'message': '密码修改成功'})
    return jsonify({'error': '用户不存在'}), 404


# ============ 用户管理 API（admin）============

@app.route('/admin/api/admin/users', methods=['GET'])
def api_admin_users_list():
    """用户列表（admin）。"""
    users = load_users()
    return jsonify({'users': [{
        'id': u['id'], 'username': u['username'], 'email': u.get('email', ''),
        'role': u['role'], 'status': u.get('status', 'active'),
        'created_at': u.get('created_at', ''), 'last_login': u.get('last_login', ''),
    } for u in users]})


@app.route('/admin/api/admin/users', methods=['POST'])
def api_admin_user_create():
    """创建用户（admin），可指定角色。"""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    role = data.get('role') or 'viewer'
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if role not in ROLE_LEVEL:
        return jsonify({'error': '无效的角色'}), 400
    if find_user(username=username):
        return jsonify({'error': '用户名已存在'}), 409
    users = load_users()
    user = {
        'id': f"u_{int(time.time())}_{len(users) + 1}",
        'username': username,
        'password_hash': generate_password_hash(password),
        'email': (data.get('email') or '').strip(),
        'role': role,
        'status': 'active',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'last_login': None,
    }
    users.append(user)
    save_users(users)
    return jsonify({'success': True, 'user': user}), 201


@app.route('/admin/api/admin/users/<user_id>', methods=['PUT'])
def api_admin_user_update(user_id):
    """更新用户角色/状态/重置密码（admin）。"""
    data = request.json or {}
    users = load_users()
    for u in users:
        if u.get('id') == user_id:
            if 'role' in data:
                if data['role'] not in ROLE_LEVEL:
                    return jsonify({'error': '无效的角色'}), 400
                u['role'] = data['role']
            if 'status' in data:
                if data['status'] == '__toggle':
                    u['status'] = 'disabled' if u.get('status') == 'active' else 'active'
                else:
                    u['status'] = 'active' if data['status'] == 'active' else 'disabled'
            if data.get('password'):
                if len(data['password']) < 6:
                    return jsonify({'error': '密码长度不能少于 6 位'}), 400
                u['password_hash'] = generate_password_hash(data['password'])
            save_users(users)
            return jsonify({'success': True, 'user': u})
    return jsonify({'error': '用户不存在'}), 404


@app.route('/admin/api/admin/users/<user_id>', methods=['DELETE'])
def api_admin_user_delete(user_id):
    """删除用户（admin）。"""
    users = load_users()
    new_users = [u for u in users if u.get('id') != user_id]
    if len(new_users) == len(users):
        return jsonify({'error': '用户不存在'}), 404
    save_users(new_users)
    return jsonify({'success': True})


crawler_status = {
    'running': False,
    'last_run': None,
    'last_status': None,
    'progress': '',
    'pid': None,
    'log': [],
    'history': []
}

# 保护 crawler_status 的跨线程读写：execute_crawler 后台线程写日志，
# /admin/api/crawler/status 请求线程读，需加锁避免 list 并发修改。
# 使用可重入锁：append_log 持锁时内部还会调用 _save_crawler_status（同样加锁）。
CRAWLER_LOCK = threading.RLock()


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
        with CRAWLER_LOCK:
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


# ============ JSON 文件 mtime 缓存 ============
# 高频只读数据文件（models-lite/hardware 等）在多个 API 中被反复读取，
# 每次全量解析开销较大。这里按文件 mtime 做进程内缓存：文件未变化时直接复用，
# 避免重复读盘与 json 解析。save_json 是唯一的 JSON 写入入口，写后自动失效。
_JSON_CACHE = {}
_JSON_CACHE_LOCK = threading.Lock()


def load_json_cached(filepath):
    """加载 JSON 文件，带 mtime 缓存（仅用于高频只读数据文件）。

    文件不存在/解析失败时返回 None，与 load_json 行为一致。
    """
    try:
        mtime = os.path.getmtime(filepath)
    except OSError:
        return None
    with _JSON_CACHE_LOCK:
        hit = _JSON_CACHE.get(str(filepath))
        if hit and hit[0] == mtime:
            return hit[1]
    data = load_json(filepath)
    with _JSON_CACHE_LOCK:
        _JSON_CACHE[str(filepath)] = (mtime, data)
    return data


def _invalidate_json_cache(filepath):
    """使某个 JSON 文件（或路径前缀）的缓存失效。

    用于 save_json 之外的写路径（如备份恢复直接用 shutil 覆盖文件）。
    """
    key = str(filepath)
    with _JSON_CACHE_LOCK:
        if key in _JSON_CACHE:
            _JSON_CACHE.pop(key, None)


def save_json(filepath, data):
    """保存 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _invalidate_json_cache(filepath)


def get_data_size_mb():
    """计算 data 目录下所有文件的总大小（MB）"""
    total_bytes = sum(
        os.path.getsize(DATA_DIR / f) for f in os.listdir(DATA_DIR)
        if os.path.isfile(DATA_DIR / f)
    )
    return round(total_bytes / 1024 / 1024, 2)


def get_data_stats():
    """获取数据统计信息"""
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    detail = load_json_cached(DATA_DIR / 'models-detail.json') or []
    train = load_json_cached(DATA_DIR / 'train-models.json') or {}
    hardware = load_json_cached(DATA_DIR / 'hardware.json') or []
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


def _parse_int(request, key, default, min_val=None, max_val=None):
    """安全解析整型请求参数。

    非法值（非数字/越界）回退到 default，可选夹取到 [min_val, max_val]，
    避免 ?page=abc 之类的畸形参数直接抛 ValueError 导致 500。
    """
    try:
        val = int(request.args.get(key, default))
    except (TypeError, ValueError):
        val = default
    if min_val is not None:
        val = max(min_val, val)
    if max_val is not None:
        val = min(max_val, val)
    return val


def get_all_sources():
    """获取所有数据来源"""
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    return sorted(list(set(m.get('source', '未知') for m in models)))


def get_all_categories():
    """获取所有分类"""
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    return sorted(list(set(m.get('category', '其他') for m in models)))


# ============ 静态文件路由 ============

@app.route('/')
def index():
    return send_from_directory(str(BASE_DIR), 'index.html')


# ============ Admin 路由 ============

def _no_cache(resp):
    """禁止浏览器缓存静态资源，确保改版后强制拉取最新 js/css。"""
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/admin')
@app.route('/admin/')
def admin_index():
    return send_from_directory(str(BASE_DIR / 'admin'), 'index.html')


@app.route('/admin/css/<path:filename>')
def admin_css(filename):
    resp = send_from_directory(str(BASE_DIR / 'admin' / 'css'), filename)
    _no_cache(resp)
    return resp


@app.route('/admin/js/<path:filename>')
def admin_js(filename):
    resp = send_from_directory(str(BASE_DIR / 'admin' / 'js'), filename)
    _no_cache(resp)
    return resp


@app.route('/admin/api/stats')
def api_stats():
    return jsonify(get_data_stats())


@app.route('/admin/api/models')
def api_models():
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    search = request.args.get('search', '')
    source = request.args.get('source', '')
    category = request.args.get('category', '')
    page = _parse_int(request, 'page', 1)
    page_size = _parse_int(request, 'page_size', 50)

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
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    detail = load_json_cached(DATA_DIR / 'models-detail.json') or []
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
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    for i, m in enumerate(models):
        if m.get('id') == model_id:
            models[i].update(data)
            save_json(DATA_DIR / 'models-lite.json', models)
            return jsonify({'success': True, 'model': models[i]})
    return jsonify({'error': '模型不存在'}), 404


@app.route('/admin/api/models/<model_id>', methods=['DELETE'])
def api_model_delete(model_id):
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    new_models = [m for m in models if m.get('id') != model_id]
    if len(new_models) == len(models):
        return jsonify({'error': '模型不存在'}), 404
    save_json(DATA_DIR / 'models-lite.json', new_models)
    full_models = load_json_cached(DATA_DIR / 'models.json') or []
    full_models = [m for m in full_models if m.get('id') != model_id]
    save_json(DATA_DIR / 'models.json', full_models)
    return jsonify({'success': True, 'deleted': model_id})


@app.route('/admin/api/models/batch', methods=['POST'])
def api_models_batch():
    action = request.json.get('action')
    ids = request.json.get('ids', [])
    if not ids:
        return jsonify({'error': '请选择模型'}), 400
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    if action == 'delete':
        new_models = [m for m in models if m.get('id') not in ids]
        save_json(DATA_DIR / 'models-lite.json', new_models)
        full_models = load_json_cached(DATA_DIR / 'models.json') or []
        full_models = [m for m in full_models if m.get('id') not in ids]
        save_json(DATA_DIR / 'models.json', full_models)
        return jsonify({'success': True, 'deleted': len(ids), 'remaining': len(new_models)})
    elif action == 'export':
        selected = [m for m in models if m.get('id') in ids]
        return jsonify({'success': True, 'models': selected, 'count': len(selected)})
    return jsonify({'error': '未知操作'}), 400


@app.route('/admin/api/crawler/status')
def api_crawler_status():
    # 在锁内取快照，避免序列化过程中后台线程仍在 append 日志导致并发修改
    with CRAWLER_LOCK:
        snapshot = {
            'running': crawler_status['running'],
            'last_run': crawler_status['last_run'],
            'last_status': crawler_status['last_status'],
            'progress': crawler_status['progress'],
            'pid': crawler_status['pid'],
            'log': list(crawler_status['log']),
            'history': list(crawler_status['history']),
        }
    return jsonify(snapshot)


def execute_crawler():
    """后台执行爬虫子进程，实时更新 crawler_status（含过程日志）。
    供手动触发（/admin/api/crawler/run）与定时爬取任务共用。"""
    crawler_status['running'] = True
    crawler_status['last_run'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    crawler_status['last_status'] = None
    crawler_status['log'] = []
    crawler_status['progress'] = '正在启动爬虫...'
    _save_crawler_status()

    def append_log(line):
        line = line.rstrip('\n')
        if not line:
            return
        with CRAWLER_LOCK:
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


@app.route('/admin/api/crawler/run', methods=['POST'])
def api_crawler_run():
    if crawler_status['running']:
        return jsonify({'error': '爬虫正在运行中'}), 400

    thread = threading.Thread(target=execute_crawler, daemon=True)
    thread.start()
    return jsonify({'success': True, 'message': '爬虫已启动'})


@app.route('/admin/api/data/backup', methods=['POST'])
def api_data_backup():
    backup_dir = DATA_DIR / 'backups'
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_info = []
    for f in BACKUP_FILES:
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
    # restore 直接用 shutil 覆盖目标文件，不走 save_json，需手动使缓存失效
    _invalidate_json_cache(target_path)
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
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    hardware = load_json_cached(DATA_DIR / 'hardware.json') or []
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
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    search = request.args.get('search', '').lower()
    category = request.args.get('category', '')
    tag = request.args.get('tag', '')
    support = request.args.get('support', '')
    hardware = request.args.get('hardware', '')
    sort = request.args.get('sort', 'default')
    page = _parse_int(request, 'page', 1)
    page_size = _parse_int(request, 'page_size', 50)

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
    data = load_json_cached(DATA_DIR / 'global-models.json') or {}
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
    page = _parse_int(request, 'page', 1)
    page_size = _parse_int(request, 'page_size', 24)

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


@app.route('/admin/api/global-models/<model_id>', methods=['GET', 'PUT'])
def api_global_model_update(model_id):
    """Admin：读取/保存编辑后的全球AI大模型数据"""
    if request.method == 'GET':
        payload = load_json_cached(DATA_DIR / 'global-models.json') or {}
        for m in payload.get('models', []):
            if str(m.get('model_id')) == str(model_id):
                return jsonify({'model': m})
        return jsonify({'error': '模型不存在'}), 404
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    payload = load_json_cached(DATA_DIR / 'global-models.json') or {}
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
        limit = _parse_int(request, 'limit', 30)
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

    # 上游 DataLearner 页面结构可能改版，精细改写（toolbar 注入、按钮/链接删除）
    # 用 try/except 兜底：任一环节异常时降级为"保留原始 <main> 主体"，避免整页 500。
    try:
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
    except Exception:
        # 解析失败时保持 main_html 为原始 <main> 主体，仍能正常展示
        pass

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
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    detail = load_json_cached(DATA_DIR / 'models-detail.json') or []
    m = next((x for x in models if x.get('id') == model_id), None)
    d = next((x for x in detail if x.get('id') == model_id), None)
    if not m:
        return jsonify({'error': '模型不存在'}), 404
    return jsonify({'model': m, 'detail': d})


@app.route('/admin/api/homepage/hardware')
def api_homepage_hardware():
    """首页硬件数据"""
    hardware = load_json_cached(DATA_DIR / 'hardware.json') or []
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
    hardware = load_json_cached(DATA_DIR / 'nv-hardware.json') or []
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
    page = _parse_int(request, 'page', 1)
    page_size = _parse_int(request, 'page_size', 50)

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


# ============ 统一计算 API（复用 Skill 计算引擎，单一口径） ============
# 计算逻辑统一由 skills/ 下的 Python 引擎承担，避免与前端 JS / 编排 Skill 多处重复实现漂移。
SKILLS_DIR = BASE_DIR / 'skills'


def _load_calc_engine(rel_module):
    """动态加载 Skill 计算引擎模块（路径含目录名，用 importlib 避免目录包约束）。"""
    import importlib.util
    path = SKILLS_DIR / rel_module
    spec = importlib.util.spec_from_file_location('_calc_engine', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@app.route('/api/calc/token')
def api_calc_token():
    """LLM Token 计算：复用 llm-token-calculator 引擎，口径与页面 recalc() 一致。

    参数：gpu, model, gpu_count, quant, kv_prec, prompt_len, gen_len,
          efficiency, tp_coef, seq
    """
    gpu = request.args.get('gpu', '')
    model = request.args.get('model', '')
    if not gpu or not model:
        return jsonify({'error': '缺少 gpu 或 model 参数'}), 400
    try:
        eng = _load_calc_engine('llm-token-calculator/token_calc.py')
        gpu_lib = eng.load_gpu_lib(str(BASE_DIR))
        model_lib = eng.load_model_lib(str(BASE_DIR))
    except Exception as e:  # noqa: BLE001
        return jsonify({'error': '计算引擎加载失败: %s' % e}), 500

    def f(name, default=None):
        v = request.args.get(name)
        if v is None or v == '':
            return default
        try:
            return float(v)
        except ValueError:
            return default

    if gpu not in gpu_lib:
        return jsonify({'error': 'GPU 型号不存在: %s' % gpu}), 404
    m = model_lib.get(model)
    if m is None:
        low = model.lower()
        m = next((v for k, v in model_lib.items()
                  if k.lower() == low or v['modelCode'].lower() == low), None)
        if m is None:
            return jsonify({'error': '模型不存在: %s' % model}), 404

    params = {
        'gpu_name': gpu, 'model_name': m['name'],
        'gpu_count': int(f('gpu_count', 8) or 8),
        'bandwidth': gpu_lib[gpu]['bw'], 'fp16': gpu_lib[gpu]['fp16'],
        'vram': gpu_lib[gpu]['vram'],
        'quant_prec': request.args.get('quant', 'INT8'),
        'kv_prec': request.args.get('kv_prec', 'FP16'),
        'prompt_len': f('prompt_len', 512), 'gen_len': f('gen_len', 128000),
        'efficiency': f('efficiency', 0.65), 'tp_coef': f('tp_coef', 0.92),
        'seq': f('seq', 8192),
        'model': m,
    }
    try:
        r = eng.calc(params)
        # 不同量化精度对比（与页面「不同量化精度对比」表口径一致）
        active = m['active']
        vram = gpu_lib[gpu]['vram']
        bw = gpu_lib[gpu]['bw']
        eff = f('efficiency', 0.65)
        quant_compare = []
        for p in ('FP32', 'FP16', 'INT8', 'INT4', 'INT2'):
            b = eng.QUANT_BYTES[p]
            w = active * b
            t = bw / w if w > 0 else 0
            quant_compare.append({
                'precision': p, 'bytes': b, 'weight_gb': w,
                'theo_decode_toks': t, 'actual_decode_toks': t * eff,
                'enough_single_gpu': w <= vram,
            })
    except Exception as e:  # noqa: BLE001
        return jsonify({'error': '计算失败: %s' % e}), 400
    return jsonify({'gpu': gpu_lib[gpu], 'model': m, 'result': r, 'quant_compare': quant_compare})


@app.route('/api/calc/hw')
def api_calc_hw():
    """GPU 硬件对比/选型：复用 gpu-hardware-compare 引擎，口径与 hw_estimate() 一致。

    参数：model, precision, in_len, out_len, qps, mode(compare/recommend/all), gpus(逗号分隔)
    """
    model = request.args.get('model', '')
    if not model:
        return jsonify({'error': '缺少 model 参数'}), 400
    try:
        eng = _load_calc_engine('gpu-hardware-compare/hw_compare.py')
        model_lib = eng.load_model_lib(str(BASE_DIR))
    except Exception as e:  # noqa: BLE001
        return jsonify({'error': '计算引擎加载失败: %s' % e}), 500

    m = eng.resolve_model(model_lib, model)
    if m is None:
        return jsonify({'error': '模型不存在: %s' % model}), 404

    def f(name, default):
        v = request.args.get(name)
        if v is None or v == '':
            return default
        try:
            return float(v)
        except ValueError:
            return default

    precision = request.args.get('precision', 'fp16').lower()
    in_len = f('in_len', 512)
    out_len = f('out_len', 512)
    qps = f('qps', 1.0)
    mode = request.args.get('mode', 'all')
    gpus = None
    if request.args.get('gpus'):
        gpus = [g.strip() for g in request.args.get('gpus').split(',') if g.strip()]

    report = {'model': {k: m[k] for k in ('name', 'modelCode', 'total', 'active', 'layers',
                                          'kvHeads', 'headDim', 'ctx', 'arch', 'moe')}}
    try:
        if mode in ('compare', 'all'):
            report['compare'] = eng.gpu_compare(m, precision, in_len, out_len, gpus, str(BASE_DIR))
        if mode in ('recommend', 'all'):
            report['recommend'] = eng.recommend_cards(m, precision, in_len, out_len, qps, str(BASE_DIR))
    except Exception as e:  # noqa: BLE001
        return jsonify({'error': '计算失败: %s' % e}), 400
    return jsonify(report)


# ---------- HF（hf-mirror）架构字段补全 ----------
HF_MIRROR_BASE = 'https://hf-mirror.com'

# 统一外部请求 UA（避免在多处重复硬编码，且便于统一伪装为浏览器）
_HTTP_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
# 外部站点（hf-mirror / datalearner / LLM 网关）偶发超时/抖动，做有限次重试
_HTTP_RETRIES = 2
_HTTP_BACKOFF = 0.8


def _http_get(url, timeout=20):
    """GET 抓取外部页面文本，带有限次重试（应对外部站点偶发超时/抖动）。"""
    req = urllib.request.Request(url, headers={'User-Agent': _HTTP_UA})
    last_exc = None
    for attempt in range(_HTTP_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', errors='replace')
        except Exception as e:  # noqa: BLE001 - 网络层统一重试
            last_exc = e
            if attempt < _HTTP_RETRIES:
                threading.Event().wait(_HTTP_BACKOFF * (attempt + 1))
    raise last_exc


def _http_post_json(url, payload, timeout=120, headers=None, retries=0):
    """POST JSON 并返回解析后的响应体（OpenAI 兼容接口统一调用入口）。

    payload 为 dict，自动序列化并携带 UA；headers 可附加（如 Authorization）。
    """
    hdrs = {'User-Agent': _HTTP_UA, 'Content-Type': 'application/json'}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers=hdrs,
        method='POST',
    )
    last_exc = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if attempt < retries:
                threading.Event().wait(_HTTP_BACKOFF * (attempt + 1))
    raise last_exc


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


# ============ 从 global-models.json 全量对齐 model-params.json ============
# 数据来源调整：模型名称/清单来自 DataLearner 抓取的 global-models.json，
# 架构字段（层数/KV头数/头维度/上下文/是否MoE）从 HF config.json/tokenizer_config.json 补全。
# 策略：全量对齐 —— 以 global-models.json 为准重建 model-params.json，
#       已存在的条目保留其架构字段（优先已有值，其次 HF 补全）。
GLOBAL_MODELS_FILE = DATA_DIR / 'global-models.json'


def _search_hf_repo(query):
    """用模型名在 hf-mirror 搜索 API 匹配仓库，返回最可能的 repo id（org/name）或 None。"""
    try:
        raw = _http_get(f'{HF_MIRROR_BASE}/api/models?search={urllib.parse.quote(query)}&limit=5', timeout=20)
        arr = json.loads(raw)
    except Exception:
        return None
    if not isinstance(arr, list) or not arr:
        return None
    for m in arr:
        rid = (m.get('id') or '').strip()
        # 优先与查询名精确匹配（忽略大小写与 -/_ 差异）
        if rid and rid.split('/')[-1].lower().replace('_', '-') == query.lower().replace('_', '-'):
            return rid
    return (arr[0].get('id') or '').strip() or None


def _resolve_hf_repo(global_model, existing):
    """解析一个模型的 HF repo id。优先级：已有 hfRepo → DataLearner 详情页提取 → hf-mirror 搜索。"""
    if existing and existing.get('hfRepo'):
        return existing['hfRepo']
    code = global_model.get('model_code')
    # 1) DataLearner 详情页提取 HF 链接
    if code:
        try:
            detail_html = _http_get(f'{DATALEARNER_DETAIL_BASE}/{code}', timeout=20)
            repo = _extract_hf_link(detail_html)
            if repo:
                return repo
        except Exception:
            pass
    # 2) hf-mirror 按模型名搜索兜底
    abbr = (global_model.get('model_abbr_name') or '').strip()
    if abbr:
        repo = _search_hf_repo(abbr)
        if repo:
            return repo
    return None


def _sync_model_params_from_global(fetch_hf=False, hf_errors=None):
    """按 global-models.json 全量对齐 model-params.json。

    返回 (items, summary)。items 为重建后的完整列表；summary 记录新增/更新/删除统计。
    fetch_hf=True 时对缺失架构字段的模型从 HF config.json 补全（较慢）。
    """
    gm = load_json(GLOBAL_MODELS_FILE) or {}
    gm_models = gm.get('models', []) or []
    old_items = load_model_params() or []
    old_by_code = {str(m.get('modelCode')): m for m in old_items if m.get('modelCode')}

    new_items = []
    added, updated, kept = 0, 0, 0
    for g in gm_models:
        code = (g.get('model_code') or '').strip()
        if not code:
            continue
        old = old_by_code.get(code)
        # 名称/参数量来自 global-models；架构字段优先保留已有，缺失时后续补
        item = {
            'modelCode': code,
            'name': (g.get('model_abbr_name') or code).strip(),
            'totalParams': g.get('totalParamsB'),
            'activeParams': g.get('activeParamsB'),
        }
        if old:
            # 保留已有架构字段与 hfRepo（避免重复抓取 / 丢失人工整理结果）
            for k in ('layers', 'attentionHeads', 'kvHeads', 'headDim', 'context',
                      'architecture', 'isMoE', 'hfRepo'):
                if old.get(k) is not None:
                    item[k] = old[k]
        # 缺架构字段时，若开启 fetch_hf 则从 HF 补全
        if fetch_hf and (item.get('layers') is None or item.get('context') is None):
            repo = item.get('hfRepo') or _resolve_hf_repo(g, old)
            if repo:
                try:
                    fields = _fetch_hf_config(repo)
                    for k, v in fields.items():
                        if k in ('layers', 'attentionHeads', 'kvHeads', 'headDim',
                                 'context', 'architecture', 'isMoE'):
                            if item.get(k) is None:
                                item[k] = v
                    item['hfRepo'] = repo
                except Exception as e:  # noqa: BLE001 - 单模型补全失败不阻断整体
                    if hf_errors is not None:
                        hf_errors.append({'code': code, 'error': str(e)})
        # 统计
        if old is None:
            added += 1
        elif item != old:
            updated += 1
        else:
            kept += 1
        new_items.append(item)

    removed = [c for c in old_by_code if c not in {m['modelCode'] for m in new_items}]
    summary = {
        'added': added,
        'updated': updated,
        'kept': kept,
        'removed': removed,
        'total_new': len(new_items),
        'total_old': len(old_items),
    }
    return new_items, summary


@app.route('/admin/api/model-params/sync', methods=['POST'])
def api_model_params_sync():
    """从 global-models.json 全量对齐 model-params.json。

    请求体可选 {"fetch_hf": true}：对齐后对缺失架构字段的模型从 HF config.json 补全。
    写前自动备份到 data/backups/。
    """
    data = request.json or {}
    fetch_hf = bool(data.get('fetch_hf'))
    hf_errors = []

    try:
        items, summary = _sync_model_params_from_global(fetch_hf=fetch_hf, hf_errors=hf_errors)
    except Exception as e:  # noqa: BLE001
        return jsonify({'error': f'同步失败: {e}'}), 500

    # 写前备份
    try:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        bak_dir = DATA_DIR / 'backups'
        bak_dir.mkdir(exist_ok=True)
        shutil.copy(MODEL_PARAMS_FILE, bak_dir / f'model-params-backup-{ts}.json')
    except Exception:
        pass  # 备份失败不阻断同步

    save_model_params(items)
    return jsonify({
        'success': True,
        'fetch_hf': fetch_hf,
        'summary': summary,
        'hf_errors': hf_errors[:20],  # 仅返回前 20 条错误，避免响应过大
        'hf_error_count': len(hf_errors),
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
    train = load_json_cached(DATA_DIR / 'train-models.json') or {}
    train_models = train.get('models', [])
    search = request.args.get('search', '').lower()
    framework = request.args.get('framework', '')
    category = request.args.get('category', '')
    status = request.args.get('status', '')
    page = _parse_int(request, 'page', 1)
    page_size = _parse_int(request, 'page_size', 30)

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


# ============ 训练模型管理（后台 CRUD）============

def _load_train_file():
    """读取训练模型清单文件，返回顶层 dict 与 models 列表。"""
    train = load_json(MODEL_TRAIN_FILE) or {}
    if not isinstance(train, dict):
        train = {'models': train if isinstance(train, list) else []}
    train.setdefault('models', [])
    return train


def _save_train_file(train):
    """保存训练模型清单文件，并同步 total 计数。"""
    train['total'] = len(train.get('models', []))
    save_json(MODEL_TRAIN_FILE, train)


@app.route('/admin/api/train-models')
def api_train_models():
    """后台训练模型列表（支持搜索/筛选/分页）。"""
    train = _load_train_file()
    models = train.get('models', [])
    search = request.args.get('search', '').lower()
    framework = request.args.get('framework', '')
    category = request.args.get('category', '')
    status = request.args.get('status', '')
    page = _parse_int(request, 'page', 1)
    page_size = _parse_int(request, 'page_size', 50)

    filtered = models
    if search:
        filtered = [m for m in filtered if search in m.get('name', '').lower()
                    or search in m.get('framework', '').lower()
                    or search in m.get('task', '').lower()]
    if framework and framework != 'all':
        filtered = [m for m in filtered if m.get('framework') == framework]
    if category and category != 'all':
        filtered = [m for m in filtered if m.get('category') == category]
    if status and status != 'all':
        filtered = [m for m in filtered if m.get('status') == status]

    page_items, total, total_pages = paginate(filtered, page, page_size)
    page_items = [enrich_train_model(m) for m in page_items]

    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'models': page_items,
        'frameworks': sorted(list(set(m.get('framework', '') for m in models if m.get('framework')))),
        'categories': sorted(list(set(m.get('category', '') for m in models if m.get('category')))),
        'statuses': sorted(list(set(m.get('status', '') for m in models if m.get('status')))),
    })


@app.route('/admin/api/train-models', methods=['POST'])
def api_train_models_add():
    """新增训练模型。"""
    data = request.json or {}
    name = str(data.get('name', '')).strip()
    if not name:
        return jsonify({'error': '模型名称不能为空'}), 400
    train = _load_train_file()
    models = train.get('models', [])
    if any(m.get('name', '').strip().lower() == name.lower() for m in models):
        return jsonify({'error': '模型已存在：' + name}), 400
    fields = ('name', 'params', 'task', 'cluster', 'precision', 'framework', 'status', 'category', 'desc', 'source')
    model = {k: data.get(k) for k in fields if data.get(k) is not None and data.get(k) != ''}
    models.append(model)
    _save_train_file(train)
    return jsonify({'success': True, 'model': model})


@app.route('/admin/api/train-models/<name>', methods=['GET', 'PUT'])
def api_train_models_update(name):
    """读取/更新训练模型（按 name 定位）。"""
    if request.method == 'GET':
        train = _load_train_file()
        for m in train.get('models', []):
            if m.get('name', '') == name:
                return jsonify({'model': m})
        return jsonify({'error': '模型不存在：' + name}), 404
    data = request.json or {}
    train = _load_train_file()
    models = train.get('models', [])
    for m in models:
        if m.get('name', '') == name:
            fields = ('name', 'params', 'task', 'cluster', 'precision', 'framework', 'status', 'category', 'desc', 'source')
            for k in fields:
                if k in data:
                    m[k] = data[k]
            _save_train_file(train)
            return jsonify({'success': True, 'model': m})
    return jsonify({'error': '模型不存在：' + name}), 404


@app.route('/admin/api/train-models/<name>', methods=['DELETE'])
def api_train_models_delete(name):
    """删除训练模型（按 name 定位）。"""
    train = _load_train_file()
    models = train.get('models', [])
    new_models = [m for m in models if m.get('name', '') != name]
    if len(new_models) == len(models):
        return jsonify({'error': '模型不存在：' + name}), 404
    train['models'] = new_models
    _save_train_file(train)
    return jsonify({'success': True, 'deleted': name})


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
    models = load_json_cached(DATA_DIR / 'models-lite.json') or []
    train = load_json_cached(DATA_DIR / 'train-models.json') or {}
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
    acl_models = load_json_cached(DATA_DIR / 'acl-pytorch-models.json') or []
    pytorch_models = load_json_cached(DATA_DIR / 'pytorch-models.json') or []

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
    page = _parse_int(request, 'page', 1)
    page_size = _parse_int(request, 'page_size', 50)

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
    mindie_models = load_json_cached(DATA_DIR / 'mindie-models.json') or []

    search = request.args.get('search', '').lower()
    category = request.args.get('category', '')
    source = request.args.get('source', '')
    data_dir = request.args.get('data_dir', '')
    page = _parse_int(request, 'page', 1)
    page_size = _parse_int(request, 'page_size', 50)

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
    data = load_json_cached(DATA_DIR / 'benchmarks.json') or {}
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
    page = _parse_int(request, 'page', 1)
    page_size = _parse_int(request, 'page_size', 24)

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


@app.route('/admin/api/benchmarks/<benchmark_id>', methods=['GET', 'PUT'])
def api_benchmark_update(benchmark_id):
    """Admin：读取/保存编辑后的评测基准数据"""
    if request.method == 'GET':
        payload = load_json_cached(DATA_DIR / 'benchmarks.json') or {}
        for b in payload.get('benchmarks', []):
            if str(b.get('id')) == str(benchmark_id):
                return jsonify({'benchmark': b})
        return jsonify({'error': '评测基准不存在'}), 404
    data = request.json
    if not data:
        return jsonify({'error': '无效数据'}), 400
    payload = load_json_cached(DATA_DIR / 'benchmarks.json') or {}
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
    backed_up = []
    for f in BACKUP_FILES:
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


def run_daily_crawler():
    """定时线程：每天 24:00（午夜 0 点）自动执行模型爬取任务"""
    while True:
        now = datetime.now()
        # 计算到下一次 24:00（即次日 00:00）的秒数
        target = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        threading.Event().wait(wait_seconds)
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 定时爬取开始（每天 24:00）...")
            # 若上一次爬虫仍在运行则跳过本次，避免并发冲突
            if crawler_status['running']:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 定时爬取跳过：爬虫仍在运行中")
                continue
            execute_crawler()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 定时爬取结束（状态: {crawler_status['last_status']}）")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y%m%d_%H%M%S')}] ⏰ 定时爬取失败: {e}")


# ============ AI使能服务报价器 ============

QUOTE_CONFIG_FILE = DATA_DIR / 'quote_config.json'
QUOTE_HISTORY_FILE = DATA_DIR / 'quote_history.json'

# 服务目录（与 js/quote-data.js 保持一致，作为后端报价金额的权威来源）
# 默认内置目录；可通过后台管理页持久化到 data/quote_services.json 后增删改。
QUOTE_SERVICES_FILE = DATA_DIR / 'quote_services.json'

QUOTE_CATEGORIES = [
    {'id': 1, 'name': 'AI赋能'},
    {'id': 2, 'name': 'AI基础开发与运行环境搭建'},
    {'id': 3, 'name': '模型安装'},
    {'id': 4, 'name': '应用搭建'},
    {'id': 5, 'name': '硬件集群组网'},
    {'id': 6, 'name': '维护升级'},
]

_DEFAULT_QUOTE_SERVICES = [
    {'code': '45SC0109', 'name': '开发与运行环境部署赋能', 'days': 2, 'category': 1},
    {'code': '45SC0110', 'name': '集群环境搭建部署赋能', 'days': 2, 'category': 1},
    {'code': '45SC0111', 'name': '开发工具赋能', 'days': 2, 'category': 1},
    {'code': '45SC0133', 'name': '模型迁移/部署赋能', 'days': 2, 'category': 1},
    {'code': '45SC0134', 'name': '本地化知识库/工作流赋能', 'days': 2, 'category': 1},
    {'code': '45SC0112', 'name': '安装部署评估与方案设计（必选）', 'days': 2, 'category': 2},
    {'code': '45SC0113', 'name': '运行开发环境搭建', 'days': 1, 'category': 2},
    {'code': '45SC0114', 'name': '推理容器镜像', 'days': 2, 'category': 2},
    {'code': '45SC0115', 'name': '模型部署评估与方案设计（必选）', 'days': 2, 'category': 3},
    {'code': '42SC0118', 'name': '模型增量包（1人天/实例）', 'days': 1, 'category': 3},
    {'code': '42SC0119', 'name': 'DeepSeek集群部署（8人天）', 'days': 8, 'category': 3},
    {'code': '45SC0135', 'name': '常规大模型部署', 'days': 5, 'category': 3},
    {'code': '42SC0120', 'name': '专项调优（单次15人天）', 'days': 15, 'category': 3},
    {'code': '45SC0136', 'name': 'RAG模型部署', 'days': 3, 'category': 3},
    {'code': '42SC0121', 'name': '模型迁移评估与方案设计（必选-单次）', 'days': 5, 'category': 3},
    {'code': '42SC0122', 'name': '模型迁移(单个)', 'days': 10, 'category': 3},
    {'code': '45SC0137', 'name': '简易前端界面', 'days': 2, 'category': 4},
    {'code': '45SC0138', 'name': 'RAG服务', 'days': 3, 'category': 4},
    {'code': '45SC0139', 'name': '知识库/工作流demo构建', 'days': 2, 'category': 4},
    {'code': '45SC0120', 'name': '集群环境搭建方案设计', 'days': 3, 'category': 5},
    {'code': '45SC0121', 'name': '双机组网', 'days': 2, 'category': 5},
    {'code': '45SC0122', 'name': '多机跨交换机组网', 'days': 5, 'category': 5},
    {'code': '45SC0123', 'name': '集群验证', 'days': 5, 'category': 5},
    {'code': '45SC0124', 'name': '根据部署模型进行升级服务', 'days': 20, 'category': 6},
]


def load_quote_services():
    """读取服务目录；文件不存在或损坏时回退到内置默认目录。"""
    data = load_json(QUOTE_SERVICES_FILE)
    if isinstance(data, list) and data:
        return data
    return [dict(s) for s in _DEFAULT_QUOTE_SERVICES]


def get_quote_service_by_code():
    return {s['code']: s for s in load_quote_services()}

# ============ 昇腾模型适配清单（技术方案选型用）============
# 检索优先级：① 昇腾适配清单 → ② MindIE → ③ 大模型训练清单 → ④ 小模型清单
MODEL_ADAPT_FILE = DATA_DIR / 'models.json'
MODEL_ADAPT_DETAIL_FILE = DATA_DIR / 'models-detail.json'
MODEL_MINDIE_FILE = DATA_DIR / 'mindie-models.json'
MODEL_TRAIN_FILE = DATA_DIR / 'train-models.json'
MODEL_SMALL_ACL_FILE = DATA_DIR / 'acl-pytorch-models.json'
MODEL_SMALL_PT_FILE = DATA_DIR / 'pytorch-models.json'


def _load_model_list(path, key=None):
    """读取模型清单文件，统一返回列表。"""
    data = load_json(path)
    if not data:
        return []
    if isinstance(data, dict):
        if key and isinstance(data.get(key), list):
            return data[key]
        for v in data.values():
            if isinstance(v, list):
                return v
        return []
    return data if isinstance(data, list) else []


def _model_name(m):
    """取模型记录的名称字段（不同清单字段名不同）。"""
    for k in ('name', 'model_abbr_name', 'model_name'):
        if m.get(k):
            return str(m[k])
    return ''


def _find_model(name):
    """按优先级查找模型：适配清单 → MindIE → 训练清单 → 小模型清单。

    返回 {source, model, matched} 或 None（未找到）。
    """
    if not name:
        return None
    target = str(name).strip().lower()

    def _search(items, source):
        for m in items:
            if _model_name(m).strip().lower() == target:
                return {'source': source, 'model': m, 'matched': _model_name(m)}
        return None

    # ① 昇腾适配清单（主源，models.json / models-detail.json）
    for f in (MODEL_ADAPT_FILE, MODEL_ADAPT_DETAIL_FILE):
        r = _search(_load_model_list(f), '昇腾适配清单')
        if r:
            return r
    # ② MindIE
    r = _search(_load_model_list(MODEL_MINDIE_FILE), 'MindIE')
    if r:
        return r
    # ③ 大模型训练清单
    r = _search(_load_model_list(MODEL_TRAIN_FILE, 'models'), '大模型训练清单')
    if r:
        return r
    # ④ 小模型清单（ACL + PyTorch）
    for f in (MODEL_SMALL_ACL_FILE, MODEL_SMALL_PT_FILE):
        r = _search(_load_model_list(f), '小模型清单')
        if r:
            return r
    return None


def load_quote_config():
    """读取报价器 LLM 连接配置。

    支持用环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 覆盖配置文件，
    便于将凭据放在环境而非落盘到 data/ 目录（data/ 已被静态路由屏蔽，此处为纵深防御）。
    """
    cfg = load_json(QUOTE_CONFIG_FILE)
    if not cfg or not isinstance(cfg, dict):
        cfg = {'llm': {'base_url': '', 'api_key': '', 'model': ''}, 'price_per_day': 6000, 'enabled': True}
    cfg.setdefault('price_per_day', 6000)
    cfg.setdefault('enabled', True)
    cfg.setdefault('llm', {})
    llm = cfg['llm']
    for env_key, cfg_key in (('LLM_BASE_URL', 'base_url'),
                             ('LLM_API_KEY', 'api_key'),
                             ('LLM_MODEL', 'model')):
        val = os.environ.get(env_key, '').strip()
        if val:
            llm[cfg_key] = val
    return cfg


def save_quote_config(cfg):
    """保存报价器 LLM 连接配置。"""
    save_json(QUOTE_CONFIG_FILE, cfg)


def load_quote_history():
    """读取历史报价列表。"""
    hist = load_json(QUOTE_HISTORY_FILE)
    return hist if isinstance(hist, list) else []


def _call_llm_for_quote(requirement, cfg):
    """调用本地大模型（OpenAI 兼容接口），返回推荐的报价 JSON 字符串。

    复用 _call_llm_json 的统一调用逻辑，仅在此构造报价专属的 system/user 提示词。
    """
    catalog_lines = []
    for s in load_quote_services():
        catalog_lines.append(f"[{s['code']}] {s['name']}（{s['days']}人天）")

    system_prompt = (
        '你是昇腾AI使能服务的售前技术方案与报价专家。根据客户需求，先给出技术方案，再推荐服务项。\n'
        '只输出一个 JSON 对象，不要输出其他任何文字。JSON 格式：\n'
        '{"plan": "技术方案正文（markdown，含：需求分析/总体架构/模型选型与理由/部署与实施步骤/服务项说明，各章节用 ## 标题）", '
        '"model": "方案选用的模型名称（若需求明确指定则用指定名称，否则从客户描述中推断）", '
        '"codes": ["服务编码1", "服务编码2"], "summary": "一句话报价方案说明"}\n'
        '要求：\n'
        '1. plan 用 markdown 撰写，条理清晰、面向售前客户。\n'
        '2. model 尽量填写具体的模型名（如 DeepSeek-R1、Qwen2.5-72B），不要编造；不确定可留空。\n'
        '3. codes 只能包含下方目录中存在且与需求相关的服务编码。\n'
        '4. 若需求涉及模型部署/环境搭建，应包含对应的"必选"评估方案项。\n'
        '5. 不要编造目录中不存在的服务或编码。\n'
        '服务目录：\n' + '\n'.join(catalog_lines)
    )
    return _call_llm_json(system_prompt, f'客户需求：{requirement}', cfg)


def _extract_json_object(content):
    """从文本中提取第一个完整 JSON 对象（字符串感知的括号配对）。

    跳过字符串值内部的 {}，避免 markdown 方案中的花括号干扰配对。
    """
    if not content:
        return None
    start = content.find('{')
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(content)):
        ch = content[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(content[start:i + 1])
                except Exception:
                    return None
    return None


def _build_quote_from_codes(codes, price_per_day):
    """根据服务编码列表，从权威目录计算报价明细与合计。"""
    service_by_code = get_quote_service_by_code()
    items = []
    for code in codes:
        svc = service_by_code.get(code)
        if not svc:
            continue
        amount = svc['days'] * price_per_day
        items.append({
            'code': svc['code'],
            'name': svc['name'],
            'days': svc['days'],
            'price_per_day': price_per_day,
            'amount': amount,
        })
    total_days = sum(it['days'] for it in items)
    total_amount = sum(it['amount'] for it in items)
    return items, total_days, total_amount


def _cn_upper_amount(num):
    """将金额转为人民币大写（分后截断）。"""
    units = ['', '拾', '佰', '仟', '万', '拾', '佰', '仟', '亿', '拾', '佰', '仟', '万亿', '拾', '佰', '仟']
    nums = '零壹贰叁肆伍陆柒捌玖'
    num = int(round(num))
    if num == 0:
        return '零元整'
    result = ''
    # 处理亿/万
    yi = num // 100000000
    wan = (num % 100000000) // 10000
    ge = num % 10000
    parts = []
    for i, val in enumerate([yi, wan, ge]):
        if val:
            s = _cn_four_digits(val, nums)
            if i == 0:
                s += '亿'
            elif i == 1:
                s += '万'
            parts.append(s)
    return ''.join(parts) + '元整'


def _cn_four_digits(val, nums):
    """把 0-9999 转成中文数字（不含单位后缀）。"""
    units = ['', '拾', '佰', '仟']
    if val == 0:
        return '零'
    s = ''
    zero = False
    pos = 3
    while pos >= 0:
        d = (val // (10 ** pos)) % 10
        if d == 0:
            zero = True
        else:
            if zero and s:
                s += '零'
            zero = False
            s += nums[d] + units[pos]
        pos -= 1
    return s


@app.route('/admin/api/quote/config', methods=['GET', 'POST'])
def api_quote_config():
    """读取/保存报价器 LLM 配置。"""
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        cfg = load_quote_config()
        if 'llm' in data and isinstance(data['llm'], dict):
            cfg['llm'].update({k: v for k, v in data['llm'].items() if v is not None})
        if 'price_per_day' in data:
            try:
                cfg['price_per_day'] = int(data['price_per_day'])
            except (TypeError, ValueError):
                pass
        if 'enabled' in data:
            cfg['enabled'] = bool(data['enabled'])
        save_quote_config(cfg)
        return jsonify(_mask_api_key(cfg))
    cfg = load_quote_config()
    return jsonify(_mask_api_key(cfg))


def _mask_api_key(cfg):
    """对返回给前端的配置掩码 api_key，避免明文凭据泄露（前端不使用该字段）。"""
    if isinstance(cfg, dict):
        llm = cfg.get('llm')
        if isinstance(llm, dict) and llm.get('api_key'):
            llm['api_key'] = '***'
    return cfg


@app.route('/admin/api/quote/catalog')
def api_quote_catalog():
    """返回服务目录（供前端展示/勾选，金额以后端计算为准）。"""
    cfg = load_quote_config()
    return jsonify({
        'services': load_quote_services(),
        'price_per_day': cfg.get('price_per_day', 6000),
        'categories': QUOTE_CATEGORIES,
    })


# ============ 使能服务目录管理（后台）============
def _save_quote_services(services):
    save_json(QUOTE_SERVICES_FILE, services)


@app.route('/admin/api/quote/services')
def api_quote_services_list():
    """后台：获取使能服务目录列表。"""
    return jsonify({
        'services': load_quote_services(),
        'categories': QUOTE_CATEGORIES,
    })


@app.route('/admin/api/quote/services', methods=['POST'])
def api_quote_services_create():
    """后台：新增使能服务。"""
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return jsonify({'error': '服务编码与服务名不能为空'}), 400
    try:
        days = int(data.get('days', 1))
    except (TypeError, ValueError):
        days = 1
    category = int(data.get('category', 1) or 1)
    services = load_quote_services()
    if any(s['code'] == code for s in services):
        return jsonify({'error': f'服务编码 {code} 已存在'}), 409
    service = {'code': code, 'name': name, 'days': days, 'category': category}
    services.append(service)
    _save_quote_services(services)
    return jsonify({'success': True, 'service': service})


@app.route('/admin/api/quote/services/<code>', methods=['GET', 'PUT'])
def api_quote_services_update(code):
    """后台：读取/修改使能服务。"""
    if request.method == 'GET':
        services = load_quote_services()
        for s in services:
            if s.get('code') == code:
                return jsonify({'service': s})
        return jsonify({'error': f'未找到服务 {code}'}), 404
    data = request.get_json(silent=True) or {}
    services = load_quote_services()
    for s in services:
        if s['code'] == code:
            if 'name' in data and data['name'] is not None:
                s['name'] = str(data['name']).strip()
            if 'days' in data:
                try:
                    s['days'] = int(data['days'])
                except (TypeError, ValueError):
                    pass
            if 'category' in data:
                try:
                    s['category'] = int(data['category'])
                except (TypeError, ValueError):
                    pass
            _save_quote_services(services)
            return jsonify({'success': True, 'service': s})
    return jsonify({'error': f'未找到服务 {code}'}), 404


@app.route('/admin/api/quote/services/<code>', methods=['DELETE'])
def api_quote_services_delete(code):
    """后台：删除使能服务。"""
    services = load_quote_services()
    new_services = [s for s in services if s['code'] != code]
    if len(new_services) == len(services):
        return jsonify({'error': f'未找到服务 {code}'}), 404
    _save_quote_services(new_services)
    return jsonify({'success': True})


@app.route('/admin/api/quote/generate', methods=['POST'])
def api_quote_generate():
    """根据客户需求调用 LLM 推荐服务项，并计算报价。"""
    data = request.get_json(silent=True) or {}
    requirement = (data.get('requirement') or '').strip()
    if not requirement:
        return jsonify({'error': '客户需求不能为空'}), 400

    cfg = load_quote_config()
    if not cfg.get('enabled', True):
        return jsonify({'error': '报价器已停用'}), 400

    try:
        result = _call_llm_for_quote(requirement, cfg)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'调用大模型失败: {e}'}), 502

    codes = result.get('codes') or []
    items, total_days, total_amount = _build_quote_from_codes(codes, cfg.get('price_per_day', 6000))
    if not items:
        return jsonify({'error': 'LLM 未能匹配到合适的服务项，请调整需求描述后重试'}), 422

    # 方案选型模型检索（按 适配清单→MindIE→训练→小模型 优先级）
    model_name = (result.get('model') or '').strip()
    model_found = _find_model(model_name) if model_name else None

    return jsonify({
        'plan': result.get('plan', ''),
        'summary': result.get('summary', ''),
        'model': {
            'name': model_name,
            'matched': (model_found or {}).get('matched', ''),
            'source': (model_found or {}).get('source', ''),
            'found': bool(model_found),
            'info': (model_found or {}).get('model') or None,
        } if model_name else None,
        'items': items,
        'total_days': total_days,
        'total_amount': total_amount,
        'total_amount_cn': _cn_upper_amount(total_amount),
        'price_per_day': cfg.get('price_per_day', 6000),
    })


@app.route('/admin/api/quote/history', methods=['GET', 'POST'])
def api_quote_history():
    """读取/保存历史报价。"""
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        if not data.get('requirement'):
            return jsonify({'error': '缺少需求信息'}), 400
        history = load_quote_history()
        record = {
            'id': f"Q{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'customer': data.get('customer', ''),
            'requirement': data.get('requirement', ''),
            'plan': data.get('plan', ''),
            'summary': data.get('summary', ''),
            'items': data.get('items', []),
            'total_days': data.get('total_days', 0),
            'total_amount': data.get('total_amount', 0),
            'total_amount_cn': data.get('total_amount_cn', ''),
            'price_per_day': data.get('price_per_day', 6000),
        }
        history.insert(0, record)
        # 最多保留 200 条
        save_json(QUOTE_HISTORY_FILE, history[:200])
        return jsonify(record)
    history = load_quote_history()
    # 后端分页 + 搜索，避免每次全量拉取后本地过滤
    search = (request.args.get('search') or '').strip().lower()
    if search:
        history = [h for h in history
                   if search in (h.get('customer') or '').lower()
                   or search in (h.get('requirement') or '').lower()]
    total = len(history)
    page = _parse_int(request, 'page', 1, 1)
    page_size = _parse_int(request, 'page_size', 50, 1, 500)
    start = (page - 1) * page_size
    items = history[start:start + page_size]
    return jsonify({'items': items, 'total': total, 'page': page, 'page_size': page_size,
                    'total_pages': max(1, -(-total // page_size))})


@app.route('/admin/api/quote/history/batch-delete', methods=['POST'])
def api_quote_history_batch_delete():
    """批量删除历史报价。"""
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'error': '缺少要删除的报价单 ID'}), 400
    id_set = set(str(i) for i in ids)
    history = load_quote_history()
    remaining = [h for h in history if h.get('id') not in id_set]
    deleted = len(history) - len(remaining)
    save_json(QUOTE_HISTORY_FILE, remaining)
    return jsonify({'ok': True, 'deleted': deleted})


@app.route('/admin/api/quote/history/<quote_id>', methods=['GET', 'DELETE'])
def api_quote_history_delete(quote_id):
    """读取/删除一条历史报价。"""
    history = load_quote_history()
    if request.method == 'GET':
        for h in history:
            if h.get('id') == quote_id:
                return jsonify({'record': h})
        return jsonify({'error': '报价单不存在'}), 404
    history = [h for h in history if h.get('id') != quote_id]
    save_json(QUOTE_HISTORY_FILE, history)
    return jsonify({'ok': True})


# ============ 需求文件解析（报价器导入） ============

SUPPORTED_REQ_EXTS = {'.txt', '.md', '.docx', '.doc', '.pdf', '.xlsx', '.xls', '.csv'}


def _extract_req_text(filepath, ext):
    """根据扩展名从需求文件中抽取纯文本，返回 (text, note)。"""
    ext = (ext or '').lower()
    if ext in ('.txt', '.md', '.csv'):
        # 文本类：兼容常见编码，优先 utf-8，回退 gbk
        for enc in ('utf-8', 'gbk', 'utf-16'):
            try:
                return filepath.read_text(encoding=enc), ''
            except (UnicodeDecodeError, UnicodeError):
                continue
        # 全部失败则用 errors=replace 兜底
        return filepath.read_text(encoding='utf-8', errors='replace'), '（部分字符无法识别，已替换）'

    if ext in ('.docx',):
        import docx
        doc = docx.Document(str(filepath))
        parts = []
        for p in doc.paragraphs:
            t = p.text.strip()
            if t:
                parts.append(t)
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(' | '.join(cells))
        return '\n'.join(parts), ''

    if ext in ('.doc',):
        # 旧版 .doc：先尝试 antiword/textract，失败则提示无法解析
        import subprocess
        for cmd in (['antiword', str(filepath)], ['textract', str(filepath)]):
            try:
                out = subprocess.run(cmd, capture_output=True, timeout=60, text=True)
                if out.returncode == 0 and out.stdout.strip():
                    return out.stdout, ''
            except Exception:
                continue
        raise ValueError('暂不支持旧版 .doc 格式，请转换为 .docx 后重试')

    if ext in ('.pdf',):
        import pdfplumber
        parts = []
        with pdfplumber.open(str(filepath)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ''
                if t.strip():
                    parts.append(t)
        return '\n'.join(parts), ''

    if ext in ('.xlsx', '.xls'):
        import openpyxl
        wb = openpyxl.load_workbook(str(filepath), read_only=True, data_only=True)
        parts = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if cells:
                    parts.append(' | '.join(cells))
        return '\n'.join(parts), ''

    raise ValueError(f'不支持的文件格式：{ext}')


def _summarize_requirement(raw_text, cfg):
    """用 LLM 对需求文件原文做需求摘取，提炼关键信息。

    返回 (summary_text, used_llm)。LLM 未配置或调用失败时回退返回原文。
    """
    if not cfg.get('enabled', True):
        return raw_text, False
    system_prompt = (
        '你是昇腾AI使能服务的售前需求分析师。用户会提供一份客户需求文件的原文，'
        '你需要从中摘取与「AI使能服务报价」相关的关键需求信息，剔除无关的冗余描述。\n'
        '只输出一个 JSON 对象，不要输出任何其他文字。JSON 格式：\n'
        '{"summary": "提炼后的客户需求摘要（一段连贯中文，按重要程度排列关键点：业务场景与目标、'
        '涉及的模型名称、算力规模（如卡数/集群/并发/QPS）、部署环境（昇腾/GPU/云）、'
        '配套需求（如RAG知识库、性能调优、运维维护、训练/推理等））。"}\n'
        '要求：\n'
        '1. 只保留与模型部署、算力、服务项相关的内容，忽略营销话术、公司介绍、签字盖章等无关内容。\n'
        '2. 若原文信息不足，仅描述已明确的内容，不要编造或补充。\n'
        '3. 摘要控制在 300 字以内，条理清晰。'
    )
    try:
        obj = _call_llm_json(system_prompt, f'需求文件原文：\n{raw_text}', cfg, temperature=0.2, max_tokens=1000)
        summary = (obj or {}).get('summary') or ''
        summary = summary.strip()
        if summary:
            return summary, True
    except Exception:
        pass
    return raw_text, False


@app.route('/admin/api/quote/parse-requirement', methods=['POST'])
def api_quote_parse_requirement():
    """上传需求文件，解析文本后调用 LLM 提炼关键需求，供报价器一键导入。

    支持 .txt / .md / .docx / .doc / .pdf / .xlsx / .xls / .csv。
    """
    if 'file' not in request.files:
        return jsonify({'error': '未选择文件'}), 400
    up = request.files['file']
    if not up or not up.filename:
        return jsonify({'error': '未选择文件'}), 400
    ext = Path(up.filename).suffix.lower()
    if ext not in SUPPORTED_REQ_EXTS:
        return jsonify({'error': f'不支持的文件格式：{ext or "未知"}，请上传 ' + ' / '.join(sorted(SUPPORTED_REQ_EXTS))}), 400

    # 限制上传大小（10MB）
    up.stream.seek(0, 2)
    size = up.stream.tell()
    up.stream.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({'error': '文件过大，请上传 10MB 以内的文件'}), 400

    tmp = DATA_DIR / ('_req_upload_' + up.filename)
    try:
        up.save(str(tmp))
        text, note = _extract_req_text(tmp, ext)
    except Exception as e:
        return jsonify({'error': f'文件解析失败：{e}'}), 400
    finally:
        if tmp.exists():
            tmp.unlink()

    text = (text or '').strip()
    if not text:
        return jsonify({'error': '未能从文件中提取到有效内容'}), 422

    # 截断过长原文，避免超出模型上下文
    max_len = 8000
    truncated = len(text) > max_len
    if truncated:
        text = text[:max_len] + '\n……（原文过长，已截断）'

    # 用 LLM 提炼关键需求；失败则回退返回原文
    cfg = load_quote_config()
    summary, used_llm = _summarize_requirement(text, cfg)
    return jsonify({
        'text': text,
        'summary': summary,
        'used_llm': used_llm,
        'filename': up.filename,
        'note': note,
        'truncated': truncated,
    })


# ============ 模型性能查询 ============

PERFORMANCE_FILE = DATA_DIR / 'performance.json'
# Excel 源数据目录（A 方式：本地路径导入）
PERF_SRC_DIR = BASE_DIR / 'data_preformce_data'
# 标准化后的性能记录字段（页面展示用）
PERF_METRIC_FIELDS = [
    'ttft_ms', 'ttft_p90', 'tpot_ms', 'tpot_p90', 'e2e_s',
    'output_tps', 'per_card_output_tps', 'e2e_tps', 'per_card_e2e_tps',
    'qps', 'qpm',
]

_perf_cache = {'mtime': None, 'data': None}


def load_performance(force=False):
    """读取性能数据（带 mtime 缓存）。文件不存在时返回空结构。"""
    mtime = PERFORMANCE_FILE.stat().st_mtime if PERFORMANCE_FILE.exists() else 0
    if _perf_cache['data'] is None or force or _perf_cache['mtime'] != mtime:
        data = load_json(PERFORMANCE_FILE)
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            data = {'source': '昇腾推理性能基线合集', 'updated_at': '', 'total': 0, 'items': []}
        _perf_cache['mtime'] = mtime
        _perf_cache['data'] = data
    return _perf_cache['data']


def save_performance(data):
    """保存性能数据并刷新缓存。"""
    save_json(PERFORMANCE_FILE, data)
    _perf_cache['mtime'] = PERFORMANCE_FILE.stat().st_mtime if PERFORMANCE_FILE.exists() else 0
    _perf_cache['data'] = data


def _perf_next_id(items):
    """生成下一个自增 id（perf-N）。"""
    mx = 0
    for it in items:
        m = re.search(r'(\d+)$', str(it.get('id', '')))
        if m:
            mx = max(mx, int(m.group(1)))
    return f'perf-{mx + 1}'


def _perf_clean_rec(rec):
    """清洗单条性能记录：只保留白名单字段、数值字段转 float/None。"""
    allowed = {'id', 'model', 'framework', 'product', 'scenario', 'hardware', 'topology',
               'total_cards', 'data_format', 'avg_input', 'avg_output', 'prefix_cache',
               'concurrency', 'max_concurrency', 'req_rate', 'version', 'parallel',
               'source_file', 'source_sheet', 'note',
               'avg_input_raw', 'avg_output_raw'}
    allowed |= set(PERF_METRIC_FIELDS)
    out = {}
    for k, v in (rec or {}).items():
        if k not in allowed:
            continue
        if k in PERF_METRIC_FIELDS or k in ('total_cards', 'avg_input', 'avg_output',
                                            'prefix_cache', 'concurrency', 'max_concurrency', 'req_rate'):
            try:
                out[k] = None if v in (None, '') else float(v)
            except (TypeError, ValueError):
                out[k] = None
        else:
            out[k] = None if v is None else str(v).strip()
    return out


@app.route('/admin/api/performance/sources')
def api_perf_sources():
    """后台：扫描本地 Excel 源目录，返回各文件的导入状态。"""
    sources = []
    if PERF_SRC_DIR.is_dir():
        for f in sorted(PERF_SRC_DIR.glob('*.xlsx')):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                size = f.stat().st_size
            except OSError:
                mtime, size = '', 0
            sources.append({
                'name': f.name,
                'path': str(f),
                'size': size,
                'mtime': mtime,
            })
    data = load_performance()
    # 统计每个源文件已导入的记录数
    count_by_file = {}
    for it in data.get('items', []):
        sf = it.get('source_file') or ''
        count_by_file[sf] = count_by_file.get(sf, 0) + 1
    for s in sources:
        s['imported'] = count_by_file.get(s['name'], 0)
    return jsonify({
        'sources': sources,
        'total': data.get('total', 0),
        'updated_at': data.get('updated_at', ''),
    })


@app.route('/admin/api/performance/import', methods=['POST'])
def api_perf_import():
    """导入性能数据。

    方式 A：request.json['path'] —— 本地 data_preformce_data 目录下的 xlsx 路径
    方式 B：multipart 上传文件字段 file —— 浏览器上传 xlsx
    """
    data = load_performance()
    items = data.get('items', [])

    # 方式 B：multipart 上传
    if 'file' in request.files:
        up = request.files['file']
        if not up or not up.filename:
            return jsonify({'error': '未选择文件'}), 400
        if not up.filename.lower().endswith('.xlsx'):
            return jsonify({'error': '仅支持 .xlsx 文件'}), 400
        tmp = DATA_DIR / ('_upload_' + up.filename)
        try:
            up.save(str(tmp))
            recs = _parse_perf_xlsx(str(tmp), up.filename)
        except Exception as e:
            return jsonify({'error': f'解析失败: {e}'}), 400
        finally:
            if tmp.exists():
                tmp.unlink()
        full = (request.form.get('mode') or '').strip().lower() == 'full'
        return _merge_perf_import(recs, up.filename, full=full)

    # 方式 A：本地路径导入
    body = request.get_json(silent=True) or {}
    path = (body.get('path') or '').strip()
    if not path:
        return jsonify({'error': '请提供本地文件路径（path）或上传文件'}), 400
    p = Path(path)
    # 允许绝对路径或相对项目根的 data_preformce_data/*.xlsx
    if not p.is_absolute():
        p = BASE_DIR / p
    if not p.exists() or not p.is_file():
        return jsonify({'error': f'文件不存在: {p}'}), 404
    if p.suffix.lower() != '.xlsx':
        return jsonify({'error': '仅支持 .xlsx 文件'}), 400
    try:
        recs = _parse_perf_xlsx(str(p), p.name)
    except Exception as e:
        return jsonify({'error': f'解析失败: {e}'}), 400
    full = (body.get('mode') or '').strip().lower() == 'full'
    return _merge_perf_import(recs, p.name, full=full)


def _parse_perf_xlsx(path, display_name):
    """调用解析脚本的核心函数，解析单个 xlsx 为标准化记录列表。"""
    # 复用 scripts/parse_performance.py 的解析逻辑（避免重复实现）
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'parse_performance_mod', str(BASE_DIR / 'scripts' / 'parse_performance.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse_file(Path(path))


def _merge_perf_import(recs, file_name, full=False):
    """合并导入记录到 performance.json（按关键字段去重）并返回统计。

    full=False：增量合并，已存在的记录跳过，只新增。
    full=True：全量重导，清空现有记录后用 recs 重建。
    """
    if not recs:
        return jsonify({'error': '未解析到有效数据记录'}), 422
    data = load_performance()
    items = [] if full else data.get('items', [])
    seen = set()
    for it in items:
        key = (str(it.get('model')), str(it.get('product')), str(it.get('scenario')),
               it.get('avg_input'), it.get('avg_output'), it.get('total_cards'),
               it.get('ttft_ms'), it.get('output_tps'),
               str(it.get('source_file')), str(it.get('source_sheet')))
        seen.add(key)
    added = 0
    for rec in recs:
        key = (rec['model'], rec['product'], rec['scenario'],
               rec['avg_input'], rec['avg_output'], rec.get('total_cards'),
               rec.get('ttft_ms'), rec.get('output_tps'),
               file_name, rec['source_sheet'])
        if key in seen:
            continue
        seen.add(key)
        rec['id'] = _perf_next_id(items)
        rec['source_file'] = file_name
        items.append(rec)
        added += 1
    data['items'] = items
    data['total'] = len(items)
    data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_performance(data)
    return jsonify({'success': True, 'added': added, 'total': len(items)})


@app.route('/admin/api/performance/items')
def api_perf_items():
    """后台：性能记录列表（支持搜索与分页）。"""
    data = load_performance()
    items = data.get('items', [])
    q = (request.args.get('q') or '').strip().lower()
    page = _parse_int(request, 'page', 1, min_val=1)
    page_size = _parse_int(request, 'page_size', 20, min_val=1, max_val=200)
    if q:
        items = [it for it in items if q in str(it.get('model', '')).lower()
                 or q in str(it.get('product', '')).lower()
                 or q in str(it.get('framework', '')).lower()]
    total = len(items)
    start = (page - 1) * page_size
    return jsonify({
        'items': items[start:start + page_size],
        'total': total,
        'page': page,
        'page_size': page_size,
    })


@app.route('/admin/api/performance/items', methods=['POST'])
def api_perf_item_create():
    """后台：新增单条性能记录。"""
    data = load_performance()
    items = data.get('items', [])
    rec = _perf_clean_rec(request.get_json(silent=True) or {})
    if not rec.get('model'):
        return jsonify({'error': '模型名称不能为空'}), 400
    rec['id'] = _perf_next_id(items)
    rec['source_file'] = rec.get('source_file') or '手动添加'
    items.append(rec)
    data['items'] = items
    data['total'] = len(items)
    data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_performance(data)
    return jsonify({'success': True, 'item': rec})


@app.route('/admin/api/performance/items/<perf_id>', methods=['PUT'])
def api_perf_item_update(perf_id):
    """后台：修改单条性能记录。"""
    data = load_performance()
    items = data.get('items', [])
    for it in items:
        if it.get('id') == perf_id:
            patch = _perf_clean_rec(request.get_json(silent=True) or {})
            # 保留 id / source_file / source_sheet 不被覆盖
            patch.pop('id', None)
            patch.pop('source_file', None)
            patch.pop('source_sheet', None)
            it.update(patch)
            data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            save_performance(data)
            return jsonify({'success': True, 'item': it})
    return jsonify({'error': f'未找到记录 {perf_id}'}), 404


@app.route('/admin/api/performance/items/<perf_id>', methods=['DELETE'])
def api_perf_item_delete(perf_id):
    """后台：删除单条性能记录。"""
    data = load_performance()
    items = data.get('items', [])
    new_items = [it for it in items if it.get('id') != perf_id]
    if len(new_items) == len(items):
        return jsonify({'error': f'未找到记录 {perf_id}'}), 404
    data['items'] = new_items
    data['total'] = len(new_items)
    data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_performance(data)
    return jsonify({'success': True})


@app.route('/admin/api/performance/filters')
def api_perf_filters():
    """返回筛选项可选值（模型/框架/版本/产品组合/场景/数据格式/卡数）。"""
    data = load_performance()
    items = data.get('items', [])
    def _uniq(field):
        return sorted({str(it.get(field)).strip() for it in items if it.get(field)})
    cards = sorted({int(it['total_cards']) for it in items
                    if it.get('total_cards') is not None and int(it['total_cards']) > 0})
    return jsonify({
        'models': _uniq('model'),
        'frameworks': _uniq('framework'),
        'versions': _uniq('version'),
        'products': _uniq('product'),
        'scenarios': _uniq('scenario'),
        'data_formats': _uniq('data_format'),
        'cards': cards,
    })


@app.route('/admin/api/performance/query')
def api_perf_query():
    """性能查询（页面使用）：按筛选条件返回匹配记录。"""
    data = load_performance()
    items = data.get('items', [])
    args = request.args

    def _match(it, field, arg_key):
        val = (args.get(arg_key) or '').strip()
        if not val:
            return True
        return str(it.get(field, '')).strip() == val

    def _num_range(it, field, arg_min, arg_max):
        v = it.get(field)
        if v is None:
            return True
        lo = args.get(arg_min)
        hi = args.get(arg_max)
        if lo not in (None, ''):
            try:
                if v < float(lo):
                    return False
            except ValueError:
                pass
        if hi not in (None, ''):
            try:
                if v > float(hi):
                    return False
            except ValueError:
                pass
        return True

    filtered = [
        it for it in items
        if _match(it, 'model', 'model')
        and _match(it, 'framework', 'framework')
        and _match(it, 'version', 'version')
        and _match(it, 'product', 'product')
        and _match(it, 'scenario', 'scenario')
        and _match(it, 'data_format', 'data_format')
        and _match(it, 'total_cards', 'cards')
        and _num_range(it, 'avg_input', 'min_in', 'max_in')
        and _num_range(it, 'avg_output', 'min_out', 'max_out')
    ]
    return jsonify({'total': len(filtered), 'items': filtered})


# ============ 售前选型：模型→推荐设备 + 业务满足度评估 ============

# 显存判定：product / 设备名中包含的关键词 → 显存标注
_MEM_32G_KEYWORDS = ('32g', '32 g', 'w8a8 32', '32gb')
_MEM_64G_KEYWORDS = ('64g', '64 g', 'w8a8 64', '64gb')
# models-lite.recommendedHardware 中的噪声默认值，不作为有效推荐
_REC_NOISE = {'Atlas 800T A3', 'Atlas 系列硬件', 'Ascend C', 'Ascend AI处理器',
              'Ascend 实测确认', 'Atlas A2', 'Ascend NPU model', 'Ascend Model Agent'}


def _perf_valid_official_hw(value):
    """判断 models-lite.recommendedHardware 是否为有效的官方推荐硬件名。

    仅接受以 Atlas 开头、且不含 GitHub 项目噪声（路径分隔符 /、Star/Fork、README 等）的干净硬件名。
    """
    v = (value or '').strip()
    if not v or not v.startswith('Atlas'):
        return False
    if v in _REC_NOISE:
        return False
    noise = ('/', 'Star', 'Fork', 'README', 'Pull', 'Issue', '代码', '项目', '仓库', '部署', '验证', '生态')
    if any(n in v for n in noise):
        return False
    # 过长或过短视为异常
    if not (3 <= len(v) <= 40):
        return False
    return True


def _perf_dev_memory(product):
    """根据产品组合字符串粗判显存（32G/64G/未知）。"""
    p = (product or '').lower()
    if any(k in p for k in _MEM_64G_KEYWORDS):
        return '64G'
    if any(k in p for k in _MEM_32G_KEYWORDS):
        return '32G'
    if '300idu' in p or '300i duo' in p:
        return '48/96G'
    return ''


def _perf_clean_dev_name(product):
    """规整产品组合名，去掉 W8A8 等格式后缀，便于展示。"""
    p = str(product or '').strip()
    for suf in (' w8a8sc', ' W8A8SC', ' w8a8', ' W8A8', ' w8a8s', ' W8A8S'):
        p = p.replace(suf, '')
    return p.strip()


def _perf_pick_representative(group):
    """从同一产品组合的多条记录中选一条代表性记录（优先典型输入输出 + 高并发）。"""
    if not group:
        return None
    # 优先 1024/1024 或 2048/2048 的典型测试点
    def score(it):
        ai = it.get('avg_input') or 0
        ao = it.get('avg_output') or 0
        s = 0
        if ai in (1024, 2048) and ao in (1024, 2048):
            s += 100
        s += (it.get('concurrency') or 0)
        return s
    return max(group, key=score)


def _perf_hw_memory(prod, hardware):
    """先从产品名关键词判定显存，再从硬件库按名称匹配兜底。"""
    mem = _perf_dev_memory(prod)
    if mem:
        return mem
    pl = (prod or '').lower()
    # 归一化：去掉空格/分隔符便于匹配硬件名
    norm = re.sub(r'[\s_\-/]+', '', pl)
    for h in hardware:
        name = re.sub(r'[\s_\-/]+', '', str(h.get('name', '')).lower())
        if not name:
            continue
        if name in norm or norm in name or norm.split('w8a8')[0] in name:
            m = str(h.get('memory') or '')
            if '64g' in m.lower() or '64 g' in m.lower():
                return '64G'
            if '32g' in m.lower() or '32 g' in m.lower():
                return '32G'
            if '48' in m or '96' in m:
                return '48/96G'
            break
    return ''


def _perf_norm_name(s):
    """归一化模型名用于模糊匹配：去大小写、空格、连字符、点、下划线。

    使 'Qwen2.5-72B-Instruct' 能匹配 'Qwen2.5-72B'，'deepseek v4 flash' 能匹配
    'DeepSeek-V4-Flash'，避免用户带精度后缀/变体输入时匹配失败导致无推荐设备。
    """
    return re.sub(r'[\s\-_.]+', '', str(s or '')).lower()


def _perf_recommend_hardware(model, items, models_lite, hardware):
    """按模型聚合推荐设备（融合 performance 实测 + models-lite 官方推荐 + hardware 参数）。"""
    model_l = _perf_norm_name(model)
    if not model_l:
        return []

    # 1) performance.json 实测：按 product 聚合（归一化双向子串匹配，容忍大小写/空格/连字符/后缀差异）
    grouped = {}
    for it in items:
        m = _perf_norm_name(it.get('model'))
        if m and (model_l in m or m in model_l):
            prod = it.get('product') or '未标注产品'
            grouped.setdefault(prod, []).append(it)

    # 2) models-lite 官方推荐（仅保留有效的干净硬件名，过滤 GitHub 噪声）
    rec_hw = []
    min_hw = ''
    for x in models_lite:
        if _perf_norm_name(x.get('name')) == model_l:
            r = str(x.get('recommendedHardware') or '').strip()
            if _perf_valid_official_hw(r):
                rec_hw.append(r)
            min_hw = str(x.get('minHardware') or '').strip()

    # 3) hardware.json 参数索引（按名称关键词匹配显存/算力）
    hw_idx = {str(h.get('name', '')).lower(): h for h in hardware}

    devices = []
    for prod, group in grouped.items():
        rep = _perf_pick_representative(group)
        mem = _perf_hw_memory(prod, hardware)
        devices.append({
            'product': prod,
            'display': _perf_clean_dev_name(prod),
            'memory': mem,
            'source': '实测',
            'total_cards': rep.get('total_cards'),
            'avg_input': rep.get('avg_input'),
            'avg_output': rep.get('avg_output'),
            'concurrency': rep.get('concurrency'),
            'ttft_ms': rep.get('ttft_ms'),
            'tpot_ms': rep.get('tpot_ms'),
            'output_tps': rep.get('output_tps'),
            'per_card_output_tps': rep.get('per_card_output_tps'),
            'e2e_tps': rep.get('e2e_tps'),
            'per_card_e2e_tps': rep.get('per_card_e2e_tps'),
            'qps': rep.get('qps'),
            'records': len(group),
        })

    # 官方推荐硬件作为补充（无实测时给出候选）
    for r in rec_hw:
        rl = r.lower()
        if any(str(d['display']).lower() in rl or rl in str(d['product']).lower() for d in devices):
            continue
        mem = ''
        for name, h in hw_idx.items():
            if rl in name or name in rl:
                m = str(h.get('memory') or '')
                if '64g' in m.lower() or '64 g' in m.lower():
                    mem = '64G'
                elif '32g' in m.lower():
                    mem = '32G'
                break
        devices.append({
            'product': r, 'display': r, 'memory': mem, 'source': '官方推荐',
            'total_cards': None, 'avg_input': None, 'avg_output': None,
            'concurrency': None, 'ttft_ms': None, 'tpot_ms': None,
            'output_tps': None, 'per_card_output_tps': None,
            'e2e_tps': None, 'per_card_e2e_tps': None, 'qps': None, 'records': 0,
        })

    # 排序：有实测的优先（按单卡吞吐降序）
    def sort_key(d):
        v = d['per_card_e2e_tps'] if d.get('per_card_e2e_tps') else d['e2e_tps']
        return (1 if d['source'] == '实测' else 0, v if v else -1)
    devices.sort(key=sort_key, reverse=True)
    return devices


def _perf_satisfy(dev, biz):
    """业务满足度评估：返回 (level, reasons, advice)。level: 满足/临界/不满足/无数据。"""
    if dev.get('source') != '实测':
        return ('无数据', ['暂无该设备的实测性能数据，无法评估'], '建议联系技术团队实测评估')

    reasons = []
    advice = []
    level_bad = False
    level_warn = False

    # 输入/输出长度匹配
    need_in = biz.get('input_len')
    need_out = biz.get('output_len')
    if need_in and dev.get('avg_input') and need_in > dev['avg_input'] * 1.5:
        reasons.append(f'业务输入长度({need_in})超出实测基线({dev["avg_input"]:.0f})较多，时延/吞吐可能偏差')
        level_warn = True

    # 并发
    need_conc = biz.get('concurrency')
    rec_conc = dev.get('concurrency')
    if need_conc and rec_conc:
        if need_conc > rec_conc * 1.2:
            reasons.append(f'期望并发({need_conc:.0f})高于实测基线({rec_conc:.0f})，建议实测验证')
            level_warn = True

    # 时延上限（TTFT）
    need_ttft = biz.get('max_ttft')
    rec_ttft = dev.get('ttft_ms')
    if need_ttft and rec_ttft:
        if rec_ttft > need_ttft:
            reasons.append(f'实测首token时延({rec_ttft:.0f}ms)超过业务上限({need_ttft:.0f}ms)')
            level_bad = True
        elif rec_ttft > need_ttft * 0.85:
            reasons.append(f'首token时延({rec_ttft:.0f}ms)接近业务上限({need_ttft:.0f}ms)，偏紧')
            level_warn = True

    # QPS / 吞吐
    need_qps = biz.get('qps')
    rec_qps = dev.get('qps')
    if need_qps and rec_qps:
        if need_qps > rec_qps * 1.2:
            reasons.append(f'期望QPS({need_qps:.2f})高于实测基线({rec_qps:.2f})，建议增加卡数或换更高配设备')
            advice.append('增加总卡数 / 换 64G 大显存设备')
            level_bad = True
        elif need_qps > rec_qps:
            reasons.append(f'期望QPS({need_qps:.2f})接近实测基线({rec_qps:.2f})，偏紧')
            level_warn = True

    if level_bad:
        level = '不满足'
        if not advice:
            advice.append('建议增加总卡数 / 换 64G 大显存设备，或联系技术团队评估')
    elif level_warn:
        level = '临界'
        advice.append('建议在目标场景下实测验证后再承诺')
    else:
        level = '满足'
        advice.append('实测基线可覆盖当前业务参数')
    if not reasons:
        reasons.append('未提供业务约束，仅展示实测基线')
    return (level, reasons, advice)


@app.route('/admin/api/performance/models')
def api_perf_models():
    """售前选型：返回可用于推荐的模型列表（performance 实测 + models-lite 适配）。"""
    data = load_performance()
    perf_models = sorted({str(it.get('model', '')).strip() for it in data.get('items', []) if it.get('model')})
    lite = load_json_cached(DATA_DIR / 'models-lite.json') or []
    lite_models = sorted({str(x.get('name', '')).strip() for x in lite if x.get('name')})
    return jsonify({'performance_models': perf_models, 'lite_models': lite_models})


@app.route('/admin/api/performance/recommend')
def api_perf_recommend():
    """售前选型：按模型推荐设备 + 业务满足度评估。"""
    model = (request.args.get('model') or '').strip()
    if not model:
        return jsonify({'error': '请提供模型名称'}), 400

    data = load_performance()
    items = data.get('items', [])
    lite = load_json_cached(DATA_DIR / 'models-lite.json') or []
    hardware = load_json_cached(DATA_DIR / 'hardware.json') or []

    # 业务参数（可选）
    def _f(k):
        v = request.args.get(k)
        if v in (None, ''):
            return None
        try:
            return float(v)
        except ValueError:
            return None
    biz = {
        'input_len': _f('input_len'),
        'output_len': _f('output_len'),
        'concurrency': _f('concurrency'),
        'max_ttft': _f('max_ttft'),
        'qps': _f('qps'),
    }

    devices = _perf_recommend_hardware(model, items, lite, hardware)
    # 满足度评估
    for d in devices:
        level, reasons, advice = _perf_satisfy(d, biz)
        d['satisfy_level'] = level
        d['satisfy_reasons'] = reasons
        d['satisfy_advice'] = advice

    _mn = _perf_norm_name(model)
    matched = [it for it in items if _mn and (_mn in _perf_norm_name(it.get('model')) or _perf_norm_name(it.get('model')) in _mn)]
    return jsonify({
        'model': model,
        'matched_total': len(matched),
        'devices': devices,
        'has_biz': any(v is not None for v in biz.values()),
    })


def _call_llm_json(system_prompt, user_content, cfg, temperature=0.2, max_tokens=2000):
    """通用 LLM 调用（OpenAI 兼容接口），要求模型返回一个 JSON 对象。

    复用报价器的 LLM 配置（load_quote_config）。调用失败抛 ValueError / 网络异常。
    """
    llm = cfg.get('llm', {})
    base_url = (llm.get('base_url') or '').rstrip('/')
    api_key = llm.get('api_key') or ''
    model = llm.get('model') or ''
    if not base_url or not model:
        raise ValueError('LLM 未配置：请先在报价器页面设置 base_url 和 model')

    if base_url.endswith('/chat/completions'):
        url = base_url
    elif base_url.endswith('/v1'):
        url = base_url + '/chat/completions'
    else:
        url = base_url + '/v1/chat/completions'

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content},
        ],
        'temperature': float(llm.get('temperature', temperature)),
        'max_tokens': int(llm.get('max_tokens', max_tokens)),
        'stream': False,
    }
    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    body = _http_post_json(url, payload, headers=headers)
    content = body['choices'][0]['message']['content']
    obj = _extract_json_object(content)
    if obj is None:
        raise ValueError('LLM 返回内容不包含有效 JSON')
    return obj


@app.route('/admin/api/performance/llm-advice', methods=['POST'])
def api_perf_llm_advice():
    """售前选型：用 LLM 补充解读规则引擎结果，给出结构化选型建议。"""
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    devices = data.get('devices') or []
    biz = data.get('biz') or {}
    if not model:
        return jsonify({'error': '请提供模型名称'}), 400
    if not devices:
        return jsonify({'error': '暂无设备数据，请先完成选型'}), 400

    cfg = load_quote_config()
    if not cfg.get('enabled', True):
        return jsonify({'error': 'LLM 服务已停用，请在报价器页面启用'}), 400

    # 构造给 LLM 的输入：业务参数 + 规则引擎评估结果
    biz_lines = []
    labels = {
        'input_len': '输入长度',
        'output_len': '输出长度',
        'concurrency': '并发数',
        'max_ttft': '最大首token时延(ms)',
        'qps': 'QPS',
    }
    for k, label in labels.items():
        v = biz.get(k)
        if v not in (None, ''):
            biz_lines.append(f"{label}={v}")
    biz_desc = '；'.join(biz_lines) if biz_lines else '未提供（按通用场景评估）'

    dev_lines = []
    dev_names = []
    for d in devices:
        dev_name = d.get('device') or d.get('name') or d.get('display') or d.get('product') or '未知设备'
        dev_names.append(dev_name)
        dev_lines.append(
            f"- 设备 {dev_name}（显存 {d.get('memory') or '未知'}，"
            f"来源 {d.get('source') or d.get('source_label') or '未知'}）"
            f"：满足度=「{d.get('satisfy_level') or '无数据'}」"
            + (f"，理由：{d.get('satisfy_reasons')}" if d.get('satisfy_reasons') else '')
            + (f"，建议：{d.get('satisfy_advice')}" if d.get('satisfy_advice') else '')
        )
    valid_names = '、'.join(dev_names) or '（无）'

    system_prompt = (
        '你是昇腾服务器售前选型专家。系统已根据实测性能数据与业务参数，用规则引擎对每个候选设备'
        '给出了满足度评估（满足/临界/不满足/无数据）。你的任务是在此基础上，用售前视角对结果进行'
        '补充解读并给出结构化选型建议。\n'
        '只输出一个 JSON 对象，不要输出任何其他文字。JSON 格式：\n'
        '{"recommend": "首选推荐的设备名称（必须严格等于下方有效设备名之一，若认为无合适设备填 null）", '
        '"confidence": "高|中|低", '
        '"summary": "一段面向客户的自然语言选型解读（150字内，说明为什么推荐/不推荐、关键取舍）", '
        '"risk": "该选型的主要风险或注意事项（无则填空字符串）", '
        '"advice": "给售前/客户的下一步建议（如扩容、降并发、换卡等）"}\n'
        '要求：\n'
        '1. recommend 必须严格等于下方「有效设备名」列表中的某一个名称，不要加任何前缀、括号或修饰。\n'
        '2. 结合业务参数（并发、QPS、时延等）判断设备是否满足，而非只看满足度标签。\n'
        '3. 规则引擎已判为「不满足」的设备一般不应作为首选，除非它是唯一选项并给出风险提示。\n'
        '4. summary 面向客户、通俗易懂，避免过多技术堆砌。\n'
        f'有效设备名：{valid_names}'
    )
    user_content = (
        f"模型：{model}\n"
        f"业务参数：{biz_desc}\n"
        f"候选设备与规则引擎评估结果：\n" + '\n'.join(dev_lines)
    )

    try:
        result = _call_llm_json(system_prompt, user_content, cfg)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'调用大模型失败: {e}'}), 502

    return jsonify({
        'model': model,
        'recommend': result.get('recommend'),
        'confidence': result.get('confidence'),
        'summary': result.get('summary', ''),
        'risk': result.get('risk', ''),
        'advice': result.get('advice', ''),
    })


def _perf_calc_cards(dev, biz):
    """按业务参数推算所需设备（卡）数量。

    基于实测的单卡 QPS / 单卡并发 / 单卡吞吐，取各约束所需卡数的上限。
    返回 (cards, reason)；无实测数据返回 (None, 原因)。
    """
    if dev.get('source') != '实测':
        return (None, '无实测数据，无法推算设备数量')

    total_cards = dev.get('total_cards') or 1
    per_card_qps = (dev.get('qps') or 0) / total_cards if dev.get('qps') else None
    per_card_conc = (dev.get('concurrency') or 0) / total_cards if dev.get('concurrency') else None

    need = []
    qps = biz.get('qps')
    if qps and per_card_qps:
        c = max(1, int(-(-qps // per_card_qps)))  # ceil
        need.append(('QPS', c))
    conc = biz.get('concurrency')
    if conc and per_card_conc:
        c = max(1, int(-(-conc // per_card_conc)))
        need.append(('并发', c))

    if not need:
        return (None, '未提供 QPS/并发约束，无法推算设备数量')

    cards = max(c for _, c in need)
    labels = '、'.join(f"{k}需{c}卡" for k, c in need)
    # 模型部署约束：实测基线卡数即该模型在该设备上拉起服务所需的最小卡数。
    # 仅按性能推算可能给出不现实的低卡数（如超大模型推成 1 卡），须以基线卡数为下限。
    min_cards = int(total_cards) if total_cards else 1
    if cards < min_cards:
        cards = min_cards
        return (cards, f"按{labels}推算需{cards}卡，但 {total_cards} 卡为模型部署基线（最小拉起卡数），按实际部署取 {cards} 卡")
    return (cards, f"按{labels}推算，建议 {cards} 卡（{total_cards} 卡基线换算）")


def _perf_fusion_cards(model_entry, biz, repo=None, precision='int8'):
    """估算兜底：用 gpu-hardware-compare 引擎按显存三约束推卡数。

    model_entry: model-params.json 单条；biz: 业务参数 dict。
    返回 {'source': '估算', 'plan': [...], 'card_reason': str}；引擎异常时返回空估算。
    """
    try:
        import importlib.util
        hw_path = os.path.join(repo or str(BASE_DIR), 'skills', 'gpu-hardware-compare', 'hw_compare.py')
        spec = importlib.util.spec_from_file_location('_fusion_hw', hw_path)
        eng = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eng)

        active = model_entry.get('activeParams')
        if active is None:
            active = model_entry.get('totalParams')
        if not active:
            return {'source': '估算', 'plan': [], 'card_reason': '模型参数量缺失，无法估算'}

        # 组装模型字典（有结构时用真实 KV，否则引擎走经验比例）
        model = {
            'name': model_entry.get('name') or model_entry.get('modelCode') or '',
            'active': active,
            'total': model_entry.get('totalParams') or active,
            'layers': model_entry.get('layers'),
            'kvHeads': model_entry.get('kvHeads'),
            'headDim': model_entry.get('headDim'),
        }
        in_len = biz.get('input_len') or 0
        out_len = biz.get('output_len') or 0
        qps = biz.get('qps') or 0
        result = eng.recommend_cards(model, precision, in_len, out_len, qps, repo or str(BASE_DIR))
        plans = result.get('plans', [])
        if not plans:
            return {'source': '估算', 'plan': [], 'card_reason': '估算未产出可行方案（可能超出单集群上限）'}
        best = plans[0]
        card_reason = ('估算（显存三约束）：推荐 %s × %s 卡，总显存需求约 %sGB，成本约 %s 万'
                       % (best['gpu'], best['cards'], round(result.get('total_vram_gb', 0), 1),
                          round(best['cost_cny'] / 10000, 1)))
        return {'source': '估算', 'plan': plans, 'card_reason': card_reason,
                'best': best, 'total_vram_gb': result.get('total_vram_gb')}
    except Exception as e:  # noqa: BLE001 - 估算失败不阻断
        return {'source': '估算', 'plan': [], 'card_reason': '估算引擎异常: %s' % e}


def _perf_requirement_candidates(items, biz, hardware, top_n=6, repo=None, model_params=None):
    """需求驱动的规则引擎初筛：返回满足度最好的候选模型及其最优设备。

    融合策略（方案③）：有实测用实测，无实测用 Skill 估算兜底。
    - 有实测的模型：选单卡吞吐最高的设备为代表，做满足度评估与实测卡数推算，并附加估算方案。
    - 无实测数据的模型（来自 model-params 参数库）：用 gpu-hardware-compare 引擎估算兜底。
    返回统一候选列表（每条含 device.source = 实测|估算）。
    """
    # 按模型聚合实测记录
    models = {}
    for it in items:
        m = str(it.get('model', '')).strip()
        if not m:
            continue
        models.setdefault(m, []).append(it)

    cands = []
    for m, group in models.items():
        best = None
        best_tps = -1
        for it in group:
            tps = it.get('per_card_e2e_tps') or it.get('e2e_tps') or 0
            if tps > best_tps:
                best_tps = tps
                best = it
        if best is None:
            continue
        prod = best.get('product') or '未标注产品'
        dev = {
            'product': prod,
            'display': _perf_clean_dev_name(prod),
            'memory': _perf_hw_memory(prod, hardware),
            'source': '实测',
            'total_cards': best.get('total_cards'),
            'concurrency': best.get('concurrency'),
            'ttft_ms': best.get('ttft_ms'),
            'tpot_ms': best.get('tpot_ms'),
            'output_tps': best.get('output_tps'),
            'per_card_e2e_tps': best.get('per_card_e2e_tps'),
            'e2e_tps': best.get('e2e_tps'),
            'qps': best.get('qps'),
            'avg_input': best.get('avg_input'),
            'avg_output': best.get('avg_output'),
        }
        level, reasons, advice = _perf_satisfy(dev, biz)
        cards, card_reason = _perf_calc_cards(dev, biz)
        # 附加估算方案（融合：实测为主，估算作补充对比）
        entry = None
        if model_params:
            entry = _perf_find_model_param(model_params, m)
        fusion = _perf_fusion_cards(entry or {}, biz, repo) if model_params else None
        cands.append({
            'model': m,
            'device': dev,
            'satisfy_level': level,
            'reasons': reasons,
            'advice': advice,
            'cards': cards,
            'card_reason': card_reason,
            'fusion': fusion,
            'records': len(group),
        })

    # 估算兜底：从全球模型参数库补充「无实测但满足需求」的模型
    if model_params and len(cands) < top_n:
        cands = _perf_estimate_fallback_candidates(cands, model_params, biz, repo, top_n)

    # 排序：优先满足「需求输入长度」的模型（上下文覆盖），再满足 > 临界 > 无数据 > 不满足，同级按单卡吞吐降序。
    # 目的：让不同输入长度/场景产生不同推荐，避免始终推荐同一短对话模型。
    rank = {'满足': 0, '临界': 1, '无数据': 2, '不满足': 3}
    need_in = biz.get('input_len')
    def _tps(c):
        return (c['device'].get('per_card_e2e_tps') or c['device'].get('e2e_tps') or 0)
    def _req_key(c):
        tps = _tps(c)
        lvl = rank.get(c['satisfy_level'], 4)
        if not need_in:
            return (0.0, lvl, -tps)
        ctx = _perf_model_context(model_params, c['model'])
        if ctx:
            # 能覆盖需求长度 → gap=0；覆盖不足 → 按缺口比例惩罚
            gap = 0.0 if ctx >= need_in else min(1.0, (need_in - ctx) / need_in)
        else:
            # 上下文未知：视为无法确认覆盖，排在「明确能覆盖」之后
            gap = 0.5
        return (gap, lvl, -tps)
    cands.sort(key=_req_key)
    return cands[:top_n]


def _perf_model_context(model_params, model):
    """返回模型的最大上下文长度（tokens）；查不到或无效时返回 None。

    用于需求驱动选型时评估「该模型能否覆盖业务输入长度」，从而让长上下文
    需求优先推荐长上下文模型，避免始终推荐同一短对话模型。
    """
    if not model_params:
        return None
    entry = _perf_find_model_param(model_params, model)
    if not entry:
        return None
    ctx = entry.get('context')
    try:
        ctx = int(ctx)
    except (TypeError, ValueError):
        return None
    return ctx if ctx and ctx > 0 else None


def _perf_find_model_param(model_params, model):
    """在 model-params 数据中按 modelCode/name 匹配模型参数条目（大小写不敏感）。"""
    items = model_params.get('models', model_params) if isinstance(model_params, dict) else model_params
    target = re.sub(r'[\s\-_.]+', '', str(model or '').lower())
    for m in items or []:
        if not m:
            continue
        if re.sub(r'[\s\-_.]+', '', str(m.get('modelCode') or '').lower()) == target \
                or re.sub(r'[\s\-_.]+', '', str(m.get('name') or '').lower()) == target:
            return m
    return None


def _perf_estimate_fallback_candidates(cands, model_params, biz, repo, top_n):
    """估算兜底：当实测候选不足时，从 model-params 挑选若干模型用估算补足。

    优先选「有参数量且与业务场景规模匹配」的模型；仅附加估算方案，不做满足度判定。
    """
    items = model_params.get('models', model_params) if isinstance(model_params, dict) else model_params
    # 已覆盖的模型名
    covered = set(c['model'].lower() for c in cands)
    # 挑有参数量、且未被覆盖的模型；totalParams 单位为 B（如 40=40B），
    # 过滤掉 <1B 的 embedding/encoder 小模型（不适合做生成服务候选），
    # 优先取 1B~100B 的中小规模 LLM（估算更可信），按总参数升序补足。
    candidates = []
    for m in items or []:
        if not m:
            continue
        name = (m.get('name') or m.get('modelCode') or '').strip()
        if not name or name.lower() in covered:
            continue
        total = m.get('totalParams')
        if total is None or total < 1:
            continue
        candidates.append(m)
    # 按总参数升序取前 top_n - len(cands) 个，作为估算兜底候选
    candidates.sort(key=lambda x: x.get('totalParams') or 1e18)
    for entry in candidates[:max(0, top_n - len(cands))]:
        name = (entry.get('name') or entry.get('modelCode') or '').strip()
        fusion = _perf_fusion_cards(entry, biz, repo)
        dev = {
            'product': '（估算）',
            'display': name,
            'memory': '',
            'source': '估算',
            'total_cards': None,
            'concurrency': None,
            'ttft_ms': None,
            'tpot_ms': None,
            'output_tps': None,
            'per_card_e2e_tps': None,
            'e2e_tps': None,
            'qps': None,
            'avg_input': None,
            'avg_output': None,
        }
        cands.append({
            'model': name,
            'device': dev,
            'satisfy_level': '无数据',
            'reasons': ['暂无该模型实测性能数据，以下为估算方案，建议 POC 实测校准'],
            'advice': ['建议先实测验证估算吞吐与显存，再确定采购方案'],
            'cards': (fusion.get('best') or {}).get('cards'),
            'card_reason': fusion.get('card_reason'),
            'fusion': fusion,
            'records': 0,
        })
    return cands


@app.route('/admin/api/performance/recommend-by-requirement', methods=['POST'])
def api_perf_recommend_by_requirement():
    """需求驱动选型：根据业务需求推荐具体模型 + 设备 + 设备数量。

    规则引擎初筛候选（满足度 + 卡数推算），再由 LLM 做最终解读与确认。
    """
    data = request.get_json(silent=True) or {}

    def _num(k):
        v = data.get(k)
        if v in (None, ''):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    biz = {
        'input_len': _num('input_len'),
        'output_len': _num('output_len'),
        'concurrency': _num('concurrency'),
        'qps': _num('qps'),
        'max_ttft': _num('max_ttft'),
    }
    scene = (data.get('scene') or '').strip()
    mem_pref = (data.get('memory') or '').strip()

    if not any(v is not None for v in biz.values()) and not scene:
        return jsonify({'error': '请至少提供业务参数或场景描述'}), 400

    data_perf = load_performance()
    items = data_perf.get('items', [])
    if not items:
        return jsonify({'error': '暂无性能数据，无法选型'}), 400

    hardware = load_json_cached(DATA_DIR / 'hardware.json') or []
    # 融合选型：有实测用实测，无实测用 Skill 估算兜底（传入 repo + 全球模型参数库）
    model_params = load_model_params()
    cands = _perf_requirement_candidates(items, biz, hardware, top_n=6,
                                         repo=str(BASE_DIR), model_params=model_params)
    if not cands:
        return jsonify({'error': '未找到匹配的模型数据（无实测且无法估算）'}), 404

    # 规则引擎结果 → LLM 解读
    cfg = load_quote_config()
    has_llm = bool(cfg.get('enabled', True)) and bool((cfg.get('llm') or {}).get('base_url')) and bool((cfg.get('llm') or {}).get('model'))

    if has_llm:
        cand_lines = []
        for c in cands:
            d = c['device']
            # 附上模型上下文长度，供 LLM 判断输入长度匹配（长输入需求选长上下文模型）
            ctx = _perf_model_context(model_params, c['model'])
            ctx_txt = f"，上下文≈{ctx} tokens" if ctx else "，上下文未知"
            cand_lines.append(
                f"- 模型「{c['model']}」→ 设备 {d['display'] or d['product']}"
                f"（显存 {d.get('memory') or '未知'}，{c['records']} 条实测）{ctx_txt}"
                f"：满足度=「{c['satisfy_level']}」"
                f"，推算设备数量：{c['cards'] if c['cards'] else '无法推算'}（{c['card_reason'] or ''}）"
                + (f"，理由：{'；'.join(c['reasons'])}" if c['reasons'] else '')
            )
        system_prompt = (
            '你是昇腾服务器售前选型专家。系统已根据业务需求，用规则引擎从有实测数据的模型中'
            '初筛出若干候选（含推荐设备与推算的设备数量）。你的任务是：从候选模型中挑选最适合'
            '该业务需求的具体模型，给出推荐设备与设备数量，并做售前解读。\n'
            '只输出一个 JSON 对象，不要输出任何其他文字。JSON 格式：\n'
            '{"recommend": "推荐的具体模型名称（必须严格等于下方候选模型之一，若都不合适填 null）", '
            '"device": "推荐设备名称（来自该模型对应的设备）", '
            '"cards": 建议设备数量（整数，参考规则引擎推算值，允许微调；无法确定填 null）, '
            '"confidence": "高|中|低", '
            '"scene_fit": "该模型适合在什么业务场景下使用（结合用户填写的场景说明），例如适合做多轮客服/代码补全/长文档问答等，1-2句", '
            '"rationale": "模型选型理由：为什么选这个模型而不是其他候选，重点讲模型能力与该业务需求的匹配点（如长上下文、低时延、高吞吐、显存占用等），不要只罗列性能数字，1-3句", '
            '"summary": "面向客户的选型解读（120字内：综合场景适配+选型理由+是否满足业务，一句话讲清为什么选它）", '
            '"risk": "主要风险或注意事项（无则填空字符串）", '
            '"advice": "下一步建议（如扩容、实测验证、显存选择等）"}\n'
            '要求：\n'
            '1. recommend 必须严格等于下方候选模型名称之一，不要加前后缀。\n'
            '2. 结论必须同时说明「该模型用在什么场景」和「为什么选它（选型理由）」，不要只描述性能表现。\n'
            '3. 结合业务参数（并发/QPS/时延/输入输出长度）与显存偏好判断，而非只看满足度标签。\n'
            '4. 规则引擎已判「不满足」的模型一般不应作为首选，除非它是最接近且可扩容的选项。\n'
            '5. cards 优先采用规则引擎推算值，除非你有明确依据才调整。\n'
            '6. 若业务输入长度很大，优先选「上下文」能覆盖输入长度的模型（候选行标注了上下文 tokens），'
            '不要选上下文小于输入长度的短对话模型。'
        )
        user_content = (
            f"业务需求：场景「{scene or '通用'}」；输入长度 {biz.get('input_len') or '不限'}；"
            f"输出长度 {biz.get('output_len') or '不限'}；并发 {biz.get('concurrency') or '不限'}；"
            f"QPS {biz.get('qps') or '不限'}；首token时延上限 {biz.get('max_ttft') or '不限'}ms；"
            f"显存偏好 {mem_pref or '不限'}。\n"
            f"候选模型与规则引擎初筛结果：\n" + '\n'.join(cand_lines)
        )
        try:
            llm_result = _call_llm_json(system_prompt, user_content, cfg)
        except ValueError as e:
            llm_result = None
            llm_err = str(e)
        except Exception as e:
            llm_result = None
            llm_err = f'调用大模型失败: {e}'
    else:
        llm_result = None
        llm_err = 'LLM 未配置，仅返回规则引擎结果'

    # 组装最终候选列表（含规则引擎结果）
    final_cands = []
    for c in cands:
        final_cands.append({
            'model': c['model'],
            'device': c['device']['display'] or c['device']['product'],
            'product': c['device']['product'],
            'memory': c['device']['memory'],
            'source': c['device']['source'],
            'satisfy_level': c['satisfy_level'],
            'reasons': c['reasons'],
            'advice': c['advice'],
            'cards': c['cards'],
            'card_reason': c['card_reason'],
            'total_cards_baseline': c['device']['total_cards'],
            'per_card_tps': c['device'].get('per_card_e2e_tps'),
            'e2e_tps': c['device'].get('e2e_tps'),
            'ttft_ms': c['device'].get('ttft_ms'),
            'concurrency': c['device'].get('concurrency'),
            'fusion': c.get('fusion'),
            'records': c['records'],
        })

    return jsonify({
        'candidates': final_cands,
        'llm': llm_result,
        'llm_available': has_llm,
        'llm_error': None if has_llm and llm_result else (llm_err if has_llm else None),
    })


# ============ 首页静态文件路由（放在 Admin 路由之后）============

# 允许公开访问的静态资源扩展名（其余如 .py/.json/.log/.md/.xlsx 等一律屏蔽，
# 避免 server.py 源码、data/*.json 数据与凭据、日志等被匿名下载）
_PUBLIC_STATIC_EXTS = {
    '.html', '.htm', '.css', '.js', '.map',
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', '.avif',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
}
# 禁止直接服务的敏感目录（源码/数据/凭据/日志/版本库等）
_BLOCKED_STATIC_DIRS = (
    'data/', 'skills/', 'logs/', 'scripts/', 'node_modules/',
    '__pycache__/', '.git/', '.gitcode/', '.agent_history/', 'Yuxi/',
)


def _is_public_static(path):
    """判断 path 是否为允许公开访问的静态资源。

    规则：不在敏感目录内、扩展名在白名单内，才允许直接返回文件。
    """
    p = path.lstrip('/')
    if any(p.startswith(d) for d in _BLOCKED_STATIC_DIRS):
        return False
    ext = os.path.splitext(p)[1].lower()
    return ext in _PUBLIC_STATIC_EXTS


@app.route('/<path:path>')
def static_files(path):
    # 排除 admin 路由（让 Flask 匹配更具体的 admin 路由）
    if path.startswith('admin/'):
        return admin_index()
    # 仅允许公开静态资源，屏蔽源码/数据/凭据/日志等敏感文件
    if _is_public_static(path):
        file_path = BASE_DIR / path
        if file_path.exists() and file_path.is_file():
            return send_from_directory(str(BASE_DIR), path)
    # 未知路径或不公开文件：SPA 回退首页；敏感路径则返回 404，避免泄露
    if any(path.lstrip('/').startswith(d) for d in _BLOCKED_STATIC_DIRS):
        return ('Not Found', 404)
    # API 未知路径返回 JSON 404（而非 SPA HTML 回退），
    # 避免前端 res.json() 解析到 HTML 报 "Unexpected token '<'"。
    if path.startswith('api/') or path.startswith('admin/api/'):
        return jsonify({'error': '接口不存在'}), 404
    return send_from_directory(str(BASE_DIR), 'index.html')


# ============ 启动 ============
# ============ 售前三级推荐（编排 Skill 服务端封装）============
def _load_presales_module():
    """动态加载编排 Skill 的 recommend.py（避免顶层 import 与路径耦合）。"""
    import importlib.util
    path = BASE_DIR / 'skills' / 'ascend-presales-recommend' / 'recommend.py'
    spec = importlib.util.spec_from_file_location('presales_recommend', str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 售前选型可识别的场景/精度枚举（与 skills/ascend-presales-recommend/recommend.py 保持一致，
# 优先从模块动态读取，避免两处硬编码漂移）
_PRESALES_SCENES = [
    '智能问答', '内容生成', '代码辅助', '文档处理', '知识抽取', '翻译', '多模态', '语音', '推理',
    '多轮客服', '行业助手', 'Code Agent 短链', 'Code Agent 中链', '全仓库',
    '中文档 RAG', '全文档 QA', '整本书 QA',
]
_PRESALES_PRECISIONS = ['fp16', 'int8', 'int4', '极高', '较高', '一般']


def _norm_scene(text):
    """把 LLM 提取的场景归一到已知枚举；无法匹配返回 None。"""
    text = re.sub(r'[\s\-_.()（）]+', '', str(text or '').lower())
    if not text:
        return None
    for sc in _PRESALES_SCENES:
        if text == re.sub(r'[\s\-_.()（）]+', '', sc.lower()):
            return sc
    # 模糊包含匹配：长枚举优先，避免短词误吞
    best, best_len = None, 0
    for sc in _PRESALES_SCENES:
        ns = re.sub(r'[\s\-_.()（）]+', '', sc.lower())
        if ns and (ns in text or text in ns) and len(ns) > best_len:
            best, best_len = sc, len(ns)
    return best


@app.route('/api/presales-extract', methods=['POST'])
def api_presales_extract():
    """用 LLM 从大段自然语言需求中提取售前选型关键参数。

    输入：{"requirement": "客户大段需求描述"}
    输出：{success, params:{scene,precision,qps,in_len,out_len,top,require_open},
          missing:[未提取到的字段], summary:需求要点摘要}
    参数做归一化与数值校验；in_len/out_len 缺省时按场景预设套用（与推荐引擎一致）。
    """
    data = request.get_json(silent=True) or {}
    requirement = (data.get('requirement') or '').strip()
    if not requirement:
        return jsonify({'error': '请提供需求描述'}), 400

    cfg = load_quote_config()
    if not cfg.get('enabled', True):
        return jsonify({'error': 'LLM 服务已停用，请在报价器页面启用'}), 400

    scene_enum = ' / '.join(_PRESALES_SCENES)
    prec_enum = ' / '.join(_PRESALES_PRECISIONS)
    system_prompt = (
        '你是昇腾售前选型的需求解析助手。请从用户的大段业务需求描述中，提取售前选型所需的关键参数，'
        '只输出一个 JSON 对象，不要输出其他文字。字段如下（无法确定的字段返回 null 或省略）：\n'
        '{\n'
        '  "scene": 业务场景，只能取以下枚举之一：' + scene_enum + '，\n'
        '  "precision": 精度档位，只能取：' + prec_enum + '（缺省倾向 fp16），\n'
        '  "qps": 并发/峰值每秒请求数(数值)，\n'
        '  "in_len": 平均输入长度(tokens, 整数)，\n'
        '  "out_len": 平均输出长度(tokens, 整数)，\n'
        '  "top": 期望的候选模型数量(整数)，\n'
        '  "require_open": 是否要求开源/可私有化(布尔，true/false)，\n'
        '  "summary": 一句话概括核心需求要点(字符串)\n'
        '}\n'
        '判断依据：场景看业务类型；in_len/out_len 看输入输出规模或是否长文本/代码/文档；'
        'qps 看并发/吞吐要求；require_open 看是否提到私有化、开源、信创、数据不出域。'
    )
    try:
        obj = _call_llm_json(system_prompt, '客户需求：\n' + requirement, cfg)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({'error': f'调用大模型失败: {e}'}), 502
    if not isinstance(obj, dict):
        return jsonify({'error': 'LLM 返回格式异常'}), 502

    def _num(v):
        try:
            f = float(v)
            return f if f > 0 else None
        except (TypeError, ValueError):
            return None

    scene = _norm_scene(obj.get('scene'))
    precision = obj.get('precision')
    if precision not in _PRESALES_PRECISIONS:
        precision = 'fp16'
    qps = _num(obj.get('qps'))
    top_raw = _num(obj.get('top'))
    top = int(top_raw) if top_raw else None
    if top is not None:
        top = max(1, min(20, top))

    # in_len/out_len：显式给出则用，否则按场景预设(与推荐引擎 SCENE_PRESETS 一致)
    in_len = _num(obj.get('in_len'))
    out_len = _num(obj.get('out_len'))
    if scene:
        try:
            rec = _load_presales_module()
            preset = getattr(rec, 'SCENE_PRESETS', {}).get(scene, {})
            if in_len is None:
                in_len = preset.get('in_len')
            if out_len is None:
                out_len = preset.get('out_len')
        except Exception:  # noqa: BLE001
            pass
    if in_len is not None:
        in_len = int(in_len)
    if out_len is not None:
        out_len = int(out_len)

    params = {
        'scene': scene, 'precision': precision, 'qps': qps,
        'in_len': in_len, 'out_len': out_len,
        'top': top, 'require_open': bool(obj.get('require_open')),
        'summary': obj.get('summary') or '',
    }
    missing = [k for k, v in params.items() if k != 'summary' and v in (None, '')]
    return jsonify({'success': True, 'params': params, 'missing': missing})


@app.route('/api/presales-recommend', methods=['GET', 'POST'])
def api_presales_recommend():
    """售前三级推荐：①全球大模型推荐 → ②昇腾适配筛选 → ③硬件推荐+TCO。

    参数（GET query 或 POST JSON，均可）：
      scene        业务场景(智能问答/内容生成/代码辅助/文档处理/知识抽取/翻译/多模态/语音/推理)
      precision    精度档位(fp16/int8/int4/极高/较高/一般)
      qps          并发 QPS
      in_len       平均输入长度(tokens)
      out_len      平均输出长度(tokens)
      require_open 仅推荐开源/可私有化模型(1/true)
      top          候选模型数量
      adapt_only   只跑①②不做硬件估算(1/true)
    """
    src = request.get_json(silent=True) or {}
    def gv(k, default=None):
        v = request.args.get(k)
        if v is None and k in src:
            v = src[k]
        return v

    scene = gv('scene') or '智能问答'
    precision = gv('precision') or 'fp16'
    qps = float(gv('qps') or 30)
    # in_len/out_len 缺省传 None，交由 skill 按场景预设(SCENE_PRESETS)套用
    def _int_opt(k):
        v = gv(k)
        return int(v) if v not in (None, '') else None
    in_len = _int_opt('in_len')
    out_len = _int_opt('out_len')
    top = int(gv('top') or 5)
    def truthy(v):
        return str(v).lower() in ('1', 'true', 'yes', 'on')
    require_open = truthy(gv('require_open', ''))
    adapt_only = truthy(gv('adapt_only', ''))

    try:
        rec = _load_presales_module()
        args = rec.argparse.Namespace(
            repo=str(BASE_DIR), scene=scene, precision=precision, qps=qps,
            in_len=in_len, out_len=out_len, require_open=require_open,
            top=top, adapt_only=adapt_only, out=None)
        data = rec.Data(str(BASE_DIR))
        data.load()
        report = rec.build_report(data, args)
        if adapt_only:
            report.pop('step3', None)
        # params 反映套用场景预设后的实际值（report.meta 是 build_report 解析后的最终值）
        meta = report.get('meta', {})
        return jsonify({'success': True, 'params': {
            'scene': scene, 'precision': precision, 'qps': qps,
            'in_len': meta.get('in_len', in_len), 'out_len': meta.get('out_len', out_len),
            'require_open': require_open, 'top': top, 'adapt_only': adapt_only,
        }, 'report': report})
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    # 加载爬虫历史状态（重启后保留历史日志）
    _load_crawler_status()
    # 启动定时备份线程（每天 23:00 自动备份）
    backup_thread = threading.Thread(target=run_daily_backup, daemon=True)
    backup_thread.start()
    print("⏰ 定时备份已启动（每天 23:00 自动备份）")

    # 启动定时爬取线程（每天 24:00 / 午夜 0 点自动爬取模型）
    crawler_thread = threading.Thread(target=run_daily_crawler, daemon=True)
    crawler_thread.start()
    print("⏰ 定时爬取已启动（每天 24:00 自动爬取模型）")

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"🚀 服务启动于 http://localhost:{port}")
    print(f"   📋 首页: http://localhost:{port}/")
    print(f"   ⚙️  Admin: http://localhost:{port}/admin")
    if ADMIN_TOKEN:
        print("🔒 Admin 写操作鉴权已启用（X-Admin-Token）")
    else:
        print("⚠️  未设置 ADMIN_TOKEN 环境变量，Admin 写操作未鉴权；生产环境请设置 ADMIN_TOKEN 启用保护")
    app.run(host='0.0.0.0', port=port, debug=False)
