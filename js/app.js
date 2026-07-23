// ============ Init ============
async function init() {
  const statusEl = document.getElementById('refreshStatus');
  const btn = document.getElementById('refreshBtn');
  const loadingEl = document.getElementById('loadingIndicator');
  const gridEl = document.getElementById('modelGrid');

  // 并行加载所有本地数据文件
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
    // 本地数据加载失败，立即使用离线回退数据，不阻塞首屏
    statusEl.textContent = '⚠️ 本地数据加载失败，使用离线数据（后台尝试在线获取...）';
    models = FALLBACK_MODELS;
    dataSource = 'local';
    // 后台异步尝试在线获取，不阻塞首屏渲染
    setTimeout(async () => {
      const [ascendOk, omniOk, sglangOk, gitcodeOk, sactOk] = await Promise.all([
        fetchAscendData(), fetchOmniData(), fetchSGLangData(),
        fetchGitCodeData(), fetchAscendSACTData()
      ]);
      if (ascendOk || omniOk || sglangOk || gitcodeOk || sactOk) {
        models = mergeModels();
        dataSource = 'merged';
        document.getElementById('modelCount').textContent = models.length;
        const categories = [...new Set(models.map(m => m.category))];
        document.getElementById('categoryCount').textContent = categories.length;
        filterModels();
        statusEl.textContent = '在线补充 ' + models.length + ' 个';
      } else {
        statusEl.textContent = '⚠️ 在线获取失败，使用离线数据';
      }
    }, 0);
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
  statusEl.textContent = '本地数据 ' + models.length + ' 个（点击「手动刷新」获取最新在线数据）';

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


// ============ 在线数据补充加载 ============
// ============ Refresh ============
async function refreshData() {
  document.getElementById('loadingIndicator').style.display = '';
  document.getElementById('modelGrid').style.display = 'none';
  const statusEl = document.getElementById('refreshStatus');
  const btn = document.getElementById('refreshBtn');
  btn.disabled = true;
  statusEl.textContent = '正在从 vLLM Ascend + Omni + SGLang + GitCode AI + Ascend-SACT 获取最新数据...';

  // 先尝试在线获取数据
  const [ascendOk, omniOk, sglangOk, gitcodeOk, sactOk] = await Promise.all([fetchAscendData(), fetchOmniData(), fetchSGLangData(), fetchGitCodeData(), fetchAscendSACTData()]);
  if (ascendOk || omniOk || sglangOk || gitcodeOk || sactOk) {
    models = mergeModels();
    dataSource = 'merged';
    const parts = [];
    if (ascendOk) parts.push('Ascend-vllm ' + ascendModels.length + '个');
    if (omniOk) parts.push('Omni ' + omniModels.length + '个');
    if (sglangOk) parts.push('SGLang ' + sglangModels.length + '个');
    if (gitcodeOk) parts.push('AtomGit Ascend ' + gitcodeModels.length + '个');
    if (sactOk) parts.push('Ascend-SACT ' + sactModels.length + '个');
    statusEl.textContent = '在线补充 ' + parts.join(' + ') + '，共 ' + models.length + ' 个';
    document.getElementById('dataDate').textContent = new Date().toLocaleString('zh-CN');
  }
  // 加载本地数据作为补充（去重合并）
  try {
    const resp = await fetch('data/models-lite.json');
    if (resp.ok) {
      const localModels = await resp.json();
      const seen = new Set(models.map(m => m.name.toLowerCase().replace(/[\s\/-]/g, '')));
      let added = 0;
      localModels.forEach(m => {
        const key = m.name.toLowerCase().replace(/[\s\/-]/g, '');
        if (!seen.has(key)) {
          seen.add(key);
          models.push(m);
          added++;
        }
      });
      if (added > 0) {
        statusEl.textContent = '本地数据 ' + localModels.length + ' 个 | ' + statusEl.textContent + '，新增 ' + added + ' 个';
      } else {
        statusEl.textContent = '本地数据 ' + localModels.length + ' 个 | ' + statusEl.textContent;
      }
    }
  } catch(e) {
    // 如果在线和本地都失败，使用 FALLBACK_MODELS
    if (models.length === 0) {
      models = FALLBACK_MODELS;
      dataSource = 'local';
      statusEl.textContent = '⚠️ 获取失败，使用离线数据';
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

