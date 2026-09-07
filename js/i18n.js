// ============ 全局 i18n 与主题切换 ============

// ---------- 翻译词典 ----------
const I18N = {
  zh: {
    // 头部
    'site.title': '🚀 昇腾服务器 大模型适配清单',
    'site.subtitle': '查询大模型在华为昇腾平台上的适配状态与部署指南',
    'stat.models': '已收录 {n} 个模型',
    'stat.hardware': '{n} 款服务器型号',
    'stat.categories': '{n} 个类别',
    'stat.date': '加载中...',
    // 数据源
    'sync.banner': '📡 数据由服务端每日 06:00 自动同步 · <span class="refresh-status" id="refreshStatus">就绪</span>',
    'sync.ready': '就绪',
    'sync.refresh': '🔄 手动刷新',
    'sync.loading': '正在加载数据...',
    'sync.success': '✅ 数据由服务端每日 06:00 自动同步 · 共 {n} 个模型',
    'sync.refreshed': '✅ 已刷新 · 数据由服务端每日 06:00 自动同步 · 共 {n} 个模型',
    'sync.failed': '⚠️ 数据加载失败',
    'sync.refreshFailed': '⚠️ 刷新失败',
    'sync.refreshFailedCache': '⚠️ 刷新失败，使用缓存数据',
    // 导航
    'nav.browse': '📋 昇腾适配清单',
    'nav.hardware': '🔷 昇腾产品',
    'nav.hardwareGlobal': '🖥️ 全球AI硬件 ▾',
    'nav.hardwareNv': '🟢 NV产品',
    'nav.hardwareAscend': '🔷 昇腾产品',
    'nav.hardwareMuxi': '🟣 沐曦产品',
    'nav.train': '📚 昇腾大模型训练清单',
    'nav.acl': '🔬 昇腾小模型清单',
    'nav.mindie': '🧩 MindIE 模型',
    'nav.global': '📋 模型清单 ▾',
    'nav.benchmarks': '📊 评测基准',
    'nav.compare': '⚖️ 产品对比 ▾',
    'nav.compareModels': '🤖 大模型对比',
    'nav.compareHardware': '🖥️ 服务器硬件产品对比',
    'nav.globalList': '🌍 全球AI大模型',
    'nav.globalHot': '📈 最热排行',
    // 全球AI硬件页面
    'hardwareAscend.title': '🔷 昇腾产品',
    'hardwareAscend.subtitle': '华为昇腾计算产品线 · 服务器硬件与加速卡',
    'hardwareNv.title': '🟢 NV产品',
    'hardwareNv.subtitle': 'NVIDIA 服务器硬件与加速卡产品',
    'hardwareNv.empty': 'NV 产品数据正在整理中，敬请期待',
    'hardwareMuxi.title': '🟣 沐曦产品',
    'hardwareMuxi.subtitle': '沐曦 GPU 服务器硬件与加速卡产品',
    'hardwareMuxi.empty': '沐曦产品数据正在整理中，敬请期待',
    // 对比页面
    'compareModels.title': '🤖 大模型对比',
    'compareModels.subtitle': '对比多个大模型在不同评测基准（Benchmark）上的表现得分',
    'compareModels.cardModel': '选择模型',
    'compareModels.cardBench': '选择评测基准',
    'compareModels.selected': '已选',
    'compareModels.noModel': '暂未选择模型',
    'compareModels.noBench': '暂未选择评测基准',
    'compareModels.generate': '生成对比',
    'compareModels.generateHint': '至少选择 2 个模型后再生成对比',
    'compareModels.tip': '至少选择 2 个模型，未选评测时会自动填充常见榜单，便于快速生成对比结果。',
    'compareModels.loading': '正在抓取评测榜单并构建对比矩阵...',
    'compareHardware.title': '🖥️ 服务器硬件产品对比',
    'compareHardware.subtitle': '选择多个服务器硬件产品，并排对比关键规格参数',
    'compareHardware.selectHw': '选择硬件产品（可多选，最多 6 个）：',
    'compareHardware.cardAscend': '🔷 昇腾设备',
    'compareHardware.cardNonAscend': '🟢 非昇腾设备',
    'compareHardware.noAscend': '暂未选择昇腾设备',
    'compareHardware.noNonAscend': '暂未选择非昇腾设备',
    'compareHardware.loading': '正在构建硬件对比...',
    // 搜索与筛选
    'search.models': '🔍 搜索模型名称、开发者、标签...',
    'search.hardware': '🔍 搜索硬件名称、类型、芯片...',
    'search.train': '🔍 搜索模型名称、框架...',
    'search.acl': '🔍 搜索模型名称、文件夹、简介...',
    'search.mindie': '🔍 搜索模型名称、文件夹、简介...',
    'search.global': '🔍 搜索模型名称、机构...',
    'search.benchmark': '🔍 搜索基准名称、简介、类别...',
    'filter.all': '全部',
    'filter.allCategories': '全部分类',
    'filter.allHardware': '全部硬件',
    'filter.allTags': '全部标签',
    'filter.allSources': '全部来源',
    'filter.allDirs': '全部目录',
    'filter.allTypes': '全部类型',
    'filter.allOrgs': '全部机构',
    'filter.allCommercial': '全部商业用途',
    'filter.allScale': '全部规模',
    'filter.allFramework': '全部框架',
    'filter.allStatus': '全部状态',
    'filter.allChips': '全部芯片',
    'filter.support': '适配状态',
    'filter.recommended': '推荐硬件',
    'filter.sort': '综合排序',
    'filter.status': '全部状态',
    // 加载与空状态
    'loading.models': '正在加载本地模型数据...',
    'loading.acl': '正在加载小模型数据...',
    'loading.mindie': '正在加载 MindIE 模型数据...',
    'loading.global': '正在加载全球AI大模型数据...',
    'loading.benchmark': '正在加载评测基准数据...',
    'empty.models': '没有找到匹配的模型，试试其他关键词',
    'empty.hardware': '没有找到匹配的硬件，试试其他关键词',
    'empty.acl': '没有找到匹配的模型，试试其他关键词',
    'empty.mindie': '没有找到匹配的模型，试试其他关键词',
    'empty.global': '没有找到匹配的模型，试试其他关键词',
    'empty.benchmark': '没有找到匹配的基准，试试其他关键词',
    'empty.train': '没有找到匹配的训练模型',
    // 分页
    'pagination.info': '共 {total} 个模型，第 {page}/{pages} 页',
    'pagination.first': '首页',
    'pagination.prev': '上一页',
    'pagination.next': '下一页',
    'pagination.last': '末页',
    // 详情
    'detail.guide': '📄 部署指南',
    'detail.viewGuide': '查看部署指南 →',
    'detail.notes': '备注',
    // 页脚
    'footer.note': '仅供参考，请以官方最新公告为准',
    'footer.copyright': '昇腾服务器大模型适配清单 · 数据自动同步',
    // 主题与语言按钮
    'theme.dark': '🌙 暗色',
    'theme.light': '☀️ 亮色',
    'lang.zh': '中文',
    'lang.en': 'English',
  },
  en: {
    'site.title': '🚀 Ascend Server LLM Adaptation List',
    'site.subtitle': 'Check LLM adaptation status and deployment guides on Huawei Ascend',
    'stat.models': '{n} models',
    'stat.hardware': '{n} server models',
    'stat.categories': '{n} categories',
    'stat.date': 'Loading...',
    'sync.banner': '📡 Auto-synced daily at 06:00 · <span class="refresh-status" id="refreshStatus">Ready</span>',
    'sync.ready': 'Ready',
    'sync.refresh': '🔄 Refresh',
    'sync.loading': 'Loading data...',
    'sync.success': '✅ Auto-synced daily at 06:00 · {n} models total',
    'sync.refreshed': '✅ Refreshed · Auto-synced daily at 06:00 · {n} models total',
    'sync.failed': '⚠️ Failed to load data',
    'sync.refreshFailed': '⚠️ Refresh failed',
    'sync.refreshFailedCache': '⚠️ Refresh failed, using cached data',
    'nav.browse': '📋 Ascend Adaptation List',
    'nav.hardware': '🔷 Ascend Products',
    'nav.hardwareGlobal': '🖥️ Global AI Hardware ▾',
    'nav.hardwareNv': '🟢 NV Products',
    'nav.hardwareAscend': '🔷 Ascend Products',
    'nav.hardwareMuxi': '🟣 Muxi Products',
    'nav.train': '📚 Ascend LLM Training List',
    'nav.acl': '🔬 Ascend Small Model List',
    'nav.mindie': '🧩 MindIE Models',
    'nav.global': '📋 Model List ▾',
    'nav.benchmarks': '📊 Benchmarks',
    'nav.compare': '⚖️ Compare ▾',
    'nav.compareModels': '🤖 Model Comparison',
    'nav.compareHardware': '🖥️ Server Hardware Comparison',
    'nav.globalList': '🌍 Global AI Models',
    'nav.globalHot': '📈 Hot Ranking',
    // Global AI Hardware pages
    'hardwareAscend.title': '🔷 Ascend Products',
    'hardwareAscend.subtitle': 'Huawei Ascend computing product line · servers & accelerator cards',
    'hardwareNv.title': '🟢 NV Products',
    'hardwareNv.subtitle': 'NVIDIA server hardware & accelerator cards',
    'hardwareNv.empty': 'NV product data is being prepared, stay tuned',
    'hardwareMuxi.title': '🟣 Muxi Products',
    'hardwareMuxi.subtitle': 'Muxi GPU server hardware & accelerator cards',
    'hardwareMuxi.empty': 'Muxi product data is being prepared, stay tuned',
    // Compare pages
    'compareModels.title': '🤖 Model Comparison',
    'compareModels.subtitle': 'Compare model scores across different benchmarks',
    'compareModels.cardModel': 'Select Models',
    'compareModels.cardBench': 'Select Benchmarks',
    'compareModels.selected': 'Selected',
    'compareModels.noModel': 'No models selected',
    'compareModels.noBench': 'No benchmarks selected',
    'compareModels.generate': 'Generate Comparison',
    'compareModels.generateHint': 'Select at least 2 models to generate comparison',
    'compareModels.tip': 'Select at least 2 models. If no benchmark is selected, common leaderboards are auto-filled for quick comparison.',
    'compareModels.loading': 'Fetching benchmark leaderboards and building the comparison matrix...',
    'compareHardware.title': '🖥️ Server Hardware Comparison',
    'compareHardware.subtitle': 'Select multiple server hardware products to compare key specifications side by side',
    'compareHardware.selectHw': 'Select hardware products (multi-select, max 6):',
    'compareHardware.cardAscend': '🔷 Ascend Devices',
    'compareHardware.cardNonAscend': '🟢 Non-Ascend Devices',
    'compareHardware.noAscend': 'No Ascend devices selected',
    'compareHardware.noNonAscend': 'No non-Ascend devices selected',
    'compareHardware.loading': 'Building hardware comparison...',
    'search.models': '🔍 Search model, developer, tag...',
    'search.hardware': '🔍 Search hardware name, type, chip...',
    'search.train': '🔍 Search model name, framework...',
    'search.acl': '🔍 Search model, folder, description...',
    'search.mindie': '🔍 Search model, folder, description...',
    'search.global': '🔍 Search model name, organization...',
    'search.benchmark': '🔍 Search benchmark name, description, category...',
    'filter.all': 'All',
    'filter.allCategories': 'All Categories',
    'filter.allHardware': 'All Hardware',
    'filter.allTags': 'All Tags',
    'filter.allSources': 'All Sources',
    'filter.allDirs': 'All Directories',
    'filter.allTypes': 'All Types',
    'filter.allOrgs': 'All Organizations',
    'filter.allCommercial': 'All Commercial',
    'filter.allScale': 'All Scale',
    'filter.allFramework': 'All Frameworks',
    'filter.allStatus': 'All Status',
    'filter.allChips': 'All Chips',
    'filter.support': 'Support Status',
    'filter.recommended': 'Recommended Hardware',
    'filter.sort': 'Sort',
    'filter.status': 'All Status',
    'loading.models': 'Loading local model data...',
    'loading.acl': 'Loading small model data...',
    'loading.mindie': 'Loading MindIE model data...',
    'loading.global': 'Loading global AI model data...',
    'loading.benchmark': 'Loading benchmark data...',
    'empty.models': 'No matching models found. Try another keyword.',
    'empty.hardware': 'No matching hardware found. Try another keyword.',
    'empty.acl': 'No matching models found. Try another keyword.',
    'empty.mindie': 'No matching models found. Try another keyword.',
    'empty.global': 'No matching models found. Try another keyword.',
    'empty.benchmark': 'No matching benchmarks found. Try another keyword.',
    'empty.train': 'No matching training models found.',
    'pagination.info': '{total} models, page {page}/{pages}',
    'pagination.first': 'First',
    'pagination.prev': 'Prev',
    'pagination.next': 'Next',
    'pagination.last': 'Last',
    'detail.guide': '📄 Deployment Guide',
    'detail.viewGuide': 'View Guide →',
    'detail.notes': 'Notes',
    'footer.note': 'For reference only. Please refer to official announcements.',
    'footer.copyright': 'Ascend Server LLM Adaptation List · Auto-synced',
    'theme.dark': '🌙 Dark',
    'theme.light': '☀️ Light',
    'lang.zh': '中文',
    'lang.en': 'English',
  }
};

