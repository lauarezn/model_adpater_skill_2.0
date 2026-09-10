// ============ Admin 管理后台 JavaScript ============

// Admin 写操作鉴权：后端配置 ADMIN_TOKEN 后，所有 /admin/api/* 的写请求
// 需携带 X-Admin-Token。这里用全局 fetch 拦截器统一附加，管理员 token 存 localStorage。
(function () {
  var TOKEN_KEY = 'dl-admin-token';
  var origFetch = window.fetch;
  var authFailCount = 0; // 连续 401 次数，达到阈值停止循环弹窗
  window.fetch = function (input, init) {
    init = init || {};
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var token = null;
    try { token = localStorage.getItem(TOKEN_KEY); } catch (e) {}
    var headers = new Headers(init.headers || {});
    if (url.indexOf('/admin/api/') !== -1 && token) {
      headers.set('X-Admin-Token', token);
    }
    init.headers = headers;
    return origFetch.call(window, input, init).then(function (res) {
      if (res.status === 401) {
        authFailCount++;
        if (authFailCount > 3) {
          authFailCount = 0;
          try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
          setTimeout(function () { showToast('管理员令牌验证失败，请检查后重试', 'error'); }, 0);
          return res;
        }
        var inputToken = prompt('Admin 操作需要管理员令牌（后端 ADMIN_TOKEN），请输入：');
        if (inputToken) {
          try { localStorage.setItem(TOKEN_KEY, inputToken); } catch (e) {}
          // 重试原请求
          return origFetch.call(window, input, init);
        }
      } else {
        authFailCount = 0;
      }
      // 写请求非 2xx 时统一反馈后端错误（避免调用方静默失败）
      if (res.status >= 400 && res.status !== 401 && /\/admin\/api\//.test(url)) {
        var method = (init.method || 'GET').toUpperCase();
        if (method !== 'GET') {
          res.clone().json().then(function (body) {
            var msg = (body && body.error) || ('请求失败（HTTP ' + res.status + '）');
            setTimeout(function () { showToast(String(msg), 'error'); }, 0);
          }).catch(function () {
            setTimeout(function () { showToast('请求失败（HTTP ' + res.status + '）', 'error'); }, 0);
          });
        }
      }
      return res;
    });
  };
})();

let currentPage = 1;
let selectedIds = new Set();
let editingModelId = null;
let searchTimer = null;
let filtersInitialized = false;
let trainCurrentPage = 1;
let trainSearchTimer = null;
let editingTrainName = null;

// ============ 页面初始化 ============

document.addEventListener('DOMContentLoaded', function() {
  refreshStats();
  refreshCrawlerStatus();
  searchModels();
  setInterval(refreshCrawlerStatus, 10000);
});

// ============ Tab 切换 ============

function switchTab(tab) {
  document.querySelectorAll('.section').forEach(function(s) { s.classList.remove('active'); });
  document.querySelectorAll('.sidebar a').forEach(function(a) { a.classList.remove('active'); });
  document.getElementById('section-' + tab).classList.add('active');
  var activeLink = document.querySelector('.sidebar a[onclick*="' + tab + '"]');
  activeLink.classList.add('active');
  // 点击二级菜单时，确保所属目录展开
  var group = activeLink.closest ? activeLink.closest('.nav-group') : null;
  if (group) group.classList.remove('collapsed');
  if (tab === 'models') searchModels();
  if (tab === 'acl-models') searchAclModels();
  if (tab === 'mindie-models') searchMindieModels();
  if (tab === 'train-models') searchTrainModels();
  if (tab === 'crawler') refreshCrawlerStatus();
  if (tab === 'benchmarks') searchBenchmarks();
  if (tab === 'quote-services') loadQuoteServices();
  if (tab === 'quote-sheets') searchQuoteSheets();
  if (tab === 'performance') { perfLoadSources(); perfSearch(); }
  if (tab === 'global-models') searchGlobalModels();
  if (tab === 'model-params') searchModelParams();
  if (tab === 'hardware-params') searchHardwareParams();
  if (tab === 'backup') listBackups();
  if (tab === 'sources') loadSourceStats();
}

// 折叠/展开侧边栏目录
function toggleNavGroup(titleEl) {
  var group = titleEl.parentNode;
  group.classList.toggle('collapsed');
}

// ============ Toast 通知 ============

function showToast(message, type) {
  type = type || 'info';
  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(function() { toast.remove(); }, 3000);
}

// ============ 仪表盘 ============

async function refreshStats() {
  try {
    var res = await fetch('/admin/api/stats');
    var stats = await res.json();
    document.getElementById('statModels').textContent = stats.total_models;
    document.getElementById('statDetail').textContent = stats.total_detail;
    document.getElementById('statTrain').textContent = stats.total_train;
    document.getElementById('statHardware').textContent = stats.total_hardware;
    document.getElementById('statDataSize').textContent = stats.data_size_mb + ' MB';

    var catHtml = '';
    if (stats.categories && Object.keys(stats.categories).length > 0) {
      catHtml = Object.entries(stats.categories).map(function(e) {
        return '<span class="badge badge-info" style="margin:4px;font-size:0.85rem">' + e[0] + ': ' + e[1] + '</span>';
      }).join('');
    } else {
      catHtml = '<span class="empty-state">暂无数据</span>';
    }
    document.getElementById('categoryChart').innerHTML = catHtml;

    var srcHtml = '';
    if (stats.sources && Object.keys(stats.sources).length > 0) {
      srcHtml = Object.entries(stats.sources).map(function(e) {
        return '<span class="badge badge-success" style="margin:4px;font-size:0.85rem">' + e[0] + ': ' + e[1] + '</span>';
      }).join('');
    } else {
      srcHtml = '<span class="empty-state">暂无数据</span>';
    }
    document.getElementById('sourceChart').innerHTML = srcHtml;
  } catch(e) {
    showToast('加载统计数据失败', 'error');
  }
}

// ============ 模型管理 ============

