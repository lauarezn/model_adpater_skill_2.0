// ============ 全球AI大模型列表（数据来源：DataLearner）============

let globalModelsData = [];
let globalFilteredModels = [];
const GLOBAL_PAGE_SIZE = 24;
let globalCurrentPage = 1;

// 商业用途徽章样式映射
const GLOBAL_COMMERCIAL_CLASS = {
  '免费商用授权': 'commercial-free',
  '有条件免费商用授权': 'commercial-conditional',
  '收费商用授权': 'commercial-paid',
  '不可以商用': 'commercial-no',
  '不开源': 'commercial-closed',
};

// 规模中文标签映射
const GLOBAL_SCALE_LABEL = {
  'tiny': '微型',
  'small': '小型',
  'medium': '中型',
  'large': '大型',
  'xlarge': '超大型',
};

// 生命周期标签
const GLOBAL_LIFECYCLE_LABEL = {
  'ga': '已正式发布',
  'preview': '预览版',
};

// 参数规模显示：优先 parameterSizeDisplay，否则用 totalParamsB 生成
function globalParamSize(m) {
  if (m.parameterSizeDisplay) return m.parameterSizeDisplay;
  if (m.totalParamsB) {
    const v = parseFloat(m.totalParamsB);
    if (v >= 1000) return (v / 1000).toFixed(1).replace(/\.0$/, '') + 'T';
    return v + 'B';
  }
  return '未公开';
}

// 加载数据
async function initGlobalModels() {
  const loadingEl = document.getElementById('globalLoadingIndicator');
  const gridEl = document.getElementById('globalModelGrid');
  try {
    const resp = await fetch('/admin/api/global-models?page=1&page_size=24');
    if (resp.ok) {
      const data = await resp.json();
      globalModelsData = data.models;
      // 填充筛选器（用接口返回的筛选项）
      fillGlobalFilters(data.filters);
      if (data.meta) {
        const countEl = document.getElementById('globalModelCount');
        if (countEl) countEl.textContent = data.meta.total_all;
      }

      // 后台异步加载全部模型数据，支持本地筛选
      requestAnimationFrame(() => {
        fetch('/admin/api/global-models?page=1&page_size=2000').then(r => {
          if (r.ok) return r.json();
        }).then(d => {
          if (d && d.models) {
            globalModelsData = d.models;
            globalFilteredModels = [...d.models];
            globalCurrentPage = 1;
            renderGlobalModels();
          }
        }).catch(() => {});
      });

      loadingEl.style.display = 'none';
      gridEl.style.display = '';
      globalFilteredModels = [...data.models];
      renderGlobalModels();
    } else {
      throw new Error('加载失败');
    }
  } catch (e) {
    console.warn('全球AI大模型数据加载失败:', e);
    loadingEl.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><p>数据加载失败，请刷新重试</p></div>';
  }
}

function fillGlobalFilters(filters) {
  if (!filters) return;
  const typeSel = document.getElementById('globalTypeFilter');
  typeSel.innerHTML = '<option value="all">全部类型</option>' +
    filters.types.map(t => `<option value="${t}">${t}</option>`).join('');

  const pubSel = document.getElementById('globalPublisherFilter');
  pubSel.innerHTML = '<option value="all">全部机构</option>' +
    filters.publishers.map(p => `<option value="${p}">${p}</option>`).join('');

  const comSel = document.getElementById('globalCommercialFilter');
  comSel.innerHTML = '<option value="all">全部商业用途</option>' +
    filters.commercials.map(c => `<option value="${c}">${c}</option>`).join('');

  const scaleSel = document.getElementById('globalScaleFilter');
  scaleSel.innerHTML = '<option value="all">全部规模</option>' +
    filters.scales.map(s => `<option value="${s}">${GLOBAL_SCALE_LABEL[s] || s}</option>`).join('');
}

function filterGlobalModels() {
  const search = (document.getElementById('globalSearchInput').value || '').toLowerCase();
  const type = document.getElementById('globalTypeFilter').value;
  const publisher = document.getElementById('globalPublisherFilter').value;
  const commercial = document.getElementById('globalCommercialFilter').value;
  const scale = document.getElementById('globalScaleFilter').value;

  globalFilteredModels = globalModelsData.filter(m => {
    if (search && !m.model_abbr_name.toLowerCase().includes(search)
        && !m.orgName.toLowerCase().includes(search)
        && !(m.model_code || '').toLowerCase().includes(search)) return false;
    if (type !== 'all' && m.model_TYPE_NAME !== type) return false;
    if (publisher !== 'all' && m.orgName !== publisher) return false;
    if (commercial !== 'all' && (m.commercial_usage || '') !== commercial) return false;
    if (scale !== 'all' && (m.scaleBucket || '') !== scale) return false;
    return true;
  });

  globalCurrentPage = 1;
  renderGlobalModels();
}

