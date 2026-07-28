// ============ Init ============
async function init() {
  const statusEl = document.getElementById('refreshStatus');
  const btn = document.getElementById('refreshBtn');
  const loadingEl = document.getElementById('loadingIndicator');
  const gridEl = document.getElementById('modelGrid');

  // 加载本地数据文件（服务端每天定时爬取同步，无需浏览器端远程请求）
  statusEl.textContent = '正在加载本地数据...';
  const [modelsResp, trainResp] = await Promise.all([
    fetch('data/models-lite.json').catch(() => null),
    fetch('data/train-models.json').catch(() => null)
  ]);

  // 处理模型数据
  if (modelsResp && modelsResp.ok) {
    try {
      const localModels = await modelsResp.json();
      models = localModels;
      dataSource = 'local';
    } catch(e) {
      models = null;
    }
  }

  if (!models) {
    // 本地数据加载失败，使用离线回退数据
    statusEl.textContent = '⚠️ 本地数据加载失败，使用离线数据';
    models = FALLBACK_MODELS;
    dataSource = 'local';
  }

  btn.disabled = false;

  // 处理训练模型数据
  if (trainResp && trainResp.ok) {
    try {
      const data = await trainResp.json();
      trainModelsData = data.models || [];
    } catch(e) {
      trainModelsData = [];
    }
  } else {
    trainModelsData = [];
  }

  // === 首屏渲染（最小化 DOM 操作）===
  document.getElementById('hardwareCount').textContent = ASCEND_HARDWARE_DATA.length;
  document.getElementById('modelCount').textContent = models.length;
  const categories = [...new Set(models.map(m => m.category))];
  document.getElementById('categoryCount').textContent = categories.length;

  // 一次性填充筛选器
  const catFilter = document.getElementById('categoryFilter');
  const hwFilter = document.getElementById('hardwareFilter');
  catFilter.innerHTML = '<option value="all">全部分类</option>' +
    categories.map(c => `<option value="${c}">${c}</option>`).join('');

  const hwSet = new Set();
  models.forEach(m => {
    if (m.minHardware) hwSet.add(m.minHardware);
    if (m.recommendedHardware) hwSet.add(m.recommendedHardware);
  });
  hwFilter.innerHTML = '<option value="all">全部硬件</option>' +
    [...hwSet].map(h => `<option value="${h}">${h}</option>`).join('');

  // 隐藏 loading，显示网格
  loadingEl.style.display = 'none';
  gridEl.style.display = '';

  // 增量渲染：先显示前50个模型
  const initialCount = Math.min(50, models.length);
  renderModels(models.slice(0, initialCount));
  const totalPages = Math.ceil(models.length / PAGE_SIZE) || 1;
  renderPagination(totalPages);

  const now = new Date().toLocaleString('zh-CN');
  document.getElementById('dataDate').textContent = now;
  statusEl.textContent = '✅ 数据由服务端每日 06:00 自动同步 · 共 ' + models.length + ' 个模型';

  // === 后台非关键操作（不阻塞首屏）===
  requestAnimationFrame(() => {
    // 初始化完整筛选和分页
    filterModels();

    // 加载详情数据
    fetch('data/models-detail.json').then(r => r.json()).then(detailModels => {
      window._detailModels = detailModels;
    }).catch(() => {
      window._detailModels = null;
    });

    // 渲染硬件和训练模型
    renderAscendHardware(ASCEND_HARDWARE_DATA);
    initTrainModelsFromData();
  });
}


// ============ Refresh（仅重新加载本地数据，无需远程爬取）============
async function refreshData() {
  document.getElementById('loadingIndicator').style.display = '';
  document.getElementById('modelGrid').style.display = 'none';
  const statusEl = document.getElementById('refreshStatus');
  const btn = document.getElementById('refreshBtn');
  btn.disabled = true;
  statusEl.textContent = '正在重新加载本地数据...';

  try {
    const resp = await fetch('data/models-lite.json');
    if (resp.ok) {
      const localModels = await resp.json();
      models = localModels;
      dataSource = 'local';
      statusEl.textContent = '✅ 已刷新 · 数据由服务端每日 06:00 自动同步 · 共 ' + models.length + ' 个模型';
    } else {
      throw new Error('加载失败');
    }
  } catch(e) {
    if (models.length === 0) {
      models = FALLBACK_MODELS;
      dataSource = 'local';
      statusEl.textContent = '⚠️ 加载失败，使用离线数据';
    } else {
      statusEl.textContent = '⚠️ 刷新失败，使用缓存数据';
    }
  }

  btn.disabled = false;
  document.getElementById('modelCount').textContent = models.length;
  document.getElementById('loadingIndicator').style.display = 'none';
  document.getElementById('modelGrid').style.display = '';

  // 后台加载详情数据
  fetch('data/models-detail.json').then(r => r.json()).then(detailModels => {
    window._detailModels = detailModels;
  }).catch(() => {
    window._detailModels = null;
  });

  filterModels();
  renderAscendHardware(ASCEND_HARDWARE_DATA);
  await initTrainModels();
}