async function searchModels() {
  var search = document.getElementById('modelSearch').value;
  var source = document.getElementById('sourceFilter').value;
  var category = document.getElementById('categoryFilter2').value;
  try {
    var res = await fetch('/admin/api/models?search=' + encodeURIComponent(search) + '&source=' + encodeURIComponent(source) + '&category=' + encodeURIComponent(category) + '&page=' + currentPage + '&page_size=50');
    var data = await res.json();

    // 首次加载时填充筛选器下拉框
    if (!filtersInitialized && data.sources) {
      var sf = document.getElementById('sourceFilter');
      sf.innerHTML = '<option value="">全部来源</option>' + data.sources.map(function(s) {
        return '<option value="' + s.replace(/"/g, '&quot;') + '">' + s.replace(/"/g, '&quot;') + '</option>';
      }).join('');
      var cf = document.getElementById('categoryFilter2');
      cf.innerHTML = '<option value="">全部分类</option>' + data.categories.map(function(c) {
        return '<option value="' + c.replace(/"/g, '&quot;') + '">' + c.replace(/"/g, '&quot;') + '</option>';
      }).join('');
      filtersInitialized = true;
    }

    var html = '';
    data.models.forEach(function(m) {
      var statusClass = m.supportLevel === '✅ 已支持' ? 'badge-success' : m.supportLevel === '🔵 实验性' ? 'badge-warning' : 'badge-danger';
      html += '<tr>' +
        '<td><input type="checkbox" class="model-checkbox" value="' + (m.id || '').replace(/"/g, '&quot;') + '" onchange="updateSelected()"></td>' +
        '<td><strong>' + (m.name || '').replace(/</g, '&lt;') + '</strong><br><span style="font-size:0.75rem;color:var(--text-secondary)">' + (m.id || '').replace(/</g, '&lt;') + '</span></td>' +
        '<td>' + (m.developer || '').replace(/</g, '&lt;') + '</td>' +
        '<td><span class="badge badge-info">' + (m.category || '').replace(/</g, '&lt;') + '</span></td>' +
        '<td><span class="badge ' + statusClass + '">' + (m.supportLevel || '').replace(/</g, '&lt;') + '</span></td>' +
        '<td><span class="badge badge-info">' + (m.source || '').replace(/</g, '&lt;') + '</span></td>' +
        '<td style="font-size:0.75rem">' + (m.minHardware || '').replace(/</g, '&lt;') + '</td>' +
        '<td><button class="btn btn-primary btn-sm" onclick="editModel(\'' + escJsStr(m.id) + '\')">✏️</button> ' +
        '<button class="btn btn-danger btn-sm" onclick="deleteModel(\'' + escJsStr(m.id) + '\')">🗑️</button></td></tr>';
    });
    document.getElementById('modelTableBody').innerHTML = html;

    var pagHtml = '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="changePage(' + (currentPage - 1) + ')" ' + (currentPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span>第 ' + data.page + '/' + data.total_pages + ' 页 · 共 ' + data.total + ' 条</span>' +
      '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="changePage(' + (currentPage + 1) + ')" ' + (currentPage >= data.total_pages ? 'disabled' : '') + '>下一页</button>';
    document.getElementById('modelPagination').innerHTML = pagHtml;
  } catch(e) {
    showToast('加载模型列表失败', 'error');
  }
}

function debouncedSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(function() {
    currentPage = 1;
    searchModels();
  }, 300);
}

function changePage(page) { currentPage = page; searchModels(); }

function toggleSelectAll() {
  var checked = document.getElementById('selectAll').checked;
  document.querySelectorAll('.model-checkbox').forEach(function(cb) { cb.checked = checked; });
  updateSelected();
}

function updateSelected() {
  selectedIds = new Set();
  document.querySelectorAll('.model-checkbox:checked').forEach(function(cb) { selectedIds.add(cb.value); });
}

async function batchDelete() {
  if (selectedIds.size === 0) { showToast('请先选择要删除的模型', 'error'); return; }
  if (!confirm('确定删除选中的 ' + selectedIds.size + ' 个模型？')) return;
  try {
    var res = await fetch('/admin/api/models/batch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'delete', ids: Array.from(selectedIds)})
    });
    var data = await res.json();
    showToast('已删除 ' + data.deleted + ' 个模型，剩余 ' + data.remaining + ' 个', 'success');
    searchModels(); refreshStats();
  } catch(e) { showToast('批量删除失败', 'error'); }
}

async function exportSelected() {
  if (selectedIds.size === 0) { showToast('请先选择要导出的模型', 'error'); return; }
  try {
    var res = await fetch('/admin/api/models/batch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'export', ids: Array.from(selectedIds)})
    });
    var data = await res.json();
    var blob = new Blob([JSON.stringify(data.models, null, 2)], {type: 'application/json'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'exported_models_' + Date.now() + '.json';
    a.click(); URL.revokeObjectURL(url);
    showToast('已导出 ' + data.count + ' 个模型', 'success');
  } catch(e) { showToast('导出失败', 'error'); }
}

async function editModel(id) {
  try {
    var res = await fetch('/admin/api/models/' + encodeURIComponent(id));
    var data = await res.json();
    var m = data.model;
    editingModelId = id;
    var fields = ['name','developer','category','supportLevel','framework','minHardware','recommendedHardware','architecture','parameters','inferencePerf','trainingPerf','mindsporeSupport','cannVersion','notes'];
    var formHtml = '';
    fields.forEach(function(f) {
      var val = (m[f] || '');
      // 安全转义
      val = val.replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      formHtml += '<div class="form-group"><label>' + f + '</label><input type="text" id="edit_' + f + '" value="' + val + '"></div>';
    });
    document.getElementById('editForm').innerHTML = formHtml;
    document.getElementById('editModal').classList.add('active');
  } catch(e) { showToast('加载模型详情失败', 'error'); }
}

async function saveModel() {
  if (editingBenchmarkId) { saveBenchmark(); return; }
  if (editingQuoteServiceCode) { saveQuoteService(); return; }
  if (editingGlobalModelId) { saveGlobalModel(); return; }
  if (editingHardwareParamId) { saveHardwareParam(); return; }
  if (editingModelParamId) { saveModelParam(); return; }
  if (!editingModelId) return;
  var data = {};
  document.querySelectorAll('#editForm input').forEach(function(input) {
    data[input.id.replace('edit_', '')] = input.value;
  });
  try {
    var res = await fetch('/admin/api/models/' + encodeURIComponent(editingModelId), {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    if (res.ok) { showToast('模型已更新', 'success'); closeEditModal(); searchModels(); }
    else { showToast('更新失败', 'error'); }
  } catch(e) { showToast('更新失败', 'error'); }
}

function closeEditModal() { document.getElementById('editModal').classList.remove('active'); editingModelId = null; editingBenchmarkId = null; editingQuoteServiceCode = null; editingGlobalModelId = null; editingHardwareParamId = null; editingHardwareParamSource = null; editingModelParamId = null; }

async function deleteModel(id) {
  if (!confirm('确定删除模型 ' + id + '？')) return;
  try {
    var res = await fetch('/admin/api/models/' + encodeURIComponent(id), {method: 'DELETE'});
    if (res.ok) { showToast('模型已删除', 'success'); searchModels(); refreshStats(); }
  } catch(e) { showToast('删除失败', 'error'); }
}

// ============ 爬虫控制 ============

async function refreshCrawlerStatus() {
  try {
    var res = await fetch('/admin/api/crawler/status');
    var status = await res.json();
    var el = document.getElementById('crawlerStatus');
    var textEl = document.getElementById('crawlerStatusText');
    if (!el || !textEl) return;
    var dot = el.querySelector('.status-dot');
    if (status.running) {
      el.className = 'crawler-status running';
      if (dot) dot.className = 'status-dot running';
      textEl.textContent = '爬虫运行中...';
      var btn = document.getElementById('runCrawlerBtn');
      if (btn) btn.disabled = true;
    } else {
      el.className = 'crawler-status idle';
      if (dot) dot.className = 'status-dot idle';
      textEl.textContent = status.last_status === 'failed' ? '上次运行失败' : (status.last_run ? '上次运行: ' + status.last_run + ' · 状态: ' + status.last_status : '就绪');
      var btn = document.getElementById('runCrawlerBtn');
      if (btn) btn.disabled = false;
    }
    // 实时过程日志：逐行渲染 status.log，滚动到底部
    var progressEl = document.getElementById('crawlerProgress');
    if (progressEl) {
      if (status.log && status.log.length) {
        progressEl.innerHTML = status.log.map(function(l) {
          return '<div>' + escAttr(l) + '</div>';
        }).join('');
        progressEl.scrollTop = progressEl.scrollHeight;
      } else if (status.progress) {
        progressEl.textContent = status.progress;
      }
    }
    // 历史运行记录
    var histEl = document.getElementById('crawlerHistory');
    if (histEl) {
      if (status.history && status.history.length) {
        histEl.innerHTML = status.history.slice().reverse().map(function(h) {
          return '<div class="hist-item">[' + (h.time || '-') + '] ' + (h.status === 'success' ? '成功' : (h.status === 'failed' ? '失败' : (h.status || '-'))) + ' — ' + (h.summary || '') + '</div>';
        }).join('');
      } else {
        histEl.textContent = '暂无历史运行记录';
      }
    }
  } catch(e) { showToast('获取爬虫状态失败', 'error'); }
}

async function runCrawler() {
  try {
    var res = await fetch('/admin/api/crawler/run', {method: 'POST'});
    var data = await res.json();
    if (data.success) {
      showToast('爬虫已启动', 'success');
      refreshCrawlerStatus();
      var interval = setInterval(async function() {
        await refreshCrawlerStatus();
        var sr = await fetch('/admin/api/crawler/status');
        var s = await sr.json();
        if (!s.running) { clearInterval(interval); showToast('爬虫执行完成', 'success'); refreshStats(); }
      }, 3000);
    } else { showToast(data.error, 'error'); }
  } catch(e) { showToast('启动爬虫失败', 'error'); }
}

// ============ 数据备份 ============

async function createBackup() {
  try {
    var res = await fetch('/admin/api/data/backup', {method: 'POST'});
    var data = await res.json();
    if (data.success) { showToast('备份已创建: ' + data.files.length + ' 个文件', 'success'); listBackups(); }
  } catch(e) { showToast('创建备份失败', 'error'); }
}

async function listBackups() {
  try {
    var res = await fetch('/admin/api/data/backups');
    var data = await res.json();
    var list = document.getElementById('backupList');
    if (data.backups.length === 0) { list.innerHTML = '<div class="empty-state">暂无备份数据</div>'; return; }
    list.innerHTML = data.backups.map(function(b) {
      return '<div class="backup-item"><div><div class="name">' + (b.name || '').replace(/</g, '&lt;') + '</div><div class="meta">' + (b.size_kb || 0) + ' KB · ' + (b.modified || '') + '</div></div>' +
        '<button class="btn btn-primary btn-sm" onclick="restoreBackup(\'' + escJsStr(b.name) + '\')">🔄 恢复</button></div>';
    }).join('');
  } catch(e) { showToast('加载备份列表失败', 'error'); }
}

async function restoreBackup(filename) {
  if (!confirm('确定从 ' + filename + ' 恢复数据？当前数据将被覆盖！')) return;
  try {
    var res = await fetch('/admin/api/data/restore', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({filename: filename})
    });
    var data = await res.json();
    if (data.success) { showToast('已恢复: ' + data.restored, 'success'); refreshStats(); }
  } catch(e) { showToast('恢复失败', 'error'); }
}

// ============ 小模型管理 ============

let aclCurrentPage = 1;
let aclSearchTimer = null;

async function searchAclModels() {
  var search = document.getElementById('aclSearch').value;
  var source = document.getElementById('aclSourceFilter').value;
  var category = document.getElementById('aclCategoryFilter').value;
  var dataDir = document.getElementById('aclDataDirFilter').value;
  try {
    var params = new URLSearchParams();
    if (search) params.set('search', search);
    if (source) params.set('source', source);
    if (category) params.set('category', category);
    if (dataDir) params.set('data_dir', dataDir);
    params.set('page', aclCurrentPage);
    params.set('page_size', '50');

    var res = await fetch('/admin/api/acl-models?' + params.toString());
    var data = await res.json();

    // 首次加载时填充分类筛选器
    var cf = document.getElementById('aclCategoryFilter');
    if (cf && cf.options.length <= 1 && data.categories) {
      cf.innerHTML = '<option value="">全部分类</option>' + data.categories.map(function(c) {
        return '<option value="' + c.replace(/"/g, '"') + '">' + c.replace(/"/g, '"') + '</option>';
      }).join('');
    }

    var html = '';
    data.models.forEach(function(m) {
      var modelUrl = safeUrl(m.model_url || '');
      var urlHtml = modelUrl ? '<a href="' + escAttr(modelUrl) + '" target="_blank" style="color:var(--primary);font-size:0.75rem" title="' + escAttr(modelUrl) + '">🔗 查看</a>' : '<span style="color:var(--text-secondary);font-size:0.75rem">无</span>';
      html += '<tr>' +
        '<td><strong>' + escAttr(m.name) + '</strong></td>' +
        '<td style="font-size:0.8rem">' + escAttr(m.folder) + '</td>' +
        '<td><span class="badge badge-info">' + escAttr(m.category) + '</span></td>' +
        '<td><span class="badge badge-info">' + escAttr(m.source) + '</span></td>' +
        '<td><span class="badge badge-success">' + escAttr(m.data_dir) + '</span></td>' +
        '<td>' + urlHtml + '</td></tr>';
    });
    document.getElementById('aclTableBody').innerHTML = html;

    var pagHtml = '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="aclChangePage(' + (aclCurrentPage - 1) + ')" ' + (aclCurrentPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span>第 ' + data.page + '/' + data.total_pages + ' 页 · 共 ' + data.total + ' 条</span>' +
      '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="aclChangePage(' + (aclCurrentPage + 1) + ')" ' + (aclCurrentPage >= data.total_pages ? 'disabled' : '') + '>下一页</button>';
    document.getElementById('aclPagination').innerHTML = pagHtml;
  } catch(e) {
    showToast('加载小模型列表失败', 'error');
  }
}

function debouncedAclSearch() {
  clearTimeout(aclSearchTimer);
  aclSearchTimer = setTimeout(function() {
    aclCurrentPage = 1;
    searchAclModels();
  }, 300);
}

function aclChangePage(page) { aclCurrentPage = page; searchAclModels(); }

// ============ MindIE 模型管理 ============

let mindieCurrentPage = 1;
let mindieSearchTimer = null;

async function searchMindieModels() {
  var search = document.getElementById('mindieSearch').value;
  var category = document.getElementById('mindieCategoryFilter').value;
  var dataDir = document.getElementById('mindieDataDirFilter').value;
  try {
    var params = new URLSearchParams();
    if (search) params.set('search', search);
    if (category) params.set('category', category);
    if (dataDir) params.set('data_dir', dataDir);
    params.set('page', mindieCurrentPage);
    params.set('page_size', '50');

    var res = await fetch('/admin/api/mindie-models?' + params.toString());
    var data = await res.json();

    // 首次加载时填充筛选器
    var cf = document.getElementById('mindieCategoryFilter');
    if (cf && cf.options.length <= 1 && data.categories) {
      cf.innerHTML = '<option value="">全部分类</option>' + data.categories.map(function(c) {
        return '<option value="' + c.replace(/"/g, '"') + '">' + c.replace(/"/g, '"') + '</option>';
      }).join('');
    }
    var df = document.getElementById('mindieDataDirFilter');
    if (df && df.options.length <= 1 && data.data_dirs) {
      df.innerHTML = '<option value="">全部目录</option>' + data.data_dirs.map(function(d) {
        return '<option value="' + d.replace(/"/g, '"') + '">' + d.replace(/"/g, '"') + '</option>';
      }).join('');
    }

    var html = '';
    data.models.forEach(function(m) {
      var modelUrl = safeUrl(m.model_url || '');
      var urlHtml = modelUrl ? '<a href="' + escAttr(modelUrl) + '" target="_blank" style="color:var(--primary);font-size:0.75rem" title="' + escAttr(modelUrl) + '">🔗 查看</a>' : '<span style="color:var(--text-secondary);font-size:0.75rem">无</span>';
      html += '<tr>' +
        '<td><strong>' + escAttr(m.name) + '</strong></td>' +
        '<td style="font-size:0.8rem">' + escAttr(m.folder) + '</td>' +
        '<td><span class="badge badge-info">' + escAttr(m.category) + '</span></td>' +
        '<td><span class="badge badge-info">' + escAttr(m.source) + '</span></td>' +
        '<td><span class="badge badge-success">' + escAttr(m.data_dir) + '</span></td>' +
        '<td>' + urlHtml + '</td></tr>';
    });
    document.getElementById('mindieTableBody').innerHTML = html;

    var pagHtml = '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="mindieChangePage(' + (mindieCurrentPage - 1) + ')" ' + (mindieCurrentPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span>第 ' + data.page + '/' + data.total_pages + ' 页 · 共 ' + data.total + ' 条</span>' +
      '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="mindieChangePage(' + (mindieCurrentPage + 1) + ')" ' + (mindieCurrentPage >= data.total_pages ? 'disabled' : '') + '>下一页</button>';
    document.getElementById('mindiePagination').innerHTML = pagHtml;
  } catch(e) {
    showToast('加载 MindIE 模型列表失败', 'error');
  }
}

function debouncedMindieSearch() {
  clearTimeout(mindieSearchTimer);
  mindieSearchTimer = setTimeout(function() {
    mindieCurrentPage = 1;
    searchMindieModels();
  }, 300);
}

function mindieChangePage(page) { mindieCurrentPage = page; searchMindieModels(); }

// ============ 训练模型管理 ============
async function searchTrainModels() {
  var search = document.getElementById('trainSearch').value;
  var framework = document.getElementById('trainFrameworkFilter').value;
  var category = document.getElementById('trainCategoryFilter').value;
  var status = document.getElementById('trainStatusFilter').value;
  try {
    var params = new URLSearchParams();
    if (search) params.set('search', search);
    if (framework) params.set('framework', framework);
    if (category) params.set('category', category);
    if (status) params.set('status', status);
    params.set('page', trainCurrentPage);
    params.set('page_size', '50');

    var res = await fetch('/admin/api/train-models?' + params.toString());
    var data = await res.json();

    var ff = document.getElementById('trainFrameworkFilter');
    if (ff && ff.options.length <= 1 && data.frameworks) {
      ff.innerHTML = '<option value="">全部框架</option>' + data.frameworks.map(function(c) {
        return '<option value="' + escAttr(c) + '">' + escAttr(c) + '</option>';
      }).join('');
    }
    var cf = document.getElementById('trainCategoryFilter');
    if (cf && cf.options.length <= 1 && data.categories) {
      cf.innerHTML = '<option value="">全部分类</option>' + data.categories.map(function(c) {
        return '<option value="' + escAttr(c) + '">' + escAttr(c) + '</option>';
      }).join('');
    }
    var sf = document.getElementById('trainStatusFilter');
    if (sf && sf.options.length <= 1 && data.statuses) {
      sf.innerHTML = '<option value="">全部状态</option>' + data.statuses.map(function(c) {
        return '<option value="' + escAttr(c) + '">' + escAttr(c) + '</option>';
      }).join('');
    }

    var html = '';
    data.models.forEach(function(m) {
      html += '<tr>' +
        '<td><strong>' + escAttr(m.name) + '</strong></td>' +
        '<td>' + escAttr(m.params) + '</td>' +
        '<td>' + escAttr(m.task) + '</td>' +
        '<td>' + escAttr(m.cluster) + '</td>' +
        '<td>' + escAttr(m.precision) + '</td>' +
        '<td><span class="badge badge-info">' + escAttr(m.framework) + '</span></td>' +
        '<td><span class="badge ' + (m.status === '已支持' ? 'badge-success' : 'badge-warning') + '">' + escAttr(m.status) + '</span></td>' +
        '<td><span class="badge badge-info">' + escAttr(m.category) + '</span></td>' +
        '<td>' + escAttr(m.source) + '</td>' +
        '<td>' +
          '<button class="btn btn-primary btn-sm" onclick="editTrainModel(' + escJsStr(m.name) + ')">✏️</button> ' +
          '<button class="btn btn-sm" style="background:var(--danger,#e5484d);color:#fff" onclick="deleteTrainModel(' + escJsStr(m.name) + ')">🗑️</button>' +
        '</td></tr>';
    });
    document.getElementById('trainTableBody').innerHTML = html;

    var pagHtml = '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="trainChangePage(' + (trainCurrentPage - 1) + ')" ' + (trainCurrentPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span>第 ' + data.page + '/' + data.total_pages + ' 页 · 共 ' + data.total + ' 条</span>' +
      '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="trainChangePage(' + (trainCurrentPage + 1) + ')" ' + (trainCurrentPage >= data.total_pages ? 'disabled' : '') + '>下一页</button>';
    document.getElementById('trainPagination').innerHTML = pagHtml;
  } catch(e) {
    showToast('加载训练模型列表失败', 'error');
  }
}

function escJsStr(s) {
  return '"' + String(s == null ? '' : s).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
}

function debouncedTrainSearch() {
  clearTimeout(trainSearchTimer);
  trainSearchTimer = setTimeout(function() {
    trainCurrentPage = 1;
    searchTrainModels();
  }, 300);
}

function trainChangePage(page) { trainCurrentPage = page; searchTrainModels(); }

function addTrainModel() {
  editingTrainName = null;
  var formHtml =
    '<div class="form-group"><label>模型名称 *</label><input type="text" id="edit_train_name" placeholder="如 Qwen2.5-72B"></div>' +
    '<div class="form-group"><label>参数量</label><input type="text" id="edit_train_params" placeholder="如 72B"></div>' +
    '<div class="form-group"><label>任务</label><input type="text" id="edit_train_task" placeholder="如 预训练 / 微调"></div>' +
    '<div class="form-group"><label>集群</label><input type="text" id="edit_train_cluster" placeholder="如 1x8 (A3)"></div>' +
    '<div class="form-group"><label>精度</label><input type="text" id="edit_train_precision" placeholder="如 BF16"></div>' +
    '<div class="form-group"><label>框架</label><input type="text" id="edit_train_framework" placeholder="如 MM / LLM"></div>' +
    '<div class="form-group"><label>状态</label><input type="text" id="edit_train_status" placeholder="如 已支持"></div>' +
    '<div class="form-group"><label>分类</label><input type="text" id="edit_train_category" placeholder="如 大语言模型"></div>' +
    '<div class="form-group"><label>来源</label><input type="text" id="edit_train_source" placeholder="如 MindSpeed-MM"></div>' +
    '<div class="form-group"><label>描述</label><textarea id="edit_train_desc" rows="2"></textarea></div>';
  document.getElementById('editForm').innerHTML = formHtml;
  document.getElementById('editModal').classList.add('active');
}

async function editTrainModel(name) {
  var res, data, m;
  try {
    res = await fetch('/admin/api/train-models/' + encodeURIComponent(name));
    data = await res.json();
    m = data.model;
  } catch (e) { console.error(e); showToast('加载训练模型失败', 'error'); return; }
  if (!m) { showToast('未找到该模型', 'error'); return; }
  editingTrainName = name;
  var formHtml =
    '<div class="form-group"><label>模型名称（只读）</label><input type="text" value="' + escAttr(m.name) + '" readonly></div>' +
    '<div class="form-group"><label>参数量</label><input type="text" id="edit_train_params" value="' + escAttr(m.params) + '"></div>' +
    '<div class="form-group"><label>任务</label><input type="text" id="edit_train_task" value="' + escAttr(m.task) + '"></div>' +
    '<div class="form-group"><label>集群</label><input type="text" id="edit_train_cluster" value="' + escAttr(m.cluster) + '"></div>' +
    '<div class="form-group"><label>精度</label><input type="text" id="edit_train_precision" value="' + escAttr(m.precision) + '"></div>' +
    '<div class="form-group"><label>框架</label><input type="text" id="edit_train_framework" value="' + escAttr(m.framework) + '"></div>' +
    '<div class="form-group"><label>状态</label><input type="text" id="edit_train_status" value="' + escAttr(m.status) + '"></div>' +
    '<div class="form-group"><label>分类</label><input type="text" id="edit_train_category" value="' + escAttr(m.category) + '"></div>' +
    '<div class="form-group"><label>来源</label><input type="text" id="edit_train_source" value="' + escAttr(m.source) + '"></div>' +
    '<div class="form-group"><label>描述</label><textarea id="edit_train_desc" rows="2">' + escAttr(m.desc) + '</textarea></div>';
  document.getElementById('editForm').innerHTML = formHtml;
  document.getElementById('editModal').classList.add('active');
}

function saveTrainModel() {
  if (editingTrainName) {
    // 更新
    var data = {
      name: document.getElementById('edit_train_name') ? document.getElementById('edit_train_name').value : editingTrainName,
      params: document.getElementById('edit_train_params').value,
      task: document.getElementById('edit_train_task').value,
      cluster: document.getElementById('edit_train_cluster').value,
      precision: document.getElementById('edit_train_precision').value,
      framework: document.getElementById('edit_train_framework').value,
      status: document.getElementById('edit_train_status').value,
      category: document.getElementById('edit_train_category').value,
      source: document.getElementById('edit_train_source').value,
      desc: document.getElementById('edit_train_desc').value
    };
    fetch('/admin/api/train-models/' + encodeURIComponent(editingTrainName), {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    }).then(function(res) {
      if (res.ok) { showToast('训练模型已更新', 'success'); closeEditModal(); searchTrainModels(); }
      else { showToast('更新失败', 'error'); }
    }).catch(function() { showToast('更新失败', 'error'); });
  } else {
    // 新增
    var data = {
      name: document.getElementById('edit_train_name').value,
      params: document.getElementById('edit_train_params').value,
      task: document.getElementById('edit_train_task').value,
      cluster: document.getElementById('edit_train_cluster').value,
      precision: document.getElementById('edit_train_precision').value,
      framework: document.getElementById('edit_train_framework').value,
      status: document.getElementById('edit_train_status').value,
      category: document.getElementById('edit_train_category').value,
      source: document.getElementById('edit_train_source').value,
      desc: document.getElementById('edit_train_desc').value
    };
    fetch('/admin/api/train-models', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    }).then(function(res) {
      return res.json().then(function(d) { return {ok: res.ok, d: d}; });
    }).then(function(r) {
      if (r.ok) { showToast('训练模型已新增', 'success'); closeEditModal(); searchTrainModels(); }
      else { showToast(r.d.error || '新增失败', 'error'); }
    }).catch(function() { showToast('新增失败', 'error'); });
  }
}

async function deleteTrainModel(name) {
  if (!confirm('确定删除训练模型 ' + name + ' 吗？')) return;
  try {
    var res = await fetch('/admin/api/train-models/' + encodeURIComponent(name), { method: 'DELETE' });
    if (res.ok) { showToast('训练模型已删除', 'success'); searchTrainModels(); }
    else { showToast('删除失败', 'error'); }
  } catch(e) { showToast('删除失败', 'error'); }
}

// ============ 数据来源 ============

async function loadSourceStats() {
  try {
    var res = await fetch('/admin/api/sources');
    var sources = await res.json();
    var html = '';
    Object.entries(sources).forEach(function(e) {
      var name = (e[0] || '').replace(/</g, '&lt;');
      var info = e[1];
      var url = info.url || '';
      var urlHtml = url ? '<div style="margin-top:6px;font-size:0.75rem;word-break:break-all"><a href="' + url.replace(/"/g, '&quot;') + '" target="_blank" style="color:var(--primary);text-decoration:none">' + url.replace(/</g, '&lt;') + '</a></div>' : '';
      html += '<div style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px">' +
        '<h4 style="margin-bottom:8px">' + name + '</h4>' +
        '<div style="display:flex;gap:16px;font-size:0.85rem">' +
        '<span>总数: <strong>' + (info.count || 0) + '</strong></span>' +
        '<span style="color:var(--success)">✅ 已支持: ' + (info.supported || 0) + '</span>' +
        '<span style="color:var(--warning)">🔵 实验性: ' + (info.experimental || 0) + '</span></div>' +
        urlHtml + '</div>';
    });
    document.getElementById('sourceStats').innerHTML = html;
  } catch(e) { showToast('加载来源统计失败', 'error'); }
}

// ============ 评测基准管理 ============

let benchmarkAdminPage = 1;
let benchmarkAdminSearchTimer = null;
let editingBenchmarkId = null;

function escAttr(s) {
  // 正确的 HTML 实体转义（原实现把 & " < > 替换成自身，等于没有转义，导致存储型 XSS）
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// 仅允许 http/https 链接，防止 model_url 等外部数据注入 javascript: 等危险协议
function safeUrl(s) {
  var v = String(s == null ? '' : s).trim();
  if (!v) return '';
  try {
    var u = new URL(v, location.origin);
    return (u.protocol === 'http:' || u.protocol === 'https:') ? v : '';
  } catch (e) {
    return '';
  }
}


async function searchBenchmarks() {
  var search = document.getElementById('benchmarkAdminSearch').value;
  try {
    var res = await fetch('/admin/api/benchmarks?search=' + encodeURIComponent(search) + '&page=' + benchmarkAdminPage + '&page_size=50');
    var data = await res.json();
    document.getElementById('benchmarkAdminCount').textContent = data.meta ? data.meta.total_all : data.total;
    var html = '';
    data.benchmarks.forEach(function(b) {
      html += '<tr>' +
        '<td>' + (b.id == null ? '' : b.id) + '</td>' +
        '<td><strong>' + escAttr(b.shortName) + '</strong><br><span style="font-size:0.75rem;color:var(--text-secondary)">' + escAttr(b.urlCode || b.benchmarkCode) + '</span></td>' +
        '<td><span class="badge badge-info">' + escAttr(b.category) + '</span></td>' +
        '<td>' + escAttr(b.language) + '</td>' +
        '<td>' + escAttr(b.difficultyLevel) + '</td>' +
        '<td>' + (b.problemCount == null ? '' : b.problemCount) + '</td>' +
        '<td style="font-size:0.75rem">' + escAttr(b.institution) + '</td>' +
        '<td><button class="btn btn-primary btn-sm" onclick="editBenchmark(' + (b.id == null ? '\'\'' : b.id) + ')">✏️</button></td></tr>';
    });
    document.getElementById('benchmarkAdminTableBody').innerHTML = html;
    var pagHtml = '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="benchmarkChangePage(' + (benchmarkAdminPage - 1) + ')" ' + (benchmarkAdminPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span>第 ' + data.page + '/' + data.total_pages + ' 页 · 共 ' + data.total + ' 条</span>' +
      '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="benchmarkChangePage(' + (benchmarkAdminPage + 1) + ')" ' + (benchmarkAdminPage >= data.total_pages ? 'disabled' : '') + '>下一页</button>';
    document.getElementById('benchmarkAdminPagination').innerHTML = pagHtml;
  } catch(e) { showToast('加载评测基准列表失败', 'error'); }
}

function debouncedBenchmarkSearch() {
  clearTimeout(benchmarkAdminSearchTimer);
  benchmarkAdminSearchTimer = setTimeout(function() {
    benchmarkAdminPage = 1;
    searchBenchmarks();
  }, 300);
}

function benchmarkChangePage(page) { benchmarkAdminPage = page; searchBenchmarks(); }

async function editBenchmark(id) {
  var data, b;
  try {
    data = await (await fetch('/admin/api/benchmarks/' + encodeURIComponent(id))).json();
    b = data.benchmark;
  } catch (e) { console.error(e); showToast('加载评测基准失败', 'error'); return; }
  if (!b) { showToast('未找到该评测基准', 'error'); return; }
  editingBenchmarkId = id;
  var fields = ['shortName','fullName','category','language','description','institution','problemCount','metrics','difficultyLevel','releaseDate','datasetLink','paperLink','viewCount','isOfficial'];
  var formHtml = '';
  fields.forEach(function(f) {
    var val = b[f] == null ? '' : String(b[f]);
    formHtml += '<div class="form-group"><label>' + f + '</label><input type="text" id="edit_' + f + '" value="' + escAttr(val) + '"></div>';
  });
  document.getElementById('editForm').innerHTML = formHtml;
  document.getElementById('editModal').classList.add('active');
}

async function saveBenchmark() {
  if (!editingBenchmarkId) return;
  var data = {};
  document.querySelectorAll('#editForm input').forEach(function(input) {
    data[input.id.replace('edit_', '')] = input.value;
  });
  try {
    var res = await fetch('/admin/api/benchmarks/' + encodeURIComponent(editingBenchmarkId), {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    if (res.ok) { showToast('评测基准已更新', 'success'); closeEditModal(); searchBenchmarks(); }
    else { showToast('更新失败', 'error'); }
  } catch(e) { showToast('更新失败', 'error'); }
}

// ============ 使能服务管理 ============
let editingQuoteServiceCode = null;
async function loadQuoteServices() {
  try {
    var res = await fetch('/admin/api/quote/services');
    var data = await res.json();
    document.getElementById('quoteServiceAdminCount').textContent = data.services.length;
    // 填充类别下拉
    var catSel = document.getElementById('qsCategory');
    catSel.innerHTML = data.categories.map(function(c) {
      return '<option value="' + c.id + '">' + escAttr(c.name) + '</option>';
    }).join('');
    var html = '';
    var catMap = {};
    data.categories.forEach(function(c) { catMap[c.id] = c.name; });
    data.services.forEach(function(s) {
      html += '<tr>' +
        '<td><strong>' + escAttr(s.code) + '</strong></td>' +
        '<td>' + escAttr(s.name) + '</td>' +
        '<td>' + s.days + '</td>' +
        '<td><span class="badge badge-info">' + escAttr(catMap[s.category] || s.category) + '</span></td>' +
        '<td>¥ ' + (s.days * 6000).toLocaleString('zh-CN') + '</td>' +
        '<td>' +
          '<button class="btn btn-primary btn-sm" onclick="editQuoteService(" + escJsStr(s.code) + ")">✏️</button> ' +
          '<button class="btn btn-sm" style="background:var(--danger,#e5484d);color:#fff" onclick="deleteQuoteService(" + escJsStr(s.code) + ")">🗑️</button>' +
        '</td></tr>';
    });
    document.getElementById('quoteServiceAdminTableBody').innerHTML = html;
  } catch(e) { showToast('加载使能服务失败', 'error'); }
}

async function addQuoteService() {
  var code = document.getElementById('qsCode').value.trim();
  var name = document.getElementById('qsName').value.trim();
  var days = document.getElementById('qsDays').value;
  var category = document.getElementById('qsCategory').value;
  if (!code || !name) { showToast('请填写服务编码与服务名称', 'error'); return; }
  try {
    var res = await fetch('/admin/api/quote/services', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ code: code, name: name, days: days, category: category })
    });
    var data = await res.json();
    if (res.ok) {
      showToast('已新增服务 ' + code, 'success');
      document.getElementById('qsCode').value = '';
      document.getElementById('qsName').value = '';
      loadQuoteServices();
    } else { showToast(data.error || '新增失败', 'error'); }
  } catch(e) { showToast('新增失败', 'error'); }
}

async function editQuoteService(code) {
  var res, data, s;
  try {
    res = await fetch('/admin/api/quote/services/' + encodeURIComponent(code));
    data = await res.json();
    s = data.service;
  } catch (e) { console.error(e); showToast('加载服务失败', 'error'); return; }
  if (!s) { showToast('未找到该服务', 'error'); return; }
  editingQuoteServiceCode = code;
  var catOptions = data.categories.map(function(c) {
    return '<option value="' + c.id + '" ' + (c.id === s.category ? 'selected' : '') + '>' + escAttr(c.name) + '</option>';
  }).join('');
  var formHtml =
    '<div class="form-group"><label>服务编码（只读）</label><input type="text" id="edit_qs_code" value="' + escAttr(s.code) + '" readonly></div>' +
    '<div class="form-group"><label>服务名称</label><input type="text" id="edit_qs_name" value="' + escAttr(s.name) + '"></div>' +
    '<div class="form-group"><label>人天</label><input type="number" id="edit_qs_days" value="' + s.days + '" min="1"></div>' +
    '<div class="form-group"><label>类别</label><select id="edit_qs_category">' + catOptions + '</select></div>';
  document.getElementById('editForm').innerHTML = formHtml;
  document.getElementById('editModal').classList.add('active');
}

async function saveQuoteService() {
  if (!editingQuoteServiceCode) return;
  var data = {
    name: document.getElementById('edit_qs_name').value,
    days: document.getElementById('edit_qs_days').value,
    category: document.getElementById('edit_qs_category').value
  };
  try {
    var res = await fetch('/admin/api/quote/services/' + encodeURIComponent(editingQuoteServiceCode), {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    if (res.ok) { showToast('服务已更新', 'success'); closeEditModal(); loadQuoteServices(); }
    else { showToast('更新失败', 'error'); }
  } catch(e) { showToast('更新失败', 'error'); }
}

async function deleteQuoteService(code) {
  if (!confirm('确定删除服务 ' + code + ' 吗？删除后报价器不再推荐该服务。')) return;
  try {
    var res = await fetch('/admin/api/quote/services/' + encodeURIComponent(code), { method: 'DELETE' });
    if (res.ok) { showToast('已删除服务 ' + code, 'success'); loadQuoteServices(); }
    else { showToast('删除失败', 'error'); }
  } catch(e) { showToast('删除失败', 'error'); }
}

// ============ 使能服务报价单管理 ============
let quoteSheetPage = 1;
let quoteSheetSearchTimer = null;

async function searchQuoteSheets() {
  var search = (document.getElementById('quoteSheetSearch').value || '').trim().toLowerCase();
  try {
    var res = await fetch('/admin/api/quote/history?search=' + encodeURIComponent(search) + '&page=' + quoteSheetPage + '&page_size=50');
    var data = await res.json();
    var items = (data && data.items) || [];
    var total = (data && data.total) || items.length;
    document.getElementById('quoteSheetAdminCount').textContent = total;
    renderQuoteSheets(items, total);
  } catch(e) { showToast('加载报价单失败', 'error'); }
}

function renderQuoteSheets(items, total) {
  var pageSize = 50;
  var pages = Math.max(1, Math.ceil(total / pageSize));
  if (quoteSheetPage > pages) quoteSheetPage = pages;
  var tbody = document.getElementById('quoteSheetAdminTableBody');
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-secondary)">暂无报价单</td></tr>';
  } else {
    tbody.innerHTML = items.map(function(h) {
      return '<tr>' +
        '<td><strong>' + escAttr(h.id) + '</strong></td>' +
        '<td>' + escAttr(h.customer || '未命名客户') + '</td>' +
        '<td>' + escAttr(h.created_at || '') + '</td>' +
        '<td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escAttr(h.requirement || '') + '">' + escAttr(h.requirement || '') + '</td>' +
        '<td>' + h.total_days + '</td>' +
        '<td>¥ ' + (h.total_amount || 0).toLocaleString('zh-CN') + '</td>' +
        '<td>' +
          '<button class="btn btn-primary btn-sm" onclick="viewQuoteSheet(" + escJsStr(h.id) + ")">👁️ 查看</button> ' +
          '<button class="btn btn-sm" style="background:var(--danger,#e5484d);color:#fff" onclick="deleteQuoteSheet(" + escJsStr(h.id) + ")">🗑️</button>' +
        '</td></tr>';
    }).join('');
  }
  // 分页
  var pag = document.getElementById('quoteSheetAdminPagination');
  if (pages <= 1) { pag.innerHTML = ''; return; }
  var phtml = '';
  for (var i = 1; i <= pages; i++) {
    phtml += '<button class="btn btn-sm ' + (i === quoteSheetPage ? 'btn-primary' : '') + '" style="margin:2px" onclick="quoteSheetPage=' + i + ';searchQuoteSheets()">' + i + '</button>';
  }
  pag.innerHTML = phtml;
}

function debouncedQuoteSheetSearch() {
  clearTimeout(quoteSheetSearchTimer);
  quoteSheetSearchTimer = setTimeout(searchQuoteSheets, 300);
}

function viewQuoteSheet(id) {
  fetch('/admin/api/quote/history/' + encodeURIComponent(id)).then(function(res) { return res.json(); }).then(function(data) {
    var h = data.record;
    if (!h) { showToast('未找到该报价单', 'error'); return; }
    renderQuoteSheetDetail(h);
  }).catch(function() { showToast('加载报价单失败', 'error'); });
}

function renderQuoteSheetDetail(h) {
  var itemsHtml = (h.items || []).map(function(it, i) {
    return '<tr>' +
      '<td>' + (i + 1) + '</td>' +
      '<td>' + escAttr(it.code) + '</td>' +
      '<td>' + escAttr(it.name) + '</td>' +
      '<td>' + it.days + '</td>' +
      '<td>' + (it.price_per_day || 0).toLocaleString('zh-CN') + '</td>' +
      '<td>' + (it.amount || 0).toLocaleString('zh-CN') + '</td>' +
      '</tr>';
  }).join('');
  var html =
    '<div style="margin-bottom:12px;line-height:1.9">' +
      '<div><b>客户名称：</b>' + escAttr(h.customer || '（未填写）') + '</div>' +
      '<div><b>报价日期：</b>' + escAttr(h.created_at || '') + '</div>' +
      '<div><b>服务范围：</b>' + escAttr(h.requirement || '') + '</div>' +
      '<div><b>方案说明：</b>' + escAttr(h.summary || '（无）') + '</div>' +
    '</div>' +
    '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:0.85rem">' +
      '<thead><tr style="background:var(--bg-hover)">' +
        '<th style="padding:8px;border:1px solid var(--border);text-align:left">序号</th>' +
        '<th style="padding:8px;border:1px solid var(--border);text-align:left">服务编码</th>' +
        '<th style="padding:8px;border:1px solid var(--border);text-align:left">服务项</th>' +
        '<th style="padding:8px;border:1px solid var(--border);text-align:left">人天</th>' +
        '<th style="padding:8px;border:1px solid var(--border);text-align:left">单价(元)</th>' +
        '<th style="padding:8px;border:1px solid var(--border);text-align:left">金额(元)</th>' +
      '</tr></thead><tbody>' + itemsHtml + '</tbody></table></div>' +
    '<div style="margin-top:14px;font-weight:700;text-align:right">合计：¥ ' + (h.total_amount || 0).toLocaleString('zh-CN') + ' 元（' + h.total_days + ' 人天）</div>' +
    '<div style="text-align:right;color:var(--text-secondary);margin-top:4px">大写：' + escAttr(h.total_amount_cn || '') + '</div>';
  if (h.plan) {
    html += '<div style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px"><b>技术方案：</b><pre style="white-space:pre-wrap;background:var(--bg-hover);padding:10px;border-radius:6px;font-size:0.8rem;max-height:240px;overflow:auto">' + escAttr(h.plan) + '</pre></div>';
  }
  document.getElementById('quoteSheetModalBody').innerHTML = html;
  document.getElementById('quoteSheetModal').classList.add('active');
}

function closeQuoteSheetModal() {
  document.getElementById('quoteSheetModal').classList.remove('active');
}

async function deleteQuoteSheet(id) {
  if (!confirm('确定删除报价单 ' + id + ' 吗？')) return;
  try {
    var res = await fetch('/admin/api/quote/history/' + encodeURIComponent(id), { method: 'DELETE' });
    if (res.ok) { showToast('已删除报价单', 'success'); searchQuoteSheets(); }
    else { showToast('删除失败', 'error'); }
  } catch(e) { showToast('删除失败', 'error'); }
}

async function deleteAllQuoteSheets() {
  if (!confirm('确定清空全部报价单吗？此操作不可恢复！')) return;
  try {
    // 拉取全部 id（上限 500），再一次性批量删除，避免逐条串行 DELETE
    var res = await fetch('/admin/api/quote/history?page=1&page_size=500');
    var data = await res.json();
    var ids = (data.items || []).map(function(h) { return h.id; });
    if (!ids.length) { showToast('当前没有报价单', 'info'); return; }
    var del = await fetch('/admin/api/quote/history/batch-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: ids })
    });
    var result = await del.json();
    showToast('已清空 ' + (result.deleted || ids.length) + ' 条报价单', 'success');
    quoteSheetPage = 1;
    searchQuoteSheets();
  } catch(e) { showToast('清空失败', 'error'); }
}

// ============ 模型性能管理 ============

let perfAdminPage = 1;
let perfSearchTimer = null;
let perfEditingId = null;

async function perfLoadSources() {
  try {
    var res = await fetch('/admin/api/performance/sources');
    var data = await res.json();
    document.getElementById('perfAdminCount').textContent = data.total || 0;
    var sel = document.getElementById('perfSourceSelect');
    sel.innerHTML = '<option value="">-- 选择本地 data_preformce_data 目录下的 Excel --</option>';
    (data.sources || []).forEach(function(s) {
      var opt = document.createElement('option');
      opt.value = s.path;
      opt.textContent = s.name + '（已导入 ' + (s.imported || 0) + ' 条）';
      sel.appendChild(opt);
    });
    document.getElementById('perfImportMsg').innerHTML = '<span style="color:var(--text-secondary)">数据总条数：' + (data.total || 0) + ' · 更新于：' + (data.updated_at || '-') + '</span>';
    // 同步刷新下方记录列表，避免「刷新源列表」后表格仍显示旧数据
    perfSearch();
  } catch(e) { showToast('加载性能数据源失败', 'error'); }
}

function perfImportMsg(text, type) {
  var el = document.getElementById('perfImportMsg');
  if (!el) return;
  var color = type === 'ok' ? 'var(--success,#2f9e44)' : (type === 'error' ? 'var(--danger,#e5484d)' : 'var(--text-secondary)');
  el.innerHTML = '<span style="color:' + color + '">' + escAttr(text) + '</span>';
}

async function perfImportLocal() {
  var path = document.getElementById('perfSourceSelect').value;
  if (!path) { showToast('请先选择要导入的 Excel 文件', 'error'); return; }
  perfImportMsg('⏳ 正在导入，请稍候…', 'ok');
  try {
    var res = await fetch('/admin/api/performance/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: path })
    });
    var data = await res.json();
    if (data.success) {
      perfImportMsg('✅ 导入完成：新增 ' + data.added + ' 条，当前共 ' + data.total + ' 条', 'ok');
      perfLoadSources();
      perfSearch();
    } else { perfImportMsg('❌ ' + (data.error || '导入失败'), 'error'); }
  } catch(e) { perfImportMsg('❌ 导入失败', 'error'); }
}

async function perfFullReimport() {
  // 全量重导：清空当前性能数据，用所选 Excel 全量重建（Excel 增删改均能同步）
  var path = document.getElementById('perfSourceSelect').value;
  if (!path) { showToast('请先选择要全量重导的 Excel 文件', 'error'); return; }
  var name = document.getElementById('perfSourceSelect').selectedOptions[0].textContent || path;
  if (!confirm('确定要「全量重导」吗？\n将清空当前全部性能数据，并用「' + name + '」重新导入。此操作不可撤销。')) return;
  perfImportMsg('⏳ 正在全量重导，请稍候…', 'ok');
  try {
    var res = await fetch('/admin/api/performance/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: path, mode: 'full' })
    });
    var data = await res.json();
    if (data.success) {
      perfImportMsg('✅ 全量重导完成：共 ' + data.total + ' 条', 'ok');
      perfLoadSources();
      perfSearch();
    } else { perfImportMsg('❌ ' + (data.error || '全量重导失败'), 'error'); }
  } catch(e) { perfImportMsg('❌ 全量重导失败', 'error'); }
}

function perfImportUpload(input) {
  var file = input.files[0];
  if (!file) return;
  var fd = new FormData();
  fd.append('file', file);
  perfImportMsg('⏳ 正在上传并导入 ' + escAttr(file.name) + ' …', 'ok');
  fetch('/admin/api/performance/import', { method: 'POST', body: fd })
    .then(function(r) { return r.json(); })
    .then(function(res) {
      if (res.success) {
        perfImportMsg('✅ 上传导入完成：新增 ' + res.added + ' 条，当前共 ' + res.total + ' 条', 'ok');
        perfLoadSources();
        perfSearch();
      } else { perfImportMsg('❌ ' + (res.error || '导入失败'), 'error'); }
    })
    .catch(function() { perfImportMsg('❌ 上传导入失败', 'error'); })
    .then(function() { input.value = ''; });
}

function perfFmtNum(v) {
  if (v === null || v === undefined || v === '') return '-';
  var n = Number(v);
  if (isNaN(n)) return escAttr(v);
  return n % 1 === 0 ? n : n.toFixed(2);
}

async function perfSearch() {
  var q = (document.getElementById('perfSearch').value || '').trim();
  try {
    var res = await fetch('/admin/api/performance/items?page=' + perfAdminPage + '&page_size=20&q=' + encodeURIComponent(q));
    var data = await res.json();
    document.getElementById('perfAdminCount').textContent = data.total || 0;
    perfRenderItems(data.items || [], data.total);
  } catch(e) { showToast('加载性能数据失败', 'error'); }
}

function perfIoText(it) {
  // 输入/输出优先展示数据源中的实际内容（如 "8K"/"1K"），缺失时回退到格式化数字
  var ir = it.avg_input_raw, orr = it.avg_output_raw;
  if (ir && orr) return escAttr(ir) + '/' + escAttr(orr);
  if (ir) return escAttr(ir) + '/' + perfFmtNum(it.avg_output);
  if (orr) return perfFmtNum(it.avg_input) + '/' + escAttr(orr);
  return perfFmtNum(it.avg_input) + '/' + perfFmtNum(it.avg_output);
}

function perfRenderItems(list, total) {
  var tbody = document.getElementById('perfAdminTableBody');
  if (!list.length) {
    tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:var(--text-secondary)">暂无性能数据，请先导入 Excel 或手动新增</td></tr>';
  } else {
    var html = '';
    list.forEach(function(it) {
      html += '<tr>' +
        '<td><strong>' + escAttr(it.model) + '</strong>' + (it.hardware ? '<br><span style="font-size:0.75rem;color:var(--text-secondary)">' + escAttr(it.hardware) + '</span>' : '') + '</td>' +
        '<td>' + escAttr(it.framework) + '</td>' +
        '<td style="font-size:0.75rem">' + escAttr(it.product) + '</td>' +
        '<td style="font-size:0.75rem">' + escAttr(it.scenario) + '</td>' +
        '<td class="num">' + perfFmtNum(it.total_cards) + '</td>' +
        '<td class="num">' + perfIoText(it) + '</td>' +
        '<td class="num">' + perfFmtNum(it.ttft_ms) + '</td>' +
        '<td class="num">' + perfFmtNum(it.tpot_ms) + '</td>' +
        '<td class="num">' + perfFmtNum(it.output_tps) + '</td>' +
        '<td style="font-size:0.75rem">' + escAttr(it.source_file) + '</td>' +
        '<td>' +
          '<button class="btn btn-primary btn-sm" onclick="perfEdit(" + escJsStr(it.id) + ")">✏️</button> ' +
          '<button class="btn btn-sm" style="background:var(--danger,#e5484d);color:#fff" onclick="perfDelete(" + escJsStr(it.id) + ")">🗑️</button>' +
        '</td></tr>';
    });
    tbody.innerHTML = html;
  }
  var pageSize = 20;
  var pages = Math.max(1, Math.ceil(total / pageSize));
  if (perfAdminPage > pages) { perfAdminPage = pages; }
  var pag = document.getElementById('perfAdminPagination');
  var phtml = '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="perfAdminPage=' + (perfAdminPage - 1) + ';perfSearch()" ' + (perfAdminPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
    '<span style="margin:0 8px">第 ' + perfAdminPage + '/' + pages + ' 页 · 共 ' + total + ' 条</span>' +
    '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="perfAdminPage=' + (perfAdminPage + 1) + ';perfSearch()" ' + (perfAdminPage >= pages ? 'disabled' : '') + '>下一页</button>';
  pag.innerHTML = phtml;
}

function debouncedPerfSearch() {
  clearTimeout(perfSearchTimer);
  perfSearchTimer = setTimeout(function() { perfAdminPage = 1; perfSearch(); }, 300);
}

function perfOpenAdd() {
  perfEditingId = null;
  document.getElementById('perfModalTitle').textContent = '➕ 新增性能记录';
  document.getElementById('perfModalBody').innerHTML = perfFormHtml(null);
  document.getElementById('perfModal').style.display = 'flex';
}

async function perfEdit(id) {
  try {
    var res = await fetch('/admin/api/performance/items?page_size=200');
    var data = await res.json();
    var it = (data.items || []).find(function(x) { return String(x.id) === String(id); });
    if (!it) { showToast('未找到该性能记录', 'error'); return; }
    perfEditingId = id;
    document.getElementById('perfModalTitle').textContent = '✏️ 编辑性能记录';
    document.getElementById('perfModalBody').innerHTML = perfFormHtml(it);
    document.getElementById('perfModal').style.display = 'flex';
  } catch(e) { showToast('加载性能记录失败', 'error'); }
}

function perfFormHtml(it) {
  it = it || {};
  function f(field) { return it[field] == null ? '' : it[field]; }
  function numField(field, label, placeholder) {
    return '<div class="form-group"><label>' + label + '</label><input type="number" step="any" id="perf_f_' + field + '" value="' + escAttr(f(field)) + '" placeholder="' + placeholder + '"></div>';
  }
  return '' +
    '<div class="form-group"><label>模型名称 *</label><input type="text" id="perf_f_model" value="' + escAttr(f('model')) + '" placeholder="例如 Llama3-70B"></div>' +
    '<div class="form-row">' +
      '<div class="form-group"><label>框架</label><input type="text" id="perf_f_framework" value="' + escAttr(f('framework')) + '" placeholder="例如 MindIE"></div>' +
      '<div class="form-group"><label>版本</label><input type="text" id="perf_f_version" value="' + escAttr(f('version')) + '" placeholder="例如 1.0"></div>' +
    '</div>' +
    '<div class="form-row">' +
      '<div class="form-group"><label>产品组合</label><input type="text" id="perf_f_product" value="' + escAttr(f('product')) + '" placeholder="例如 Atlas 800I A2"></div>' +
      '<div class="form-group"><label>硬件</label><input type="text" id="perf_f_hardware" value="' + escAttr(f('hardware')) + '" placeholder="例如 Ascend 910B"></div>' +
    '</div>' +
    '<div class="form-row">' +
      '<div class="form-group"><label>场景</label><input type="text" id="perf_f_scenario" value="' + escAttr(f('scenario')) + '" placeholder="例如 长序列推理"></div>' +
      '<div class="form-group"><label>数据格式</label><input type="text" id="perf_f_data_format" value="' + escAttr(f('data_format')) + '" placeholder="例如 FP16"></div>' +
    '</div>' +
    '<div class="form-row">' +
      numField('total_cards', '卡数', '例如 8') +
      numField('avg_input', '平均输入 tokens', '例如 2048') +
    '</div>' +
    '<div class="form-row">' +
      numField('avg_output', '平均输出 tokens', '例如 256') +
      numField('prefix_cache', '前缀缓存', '例如 0') +
    '</div>' +
    '<div class="form-row">' +
      numField('concurrency', '并发数', '例如 32') +
      numField('max_concurrency', '最大并发', '例如 64') +
    '</div>' +
    '<div class="form-row">' +
      numField('ttft_ms', 'TTFT(ms)', '首 token 时延') +
      numField('tpot_ms', 'TPOT(ms)', '每 token 时延') +
    '</div>' +
    '<div class="form-row">' +
      numField('output_tps', '输出吞吐(tps)', '输出 token/s') +
      numField('qps', 'QPS', '请求/秒') +
    '</div>' +
    '<div class="form-group"><label>备注</label><textarea id="perf_f_note" rows="2" placeholder="可选">' + escAttr(f('note')) + '</textarea></div>' +
    '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;">' +
      '<button class="btn btn-primary" onclick="perfSave()">💾 保存</button>' +
      '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="perfCloseModal()">取消</button>' +
    '</div>';
}

function perfCloseModal() {
  document.getElementById('perfModal').style.display = 'none';
}

function perfFormVal(id) {
  var el = document.getElementById(id);
  return el ? el.value : '';
}

async function perfSave() {
  var model = perfFormVal('perf_f_model').trim();
  if (!model) { showToast('模型名称不能为空', 'error'); return; }
  var payload = {
    model: model,
    framework: perfFormVal('perf_f_framework'),
    version: perfFormVal('perf_f_version'),
    product: perfFormVal('perf_f_product'),
    hardware: perfFormVal('perf_f_hardware'),
    scenario: perfFormVal('perf_f_scenario'),
    data_format: perfFormVal('perf_f_data_format'),
    total_cards: perfFormVal('perf_f_total_cards'),
    avg_input: perfFormVal('perf_f_avg_input'),
    avg_output: perfFormVal('perf_f_avg_output'),
    prefix_cache: perfFormVal('perf_f_prefix_cache'),
    concurrency: perfFormVal('perf_f_concurrency'),
    max_concurrency: perfFormVal('perf_f_max_concurrency'),
    ttft_ms: perfFormVal('perf_f_ttft_ms'),
    tpot_ms: perfFormVal('perf_f_tpot_ms'),
    output_tps: perfFormVal('perf_f_output_tps'),
    qps: perfFormVal('perf_f_qps'),
    note: perfFormVal('perf_f_note')
  };
  try {
    var isEdit = !!perfEditingId;
    var url = '/admin/api/performance/items';
    var opts = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) };
    if (isEdit) {
      url = '/admin/api/performance/items/' + encodeURIComponent(perfEditingId);
      opts = { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) };
    }
    var res = await fetch(url, opts);
    var data = await res.json();
    if (data.success) {
      showToast(isEdit ? '已保存修改' : '已新增记录', 'success');
      perfCloseModal();
      perfLoadSources();
      perfSearch();
    } else { showToast(data.error || '保存失败', 'error'); }
  } catch(e) { showToast('保存失败', 'error'); }
}

async function perfDelete(id) {
  if (!confirm('确定删除该性能记录吗？')) return;
  try {
    var res = await fetch('/admin/api/performance/items/' + encodeURIComponent(id), { method: 'DELETE' });
    if (res.ok) { showToast('已删除', 'success'); perfLoadSources(); perfSearch(); }
    else { showToast('删除失败', 'error'); }
  } catch(e) { showToast('删除失败', 'error'); }
}

// ============ 全球AI大模型管理 ============

let globalModelAdminPage = 1;
let globalModelSearchTimer = null;
let editingGlobalModelId = null;

async function searchGlobalModels() {
  var search = document.getElementById('globalModelAdminSearch').value;
  try {
    var res = await fetch('/admin/api/global-models?search=' + encodeURIComponent(search) + '&page=' + globalModelAdminPage + '&page_size=50');
    var data = await res.json();
    document.getElementById('globalModelAdminCount').textContent = data.meta ? data.meta.total_all : data.total;
    var html = '';
    data.models.forEach(function(m) {
      html += '<tr>' +
        '<td>' + (m.model_id == null ? '' : m.model_id) + '</td>' +
        '<td><strong>' + escAttr(m.model_abbr_name) + '</strong></td>' +
        '<td style="font-size:0.75rem">' + escAttr(m.model_code) + '</td>' +
        '<td style="font-size:0.75rem">' + escAttr(m.orgName) + '</td>' +
        '<td><span class="badge badge-info">' + escAttr(m.model_TYPE_NAME) + '</span></td>' +
        '<td style="font-size:0.75rem">' + escAttr(m.parameterSizeDisplay || m.parameter_size) + '</td>' +
        '<td style="font-size:0.75rem">' + escAttr(m.commercial_usage) + '</td>' +
        '<td><button class="btn btn-primary btn-sm" onclick="editGlobalModel(' + (m.model_id == null ? '\'\'' : m.model_id) + ')">✏️</button></td></tr>';
    });
    document.getElementById('globalModelAdminTableBody').innerHTML = html;
    var pagHtml = '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="globalModelChangePage(' + (globalModelAdminPage - 1) + ')" ' + (globalModelAdminPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span>第 ' + data.page + '/' + data.total_pages + ' 页 · 共 ' + data.total + ' 条</span>' +
      '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="globalModelChangePage(' + (globalModelAdminPage + 1) + ')" ' + (globalModelAdminPage >= data.total_pages ? 'disabled' : '') + '>下一页</button>';
    document.getElementById('globalModelAdminPagination').innerHTML = pagHtml;
  } catch(e) { showToast('加载全球AI大模型列表失败', 'error'); }
}

function debouncedGlobalModelSearch() {
  clearTimeout(globalModelSearchTimer);
  globalModelSearchTimer = setTimeout(function() {
    globalModelAdminPage = 1;
    searchGlobalModels();
  }, 300);
}

function globalModelChangePage(page) { globalModelAdminPage = page; searchGlobalModels(); }

async function editGlobalModel(id) {
  var data, m;
  try {
    data = await (await fetch('/admin/api/global-models/' + encodeURIComponent(id))).json();
    m = data.model;
  } catch (e) { console.error(e); showToast('加载全球模型失败', 'error'); return; }
  if (!m) { showToast('未找到该模型', 'error'); return; }
  editingGlobalModelId = id;
  var fields = ['model_abbr_name','model_code','model_TYPE_NAME','orgName','parameterSizeDisplay','parameter_size','commercial_usage','viewCount','releaseStatus','lifecycleStatus','publish_time','knowledgeCutoffDate','totalParamsB','activeParamsB','scaleBucket','aliases'];
  var formHtml = '';
  fields.forEach(function(f) {
    var val = m[f] == null ? '' : String(m[f]);
    formHtml += '<div class="form-group"><label>' + f + '</label><input type="text" id="edit_' + f + '" value="' + escAttr(val) + '"></div>';
  });
  document.getElementById('editForm').innerHTML = formHtml;
  document.getElementById('editModal').classList.add('active');
}

async function saveGlobalModel() {
  if (!editingGlobalModelId) return;
  var data = {};
  document.querySelectorAll('#editForm input').forEach(function(input) {
    data[input.id.replace('edit_', '')] = input.value;
  });
  try {
    var res = await fetch('/admin/api/global-models/' + encodeURIComponent(editingGlobalModelId), {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    if (res.ok) { showToast('模型已更新', 'success'); closeEditModal(); searchGlobalModels(); }
    else { showToast('更新失败', 'error'); }
  } catch(e) { showToast('更新失败', 'error'); }
}

// ============ 全球硬件参数管理 ============

let editingHardwareParamId = null;
let editingHardwareParamSource = null;
let hardwareParamSearchTimer = null;

// GPU_LIB 字段（LLM Token 计算器与后台共用）：
// name=GPU型号, bw=显存带宽(GB/s), fp16=FP16算力(TFLOPS), fp8=FP8算力(TFLOPS),
// vram=显存容量(GB), memType=显存类型, ic=互联带宽(GB/s), price=参考价格(元)
var GL_FIELDS = [
  {key:'name', label:'GPU型号'},
  {key:'bw', label:'显存带宽(GB/s)'},
  {key:'fp16', label:'FP16算力(TFLOPS)'},
  {key:'fp8', label:'FP8算力(TFLOPS)'},
  {key:'vram', label:'显存容量(GB)'},
  {key:'memType', label:'显存类型'},
  {key:'ic', label:'互联带宽(GB/s)'},
  {key:'price', label:'参考价格(元)'}
];
var GL_NUMERIC = ['bw','fp16','fp8','vram','ic','price'];

function glFmt(v) {
  if (v === null || v === undefined || v === '') return '<span style="color:var(--text-secondary)">-</span>';
  if (v === -1) return '<span style="color:var(--text-secondary)">-</span>';
  return Number(v).toLocaleString('en-US');
}

// 将字符串安全嵌入 HTML 属性中的 JS 字符串（单引号包裹 + HTML 实体转义）
function escJs(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

async function searchHardwareParams() {
  var search = document.getElementById('hardwareParamSearch').value;
  var source = document.getElementById('hardwareSourceFilter').value;
  try {
    var res = await fetch('/admin/api/gpu-lib?search=' + encodeURIComponent(search) + '&source=' + encodeURIComponent(source));
    var data = await res.json();
    document.getElementById('hardwareParamCount').textContent = data.total_all;
    var html = '';
    data.hardware.forEach(function(h) {
      var srcBadge = h._fromGlobal ? '<span class="badge badge-info">全球提取</span>' : '<span class="badge badge-success">内置</span>';
      html += '<tr>' +
        '<td><strong>' + escAttr(h.name) + '</strong> ' + srcBadge + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + glFmt(h.bw) + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + glFmt(h.fp16) + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + glFmt(h.fp8) + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + glFmt(h.vram) + '</td>' +
        '<td style="font-size:0.78rem">' + escAttr(h.memType || '-') + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + glFmt(h.ic) + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + glFmt(h.price) + '</td>' +
        '<td style="white-space:nowrap">' +
          '<button class="btn btn-primary btn-sm" onclick="editHardwareParam(\'' + escJs(h.name) + '\')">✏️</button> ' +
          '<button class="btn btn-danger btn-sm" onclick="deleteHardwareParam(\'' + escJs(h.name) + '\')">🗑️</button>' +
        '</td></tr>';
    });
    document.getElementById('hardwareParamTableBody').innerHTML = html || '<tr><td colspan="9" style="text-align:center;color:var(--text-secondary)">暂无硬件参数</td></tr>';
  } catch(e) { showToast('加载硬件参数失败', 'error'); }
}

function debouncedHardwareParamSearch() {
  clearTimeout(hardwareParamSearchTimer);
  hardwareParamSearchTimer = setTimeout(searchHardwareParams, 300);
}

function buildGlForm(g) {
  var formHtml = '';
  GL_FIELDS.forEach(function(f) {
    var val = g ? g[f.key] : '';
    if (val == null) val = '';
    formHtml += '<div class="form-group"><label>' + f.label + '</label><input type="text" id="edit_' + f.key + '" value="' + escAttr(String(val)) + '"' + (f.key === 'name' ? ' placeholder="GPU型号（必填）"' : '') + '></div>';
  });
  return formHtml;
}

function editHardwareParam(name) {
  fetch('/admin/api/gpu-lib')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var h = (data.hardware || []).find(function(x) { return String(x.name) === String(name); });
      if (!h) { showToast('未找到该 GPU', 'error'); return; }
      editingHardwareParamId = name;
      editingHardwareParamSource = null;
      document.getElementById('editForm').innerHTML = buildGlForm(h);
      document.getElementById('editModal').classList.add('active');
    })
    .catch(function() { showToast('加载硬件失败', 'error'); });
}

function addHardwareParam() {
  editingHardwareParamId = '__new__';
  editingHardwareParamSource = null;
  document.getElementById('editForm').innerHTML = buildGlForm(null);
  document.getElementById('editModal').classList.add('active');
}

async function saveHardwareParam() {
  if (!editingHardwareParamId) return;
  var data = {};
  var name = (document.getElementById('edit_name').value || '').trim();
  if (!name) { showToast('GPU型号不能为空', 'error'); return; }
  GL_FIELDS.forEach(function(f) {
    var el = document.getElementById('edit_' + f.key);
    if (!el) return;
    var v = el.value.trim();
    if (f.key === 'name') { data.name = v; return; }
    if (f.key === 'memType') { data.memType = v; return; }
    // 数值字段：空则 null，-1 保持 -1
    if (v === '') { data[f.key] = null; }
    else {
      var n = Number(v);
      data[f.key] = isNaN(n) ? null : n;
    }
  });
  var isNew = editingHardwareParamId === '__new__';
  var url = isNew ? '/admin/api/gpu-lib' : '/admin/api/gpu-lib/' + encodeURIComponent(editingHardwareParamId);
  try {
    var res = await fetch(url, {
      method: isNew ? 'POST' : 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    var result = await res.json();
    if (res.ok) { showToast(isNew ? 'GPU 已新增' : 'GPU 已更新', 'success'); closeEditModal(); searchHardwareParams(); }
    else { showToast(result.error || '保存失败', 'error'); }
  } catch(e) { showToast('保存失败', 'error'); }
}

async function deleteHardwareParam(name) {
  if (!confirm('确定删除 GPU「' + name + '」？')) return;
  try {
    var res = await fetch('/admin/api/gpu-lib/' + encodeURIComponent(name), {method: 'DELETE'});
    if (res.ok) { showToast('GPU 已删除', 'success'); searchHardwareParams(); }
    else { showToast('删除失败', 'error'); }
  } catch(e) { showToast('删除失败', 'error'); }
}

// ============ 全球AI模型参数管理 ============
let editingModelParamId = null;
let modelParamPage = 1;
let modelParamSearchTimer = null;

// 字段：名称、总参、激活、层数、注意力头数、KV头数、头维度、上下文、架构、是否MoE
var MP_FIELDS = [
  {key:'name', label:'名称'},
  {key:'totalParams', label:'总参(B)'},
  {key:'activeParams', label:'激活(B)'},
  {key:'layers', label:'层数'},
  {key:'attentionHeads', label:'注意力头数'},
  {key:'kvHeads', label:'KV头数'},
  {key:'headDim', label:'头维度'},
  {key:'context', label:'上下文(tokens)'},
  {key:'architecture', label:'架构(Dense/MoE)'},
  {key:'isMoE', label:'是否MoE(是/否)'}
];
var MP_NUMERIC = ['totalParams','activeParams','layers','attentionHeads','kvHeads','headDim','context'];

function mpFmt(v) {
  if (v === null || v === undefined || v === '') return '<span style="color:var(--text-secondary)">-</span>';
  return Number(v).toLocaleString('en-US');
}

async function searchModelParams(page) {
  if (page) modelParamPage = page;
  var search = document.getElementById('modelParamSearch').value;
  var hasParams = document.getElementById('modelParamHasFilter').value;
  try {
    var res = await fetch('/admin/api/model-params?search=' + encodeURIComponent(search) + '&hasParams=' + encodeURIComponent(hasParams) + '&page=' + modelParamPage + '&page_size=50');
    var data = await res.json();
    document.getElementById('modelParamCount').textContent = data.total_all;
    var html = '';
    data.models.forEach(function(m) {
      var moeBadge = m.isMoE === '是'
        ? '<span class="badge badge-warning">MoE</span>'
        : (m.isMoE === '否' ? '<span class="badge badge-success">Dense</span>' : '<span style="color:var(--text-secondary)">-</span>');
      html += '<tr>' +
        '<td><strong>' + escAttr(m.name) + '</strong><br><span style="color:var(--text-secondary);font-size:0.7rem">' + escAttr(m.modelCode) + '</span></td>' +
        '<td style="text-align:right;font-size:0.78rem">' + mpFmt(m.totalParams) + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + mpFmt(m.activeParams) + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + mpFmt(m.layers) + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + mpFmt(m.attentionHeads) + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + mpFmt(m.kvHeads) + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + mpFmt(m.headDim) + '</td>' +
        '<td style="text-align:right;font-size:0.78rem">' + mpFmt(m.context) + '</td>' +
        '<td style="font-size:0.78rem">' + escAttr(m.architecture || '-') + '</td>' +
        '<td style="font-size:0.78rem">' + moeBadge + '</td>' +
        '<td style="white-space:nowrap">' +
          '<button class="btn btn-primary btn-sm" title="从HF补全架构" onclick="fetchHfModelParam(\'' + escJs(m.modelCode) + '\')">⬇️</button> ' +
          '<button class="btn btn-primary btn-sm" onclick="editModelParam(\'' + escJs(m.modelCode) + '\')">✏️</button> ' +
          '<button class="btn btn-danger btn-sm" onclick="deleteModelParam(\'' + escJs(m.modelCode) + '\')">🗑️</button>' +
        '</td></tr>';
    });
    document.getElementById('modelParamTableBody').innerHTML = html || '<tr><td colspan="11" style="text-align:center;color:var(--text-secondary)">暂无模型参数</td></tr>';
    var pagHtml = '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="searchModelParams(' + (modelParamPage - 1) + ')" ' + (modelParamPage <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span>第 ' + data.page + '/' + data.total_pages + ' 页 · 共 ' + data.total + ' 条</span>' +
      '<button class="btn btn-sm" style="background:var(--bg-hover);color:var(--text)" onclick="searchModelParams(' + (modelParamPage + 1) + ')" ' + (modelParamPage >= data.total_pages ? 'disabled' : '') + '>下一页</button>';
    document.getElementById('modelParamPagination').innerHTML = pagHtml;
  } catch(e) { showToast('加载模型参数失败', 'error'); }
}

function buildMpForm(m, isNew) {
  var formHtml = '';
  // 模型标识（新增可填，编辑只读）
  var codeVal = m ? (m.modelCode || '') : '';
  formHtml += '<div class="form-group"><label>模型标识(modelCode)</label><input type="text" id="edit_modelCode" value="' + escAttr(codeVal) + '" ' + (isNew ? 'placeholder="如 glm-5-3"' : 'readonly') + '></div>';
  MP_FIELDS.forEach(function(f) {
    var val = m ? m[f.key] : '';
    if (val == null) val = '';
    formHtml += '<div class="form-group"><label>' + f.label + '</label><input type="text" id="edit_' + f.key + '" value="' + escAttr(String(val)) + '"' + (f.key === 'name' ? ' placeholder="模型名称（必填）"' : '') + '></div>';
  });
  return formHtml;
}

function editModelParam(code) {
  fetch('/admin/api/model-params?search=' + encodeURIComponent(code) + '&page_size=100')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var m = (data.models || []).find(function(x) { return String(x.modelCode) === String(code); });
      if (!m) { showToast('未找到该模型', 'error'); return; }
      editingModelParamId = code;
      document.getElementById('editForm').innerHTML = buildMpForm(m, false);
      document.getElementById('editModal').classList.add('active');
    })
    .catch(function() { showToast('加载模型失败', 'error'); });
}

function addModelParam() {
  editingModelParamId = '__new__';
  document.getElementById('editForm').innerHTML = buildMpForm(null, true);
  document.getElementById('editModal').classList.add('active');
}

async function saveModelParam() {
  if (!editingModelParamId) return;
  var data = {};
  var code = (document.getElementById('edit_modelCode').value || '').trim();
  var name = (document.getElementById('edit_name').value || '').trim();
  if (!code) { showToast('模型标识不能为空', 'error'); return; }
  if (!name) { showToast('模型名称不能为空', 'error'); return; }
  data.modelCode = code;
  data.name = name;
  MP_FIELDS.forEach(function(f) {
    if (f.key === 'name') return;
    var el = document.getElementById('edit_' + f.key);
    if (!el) return;
    var v = el.value.trim();
    if (f.key === 'architecture' || f.key === 'isMoE') { data[f.key] = v; return; }
    if (v === '') { data[f.key] = null; }
    else {
      var n = Number(v);
      data[f.key] = isNaN(n) ? null : n;
    }
  });
  var isNew = editingModelParamId === '__new__';
  var url = isNew ? '/admin/api/model-params' : '/admin/api/model-params/' + encodeURIComponent(editingModelParamId);
  try {
    var res = await fetch(url, {
      method: isNew ? 'POST' : 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    var result = await res.json();
    if (res.ok) { showToast(isNew ? '模型参数已新增' : '模型参数已更新', 'success'); closeEditModal(); searchModelParams(); }
    else { showToast(result.error || '保存失败', 'error'); }
  } catch(e) { showToast('保存失败', 'error'); }
}

async function deleteModelParam(code) {
  if (!confirm('确定删除模型「' + code + '」？')) return;
  try {
    var res = await fetch('/admin/api/model-params/' + encodeURIComponent(code), {method: 'DELETE'});
    if (res.ok) { showToast('模型参数已删除', 'success'); searchModelParams(); }
    else { showToast('删除失败', 'error'); }
  } catch(e) { showToast('删除失败', 'error'); }
}

async function fetchHfModelParam(code) {
  if (!confirm('从 HF（hf-mirror）抓取「' + code + '」的 config.json 补全层数/KV头数/头维度/上下文？')) return;
  showToast('正在从 HF 补全，请稍候...', 'info');
  try {
    var res = await fetch('/admin/api/model-params/fetch-hf', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({code: code})
    });
    var result = await res.json();
    var r = (result.results || [])[0];
    if (r && r.success) {
      showToast('HF 补全成功（' + (r.hfRepo || '') + '）', 'success');
    } else {
      showToast((r && r.error) || 'HF 补全失败', 'error');
    }
    searchModelParams();
  } catch(e) { showToast('HF 补全失败', 'error'); }
}

function debouncedModelParamSearch() {
  clearTimeout(modelParamSearchTimer);
  modelParamSearchTimer = setTimeout(function() {
    modelParamPage = 1;
    searchModelParams(1);
  }, 300);
}

async function fetchHfAllModelParams() {
  if (!confirm('将从 HF（hf-mirror）对所有模型一键补全架构字段（层数/KV头数/头维度/上下文）？\n该操作需要较长时间，闭源模型（无 HF 仓库）会自动跳过。')) return;
  var btn = document.querySelector('.search-bar button[onclick="fetchHfAllModelParams()"]');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 补全中...'; }
  try {
    // 1. 获取所有模型 codes
    var res = await fetch('/admin/api/model-params?page=1&page_size=1000');
    var data = await res.json();
    var codes = (data.models || []).map(function(m) { return m.modelCode; });
    if (!codes.length) { showToast('没有可补全的模型', 'error'); return; }

    // 2. 分批调用后端（每批 10 个），显示进度
    var batchSize = 10;
    var successCount = 0;
    var total = codes.length;
    for (var i = 0; i < total; i += batchSize) {
      var batch = codes.slice(i, i + batchSize);
      showToast('一键补全中... ' + Math.min(i + batchSize, total) + '/' + total + ' 个（成功 ' + successCount + '）', 'info');
      try {
        var r = await fetch('/admin/api/model-params/fetch-hf', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({codes: batch})
        });
        var result = await r.json();
        successCount += result.success_count || 0;
      } catch(e) { /* 单批失败继续 */ }
    }
    showToast('一键补全完成：成功补全 ' + successCount + ' / ' + total + ' 个', 'success');
    searchModelParams(1);
  } catch(e) {
    showToast('一键补全失败', 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '⬇️ 一键补全'; }
  }
}
