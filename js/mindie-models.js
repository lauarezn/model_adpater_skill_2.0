// ============ MindIE 模型页面 ============

let mindieModels = [];
let mindieFilteredModels = [];
let mindieCurrentPage = 1;
const MINDIE_PAGE_SIZE = 50;

// 分类图标映射
const MINDIE_CATEGORY_ICONS = {
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
const MINDIE_SOURCE_CLASSES = {
  'built-in': 'source-ascend',
  'contrib': 'source-gitcode'
};
const MINDIE_SOURCE_LABELS = {
  'built-in': '内置',
  'contrib': '社区'
};

// 数据目录标签
const MINDIE_DATA_DIR_LABELS = {
  'MindIE/LLM': 'LLM',
  'MindIE/MindIE-Torch': 'MindIE-Torch',
  'MindIE/MultiModal': 'MultiModal'
};

function loadMindieModels() {
  const loadingEl = document.getElementById('mindieLoadingIndicator');
  const gridEl = document.getElementById('mindieModelGrid');
  const statsEl = document.getElementById('mindieModelCount');

  fetch('/admin/api/mindie-models')
    .then(resp => resp.json())
    .then(data => {
      mindieModels = data.models;
      mindieFilteredModels = [...mindieModels];

      // 更新统计
      if (statsEl) statsEl.textContent = mindieModels.length;

      // 填充分类筛选器
      const catFilter = document.getElementById('mindieCategoryFilter');
      if (catFilter && data.categories) {
        catFilter.innerHTML = '<option value="all">全部分类</option>' +
          data.categories.map(c => `<option value="${c}">${MINDIE_CATEGORY_ICONS[c] || '📦'} ${c}</option>`).join('');
      }

      // 填充来源筛选器
      const srcFilter = document.getElementById('mindieSourceFilter');
      if (srcFilter && data.sources) {
        srcFilter.innerHTML = '<option value="all">全部来源</option>' +
          data.sources.map(s => `<option value="${s}">${MINDIE_SOURCE_LABELS[s] || s}</option>`).join('');
      }

      // 填充数据目录筛选器
      const dirFilter = document.getElementById('mindieDataDirFilter');
      if (dirFilter && data.data_dirs) {
        dirFilter.innerHTML = '<option value="all">全部目录</option>' +
          data.data_dirs.map(d => `<option value="${d}">${MINDIE_DATA_DIR_LABELS[d] || d}</option>`).join('');
      }

      // 隐藏 loading，显示网格
      loadingEl.style.display = 'none';
      gridEl.style.display = '';

      renderMindieModels(mindieModels);
      renderMindiePagination(Math.ceil(mindieModels.length / MINDIE_PAGE_SIZE));
    })
    .catch(err => {
      console.warn('MindIE 模型数据加载失败:', err);
      loadingEl.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><p>MindIE 模型数据加载失败，请刷新重试</p></div>';
    });
}

function renderMindieModels(data) {
  const grid = document.getElementById('mindieModelGrid');
  const empty = document.getElementById('mindieEmptyState');

  if (data.length === 0) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  grid.innerHTML = data.map(m => {
    const sourceClass = MINDIE_SOURCE_CLASSES[m.source] || 'source-ascend';
    const sourceLabel = MINDIE_SOURCE_LABELS[m.source] || m.source;
    const icon = MINDIE_CATEGORY_ICONS[m.category] || '📦';
    const dataDirLabel = MINDIE_DATA_DIR_LABELS[m.data_dir] || m.data_dir || '';
    const dataDirClass = m.data_dir === 'MindIE/MultiModal' ? 'source-sglang' :
                         m.data_dir === 'MindIE/MindIE-Torch' ? 'source-omni' : 'source-ascend';
    const modelUrl = m.model_url || '';

    return `
      <div class="acl-model-card" onclick="showMindieModelDetail('${m.name.replace(/'/g, "\\'")}')">
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

function filterMindieModels() {
  const search = document.getElementById('mindieSearchInput').value.toLowerCase();
  const category = document.getElementById('mindieCategoryFilter').value;
  const source = document.getElementById('mindieSourceFilter').value;
  const dataDir = document.getElementById('mindieDataDirFilter').value;

  mindieFilteredModels = mindieModels.filter(m => {
    if (search && !m.name.toLowerCase().includes(search) &&
        !m.folder.toLowerCase().includes(search) &&
        !m.description.toLowerCase().includes(search)) return false;
    if (category !== 'all' && m.category !== category) return false;
    if (source !== 'all' && m.source !== source) return false;
    if (dataDir !== 'all' && m.data_dir !== dataDir) return false;
    return true;
  });

  mindieCurrentPage = 1;
  renderMindiePage();
}

function renderMindiePage() {
  const totalPages = Math.ceil(mindieFilteredModels.length / MINDIE_PAGE_SIZE) || 1;
  const start = (mindieCurrentPage - 1) * MINDIE_PAGE_SIZE;
  const end = Math.min(start + MINDIE_PAGE_SIZE, mindieFilteredModels.length);
  const pageData = mindieFilteredModels.slice(start, end);

  renderMindieModels(pageData);
  renderMindiePagination(totalPages);
}

function renderMindiePagination(totalPages) {
  const pagination = document.getElementById('mindiePagination');
  const pageNumbers = document.getElementById('mindiePageNumbers');
  const pagePrev = document.getElementById('mindiePagePrev');
  const pageNext = document.getElementById('mindiePageNext');
  const pageInfo = document.getElementById('mindiePageInfo');

  if (mindieFilteredModels.length === 0) {
    pagination.style.display = 'none';
    return;
  }
  pagination.style.display = 'flex';

  pagePrev.disabled = mindieCurrentPage <= 1;
  pageNext.disabled = mindieCurrentPage >= totalPages;

  pageInfo.textContent = '共 ' + mindieFilteredModels.length + ' 个模型，第 ' + mindieCurrentPage + '/' + totalPages + ' 页';

  let html = '';
  const maxVisible = 7;
  let startPage = Math.max(1, mindieCurrentPage - Math.floor(maxVisible / 2));
  let endPage = Math.min(totalPages, startPage + maxVisible - 1);
  if (endPage - startPage + 1 < maxVisible) {
    startPage = Math.max(1, endPage - maxVisible + 1);
  }

  if (startPage > 1) {
    html += '<button class="pagination-btn" onclick="goToMindiePage(1)">1</button>';
    if (startPage > 2) html += '<span class="pagination-info">...</span>';
  }
  for (let i = startPage; i <= endPage; i++) {
    html += '<button class="pagination-btn' + (i === mindieCurrentPage ? ' active' : '') + '" onclick="goToMindiePage(' + i + ')">' + i + '</button>';
  }
  if (endPage < totalPages) {
    if (endPage < totalPages - 1) html += '<span class="pagination-info">...</span>';
    html += '<button class="pagination-btn" onclick="goToMindiePage(' + totalPages + ')">' + totalPages + '</button>';
  }

  pageNumbers.innerHTML = html;
}

function goToMindiePage(page) {
  const totalPages = Math.ceil(mindieFilteredModels.length / MINDIE_PAGE_SIZE) || 1;
  if (page < 1 || page > totalPages) return;
  mindieCurrentPage = page;
  renderMindiePage();
  document.getElementById('mindieModelGrid').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showMindieModelDetail(name) {
  const m = mindieModels.find(x => x.name === name);
  if (!m) return;

  const icon = MINDIE_CATEGORY_ICONS[m.category] || '📦';
  const sourceLabel = MINDIE_SOURCE_LABELS[m.source] || m.source;
  const sourceClass = MINDIE_SOURCE_CLASSES[m.source] || 'source-ascend';
  const dataDirLabel = MINDIE_DATA_DIR_LABELS[m.data_dir] || m.data_dir || '';

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
        📖 该模型位于 <strong>${m.data_dir || 'MindIE'}</strong> 目录下
      </p>
      ${modelUrl ? `<p style="color:var(--color-primary);font-size:0.9rem;margin-top:8px">
        🔗 部署指南：<a href="${modelUrl}" target="_blank" style="color:var(--color-primary);text-decoration:underline">查看 README</a>
      </p>` : ''}
    </div>
  `;
  document.getElementById('modalOverlay').classList.add('active');
}
