// ============ Navigation ============
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('section-' + btn.dataset.section).classList.add('active');
  });
});

// ============ Model Cards ============
function renderModels(data) {
  const grid = document.getElementById('modelGrid');
  const empty = document.getElementById('emptyState');

  if (data.length === 0) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  grid.innerHTML = data.map(m => {
    const supportClass = m.supportLevel === '✅ 已支持' ? 'support-supported' :
                         m.supportLevel === '🔵 实验性' ? 'support-experimental' : 'support-extended';
    const perfClass = m.inferencePerf === '优' ? 'perf-supported' : 'perf-experimental';
    const hasDoc = m.docUrl && m.docUrl.length > 0;
    const sourceClass = m.source === 'vLLM Omni' ? 'source-omni' : m.source === 'SGLang Ascend' ? 'source-sglang' : m.source === 'GitCode AI' ? 'source-gitcode' : 'source-ascend';
    const sourceLabel = m.source === 'vLLM Omni' ? 'Omni' : m.source === 'SGLang Ascend' ? 'SGLang' : m.source === 'GitCode AI' ? 'GitCode' : 'Ascend';

    return `
      <div class="model-card" onclick="showModelDetail('${m.id}')">
        <div class="model-card-header">
          <div>
            <div class="model-card-name">${m.name}</div>
            <div class="model-card-developer">${m.developer}</div>
          </div>
          <span class="support-badge ${supportClass}">${m.supportLevel}</span>
        </div>
        <div class="model-card-meta">
          <span class="meta-tag category">${m.category}</span>
          <span class="meta-tag">${m.architecture}</span>
          <span class="meta-tag hardware">${m.minHardware}</span>
          <span class="meta-tag ${sourceClass}">${sourceLabel}</span>
        </div>
        <dl class="model-card-details">
          <dt>适配状态</dt>
          <dd><span class="perf-bar"><span class="perf-dot ${perfClass}"></span> ${m.supportLevel}</span></dd>
          <dt>框架</dt>
          <dd>${m.framework}</dd>
          <dt>推荐硬件</dt>
          <dd>${m.recommendedHardware}</dd>
          <dt>${hasDoc ? '📄 部署文档' : '备注'}</dt>
          <dd>${hasDoc ? `<a href="${m.docUrl}" target="_blank" class="doc-link" onclick="event.stopPropagation()">查看部署指南 →</a>` : m.notes}</dd>
        </dl>
        <div class="tags">
          ${m.tags.map(t => `<span class="tag">${t}</span>`).join('')}
        </div>
      </div>
    `;
  }).join('');
}

// 分页状态
let currentPage = 1;
const PAGE_SIZE = 50;
let filteredModels = [];

function filterModels() {
  const search = document.getElementById('searchInput').value.toLowerCase();
  const category = document.getElementById('categoryFilter').value;
  const support = document.getElementById('supportFilter').value;
  const hardware = document.getElementById('hardwareFilter').value;
  const sort = document.getElementById('sortFilter').value;

  filteredModels = models.filter(m => {
    if (search && !m.name.toLowerCase().includes(search) && !m.developer.toLowerCase().includes(search) && !m.tags.some(t => t.toLowerCase().includes(search))) return false;
    if (category !== 'all' && m.category !== category) return false;
    if (support !== 'all') {
      if (support === '✅ 已支持' && m.supportLevel !== '✅ 已支持') return false;
      if (support === '🔵 实验性' && m.supportLevel !== '🔵 实验性') return false;
      if (support === '扩展兼容' && m.supportLevel !== '扩展兼容') return false;
    }
    if (hardware !== 'all' && !m.minHardware.includes(hardware) && !m.recommendedHardware.includes(hardware)) return false;
    return true;
  });

  // 排序
  if (sort === 'popular') {
    filteredModels.sort((a, b) => {
      const aNum = parseInt(a.developer) || 0;
      const bNum = parseInt(b.developer) || 0;
      if (bNum !== aNum) return bNum - aNum;
      return parseInt(b.id) - parseInt(a.id);
    });
  } else if (sort === 'newest') {
    filteredModels.sort((a, b) => parseInt(b.id) - parseInt(a.id));
  } else if (sort === 'updated') {
    filteredModels.sort((a, b) => parseInt(b.id) - parseInt(a.id));
  } else {
    filteredModels.sort((a, b) => parseInt(a.id) - parseInt(b.id));
  }

  currentPage = 1;
  renderPage();
}

function renderPage() {
  const totalPages = Math.ceil(filteredModels.length / PAGE_SIZE) || 1;
  const start = (currentPage - 1) * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, filteredModels.length);
  const pageData = filteredModels.slice(start, end);

  renderModels(pageData);
  renderPagination(totalPages);
}

