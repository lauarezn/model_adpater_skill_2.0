// ============ NV（NVIDIA）产品数据 ============
// 数据由服务端从 data/nv-hardware.json 提供，通过 /admin/api/homepage/nv-hardware 接口获取
window.NV_HARDWARE_DATA = [];

// ============ NV 产品渲染 ============
function renderNvHardware(data) {
  const grid = document.getElementById('nvHardwareGrid');
  const empty = document.getElementById('nvEmptyState');
  if (!grid) return;
  if (data.length === 0) {
    grid.innerHTML = '';
    if (empty) empty.style.display = 'block';
    return;
  }
  if (empty) empty.style.display = 'none';

  grid.innerHTML = data.map(h => {
    let specsHtml = '';
    let specRows;
    if (h.type === 'AI训练服务器' || h.type === 'AI推理服务器') {
      // 整机服务器：展示 GPU/CPU/算力/NVLink/场景
      specRows = [
        ['GPU', h.chip],
        ['CPU', (h.detailSpecs && h.detailSpecs.cpu) || ''],
        ['GPU 总显存', h.memory],
        ['算力', h.fp16Perf || h.fp32Perf],
        ['NVLink', h.interconnect],
        ['适用场景', h.scenario]
      ];
    } else {
      // 加速卡：展示芯片/显存/FP16/FP32/互联/场景
      specRows = [
        ['芯片', h.chip],
        ['显存', h.memory],
        ['FP16 算力', h.fp16Perf],
        ['FP32 算力', h.fp32Perf],
        ['互联', h.interconnect],
        ['适用场景', h.scenario]
      ];
    }
    specRows.forEach(([label, val]) => {
      if (val) specsHtml += `<dt>${label}</dt><dd>${val}</dd>`;
    });

    return `
    <div class="ascend-hw-card" onclick="showNvHardwareDetail('${h.id}')" style="cursor:pointer">
      <h3>${h.name}</h3>
      <div class="hw-subtitle">${h.chip} · ${h.formFactor || ''}</div>
      <span class="hw-badge" data-type="${h.type}">${h.type}</span>
      <div class="hw-specs">${specsHtml}</div>
      <div style="display:flex;gap:4px;flex-wrap:wrap">
        ${(h.features || []).map(f => `<span class="tag">${f}</span>`).join('')}
      </div>
      <div class="hw-card-footer">
        <span class="hw-detail-trigger">📋 点击查看详细规格</span>
      </div>
    </div>`;
  }).join('');
}

function filterNvHardware() {
  const searchEl = document.getElementById('nvSearchInput');
  const chipEl = document.getElementById('nvChipFilter');
  const search = searchEl ? searchEl.value.toLowerCase() : '';
  const chip = chipEl ? chipEl.value : 'all';

  let filtered = window.NV_HARDWARE_DATA.filter(h => {
    if (search && !h.name.toLowerCase().includes(search) && !h.type.toLowerCase().includes(search) && !h.chip.toLowerCase().includes(search) && !h.scenario.toLowerCase().includes(search)) return false;
    if (chip !== 'all' && !h.chip.includes(chip)) return false;
    return true;
  });
  renderNvHardware(filtered);
}

