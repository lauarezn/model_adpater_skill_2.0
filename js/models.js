// ============ Navigation ============
function switchSection(section) {
  var target = document.getElementById('section-' + section);
  if (!target) return;
  document.querySelectorAll('.nav-btn, .dropdown-item').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  // 命中按钮：普通 nav-btn 或下拉子项（dropdown-item）
  var btn = document.querySelector('.nav-btn[data-section="' + section + '"]') ||
            document.querySelector('.dropdown-item[data-section="' + section + '"]');
  if (btn) btn.classList.add('active');
  // 若命中的是下拉子项，则同时高亮其父级下拉切换按钮
  if (btn && btn.classList.contains('dropdown-item')) {
    var dd = btn.closest('.nav-dropdown');
    if (dd) {
      var toggle = dd.querySelector('.dropdown-toggle');
      if (toggle) toggle.classList.add('active');
    }
  }
  target.classList.add('active');
  closeAllDropdowns();
}

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    switchSection(btn.dataset.section);
  });
});

// 下拉菜单（通用，支持多个 .nav-dropdown）：切换按钮展开/收起
function positionDropdown(dd) {
  var toggle = dd.querySelector('.dropdown-toggle');
  var menu = dd.querySelector('.dropdown-menu');
  if (!toggle || !menu) return;
  var rect = toggle.getBoundingClientRect();
  menu.style.top = rect.bottom + 4 + 'px';
  menu.style.left = rect.left + 'px';
  menu.style.minWidth = Math.max(220, rect.width) + 'px';
}
function closeAllDropdowns() {
  document.querySelectorAll('.nav-dropdown').forEach(function (dd) {
    dd.classList.remove('open');
    var toggle = dd.querySelector('.dropdown-toggle');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  });
}
function openDropdown(dd) {
  closeAllDropdowns();
  positionDropdown(dd);
  dd.classList.add('open');
  var toggle = dd.querySelector('.dropdown-toggle');
  if (toggle) toggle.setAttribute('aria-expanded', 'true');
}
// 每个下拉：点击切换按钮展开/收起
document.querySelectorAll('.nav-dropdown').forEach(function (dd) {
  var toggle = dd.querySelector('.dropdown-toggle');
  if (!toggle) return;
  toggle.addEventListener('click', function (e) {
    e.stopPropagation();
    if (dd.classList.contains('open')) {
      closeAllDropdowns();
    } else {
      openDropdown(dd);
    }
  });
});
// 下拉子项：选中后收起菜单并切换板块
document.querySelectorAll('.nav-dropdown .dropdown-item').forEach(function (item) {
  item.addEventListener('click', function (e) {
    e.stopPropagation();
    closeAllDropdowns();
    switchSection(item.dataset.section);
    // 若子项带有 data-view（如「全球AI大模型」下的模型清单/最热排行），在切换板块后同步切换视图
    if (item.dataset.view && typeof window.switchGlobalView === 'function') {
      // 同一 section 可能对应多个视图项（如 global-models 的「全球AI大模型」list 与「最热排行」hot），
      // switchSection 只会高亮第一个匹配项，这里需按当前点击的视图项重新高亮，避免高亮与内容不一致
      document.querySelectorAll('.dropdown-item[data-section="' + item.dataset.section + '"]').forEach(function (x) {
        x.classList.remove('active');
      });
      item.classList.add('active');
      switchGlobalView(item.dataset.view);
    }
  });
});
// 点击页面其它区域关闭下拉
document.addEventListener('click', function () {
  closeAllDropdowns();
});
// 页面滚动/窗口变化时保持下拉菜单跟随定位（不随导航横向滑动）
window.addEventListener('scroll', function () {
  document.querySelectorAll('.nav-dropdown.open').forEach(positionDropdown);
}, true);
window.addEventListener('resize', function () {
  document.querySelectorAll('.nav-dropdown.open').forEach(positionDropdown);
});

// 支持通过 URL hash（如 /#benchmarks）直接定位到指定板块
(function () {
  var section = (location.hash || '').replace('#', '');
  if (section) switchSection(section);
})();

// 支持通过 URL 查询参数（?section=xxx）定位到对应板块
(function () {
  var qs = new URLSearchParams(location.search);
  var section = qs.get('section');
  if (section) switchSection(section);
})();

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
    // 部署硬件：从模型数据中提取部署硬件信息
    // 优先使用 minHardware（来自支持矩阵或部署页面解析），否则显示 NA
    const deployHw = (hasDoc && m.minHardware) ? m.minHardware : 'NA';

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
          <span class="meta-tag ${sourceClass}">${sourceLabel}</span>
        </div>
        <dl class="model-card-details">
          <dt>适配状态</dt>
          <dd><span class="perf-bar"><span class="perf-dot ${perfClass}"></span> ${m.supportLevel}</span></dd>
          <dt>框架</dt>
          <dd>${m.framework}</dd>
          <dt>部署硬件</dt>
          <dd>${deployHw}</dd>
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
  const tag = document.getElementById('tagFilter').value;
  const support = document.getElementById('supportFilter').value;
  const hardware = document.getElementById('hardwareFilter').value;
  const sort = document.getElementById('sortFilter').value;

  filteredModels = models.filter(m => {
    if (search && !m.name.toLowerCase().includes(search) && !m.developer.toLowerCase().includes(search) && !m.tags.some(t => t.toLowerCase().includes(search))) return false;
    if (category !== 'all' && m.category !== category) return false;
    if (tag !== 'all' && !m.tags.includes(tag)) return false;
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
  // 部署硬件：从模型数据中提取部署硬件信息
  // 优先使用 minHardware（来自支持矩阵或部署页面解析），否则显示 NA
  const deployHw = (hasDoc && m.minHardware) ? m.minHardware : 'NA';

  document.getElementById('modalBody').innerHTML = `
    <h2>${m.name} <span class="support-badge ${supportClass}" style="font-size:0.8rem;vertical-align:middle">${m.supportLevel}</span></h2>
    <p style="color:var(--color-text-secondary);margin-bottom:20px">${m.developer} · ${m.category} · <span style="color:${sourceColor}">数据源: ${sourceLabel}</span></p>
    <dl>
      <dt>架构</dt><dd>${m.architecture}</dd>
      <dt>适配状态</dt><dd><span class="perf-bar"><span class="perf-dot ${perfClass}"></span> ${m.supportLevel}</span></dd>
      <dt>支持框架</dt><dd>${m.framework}</dd>
      <dt>部署硬件</dt><dd>${deployHw}</dd>
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
  const overlay = document.getElementById('modalOverlay');
  overlay.classList.remove('active');
  overlay.classList.remove('global-modal');
  document.body.style.overflow = '';
}

// ESC 键关闭弹窗
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    const overlay = document.getElementById('modalOverlay');
    if (overlay && overlay.classList.contains('active')) {
      overlay.classList.remove('active');
      overlay.classList.remove('global-modal');
      document.body.style.overflow = '';
    }
  }
});

