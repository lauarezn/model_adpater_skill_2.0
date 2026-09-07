// ============ Admin 管理后台 JavaScript ============

let currentPage = 1;
let selectedIds = new Set();
let editingModelId = null;
let searchTimer = null;
let filtersInitialized = false;

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
  document.querySelector('.sidebar a[onclick*="' + tab + '"]').classList.add('active');
  if (tab === 'models') searchModels();
  if (tab === 'acl-models') searchAclModels();
  if (tab === 'mindie-models') searchMindieModels();
  if (tab === 'crawler') refreshCrawlerStatus();
  if (tab === 'benchmarks') searchBenchmarks();
  if (tab === 'global-models') searchGlobalModels();
  if (tab === 'model-params') searchModelParams();
  if (tab === 'hardware-params') searchHardwareParams();
  if (tab === 'backup') listBackups();
  if (tab === 'sources') loadSourceStats();
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
        '<td><button class="btn btn-primary btn-sm" onclick="editModel(\'' + (m.id || '').replace(/'/g, "\\'") + '\')">✏️</button> ' +
        '<button class="btn btn-danger btn-sm" onclick="deleteModel(\'' + (m.id || '').replace(/'/g, "\\'") + '\')">🗑️</button></td></tr>';
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

function closeEditModal() { document.getElementById('editModal').classList.remove('active'); editingModelId = null; editingBenchmarkId = null; editingGlobalModelId = null; editingHardwareParamId = null; editingHardwareParamSource = null; editingModelParamId = null; }

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
          return '<div>' + String(l).replace(/</g, '<').replace(/>/g, '>') + '</div>';
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
        '<button class="btn btn-primary btn-sm" onclick="restoreBackup(\'' + (b.name || '').replace(/'/g, "\\'") + '\')">🔄 恢复</button></div>';
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
      var modelUrl = m.model_url || '';
      var urlHtml = modelUrl ? '<a href="' + modelUrl.replace(/"/g, '"') + '" target="_blank" style="color:var(--primary);font-size:0.75rem" title="' + modelUrl.replace(/"/g, '"') + '">🔗 查看</a>' : '<span style="color:var(--text-secondary);font-size:0.75rem">无</span>';
      html += '<tr>' +
        '<td><strong>' + (m.name || '').replace(/</g, '<') + '</strong></td>' +
        '<td style="font-size:0.8rem">' + (m.folder || '').replace(/</g, '<') + '</td>' +
        '<td><span class="badge badge-info">' + (m.category || '').replace(/</g, '<') + '</span></td>' +
        '<td><span class="badge badge-info">' + (m.source || '').replace(/</g, '<') + '</span></td>' +
        '<td><span class="badge badge-success">' + (m.data_dir || '').replace(/</g, '<') + '</span></td>' +
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
      var modelUrl = m.model_url || '';
      var urlHtml = modelUrl ? '<a href="' + modelUrl.replace(/"/g, '"') + '" target="_blank" style="color:var(--primary);font-size:0.75rem" title="' + modelUrl.replace(/"/g, '"') + '">🔗 查看</a>' : '<span style="color:var(--text-secondary);font-size:0.75rem">无</span>';
      html += '<tr>' +
        '<td><strong>' + (m.name || '').replace(/</g, '<') + '</strong></td>' +
        '<td style="font-size:0.8rem">' + (m.folder || '').replace(/</g, '<') + '</td>' +
        '<td><span class="badge badge-info">' + (m.category || '').replace(/</g, '<') + '</span></td>' +
        '<td><span class="badge badge-info">' + (m.source || '').replace(/</g, '<') + '</span></td>' +
        '<td><span class="badge badge-success">' + (m.data_dir || '').replace(/</g, '<') + '</span></td>' +
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
  return String(s == null ? '' : s).replace(/&/g, '&').replace(/"/g, '"').replace(/</g, '<').replace(/>/g, '>');
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
  var data = await (await fetch('/admin/api/benchmarks?page=1&page_size=2000')).json();
  var b = data.benchmarks.find(function(x) { return String(x.id) === String(id); });
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
  var data = await (await fetch('/admin/api/global-models?page=1&page_size=2000')).json();
  var m = data.models.find(function(x) { return String(x.model_id) === String(id); });
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
