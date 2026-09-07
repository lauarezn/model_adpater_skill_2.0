// ============ 昇腾硬件数据（通过 Admin API 加载，前后端分离）============
// 硬件数据由服务端从 hardware.json 提供，通过 /admin/api/homepage/hardware 接口获取
// 使用 window 全局变量，确保所有 JS 文件中的引用一致
window.ASCEND_HARDWARE_DATA = [];

// ============ 详情规格值格式化（转义 + 列表转换）============
function escDetail(val) {
  return String(val == null ? '' : val)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// 将 detailSpecs 值中的 “•” 列表转换为 HTML <ul><li>，其余行作为段落
function formatDetailValue(val) {
  const lines = String(val == null ? '' : val).split('\n');
  let html = '';
  let inList = false;
  lines.forEach(line => {
    const t = line.trim();
    if (t.startsWith('•')) {
      if (!inList) { html += '<ul class="hw-detail-list">'; inList = true; }
      html += '<li>' + escDetail(t.replace(/^•\s*/, '')) + '</li>';
    } else if (t) {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<div class="hw-detail-line">' + escDetail(t) + '</div>';
    }
  });
  if (inList) html += '</ul>';
  return html;
}

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
      { label: 'AI处理器', icon: '🔲', key: 'aiProcessor' },
      { label: 'AI算力（单 AI 处理器）', icon: '⚡', key: 'aiPerf' },
      { label: 'AI算力（整机）', icon: '⚡', key: 'aiPerfTotal' },
      { label: 'FP16 张量算力（单 AI 处理器）', icon: '⚡', key: 'fp16Single' },
      { label: 'FP32 张量算力（单 AI 处理器）', icon: '⚡', key: 'fp32Single' },
      { label: 'FP16 张量算力', icon: '⚡', key: 'fp16Total' },
      { label: 'FP32 张量算力', icon: '⚡', key: 'fp32Total' },
      { label: 'HF32 张量算力（单 AI 处理器）', icon: '⚡', key: 'hf32Single' },
      { label: 'HF32 张量算力', icon: '⚡', key: 'hf32Total' },
      { label: 'FP16/BF16 张量算力（单 AI 处理器）', icon: '⚡', key: 'fp16bf16Single' },
      { label: 'FP16/BF16 张量算力', icon: '⚡', key: 'fp16bf16Total' },
      { label: 'FP8/HiF8/mxFP8 张量算力（单 AI 处理器）', icon: '⚡', key: 'fp8Single' },
      { label: 'FP8/HiF8/mxFP8 张量算力', icon: '⚡', key: 'fp8Total' },
      { label: 'INT8 张量算力（单 AI 处理器）', icon: '⚡', key: 'int8Single' },
      { label: 'INT8 张量算力', icon: '⚡', key: 'int8Total' },
      { label: 'mxFP4 张量算力（单 AI 处理器）', icon: '⚡', key: 'mxfp4Single' },
      { label: 'mxFP4 张量算力', icon: '⚡', key: 'mxfp4Total' },
      { label: 'HF32 算力', icon: '⚡', key: 'hf32' },
      { label: 'FP32 算力', icon: '⚡', key: 'fp32' },
      { label: 'FP16/BF16 算力', icon: '⚡', key: 'fp16bf16' },
      { label: 'FP8/HiF8/mxFP8 算力', icon: '⚡', key: 'fp8' },
      { label: 'INT8 算力', icon: '⚡', key: 'int8' },
      { label: 'mxFP4 算力', icon: '⚡', key: 'mxfp4' },
      { label: '片上内存', icon: '💾', key: 'onChipMemory' },
      { label: 'GPU 显存', icon: '💾', key: 'gpuMemory' },
      { label: 'GPU 显存带宽', icon: '🌐', key: 'memoryBandwidth' },
      { label: '内存规格', icon: '🧠', key: 'memorySpec' },
      { label: 'CPU处理器', icon: '🖥️', key: 'cpu' },
      { label: 'CPU核心数', icon: '🔢', key: 'cpuCores' },
      { label: '内存', icon: '🧠', key: 'systemMemory' },
      { label: 'CPU算力', icon: '🖥️', key: 'cpuPerf' },
      { label: '基本形态', icon: '📦', key: 'formDetail' },
      { label: '框内互联', icon: '🔗', key: 'intraNodeInterconnect' },
      { label: '框间互联', icon: '🔗', key: 'interNodeInterconnect' },
      { label: '卡间互连', icon: '🔗', key: 'cardInterconnect' },
      { label: '高速端口', icon: '🔗', key: 'highSpeedPort' },
      { label: 'PCIe接口', icon: '🔌', key: 'pcieInterface' },
      { label: '交换网络', icon: '🌐', key: 'network' },
      { label: '网络接口卡', icon: '🌐', key: 'networkCard' },
      { label: '10GE/25GE 接口卡', icon: '🔌', key: 'ioCard' },
      { label: '编解码能力', icon: '🎬', key: 'codec' },
      { label: '虚拟化实例', icon: '🔲', key: 'virtualization' },
      { label: '存储', icon: '📀', key: 'storage' },
      { label: 'PCIe扩展槽位', icon: '🔌', key: 'pcieSlots' },
      { label: '接口', icon: '🔧', key: 'interfaces' },
      { label: '系统管理', icon: '⚙️', key: 'management' },
      { label: '集群扩展', icon: '🌐', key: 'clusterExtend' },
      { label: '风扇', icon: '🌀', key: 'fan' },
      { label: '功耗', icon: '⚡', key: 'powerConsumption' },
      { label: '液冷可靠性', icon: '❄️', key: 'cooling' },
      { label: '显卡', icon: '🖥️', key: 'gpu' },
      { label: '安全特性', icon: '🔒', key: 'security' },
      { label: '环境规格', icon: '📐', key: 'environment' }
    ];
    detailSpecsHtml = specItems
      .filter(item => ds[item.key])
      .map(item => `
        <div class="hw-detail-section">
          <div class="section-header"><h4>${item.icon} ${item.label}</h4></div>
          <div class="section-body">${formatDetailValue(ds[item.key])}</div>
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
