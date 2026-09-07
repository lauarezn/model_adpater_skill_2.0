// ============ Init ============
async function init() {
  const statusEl = document.getElementById('refreshStatus');
  const btn = document.getElementById('refreshBtn');
  const loadingEl = document.getElementById('loadingIndicator');
  const gridEl = document.getElementById('modelGrid');

  // 通过 Admin API 加载数据（前后端分离）
  statusEl.textContent = '正在加载数据...';

  try {
    // 第一步：先加载轻量的统计数据（首屏最快展示）
    const statsResp = await fetch('/admin/api/homepage/stats').catch(() => null);
    if (statsResp && statsResp.ok) {
      const stats = await statsResp.json();
      document.getElementById('hardwareCount').textContent = stats.hardwareCount;
      document.getElementById('modelCount').textContent = stats.modelCount;
      document.getElementById('categoryCount').textContent = stats.categoryCount;
      document.getElementById('dataDate').textContent = stats.dataDate;
    }

    // 第二步：加载模型数据（首屏只加载前50条，大幅减少传输量）
    const modelsResp = await fetch('/admin/api/homepage/models?page=1&page_size=50').catch(() => null);

    if (modelsResp && modelsResp.ok) {
      const data = await modelsResp.json();
      models = data.models;
      dataSource = 'local';

      // 填充筛选器
      const catFilter = document.getElementById('categoryFilter');
      const hwFilter = document.getElementById('hardwareFilter');
      const tagFilter = document.getElementById('tagFilter');
      catFilter.innerHTML = '<option value="all">全部分类</option>' +
        data.categories.map(c => `<option value="${c}">${c}</option>`).join('');

      hwFilter.innerHTML = '<option value="all">全部硬件</option>' +
        data.hardwareOptions.map(h => `<option value="${h}">${h}</option>`).join('');

      if (tagFilter) {
        tagFilter.innerHTML = '<option value="all">全部标签</option>' +
          data.tags.map(t => `<option value="${t}">${t}</option>`).join('');
      }

      // 隐藏 loading，显示网格
      loadingEl.style.display = 'none';
      gridEl.style.display = '';

      // 渲染首屏模型
      renderModels(models);
      const totalPages = Math.ceil(data.total / PAGE_SIZE) || 1;
      renderPagination(totalPages);

      statusEl.textContent = '✅ 数据由服务端每日 06:00 自动同步 · 共 ' + data.total + ' 个模型';

      // 后台异步加载全部模型数据（不阻塞首屏渲染）
      requestAnimationFrame(() => {
        fetch('/admin/api/homepage/models?page=1&page_size=2000').then(resp => {
          if (resp.ok) return resp.json();
        }).then(data => {
          if (data && data.models) {
            models = data.models;
            // 更新筛选器标签（可能包含更多标签）
            if (tagFilter && data.tags) {
              tagFilter.innerHTML = '<option value="all">全部标签</option>' +
                data.tags.map(t => `<option value="${t}">${t}</option>`).join('');
            }
            filterModels();
          }
        }).catch(() => {});
      });
    } else {
      throw new Error('模型数据加载失败');
    }

    // 第三步：后台加载训练模型数据（不阻塞首屏）
    requestAnimationFrame(() => {
      fetch('/admin/api/homepage/train-models?page=1&page_size=1000').then(resp => {
        if (resp.ok) return resp.json();
      }).then(trainData => {
        if (trainData) {
          trainModelsData = trainData.models || [];
          initTrainModelsFromData();
        }
      }).catch(() => {
        trainModelsData = [];
      });

      // 加载硬件数据
      loadHardwareData();

      // 加载 NV（NVIDIA）产品数据
      loadNvHardwareData();

      // 加载 ACL 小模型数据
      loadAclModels();

      // 加载 MindIE 模型数据
      loadMindieModels();

      // 加载全球AI大模型数据
      initGlobalModels();

      // 加载大模型评测基准数据
      initBenchmarks();
    });

  } catch(e) {
    console.warn('数据加载失败:', e);
    statusEl.textContent = '⚠️ 数据加载失败';
    loadingEl.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><p>数据加载失败，请刷新重试</p></div>';
  }
}

// ============ 加载硬件数据 ============
async function loadHardwareData() {
  try {
    const resp = await fetch('/admin/api/homepage/hardware');
    if (resp.ok) {
      const data = await resp.json();
      window.ASCEND_HARDWARE_DATA = data.hardware;

      // 填充芯片筛选
      const chipFilter = document.getElementById('hwChipFilter');
      if (chipFilter) {
        chipFilter.innerHTML = '<option value="all">全部芯片</option>' +
          data.chips.map(c => `<option value="${c}">${c}</option>`).join('');
      }

      renderAscendHardware(data.hardware);
    }
  } catch(e) {
    console.warn('硬件数据加载失败:', e);
  }
}

// ============ Refresh（通过 API 重新加载）============
async function refreshData() {
  document.getElementById('loadingIndicator').style.display = '';
  document.getElementById('modelGrid').style.display = 'none';
  const statusEl = document.getElementById('refreshStatus');
  const btn = document.getElementById('refreshBtn');
  btn.disabled = true;
  statusEl.textContent = '正在重新加载数据...';

  try {
    const resp = await fetch('/admin/api/homepage/models?page=1&page_size=2000');
    if (resp.ok) {
      const data = await resp.json();
      models = data.models;
      dataSource = 'local';

      // 刷新标签筛选器
      const tagFilter = document.getElementById('tagFilter');
      if (tagFilter) {
        tagFilter.innerHTML = '<option value="all">全部标签</option>' +
          data.tags.map(t => `<option value="${t}">${t}</option>`).join('');
      }

      statusEl.textContent = '✅ 已刷新 · 数据由服务端每日 06:00 自动同步 · 共 ' + data.total + ' 个模型';
    } else {
      throw new Error('加载失败');
    }
  } catch(e) {
    if (models.length === 0) {
      statusEl.textContent = '⚠️ 刷新失败';
    } else {
      statusEl.textContent = '⚠️ 刷新失败，使用缓存数据';
    }
  }

  btn.disabled = false;
  document.getElementById('modelCount').textContent = models.length;
  document.getElementById('loadingIndicator').style.display = 'none';
  document.getElementById('modelGrid').style.display = '';

  filterModels();
  loadHardwareData();
  await initTrainModels();
}

// ============ 页面加载时自动初始化 ============
init();