function renderPagination(totalPages) {
  const pagination = document.getElementById('pagination');
  const pageNumbers = document.getElementById('pageNumbers');
  const pagePrev = document.getElementById('pagePrev');
  const pageNext = document.getElementById('pageNext');
  const pageInfo = document.getElementById('pageInfo');

  if (filteredModels.length === 0) {
    pagination.style.display = 'none';
    return;
  }
  pagination.style.display = 'flex';

  pagePrev.disabled = currentPage <= 1;
  pageNext.disabled = currentPage >= totalPages;

  pageInfo.textContent = '共 ' + filteredModels.length + ' 个模型，第 ' + currentPage + '/' + totalPages + ' 页';

  // 生成页码按钮
  let html = '';
  const maxVisible = 7;
  let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
  let endPage = Math.min(totalPages, startPage + maxVisible - 1);
  if (endPage - startPage + 1 < maxVisible) {
    startPage = Math.max(1, endPage - maxVisible + 1);
  }

  if (startPage > 1) {
    html += '<button class="pagination-btn" onclick="goToPage(1)">1</button>';
    if (startPage > 2) html += '<span class="pagination-info">...</span>';
  }
  for (let i = startPage; i <= endPage; i++) {
    html += '<button class="pagination-btn' + (i === currentPage ? ' active' : '') + '" onclick="goToPage(' + i + ')">' + i + '</button>';
  }
  if (endPage < totalPages) {
    if (endPage < totalPages - 1) html += '<span class="pagination-info">...</span>';
    html += '<button class="pagination-btn" onclick="goToPage(' + totalPages + ')">' + totalPages + '</button>';
  }

  pageNumbers.innerHTML = html;
}

function goToPage(page) {
  const totalPages = Math.ceil(filteredModels.length / PAGE_SIZE) || 1;
  if (page < 1 || page > totalPages) return;
  currentPage = page;
  renderPage();
  // 滚动到模型网格顶部
  document.getElementById('modelGrid').scrollIntoView({ behavior: 'smooth', block: 'start' });
}// ============ Model Detail Modal ============
function showModelDetail(id) {
  // 优先从详情数据中查找，否则从当前 models 中查找
  let m = null;
  if (window._detailModels) {
    m = window._detailModels.find(x => x.id === id);
  }
  if (!m) {
    m = models.find(x => x.id === id);
  }
  if (!m) return;
  const perfClass = m.inferencePerf === '优' ? 'perf-supported' : 'perf-experimental';
  const supportClass = m.supportLevel === '✅ 已支持' ? 'support-supported' :
                       m.supportLevel === '🔵 实验性' ? 'support-experimental' : 'support-extended';
  const hasDoc = m.docUrl && m.docUrl.length > 0;

  const sourceLabel = m.source === 'vLLM Omni' ? 'vLLM Omni' : m.source === 'SGLang Ascend' ? 'SGLang Ascend' : m.source === 'GitCode AI' ? 'GitCode AI' : 'vLLM Ascend';

  const sourceColor = m.source === 'vLLM Omni' ? '#7C3AED' : m.source === 'SGLang Ascend' ? '#065F46' : m.source === 'GitCode AI' ? '#92400E' : '#2563EB';

  document.getElementById('modalBody').innerHTML = `
    <h2>${m.name} <span class="support-badge ${supportClass}" style="font-size:0.8rem;vertical-align:middle">${m.supportLevel}</span></h2>
    <p style="color:var(--color-text-secondary);margin-bottom:20px">${m.developer} · ${m.category} · <span style="color:${sourceColor}">数据源: ${sourceLabel}</span></p>
    <dl>
      <dt>架构</dt><dd>${m.architecture}</dd>
      <dt>适配状态</dt><dd><span class="perf-bar"><span class="perf-dot ${perfClass}"></span> ${m.supportLevel}</span></dd>
      <dt>支持框架</dt><dd>${m.framework}</dd>
      <dt>最低硬件</dt><dd>${m.minHardware}</dd>
      <dt>推荐硬件</dt><dd>${m.recommendedHardware}</dd>
      <dt>MindSpore支持</dt><dd>${m.mindsporeSupport}</dd>
      <dt>CANN版本</dt><dd>${m.cannVersion}</dd>
      <dt>备注</dt><dd>${m.notes}</dd>
      ${hasDoc ? `<dt>📄 部署文档</dt><dd><a href="${m.docUrl}" target="_blank" style="color:var(--color-primary)">${m.docUrl}</a></dd>` : ''}
    </dl>
    <div class="tags" style="margin-top:16px">${m.tags.map(t => `<span class="tag">${t}</span>`).join('')}</div>
    ${hasDoc ? `<div style="margin-top:20px;padding:16px;background:var(--color-primary-light);border-radius:8px">
      <a href="${m.docUrl}" target="_blank" style="color:var(--color-primary);font-weight:600;text-decoration:none;font-size:1rem">
        📖 查看 ${m.name} 部署指南 →
      </a>
    </div>` : ''}
  `;
  document.getElementById('modalOverlay').classList.add('active');
}

function closeModal(e) {
  if (e && e.target !== document.getElementById('modalOverlay')) return;
  document.getElementById('modalOverlay').classList.remove('active');
}