function renderGlobalModels() {
  const grid = document.getElementById('globalModelGrid');
  const empty = document.getElementById('globalEmptyState');
  const pagination = document.getElementById('globalPagination');
  const total = globalFilteredModels.length;

  if (total === 0) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    pagination.style.display = 'none';
    return;
  }
  empty.style.display = 'none';

  const totalPages = Math.ceil(total / GLOBAL_PAGE_SIZE) || 1;
  if (globalCurrentPage > totalPages) globalCurrentPage = totalPages;
  const start = (globalCurrentPage - 1) * GLOBAL_PAGE_SIZE;
  const pageModels = globalFilteredModels.slice(start, start + GLOBAL_PAGE_SIZE);

  grid.innerHTML = pageModels.map(m => {
    const comClass = GLOBAL_COMMERCIAL_CLASS[m.commercial_usage] || 'commercial-closed';
    const scaleLabel = GLOBAL_SCALE_LABEL[m.scaleBucket] || (m.scaleBucket || '未公开');
    const lifeLabel = GLOBAL_LIFECYCLE_LABEL[m.lifecycleStatus] || m.lifecycleStatus || '';
    const reasoning = m.reasoningModel === 1 ? '<span class="tag tag-reasoning">🧠 推理</span>' : '';
    const featured = m.featured === 1 ? '<span class="tag tag-featured">⭐ 精选</span>' : '';
    const preview = m.lifecycleStatus === 'preview' ? '<span class="tag tag-preview">🔶 预览</span>' : '';
    const pubTime = m.publish_time ? m.publish_time : '未公布';

    return `
      <div class="global-model-card" onclick="openGlobalModelDetail('${m.model_code}', '${m.model_abbr_name}')">
        <div class="global-card-header">
          <div>
            <div class="global-card-name">${m.model_abbr_name}</div>
            <div class="global-card-org">${m.orgName || '未知机构'}</div>
          </div>
          <span class="commercial-badge ${comClass}">${m.commercial_usage || '未知'}</span>
        </div>
        <div class="global-card-meta">
          <span class="meta-tag category">${m.model_TYPE_NAME || '未分类'}</span>
          <span class="meta-tag">规模 ${scaleLabel}</span>
          ${reasoning}${featured}${preview}
        </div>
        <dl class="global-card-details">
          <dt>参数量</dt><dd>${globalParamSize(m)}</dd>
          <dt>发布时间</dt><dd>${pubTime}</dd>
          <dt>生命周期</dt><dd>${lifeLabel || '-'}</dd>
          <dt>知识截止</dt><dd>${m.knowledgeCutoffDate || '-'}</dd>
        </dl>
        ${m.aliases && m.aliases.length ? `<div class="tags">${m.aliases.slice(0,3).map(a => `<span class="tag">别名 ${a}</span>`).join('')}</div>` : ''}
      </div>
    `;
  }).join('');

  renderGlobalPagination(totalPages, total);
}

function renderGlobalPagination(totalPages, total) {
  const pagination = document.getElementById('globalPagination');
  const pageNumbers = document.getElementById('globalPageNumbers');
  const pagePrev = document.getElementById('globalPagePrev');
  const pageNext = document.getElementById('globalPageNext');
  const pageInfo = document.getElementById('globalPageInfo');

  pagination.style.display = 'flex';
  pagePrev.disabled = globalCurrentPage <= 1;
  pageNext.disabled = globalCurrentPage >= totalPages;
  pageInfo.textContent = '共 ' + total + ' 个模型，第 ' + globalCurrentPage + '/' + totalPages + ' 页';

  let html = '';
  const maxVisible = 7;
  let startPage = Math.max(1, globalCurrentPage - Math.floor(maxVisible / 2));
  let endPage = Math.min(totalPages, startPage + maxVisible - 1);
  if (endPage - startPage + 1 < maxVisible) {
    startPage = Math.max(1, endPage - maxVisible + 1);
  }

  if (startPage > 1) {
    html += '<button class="pagination-btn" onclick="globalGoPage(1)">1</button>';
    if (startPage > 2) html += '<span class="pagination-info">...</span>';
  }
  for (let i = startPage; i <= endPage; i++) {
    html += '<button class="pagination-btn' + (i === globalCurrentPage ? ' active' : '') + '" onclick="globalGoPage(' + i + ')">' + i + '</button>';
  }
  if (endPage < totalPages) {
    if (endPage < totalPages - 1) html += '<span class="pagination-info">...</span>';
    html += '<button class="pagination-btn" onclick="globalGoPage(' + totalPages + ')">' + totalPages + '</button>';
  }
  pageNumbers.innerHTML = html;
}

function globalGoPage(page) {
  const totalPages = Math.ceil(globalFilteredModels.length / GLOBAL_PAGE_SIZE) || 1;
  if (page < 1 || page > totalPages) return;
  globalCurrentPage = page;
  renderGlobalModels();
  document.getElementById('section-global-models').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ============ 模型详情 Modal ============
// 点击卡片后，跳转到独立的模型详情页面展示完整内容
function openGlobalModelDetail(code, name) {
  window.location.href = 'model_detail.html?code=' + encodeURIComponent(code) + '&name=' + encodeURIComponent(name);
}

// ============ 初始化 ============
// 在页面加载时由 app.js 的 init 流程调用