// ============ NV 产品详情 Modal ============
function showNvHardwareDetail(id) {
  const h = window.NV_HARDWARE_DATA.find(x => x.id === id);
  if (!h) return;

  const typeClass = h.type === 'GPU加速卡' ? 'type-infer' : 'type-train';

  // 基础规格
  let specsHtml = '';
  let baseRows;
  if (h.type === 'AI训练服务器' || h.type === 'AI推理服务器') {
    baseRows = [
      ['GPU', h.chip], ['CPU', (h.detailSpecs && h.detailSpecs.cpu) || ''], ['类型', h.type], ['形态', h.formFactor],
      ['GPU 总显存', h.memory], ['算力', h.fp16Perf || h.fp32Perf], ['NVLink', h.interconnect], ['适用场景', h.scenario]
    ];
  } else {
    baseRows = [
      ['芯片', h.chip], ['类型', h.type], ['形态', h.formFactor], ['显存', h.memory],
      ['FP16 算力', h.fp16Perf], ['FP32 算力', h.fp32Perf], ['互联', h.interconnect], ['适用场景', h.scenario]
    ];
  }
  specsHtml += '<dl class="hw-detail-specs">';
  baseRows.forEach(([label, val]) => {
    if (val) specsHtml += `<dt>${label}</dt><dd>${val}</dd>`;
  });
  specsHtml += '</dl>';

  // 推荐模型
  const recHtml = h.recommended
    ? `<div class="hw-detail-section">
        <div class="section-header"><h4>🎯 推荐模型</h4></div>
        <div class="section-body"><p>${h.recommended}</p></div>
      </div>`
    : '';

  // 特性标签
  const featuresHtml = h.features && h.features.length > 0
    ? `<div class="hw-detail-section">
        <div class="section-header"><h4>✨ 产品特性</h4></div>
        <div class="section-body"><div class="tags">${h.features.map(f => `<span class="tag">${f}</span>`).join('')}</div></div>
      </div>`
    : '';

  // 标签
  const tagsHtml = h.tags && h.tags.length > 0
    ? `<div class="hw-detail-section">
        <div class="section-header"><h4>🏷️ 标签</h4></div>
        <div class="section-body"><div class="tags">${h.tags.map(t => `<span class="tag">${t}</span>`).join('')}</div></div>
      </div>`
    : '';

  // 详细规格（detailSpecs）
  let detailSpecsHtml = '';
  if (h.detailSpecs) {
    const ds = h.detailSpecs;
    const specItems = [
      // 计算精度（加速卡）
      { label: 'FP64 算力', icon: '🔢', key: 'fp64' },
      { label: 'FP64 张量算力', icon: '🔢', key: 'fp64TensorCore' },
      { label: 'FP32 算力', icon: '🔢', key: 'fp32' },
      { label: 'TF32 张量算力', icon: '🔢', key: 'tf32' },
      { label: 'BFLOAT16 张量算力', icon: '⚡', key: 'bf16TensorCore' },
      { label: 'FP16 张量算力', icon: '⚡', key: 'fp16TensorCore' },
      { label: 'INT8 张量算力', icon: '🔢', key: 'int8TensorCore' },
      // 服务器整机算力（DGX / HGX / GB200）
      { label: '配置', icon: '🧩', key: 'config' },
      { label: 'NVFP4 张量算力', icon: '⚡', key: 'nvfp4' },
      { label: 'FP4 张量算力', icon: '⚡', key: 'fp4' },
      { label: 'FP8 张量算力', icon: '⚡', key: 'fp8' },
      // 通用
      { label: 'GPU', icon: '🔲', key: 'gpu' },
      { label: 'CPU', icon: '🖥️', key: 'cpu' },
      { label: 'CPU 核心数', icon: '🖥️', key: 'cpuCores' },
      { label: 'CPU 内存 | 带宽', icon: '🧠', key: 'cpuMemory' },
      { label: 'GPU 显存', icon: '💾', key: 'gpuMemory' },
      { label: 'GPU 显存 | 带宽', icon: '💾', key: 'gpuMemoryBandwidth' },
      { label: '快速内存', icon: '⚡', key: 'fastMemory' },
      { label: '显存带宽', icon: '🌐', key: 'memoryBandwidth' },
      { label: '解码器', icon: '🎬', key: 'decoder' },
      { label: '最大功耗 (TDP)', icon: '⚡', key: 'maxTdp' },
      { label: 'Multi-Instance GPU (MIG)', icon: '🔲', key: 'mig' },
      { label: '形态', icon: '📦', key: 'formDetail' },
      { label: '互联', icon: '🔗', key: 'interconnectDetail' },
      { label: 'NVLink', icon: '🔗', key: 'nvlink' },
      { label: 'NVLink 交换系统', icon: '🔗', key: 'nvlinkSwitch' },
      { label: 'NVLink GPU 到 GPU 带宽', icon: '🔗', key: 'gpuToGpuBandwidth' },
      { label: 'NVLink 总带宽', icon: '🔗', key: 'nvlinkBandwidth' },
      { label: '网络带宽', icon: '🌐', key: 'networkBandwidth' },
      { label: '注意力性能', icon: '🎯', key: 'attentionPerf' },
      { label: '网络', icon: '🌐', key: 'network' },
      { label: '管理网络', icon: '⚙️', key: 'managementNetwork' },
      { label: '存储', icon: '📀', key: 'storage' },
      { label: '功耗', icon: '⚡', key: 'powerConsumption' },
      { label: '软件', icon: '🧩', key: 'software' },
      { label: '机架高度', icon: '📐', key: 'rackHeight' },
      { label: '支持服务', icon: '🛠️', key: 'support' },
      { label: 'NVIDIA AI Enterprise', icon: '🧩', key: 'aiEnterprise' },
      { label: '服务器选项', icon: '🖥️', key: 'serverOptions' }
    ];
    detailSpecsHtml = specItems
      .filter(item => ds[item.key])
      .map(item => `
        <div class="hw-detail-section">
          <div class="section-header"><h4>${item.icon} ${item.label}</h4></div>
          <div class="section-body"><p>${ds[item.key]}</p></div>
        </div>
      `).join('');
  }

  document.getElementById('modalBody').innerHTML = `
    <div class="hw-detail-modal">
      <div class="hw-detail-header">
        <h2>${h.name}</h2>
        <div class="hw-meta">
          <span class="hw-spec-label ${typeClass}">${h.type}</span>
          <span>${h.chip}</span>
          <span>·</span>
          <span>${h.memory}</span>
        </div>
      </div>
      ${specsHtml}
      ${recHtml}
      ${featuresHtml}
      ${tagsHtml}
      ${detailSpecsHtml}
    </div>
  `;
  const modal = document.getElementById('modalContent');
  if (modal) modal.scrollTop = 0;
  document.getElementById('modalOverlay').classList.add('active');
  document.body.style.overflow = 'hidden';
}

// ============ 加载 NV 硬件数据 ============
async function loadNvHardwareData() {
  try {
    const resp = await fetch('/admin/api/homepage/nv-hardware');
    if (resp.ok) {
      const data = await resp.json();
      window.NV_HARDWARE_DATA = data.hardware;

      const chipFilter = document.getElementById('nvChipFilter');
      if (chipFilter) {
        chipFilter.innerHTML = '<option value="all">全部芯片</option>' +
          data.chips.map(c => `<option value="${c}">${c}</option>`).join('');
      }

      renderNvHardware(data.hardware);
    }
  } catch (e) {
    console.warn('NV 硬件数据加载失败:', e);
  }
}
