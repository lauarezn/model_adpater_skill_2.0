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
// 变体后缀（用于把同系列变体合并到一张主卡片）
// 覆盖：硬件(-Ascend/-NPU/-A2/-A3/-Atlas)、量化(-w8a8/-mxfp8/-bf16等)、日期快照(-20260813)
// 例：DeepSeek-V4-Flash-0731-w8a8-A2-PD、A2ZChromatin-Accessibility-Ascend-NPU 的基础名分别为
//     DeepSeek-V4-Flash-0731、A2ZChromatin-Accessibility
const VAR_TOKEN = 'ascend|npu|a2|a3|atlas[a-z0-9]*|w8a8|w4a8|w4a16|w4a8c8|w8a8c8|w8a16|a8w8|a8w4|mxfp8|fp8|bf16|fp16|int8|int4|quantized|awq|gptq|gs|c8|orangepi|20\\d{6}';
const VAR_SUFFIX_RE = new RegExp('(?:-(' + VAR_TOKEN + '))(?:-(' + VAR_TOKEN + '|deployment|model|infer|single|mtp|pd|per-channel|[a-z0-9]+))*$', 'i');

// 计算系列基础名（小写 key 用于分组）：剥离变体后缀 + 统一分隔符(下划线/点号/横杠)
function familyKey(name) {
  return String(name).replace(VAR_SUFFIX_RE, '').replace(/[_\-.]+/g, '-').toLowerCase();
}

// 计算基础名的展示名（保留原始大小写 + 原分隔符），用于没有精确基础名模型时作为主卡片名
function baseDisplayName(name) {
  return String(name).replace(VAR_SUFFIX_RE, '').trim();
}

// 判断是否为变体（名称末尾带有变体后缀）
function isQuantHwVariant(name) {
  return VAR_SUFFIX_RE.test(String(name));
}

// 按系列基础名合并模型列表：每个系列只保留主卡片（优先基础名模型，否则取第一个），
// 并把同系列变体的部署文档链接收集到主模型的 variants 字段中。
function groupByFamily(items) {
  const groups = {};
  items.forEach(m => {
    const key = familyKey(m.name);
    (groups[key] = groups[key] || []).push(m);
  });
  const out = [];
  Object.keys(groups).forEach(key => {
    const list = groups[key];
    // 主卡片：优先名称归一化后恰等于基础名的模型（如 A2ZChromatin-Accessibility），否则取第一个
    const exact = list.find(m => String(m.name).replace(/[_\-.]+/g, '-').toLowerCase() === key);
    const main = exact || list[0];
    const variants = list.filter(m => m !== main);
    const merged = { ...main };
    if (variants.length > 0) {
      merged._variantCount = list.length;
      merged._variants = variants;
      // 若没有精确基础名模型，主卡片名显示为基础名（保留原大小写）
      if (!exact) {
        const base = baseDisplayName(main.name);
        if (base && base !== main.name) merged.name = base;
      }
    } else {
      merged._variantCount = 1;
      merged._variants = [];
    }
    out.push(merged);
  });
  return out;
}

