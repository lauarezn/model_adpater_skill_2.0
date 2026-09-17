// ============ 统一认证模块（首页与 Admin 共用）============
// 提供 token 存取、登录/注册/登出、当前用户获取、角色判断、认证弹窗。
// 角色等级：viewer(1) < member(2) < editor(3) < admin(4)，累积式。
window.Auth = (function () {
  var TOKEN_KEY = 'dl-auth-token';
  var USER_KEY = 'dl-auth-user';

  var ROLE_LEVEL = { viewer: 1, member: 2, editor: 3, admin: 4 };
  var ROLE_LABEL = { viewer: '访客', member: '正式用户', editor: '编辑', admin: '管理员' };

  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; }
  }

  function setToken(token) {
    try {
      if (token) { localStorage.setItem(TOKEN_KEY, token); }
      else { localStorage.removeItem(TOKEN_KEY); }
    } catch (e) {}
  }

  function getUser() {
    try {
      var raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function setUser(user) {
    try {
      if (user) { localStorage.setItem(USER_KEY, JSON.stringify(user)); }
      else { localStorage.removeItem(USER_KEY); }
    } catch (e) {}
  }

  function isLoggedIn() {
    return !!getToken();
  }

  function roleLevel(role) {
    return ROLE_LEVEL[role] || 0;
  }

  // 是否拥有 >= 指定角色
  function hasRole(role) {
    var u = getUser();
    if (!u) return false;
    return roleLevel(u.role) >= roleLevel(role);
  }

  function roleLabel(role) {
    return ROLE_LABEL[role] || role;
  }

  // 从后端拉取最新用户信息并刷新本地缓存
  function refreshMe() {
    var token = getToken();
    if (!token) return Promise.resolve(null);
    return fetch('/api/auth/me', { headers: { 'Authorization': 'Bearer ' + token } })
      .then(function (res) {
        if (res.ok) return res.json();
        throw new Error('未登录');
      })
      .then(function (data) {
        setUser(data.user);
        return data.user;
      })
      .catch(function () {
        setToken(null); setUser(null);
        return null;
      });
  }

  function login(username, password) {
    return fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username, password: password })
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) { throw new Error(data.error || '登录失败'); }
        setToken(data.token);
        setUser(data.user);
        return data.user;
      });
    });
  }

  function register(username, password, email) {
    return fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username, password: password, email: email || '' })
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) { throw new Error(data.error || '注册失败'); }
        return data;
      });
    });
  }

  function logout() {
    var token = getToken();
    if (token) {
      fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + token }
      }).catch(function () {});
    }
    setToken(null); setUser(null);
    if (window.location.pathname.indexOf('/admin') === 0) {
      window.location.href = '/admin';
    } else {
      window.location.reload();
    }
  }

  // 全局 fetch 拦截器：自动附加 Authorization 头；401 时清空登录态
  function installFetchInterceptor() {
    if (window.__authFetchInstalled) return;
    window.__authFetchInstalled = true;
    var origFetch = window.fetch;
    window.fetch = function (input, init) {
      init = init || {};
      var url = typeof input === 'string' ? input : (input && input.url) || '';
      // 仅对本站 API 附加，避免污染外部请求
      if (url.indexOf('/api/') !== -1 || url.indexOf('/admin/api/') !== -1) {
        var token = getToken();
        if (token) {
          var headers = new Headers(init.headers || {});
          headers.set('Authorization', 'Bearer ' + token);
          init.headers = headers;
        }
      }
      return origFetch.call(window, input, init).then(function (res) {
        if (res.status === 401 && url.indexOf('/api/auth/') === -1) {
          setToken(null); setUser(null);
        }
        return res;
      });
    };
  }

  // 认证弹窗（登录/注册切换）
  function showAuthModal(callback) {
    if (window.__authModalEl) { window.__authModalEl.style.display = 'flex'; return; }

    var modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
    modal.innerHTML =
      '<div style="background:#fff;color:#111;border-radius:12px;padding:28px;width:360px;max-width:92vw;box-shadow:0 10px 40px rgba(0,0,0,.3);font-family:-apple-system,Segoe UI,Roboto,sans-serif">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">' +
      '  <h3 id="authTitle" style="margin:0;font-size:18px">登录</h3>' +
      '  <button id="authClose" style="border:none;background:none;font-size:20px;cursor:pointer;color:#888">×</button>' +
      '</div>' +
      '<div id="authForm">' +
      '  <input id="authUser" placeholder="用户名" style="width:100%;box-sizing:border-box;padding:10px;margin-bottom:10px;border:1px solid #ddd;border-radius:6px;font-size:14px">' +
      '  <div style="position:relative;margin-bottom:10px">' +
      '    <input id="authPass" type="password" placeholder="密码" style="width:100%;box-sizing:border-box;padding:10px 38px 10px 10px;border:1px solid #ddd;border-radius:6px;font-size:14px">' +
      '    <button id="authPassToggle" type="button" tabindex="-1" title="显示/隐藏密码" style="position:absolute;top:50%;right:6px;transform:translateY(-50%);border:none;background:none;cursor:pointer;font-size:16px;color:#888;padding:4px">👁</button>' +
      '  </div>' +
      '  <input id="authEmail" placeholder="邮箱（注册选填）" style="width:100%;box-sizing:border-box;padding:10px;margin-bottom:14px;border:1px solid #ddd;border-radius:6px;font-size:14px;display:none">' +
      '  <div id="authMsg" style="color:#dc2626;font-size:13px;margin-bottom:10px;min-height:18px"></div>' +
      '  <button id="authSubmit" style="width:100%;padding:11px;background:#2563EB;color:#fff;border:none;border-radius:6px;font-size:15px;cursor:pointer">登 录</button>' +
      '</div>' +
      '<div style="margin-top:14px;text-align:center;font-size:13px;color:#555">' +
      '  <span id="authSwitchText">还没有账号？</span>' +
      '  <a id="authSwitch" href="javascript:void(0)" style="color:#2563EB">注册</a>' +
      '</div>' +
      '<div style="margin-top:10px;font-size:12px;color:#999;line-height:1.5">注册后默认仅可查看大模型清单；硬件、报价等数据需管理员审批升级后可见。</div>' +
      '</div>';

    document.body.appendChild(modal);
    window.__authModalEl = modal;

    var isLogin = true;
    var userInput = modal.querySelector('#authUser');
    var passInput = modal.querySelector('#authPass');
    var emailInput = modal.querySelector('#authEmail');
    var msgEl = modal.querySelector('#authMsg');
    var passToggle = modal.querySelector('#authPassToggle');
    if (passToggle) {
      passToggle.addEventListener('click', function () {
        var show = passInput.type === 'password';
        passInput.type = show ? 'text' : 'password';
        passToggle.textContent = show ? '🙈' : '👁';
      });
    }
    var submitBtn = modal.querySelector('#authSubmit');
    var titleEl = modal.querySelector('#authTitle');
    var switchEl = modal.querySelector('#authSwitch');
    var switchText = modal.querySelector('#authSwitchText');

    function setMode(login) {
      isLogin = login;
      titleEl.textContent = login ? '登录' : '注册';
      submitBtn.textContent = login ? '登 录' : '注 册';
      emailInput.style.display = login ? 'none' : 'block';
      switchText.textContent = login ? '还没有账号？' : '已有账号？';
      switchEl.textContent = login ? '注册' : '登录';
      msgEl.textContent = '';
      if (login) emailInput.value = '';
    }

    function submit() {
      msgEl.textContent = '';
      var username = userInput.value.trim();
      var password = passInput.value;
      var email = emailInput.value.trim();
      if (!username || !password) { msgEl.textContent = '请输入用户名和密码'; return; }
      submitBtn.disabled = true;
      submitBtn.textContent = '处理中...';
      var p = isLogin ? login(username, password) : register(username, password, email);
      p.then(function (result) {
        if (!isLogin) {
          // 注册成功后提示，并切回登录
          msgEl.style.color = '#16a34a';
          msgEl.textContent = '注册成功，请登录';
          setMode(true);
          submitBtn.disabled = false;
          submitBtn.textContent = '登 录';
          return;
        }
        modal.style.display = 'none';
        if (callback) callback(result);
        if (window.location.pathname.indexOf('/admin') !== 0) { window.location.reload(); }
      }).catch(function (err) {
        msgEl.style.color = '#dc2626';
        msgEl.textContent = err.message;
        submitBtn.disabled = false;
        submitBtn.textContent = isLogin ? '登 录' : '注 册';
      });
    }

    submitBtn.onclick = submit;
    modal.querySelector('#authClose').onclick = function () { modal.style.display = 'none'; };
    switchEl.onclick = function () { setMode(!isLogin); };
    passInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') submit(); });

    userInput.focus();
  }

  function init(callback) {
    installFetchInterceptor();
    return refreshMe().then(function (u) {
      if (callback) callback(u);
      return u;
    });
  }

  return {
    getToken: getToken,
    getUser: getUser,
    setUser: setUser,
    isLoggedIn: isLoggedIn,
    hasRole: hasRole,
    roleLevel: roleLevel,
    roleLabel: roleLabel,
    login: login,
    register: register,
    logout: logout,
    refreshMe: refreshMe,
    showAuthModal: showAuthModal,
    init: init,
    ROLE_LEVEL: ROLE_LEVEL
  };
})();