// ---------- 状态 ----------
let currentLang = localStorage.getItem('dl-lang') || 'zh';
let currentTheme = localStorage.getItem('dl-theme') || 'light';

// ---------- 工具 ----------
function t(key, vars) {
  let s = (I18N[currentLang] && I18N[currentLang][key]) || (I18N.zh[key]) || key;
  if (vars) {
    Object.keys(vars).forEach(k => {
      s = s.replace('{' + k + '}', vars[k]);
    });
  }
  return s;
}

// 替换带 data-i18n 的静态元素文本
function applyStaticI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const text = t(key);
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      el.setAttribute('placeholder', text);
    } else if (el.getAttribute('data-i18n-html') === 'true') {
      el.innerHTML = text;
    } else {
      el.textContent = text;
    }
  });
  // 更新语言/主题按钮显示
  updateSwitchButtons();
}

// ---------- 主题 ----------
function applyTheme() {
  document.documentElement.setAttribute('data-theme', currentTheme);
  updateSwitchButtons();
}

function toggleTheme() {
  currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('dl-theme', currentTheme);
  applyTheme();
}

// ---------- 语言 ----------
function applyLang() {
  currentLang = localStorage.getItem('dl-lang') || 'zh';
  document.documentElement.setAttribute('lang', currentLang === 'zh' ? 'zh-CN' : 'en');
  applyStaticI18n();
  // 触发各模块重渲染，刷新动态文案
  if (typeof onLangChange === 'function') onLangChange();
}

function toggleLang() {
  currentLang = currentLang === 'zh' ? 'en' : 'zh';
  localStorage.setItem('dl-lang', currentLang);
  applyLang();
}

// ---------- 按钮显示 ----------
function updateSwitchButtons() {
  const themeBtn = document.getElementById('themeToggleBtn');
  if (themeBtn) themeBtn.textContent = currentTheme === 'dark' ? t('theme.light') : t('theme.dark');
  const langBtn = document.getElementById('langToggleBtn');
  if (langBtn) langBtn.textContent = currentLang === 'zh' ? 'EN' : '中文';
}

// 初始化
function initI18n() {
  applyTheme();
  applyLang();
}

// 全局钩子，供各模块重渲染动态文案时调用（可覆盖）
window.onLangChange = null;
