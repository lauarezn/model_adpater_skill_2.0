// ============ 小模型页面（ACL_PyTorch + PyTorch 目录）============

let aclModels = [];
let aclFilteredModels = [];
let aclCurrentPage = 1;
const ACL_PAGE_SIZE = 50;

// 分类图标映射
const ACL_CATEGORY_ICONS = {
  '语音': '🎤',
  '计算机视觉': '👁️',
  '嵌入': '🔗',
  '具身智能': '🤖',
  '基础模型': '🧠',
  'NLP': '📝',
  'OCR': '📄',
  '知识图谱': '📊',
  '强化学习': '🎮',
  '多模态': '🖼️',
  '扩散模型': '✨',
  '自动驾驶': '🚗',
  '其他': '📦'
};

// 来源标签样式
const ACL_SOURCE_CLASSES = {
  'built-in': 'source-ascend',
  'contrib': 'source-gitcode'
};
const ACL_SOURCE_LABELS = {
  'built-in': '内置',
  'contrib': '社区'
};

// 数据目录标签
const ACL_DATA_DIR_LABELS = {
  'ACL_PyTorch': '推理',
  'PyTorch': '训练'
};

function loadAclModels() {
  const loadingEl = document.getElementById('aclLoadingIndicator');
  const gridEl = document.getElementById('aclModelGrid');
  const statsEl = document.getElementById('aclModelCount');
  const aclStatsEl = document.getElementById('aclAclCount');
  const ptStatsEl = document.getElementById('aclPtCount');

  fetch('/admin/api/acl-models')
    .then(resp => resp.json())
    .then(data => {
      aclModels = data.models;
      aclFilteredModels = [...aclModels];

      // 更新统计
      if (statsEl) statsEl.textContent = aclModels.length;
      if (aclStatsEl) aclStatsEl.textContent = data.acl_total || 0;
      if (ptStatsEl) ptStatsEl.textContent = data.pytorch_total || 0;

      // 填充分类筛选器
      const catFilter = document.getElementById('aclCategoryFilter');
      if (catFilter && data.categories) {
        catFilter.innerHTML = '<option value="all">全部分类</option>' +
          data.categories.map(c => `<option value="${c}">${ACL_CATEGORY_ICONS[c] || '📦'} ${c}</option>`).join('');
      }

      // 填充来源筛选器
      const srcFilter = document.getElementById('aclSourceFilter');
      if (srcFilter && data.sources) {
        srcFilter.innerHTML = '<option value="all">全部来源</option>' +
          data.sources.map(s => `<option value="${s}">${ACL_SOURCE_LABELS[s] || s}</option>`).join('');
      }

      // 填充数据目录筛选器
      const dirFilter = document.getElementById('aclDataDirFilter');
      if (dirFilter && data.data_dirs) {
        dirFilter.innerHTML = '<option value="all">全部目录</option>' +
          data.data_dirs.map(d => `<option value="${d}">${ACL_DATA_DIR_LABELS[d] || d}</option>`).join('');
      }

      // 隐藏 loading，显示网格
      loadingEl.style.display = 'none';
      gridEl.style.display = '';

      renderAclModels(aclModels);
      renderAclPagination(Math.ceil(aclModels.length / ACL_PAGE_SIZE));
    })
    .catch(err => {
      console.warn('小模型数据加载失败:', err);
      loadingEl.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><p>小模型数据加载失败，请刷新重试</p></div>';
    });
}

function renderAclModels(data) {
  const grid = document.getElementById('aclModelGrid');
  const empty = document.getElementById('aclEmptyState');

  if (data.length === 0) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  grid.innerHTML = data.map(m => {
    const sourceClass = ACL_SOURCE_CLASSES[m.source] || 'source-ascend';
    const sourceLabel = ACL_SOURCE_LABELS[m.source] || m.source;
    const icon = ACL_CATEGORY_ICONS[m.category] || '📦';
    const dataDirLabel = ACL_DATA_DIR_LABELS[m.data_dir] || m.data_dir || '';
    const dataDirClass = m.data_dir === 'PyTorch' ? 'source-sglang' : 'source-ascend';
    const modelUrl = m.model_url || '';

    return `
      <div class="acl-model-card" onclick="showAclModelDetail('${m.name.replace(/'/g, "\\'")}')">
        <div class="acl-model-card-header">
          <div>
            <div class="acl-model-card-name">${m.name}</div>
            <div class="acl-model-card-folder">📁 ${m.folder}</div>
          </div>
          <span class="meta-tag ${sourceClass}">${sourceLabel}</span>
        </div>
        <div class="acl-model-card-meta">
          <span class="meta-tag category">${icon} ${m.category}</span>
          ${dataDirLabel ? `<span class="meta-tag ${dataDirClass}">${dataDirLabel}</span>` : ''}
          ${modelUrl ? `<a href="${modelUrl}" target="_blank" class="meta-tag source-link" onclick="event.stopPropagation()">🔗 部署指南</a>` : ''}
        </div>
        <p class="acl-model-card-desc">${m.description}</p>
      </div>
    `;
  }).join('');
}

