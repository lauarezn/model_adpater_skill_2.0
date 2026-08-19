// ============ 昇腾硬件数据（通过 Admin API 加载，前后端分离）============
// 硬件数据由服务端从 hardware.json 提供，通过 /admin/api/homepage/hardware 接口获取
// 使用 window 全局变量，确保所有 JS 文件中的引用一致
window.ASCEND_HARDWARE_DATA = [];

// ============ Hardware Detail Modal ============
function showHardwareDetail(id) {
  const h = window.ASCEND_HARDWARE_DATA.find(x => x.id === id);
  if (!h) return;

  // 类型标签样式
  const typeClass = h.type === '中心训练硬件' ? 'type-train' : 'type-infer';

  // 基础规格表格
  let specsHtml = `
    <dl class="hw-detail-specs">
      <dt>芯片</dt><dd>${h.chip}</dd>
      <dt>芯片数量</dt><dd>${h.chipCount}</dd>
      <dt>FP16算力</dt><dd>${h.fp16Perf}</dd>
      <dt>FP32算力</dt><dd>${h.fp32Perf || '-'}</dd>
      <dt>显存</dt><dd>${h.memory}</dd>
      <dt>互联方式</dt><dd>${h.interconnect}</dd>
      <dt>适用场景</dt><dd>${h.scenario}</dd>`;
  if (h.formFactor) specsHtml += `<dt>形态</dt><dd>${h.formFactor}</dd>`;
  specsHtml += `</dl>`;

  // 推荐模型区块
  const recHtml = h.recommended
    ? `<div class="hw-detail-section">
        <div class="section-header"><h4>🎯 推荐模型</h4></div>
        <div class="section-body"><p>${h.recommended}</p></div>
      </div>`
    : '';

  // 特性标签区块
  const featuresHtml = h.features && h.features.length > 0
    ? `<div class="hw-detail-section">
        <div class="section-header"><h4>✨ 产品特性</h4></div>
        <div class="section-body"><div class="tags">${h.features.map(f => `<span class="tag">${f}</span>`).join('')}</div></div>
      </div>`
    : '';

  // 标签区块
  const tagsHtml = h.tags && h.tags.length > 0
    ? `<div class="hw-detail-section">
        <div class="section-header"><h4>🏷️ 标签</h4></div>
        <div class="section-body"><div class="tags">${h.tags.map(t => `<span class="tag">${t}</span>`).join('')}</div></div>
      </div>`
    : '';

  // 扩展规格区块（当 detailSpecs 存在时展示）
  let detailSpecsHtml = '';
  if (h.detailSpecs) {
    const ds = h.detailSpecs;
    const specItems = [
      { label: 'NPU模组与互联', icon: '🔗', key: 'npuModule' },
      { label: 'AI算力（稠密算力）', icon: '⚡', key: 'aiPerf' },
      { label: '片上内存', icon: '💾', key: 'onChipMemory' },
      { label: 'CPU处理器', icon: '🖥️', key: 'cpu' },
      { label: '内存', icon: '🧠', key: 'systemMemory' },
      { label: '交换网络', icon: '🌐', key: 'network' },
      { label: '存储', icon: '📀', key: 'storage' },
      { label: 'PCIe扩展槽位', icon: '🔌', key: 'pcieSlots' },
      { label: '接口', icon: '🔧', key: 'interfaces' },
      { label: '系统管理', icon: '⚙️', key: 'management' },
      { label: '液冷可靠性', icon: '❄️', key: 'cooling' },
      { label: '环境规格', icon: '📐', key: 'environment' },
      // PCIe卡专用规格
      { label: '基本形态', icon: '📦', key: 'formDetail' },
      { label: 'AI处理器', icon: '🔲', key: 'aiProcessor' },
      { label: '内存规格', icon: '🧠', key: 'memorySpec' },
      { label: 'CPU算力', icon: '🖥️', key: 'cpuPerf' },
      { label: '编解码能力', icon: '🎬', key: 'codec' },
      { label: '虚拟化实例', icon: '🔲', key: 'virtualization' },
      { label: 'PCIe接口', icon: '🔌', key: 'pcieInterface' },
      { label: '功耗', icon: '⚡', key: 'powerConsumption' },
      { label: '卡间互连', icon: '🔗', key: 'cardInterconnect' },
      // 训练服务器专用规格
      { label: '网络接口卡', icon: '🌐', key: 'networkCard' },
      { label: '风扇', icon: '🌀', key: 'fan' },
      { label: '安全特性', icon: '🔒', key: 'security' },
      { label: '显卡', icon: '🖥️', key: 'gpu' }
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
          <span>${h.chipCount}芯片</span>
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
