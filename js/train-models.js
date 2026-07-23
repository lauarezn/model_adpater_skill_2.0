// ============ Hardware ============
function renderAscendHardware(data) {
  const grid = document.getElementById('ascendHardwareGrid');
  const empty = document.getElementById('hwEmptyState');

  if (data.length === 0) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  grid.innerHTML = data.map(h => {
    // 基础规格
    let specsHtml = `
        <dt>芯片</dt><dd>${h.chip}</dd>
        <dt>芯片数量</dt><dd>${h.chipCount}</dd>
        <dt>FP16算力</dt><dd>${h.fp16Perf}</dd>
        <dt>FP32算力</dt><dd>${h.fp32Perf || '-'}</dd>
        <dt>显存</dt><dd>${h.memory}</dd>
        <dt>互联方式</dt><dd>${h.interconnect}</dd>
        <dt>适用场景</dt><dd>${h.scenario}</dd>`;
    // 扩展规格（仅形态）
    if (h.formFactor) specsHtml += `<dt>形态</dt><dd>${h.formFactor}</dd>`;

    return `
    <div class="ascend-hw-card" onclick="showHardwareDetail('${h.id}')" style="cursor:pointer">
      <h3>${h.name}</h3>
      <div class="hw-subtitle">${h.chip} · ${h.chipCount}芯片 · ${h.fp16Perf}</div>
      <span class="hw-badge" data-type="${h.type}">${h.type}</span>
      <div class="hw-specs">${specsHtml}</div>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div style="display:flex;gap:4px;flex-wrap:wrap">
          ${h.features.map(f => `<span class="tag">${f}</span>`).join('')}
        </div>
      </div>
    </div>`;
  }).join('');
}

function filterAscendHardware() {
  const search = document.getElementById('hwSearchInput').value.toLowerCase();
  const type = document.getElementById('hwTypeFilter').value;
  const chip = document.getElementById('hwChipFilter').value;

  let filtered = ASCEND_HARDWARE_DATA.filter(h => {
    if (search && !h.name.toLowerCase().includes(search) && !h.type.toLowerCase().includes(search) && !h.chip.toLowerCase().includes(search) && !h.scenario.toLowerCase().includes(search)) return false;
    if (type !== 'all' && h.type !== type) return false;
    if (chip !== 'all' && !h.chip.includes(chip)) return false;
    return true;
  });
  renderAscendHardware(filtered);
}

// 训练模型数据改为从本地文件异步加载
let trainModelsData = [];


const TRAIN_PAGE_SIZE = 30;
let trainCurrentPage = 1;
let trainFilteredModels = [];

async function initTrainModels() {
  // 从本地文件异步加载训练模型数据
  try {
    const resp = await fetch('data/train-models.json');
    if (resp.ok) {
      const data = await resp.json();
      trainModelsData = data.models || [];
    } else {
      throw new Error('加载失败');
    }
  } catch(e) {
    console.warn('训练模型数据加载失败:', e);
    trainModelsData = [];
  }

  trainFilteredModels = [...trainModelsData];
  trainCurrentPage = 1;

  // 填充分类筛选
  const cats = [...new Set(trainModelsData.map(m => m.category))];
  const catSelect = document.getElementById('trainCategoryFilter');
  cats.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    catSelect.appendChild(opt);
  });

  renderTrainModels();
}

// 同步版本：数据已在 init() 中并行加载完成
function initTrainModelsFromData() {
  trainFilteredModels = [...trainModelsData];
  trainCurrentPage = 1;

  // 填充分类筛选
  const cats = [...new Set(trainModelsData.map(m => m.category))];
  const catSelect = document.getElementById('trainCategoryFilter');
  catSelect.innerHTML = '<option value="all">全部分类</option>';
  cats.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    catSelect.appendChild(opt);
  });

  renderTrainModels();
}

