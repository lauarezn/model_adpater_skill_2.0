// ============ 大模型评测基准列表（数据来源：DataLearner）============

let benchmarksData = [];
let benchmarkFiltered = [];
const BENCHMARK_PAGE_SIZE = 24;
let benchmarkCurrentPage = 1;

// 难度徽章样式映射
const BENCHMARK_DIFFICULTY_CLASS = {
  '基础': 'diff-basic',
  'Intermediate': 'diff-basic',
  '中等难度': 'diff-mid',
  'Advanced': 'diff-mid',
  'Expert': 'diff-hard',
  '高难度': 'diff-hard',
  '极高难度': 'diff-hard',
  'Hard': 'diff-hard',
  '困难': 'diff-hard',
  '动态竞技榜': 'diff-mid',
};

// 难度中文标签映射（英文难度值转为中文展示）
const BENCHMARK_DIFFICULTY_LABEL = {
  '基础': '基础',
  'Intermediate': '中等',
  '中等难度': '中等',
  'Advanced': '困难',
  'Expert': '高难度',
  '高难度': '高难度',
  '极高难度': '极高难度',
  'Hard': '困难',
  '困难': '困难',
  '动态竞技榜': '动态竞技榜',
};

// 题量显示：将数字格式化为可读形式
function benchmarkProblemCount(b) {
  const n = b.problemCount;
  if (n === null || n === undefined || n === '') return '未公开';
  const v = Number(n);
  if (isNaN(v)) return n;
  if (v >= 10000) return (v / 10000).toFixed(1).replace(/\.0$/, '') + '万';
  if (v >= 1000) return (v / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  return String(v);
}

// 加载数据
async function initBenchmarks() {
  const loadingEl = document.getElementById('benchmarkLoadingIndicator');
  const gridEl = document.getElementById('benchmarkGrid');
  try {
    const resp = await fetch('/admin/api/benchmarks?page=1&page_size=24');
    if (resp.ok) {
      const data = await resp.json();
      benchmarksData = data.benchmarks;
      // 填充筛选器
      fillBenchmarkFilters(data.filters);
      if (data.meta) {
        const countEl = document.getElementById('benchmarkModelCount');
        if (countEl) countEl.textContent = data.meta.total_all;
        const dateEl = document.getElementById('benchmarkDataDate');
        if (dateEl && data.meta.fetched_at) dateEl.textContent = data.meta.fetched_at;
      }

      // 后台异步加载全部基准数据，支持本地筛选
      requestAnimationFrame(() => {
        fetch('/admin/api/benchmarks?page=1&page_size=2000').then(r => {
          if (r.ok) return r.json();
        }).then(d => {
          if (d && d.benchmarks) {
            benchmarksData = d.benchmarks;
            benchmarkFiltered = [...d.benchmarks];
            benchmarkCurrentPage = 1;
            renderBenchmarks();
          }
        }).catch(() => {});
      });

      loadingEl.style.display = 'none';
      gridEl.style.display = '';
      benchmarkFiltered = [...data.benchmarks];
      renderBenchmarks();
    } else {
      throw new Error('加载失败');
    }
  } catch (e) {
    console.warn('评测基准数据加载失败:', e);
    loadingEl.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><p>数据加载失败，请刷新重试</p></div>';
  }
}

function fillBenchmarkFilters(filters) {
  if (!filters) return;
  const catSel = document.getElementById('benchmarkCategoryFilter');
  catSel.innerHTML = '<option value="all">全部类别</option>' +
    filters.categories.map(c => `<option value="${c}">${c}</option>`).join('');

  const langSel = document.getElementById('benchmarkLanguageFilter');
  langSel.innerHTML = '<option value="all">全部语言</option>' +
    filters.languages.map(l => `<option value="${l}">${l}</option>`).join('');

  const diffSel = document.getElementById('benchmarkDifficultyFilter');
  diffSel.innerHTML = '<option value="all">全部难度</option>' +
    filters.difficulties.map(d => {
      const label = BENCHMARK_DIFFICULTY_LABEL[d] || d;
      return `<option value="${d}">${label}</option>`;
    }).join('');

  const instSel = document.getElementById('benchmarkInstitutionFilter');
  instSel.innerHTML = '<option value="all">全部机构</option>' +
    filters.institutions.map(i => `<option value="${i}">${i}</option>`).join('');
}

function filterBenchmarks() {
  const search = (document.getElementById('benchmarkSearchInput').value || '').toLowerCase();
  const category = document.getElementById('benchmarkCategoryFilter').value;
  const language = document.getElementById('benchmarkLanguageFilter').value;
  const difficulty = document.getElementById('benchmarkDifficultyFilter').value;
  const institution = document.getElementById('benchmarkInstitutionFilter').value;

  benchmarkFiltered = benchmarksData.filter(b => {
    if (search && !(b.shortName || '').toLowerCase().includes(search)
        && !(b.fullName || '').toLowerCase().includes(search)
        && !(b.description || '').toLowerCase().includes(search)
        && !(b.category || '').toLowerCase().includes(search)) return false;
    if (category !== 'all' && (b.category || '') !== category) return false;
    if (language !== 'all' && (b.language || '') !== language) return false;
    if (difficulty !== 'all' && (b.difficultyLevel || '') !== difficulty) return false;
    if (institution !== 'all' && (b.institution || '') !== institution) return false;
    return true;
  });

  benchmarkCurrentPage = 1;
  renderBenchmarks();
}

function renderBenchmarks() {
  const grid = document.getElementById('benchmarkGrid');
  const empty = document.getElementById('benchmarkEmptyState');
  const pagination = document.getElementById('benchmarkPagination');
  const total = benchmarkFiltered.length;

  if (total === 0) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    pagination.style.display = 'none';
    return;
  }
  empty.style.display = 'none';

  const totalPages = Math.ceil(total / BENCHMARK_PAGE_SIZE) || 1;
  if (benchmarkCurrentPage > totalPages) benchmarkCurrentPage = totalPages;
  const start = (benchmarkCurrentPage - 1) * BENCHMARK_PAGE_SIZE;
  const pageItems = benchmarkFiltered.slice(start, start + BENCHMARK_PAGE_SIZE);

  grid.innerHTML = pageItems.map(b => {
    const diffClass = BENCHMARK_DIFFICULTY_CLASS[b.difficultyLevel] || 'diff-mid';
    const diffLabel = BENCHMARK_DIFFICULTY_LABEL[b.difficultyLevel] || b.difficultyLevel || '未公开';
    const official = b.isOfficial === 1 ? '<span class="tag tag-official">✅ 官方</span>' : '';
    const lang = b.language ? `<span class="meta-tag">🌐 ${b.language}</span>` : '';
    const metrics = b.metrics ? `<span class="meta-tag">📊 ${b.metrics}</span>` : '';
    const count = b.problemCount ? `<span class="meta-tag">📝 ${benchmarkProblemCount(b)} 题</span>` : '';

    return `
      <div class="benchmark-card" onclick="openBenchmarkDetail('${b.urlCode || b.benchmarkCode}', '${(b.shortName || b.benchmarkCode).replace(/'/g, "\\'")}')">
        <div class="benchmark-card-header">
          <div>
            <div class="benchmark-card-name">${b.shortName || b.benchmarkCode}</div>
            <div class="benchmark-card-fullname">${b.fullName || ''}</div>
          </div>
          <span class="difficulty-badge ${diffClass}">${diffLabel}</span>
        </div>
        <div class="benchmark-card-meta">
          <span class="meta-tag category">${b.category || '未分类'}</span>
          ${lang}${metrics}${count}
          ${official}
        </div>
        <p class="benchmark-card-desc">${b.description || ''}</p>
        <div class="benchmark-card-footer">
          <span class="benchmark-card-inst">🏢 ${b.institution || '未知机构'}</span>
          <span class="benchmark-card-link">查看详情 →</span>
        </div>
      </div>
    `;
  }).join('');

  renderBenchmarkPagination(totalPages, total);
}