function renderModels(data) {
  const grid = document.getElementById('modelGrid');
  const empty = document.getElementById('emptyState');

  if (data.length === 0) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  // 同系列变体合并：每个系列只显示一张主卡片
  const mergedData = groupByFamily(data);

  grid.innerHTML = mergedData.map(m => {
    const supportClass = m.supportLevel === '✅ 已支持' ? 'support-supported' :
                         m.supportLevel === '🔵 实验性' ? 'support-experimental' : 'support-extended';
    const perfClass = m.inferencePerf === '优' ? 'perf-supported' : 'perf-experimental';
    const hasDoc = m.docUrl && m.docUrl.length > 0;
    const sourceClass = m.source === 'vLLM Omni' ? 'source-omni' : m.source === 'SGLang Ascend' ? 'source-sglang' : m.source === 'GitCode AI' ? 'source-gitcode' : 'source-ascend';
    const sourceLabel = m.source === 'vLLM Omni' ? 'Omni' : m.source === 'SGLang Ascend' ? 'SGLang' : m.source === 'GitCode AI' ? 'GitCode' : 'Ascend';
    // 部署硬件：从模型数据中提取部署硬件信息
    // 优先使用 minHardware（来自支持矩阵或部署页面解析），否则显示 NA
    const deployHw = (hasDoc && m.minHardware) ? m.minHardware : 'NA';
    // 变体徽标：主卡片 + 各变体文档链接数量
    const variantBadge = (m._variantCount > 1)
      ? `<span class="variant-badge" title="${m._variants.map(v => v.displayName || v.name).join('、')}">${m._variantCount} 个部署文档</span>`
      : '';

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
          ${variantBadge}
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

// 开发者权威度（越小越靠前，用于综合排序优先展示权威组织的模型）
// 1=头部厂商，2=国内主流厂商，3=国际知名机构，4=其他机构，5=社区
// 注：华为默认不参与优先展示（780 个模型数量过大，会挤占其他权威组织），归入权重4
const DEVELOPER_RANK = {
  '阿里云': 1, '深度求索': 1, '智谱AI': 1,
  '百度': 2, '腾讯': 2, '字节跳动': 2, '月之暗面': 2, 'MiniMax': 2,
  '阶跃星辰': 2, '百川智能': 2, '零一万物': 2, '商汤': 2, '小米': 2, '面壁智能': 2,
  'Meta': 3, 'Google': 3, 'Microsoft': 3, 'NVIDIA': 3, 'Mistral AI': 3,
  'Stability AI': 3, 'Black Forest Labs': 3, 'Wan AI': 3, 'OpenMOSS': 3,
  'OpenBMB': 3, '上海AI实验室': 3, 'FunAudioLLM': 3, 'Allen AI': 3, 'Lightricks': 3,
  '华为': 4,
};
function developerRank(dev) {
  return DEVELOPER_RANK[dev] || (dev === '社区' ? 5 : 4);
}

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
    // 综合排序：优先展示权威组织的模型，同权威度内按数据顺序(id升序)
    filteredModels.sort((a, b) => {
      const ar = developerRank(a.developer);
      const br = developerRank(b.developer);
      if (ar !== br) return ar - br;
      return parseInt(a.id) - parseInt(b.id);
    });
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

  // 收集同系列变体的部署文档链接（含当前模型），用于合并展示
  const familyItems = (window._detailModels || models).filter(x => familyKey(x.name) === familyKey(m.name));
  const docLinks = [];
  familyItems.forEach(x => {
    if (x.docUrl && x.docUrl.length > 0) {
      // 部署链接名优先用 displayName（变体原始名，如 DeepSeek-OCR2-CNPC），否则用模型名
      docLinks.push({ name: x.displayName || x.name, url: x.docUrl });
    }
  });
  const hasVariants = familyItems.length > 1;
  // 部署文档区块：主文档 + 各变体链接列表
  const docBlock = (docLinks.length > 0) ? `
    <dt>📄 部署文档${hasVariants ? `（共 ${docLinks.length} 个）` : ''}</dt>
    <dd>
      <div style="display:flex;flex-direction:column;gap:8px">
        ${docLinks.map(d => `
          <a href="${d.url}" target="_blank" style="color:var(--color-primary);word-break:break-all">${d.name} →</a>
        `).join('')}
      </div>
    </dd>` : '';

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
      ${docBlock}
    </dl>
    <div class="tags" style="margin-top:16px">${m.tags.map(t => `<span class="tag">${t}</span>`).join('')}</div>
    ${docLinks.length > 0 ? `<div style="margin-top:20px;padding:16px;background:var(--color-primary-light);border-radius:8px">
      <a href="${docLinks[0].url}" target="_blank" style="color:var(--color-primary);font-weight:600;text-decoration:none;font-size:1rem">
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