function filterTrainModels() {
  const search = (document.getElementById('trainSearchInput').value || '').toLowerCase();
  const framework = document.getElementById('trainFrameworkFilter').value;
  const category = document.getElementById('trainCategoryFilter').value;
  const status = document.getElementById('trainStatusFilter').value;

  trainFilteredModels = trainModelsData.filter(m => {
    if (search && !m.name.toLowerCase().includes(search) && !m.framework.toLowerCase().includes(search)) return false;
    if (framework !== 'all' && m.framework !== framework) return false;
    if (category !== 'all' && m.category !== category) return false;
    if (status !== 'all' && m.status !== status) return false;
    return true;
  });

  trainCurrentPage = 1;
  renderTrainModels();
}

function renderTrainModels() {
  const grid = document.getElementById('trainModelGrid');
  const pagination = document.getElementById('trainPagination');
  const total = trainFilteredModels.length;
  const totalPages = Math.ceil(total / TRAIN_PAGE_SIZE) || 1;

  if (trainCurrentPage > totalPages) trainCurrentPage = totalPages;

  const start = (trainCurrentPage - 1) * TRAIN_PAGE_SIZE;
  const end = Math.min(start + TRAIN_PAGE_SIZE, total);
  const pageModels = trainFilteredModels.slice(start, end);

  if (total === 0) {
    grid.innerHTML = '<div class="empty-state"><div class="icon">🔍</div><p>没有找到匹配的训练模型</p></div>';
    pagination.innerHTML = '';
    return;
  }

  grid.innerHTML = pageModels.map(m => {
    const statusClass = m.status === '测试中' ? 'testing' : '';
    const frameworkLabel = m.framework === 'MM' ? 'MindSpeed-MM' : 'MindSpeed-LLM';
    return `
      <div class="train-model-card">
        <div class="model-name">${m.name}</div>
        <div class="model-meta">
          <span class="tag tag-framework">${frameworkLabel}</span>
          <span class="tag tag-params">${m.params}</span>
          <span class="tag tag-cluster">${m.cluster}</span>
          <span class="tag tag-precision">${m.precision}</span>
          <span class="tag tag-status ${statusClass}">${m.status}</span>
        </div>
        <div class="model-desc">${m.desc}</div>
        <div class="model-task">任务：${m.task}</div>
        <div class="model-category">分类：${m.category}</div>
      </div>
    `;
  }).join('');

  // 分页
  let pagHtml = '<div class="page-controls">';
  pagHtml += `<button class="page-btn" onclick="trainGoPage(1)" ${trainCurrentPage <= 1 ? 'disabled' : ''}>首页</button>`;
  pagHtml += `<button class="page-btn" onclick="trainGoPage(${trainCurrentPage - 1})" ${trainCurrentPage <= 1 ? 'disabled' : ''}>上一页</button>`;

  const maxVisible = 5;
  let pageStart = Math.max(1, trainCurrentPage - Math.floor(maxVisible / 2));
  let pageEnd = Math.min(totalPages, pageStart + maxVisible - 1);
  if (pageEnd - pageStart + 1 < maxVisible) pageStart = Math.max(1, pageEnd - maxVisible + 1);

  for (let i = pageStart; i <= pageEnd; i++) {
    pagHtml += `<button class="page-btn ${i === trainCurrentPage ? 'active' : ''}" onclick="trainGoPage(${i})">${i}</button>`;
  }

  pagHtml += `<button class="page-btn" onclick="trainGoPage(${trainCurrentPage + 1})" ${trainCurrentPage >= totalPages ? 'disabled' : ''}>下一页</button>`;
  pagHtml += `<button class="page-btn" onclick="trainGoPage(${totalPages})" ${trainCurrentPage >= totalPages ? 'disabled' : ''}>末页</button>`;
  pagHtml += `<span style="margin-left:12px;font-size:0.85rem;color:var(--color-text-secondary)">共 ${total} 个模型</span>`;
  pagHtml += '</div>';
  pagination.innerHTML = pagHtml;
}

function trainGoPage(page) {
  trainCurrentPage = page;
  renderTrainModels();
  document.getElementById('section-train-models').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