function filterAclModels() {
  const search = document.getElementById('aclSearchInput').value.toLowerCase();
  const category = document.getElementById('aclCategoryFilter').value;
  const source = document.getElementById('aclSourceFilter').value;
  const dataDir = document.getElementById('aclDataDirFilter').value;

  aclFilteredModels = aclModels.filter(m => {
    if (search && !m.name.toLowerCase().includes(search) &&
        !m.folder.toLowerCase().includes(search) &&
        !m.description.toLowerCase().includes(search)) return false;
    if (category !== 'all' && m.category !== category) return false;
    if (source !== 'all' && m.source !== source) return false;
    if (dataDir !== 'all' && m.data_dir !== dataDir) return false;
    return true;
  });

  aclCurrentPage = 1;
  renderAclPage();
}

function renderAclPage() {
  const totalPages = Math.ceil(aclFilteredModels.length / ACL_PAGE_SIZE) || 1;
  const start = (aclCurrentPage - 1) * ACL_PAGE_SIZE;
  const end = Math.min(start + ACL_PAGE_SIZE, aclFilteredModels.length);
  const pageData = aclFilteredModels.slice(start, end);

  renderAclModels(pageData);
  renderAclPagination(totalPages);
}

function renderAclPagination(totalPages) {
  const pagination = document.getElementById('aclPagination');
  const pageNumbers = document.getElementById('aclPageNumbers');
  const pagePrev = document.getElementById('aclPagePrev');
  const pageNext = document.getElementById('aclPageNext');
  const pageInfo = document.getElementById('aclPageInfo');

  if (aclFilteredModels.length === 0) {
    pagination.style.display = 'none';
    return;
  }
  pagination.style.display = 'flex';

  pagePrev.disabled = aclCurrentPage <= 1;
  pageNext.disabled = aclCurrentPage >= totalPages;

  pageInfo.textContent = '共 ' + aclFilteredModels.length + ' 个模型，第 ' + aclCurrentPage + '/' + totalPages + ' 页';

  let html = '';
  const maxVisible = 7;
  let startPage = Math.max(1, aclCurrentPage - Math.floor(maxVisible / 2));
  let endPage = Math.min(totalPages, startPage + maxVisible - 1);
  if (endPage - startPage + 1 < maxVisible) {
    startPage = Math.max(1, endPage - maxVisible + 1);
  }

  if (startPage > 1) {
    html += '<button class="pagination-btn" onclick="goToAclPage(1)">1</button>';
    if (startPage > 2) html += '<span class="pagination-info">...</span>';
  }
  for (let i = startPage; i <= endPage; i++) {
    html += '<button class="pagination-btn' + (i === aclCurrentPage ? ' active' : '') + '" onclick="goToAclPage(' + i + ')">' + i + '</button>';
  }
  if (endPage < totalPages) {
    if (endPage < totalPages - 1) html += '<span class="pagination-info">...</span>';
    html += '<button class="pagination-btn" onclick="goToAclPage(' + totalPages + ')">' + totalPages + '</button>';
  }

  pageNumbers.innerHTML = html;
}

function goToAclPage(page) {
  const totalPages = Math.ceil(aclFilteredModels.length / ACL_PAGE_SIZE) || 1;
  if (page < 1 || page > totalPages) return;
  aclCurrentPage = page;
  renderAclPage();
  document.getElementById('aclModelGrid').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showAclModelDetail(name) {
  const m = aclModels.find(x => x.name === name);
  if (!m) return;

  const icon = ACL_CATEGORY_ICONS[m.category] || '📦';
  const sourceLabel = ACL_SOURCE_LABELS[m.source] || m.source;
  const sourceClass = ACL_SOURCE_CLASSES[m.source] || 'source-ascend';
  const dataDirLabel = ACL_DATA_DIR_LABELS[m.data_dir] || m.data_dir || '';

  const modelUrl = m.model_url || '';

  document.getElementById('modalBody').innerHTML = `
    <h2>${m.name}</h2>
    <p style="color:var(--color-text-secondary);margin-bottom:20px">
      <span class="meta-tag category">${icon} ${m.category}</span>
      <span class="meta-tag ${sourceClass}" style="margin-left:8px">${sourceLabel}</span>
      ${dataDirLabel ? `<span class="meta-tag source-sglang" style="margin-left:8px">${dataDirLabel}</span>` : ''}
    </p>
    <dl>
      <dt>文件夹名</dt><dd>📁 ${m.folder}</dd>
      <dt>简介</dt><dd>${m.description}</dd>
      <dt>来源</dt><dd>${sourceLabel === '内置' ? '官方内置模型（built-in）' : '社区贡献模型（contrib）'}</dd>
      ${modelUrl ? `<dt>部署指南</dt><dd><a href="${modelUrl}" target="_blank" style="color:var(--color-primary)">${modelUrl}</a></dd>` : ''}
    </dl>
    <div style="margin-top:20px;padding:16px;background:var(--color-primary-light);border-radius:8px">
      <p style="color:var(--color-primary);font-size:0.9rem">
        📖 该模型位于 <strong>${m.data_dir || 'ACL_PyTorch'}/${m.source === 'built-in' ? 'built-in' : 'contrib'}</strong> 目录下
      </p>
      ${modelUrl ? `<p style="color:var(--color-primary);font-size:0.9rem;margin-top:8px">
        🔗 部署指南：<a href="${modelUrl}" target="_blank" style="color:var(--color-primary);text-decoration:underline">查看 README</a>
      </p>` : ''}
    </div>
  `;
  document.getElementById('modalOverlay').classList.add('active');
}