function renderBenchmarkPagination(totalPages, total) {
  const pagination = document.getElementById('benchmarkPagination');
  const pageNumbers = document.getElementById('benchmarkPageNumbers');
  const pagePrev = document.getElementById('benchmarkPagePrev');
  const pageNext = document.getElementById('benchmarkPageNext');
  const pageInfo = document.getElementById('benchmarkPageInfo');

  pagination.style.display = 'flex';
  pagePrev.disabled = benchmarkCurrentPage <= 1;
  pageNext.disabled = benchmarkCurrentPage >= totalPages;
  pageInfo.textContent = '共 ' + total + ' 个基准，第 ' + benchmarkCurrentPage + '/' + totalPages + ' 页';

  let html = '';
  const maxVisible = 7;
  let startPage = Math.max(1, benchmarkCurrentPage - Math.floor(maxVisible / 2));
  let endPage = Math.min(totalPages, startPage + maxVisible - 1);
  if (endPage - startPage + 1 < maxVisible) {
    startPage = Math.max(1, endPage - maxVisible + 1);
  }

  if (startPage > 1) {
    html += '<button class="pagination-btn" onclick="benchmarkGoPage(1)">1</button>';
    if (startPage > 2) html += '<span class="pagination-info">...</span>';
  }
  for (let i = startPage; i <= endPage; i++) {
    html += '<button class="pagination-btn' + (i === benchmarkCurrentPage ? ' active' : '') + '" onclick="benchmarkGoPage(' + i + ')">' + i + '</button>';
  }
  if (endPage < totalPages) {
    if (endPage < totalPages - 1) html += '<span class="pagination-info">...</span>';
    html += '<button class="pagination-btn" onclick="benchmarkGoPage(' + totalPages + ')">' + totalPages + '</button>';
  }
  pageNumbers.innerHTML = html;
}

function benchmarkGoPage(page) {
  const totalPages = Math.ceil(benchmarkFiltered.length / BENCHMARK_PAGE_SIZE) || 1;
  if (page < 1 || page > totalPages) return;
  benchmarkCurrentPage = page;
  renderBenchmarks();
  document.getElementById('section-benchmarks').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ============ 基准详情 ============
// 点击卡片后，跳转到本站基准详情页（内容由服务端代理抓取 DataLearner 详情并展示）
function openBenchmarkDetail(urlCode, name) {
  const code = urlCode || '';
  if (!code) return;
  const qs = new URLSearchParams({ code: code });
  if (name) qs.set('name', name);
  window.location.href = 'benchmark_detail.html?' + qs.toString();
}

// ============ 初始化 ============
// 在页面加载时由 app.js 的 init 流程调用
