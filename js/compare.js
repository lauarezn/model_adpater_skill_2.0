// ============ 产品对比（大模型对比 / 服务器硬件产品对比）============
// 大模型对比严格参考 DataLearner benchmark-compare 布局：
//   左侧「选择模型」卡片 + 右侧「选择评测基准」卡片 + 底部「生成对比」按钮。
// 生成对比时抓取各评测基准的榜单，构建「模型 × 基准」得分对比矩阵（仅展示所选模型）。

let compareAllModels = [];   // 全部全球大模型
let compareAllBench = [];    // 全部评测基准

// 已选择项（Set 存储，分别用 model_code 与基准 urlCode 作为 key）
let selectedCompareModels = new Set();
let selectedCompareBench = new Set();
let selectedModelInfo = {};  // model_code -> { name, org }
let selectedBenchInfo = {};  // urlCode -> { name }

// ---------- 通用工具 ----------
function escCompare(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
function fmtScore(v) {
  if (v === null || v === undefined || v === '') return '-';
  const n = Number(v);
  if (!isNaN(n)) return n;
  return escCompare(v);
}

// ============ 大模型对比：初始化 ============
async function initCompareModels() {
  try {
    // 加载评测基准（供评测选择框）
    const bResp = await fetch('/admin/api/benchmarks?page=1&page_size=2000');
    if (bResp.ok) {
      const bData = await bResp.json();
      compareAllBench = bData.benchmarks || [];
    }
  } catch (e) { console.warn('评测基准加载失败:', e); }
  try {
    // 加载全球大模型（供模型选择框）
    const mResp = await fetch('/admin/api/global-models?page=1&page_size=1000');
    if (mResp.ok) {
      const mData = await mResp.json();
      compareAllModels = mData.models || [];
    }
  } catch (e) { console.warn('模型数据加载失败:', e); }

  renderCompareModelList();
  renderCompareBenchList();
  updateModelSelectionUI();
  updateBenchSelectionUI();
  updateGenerateHint();
}

// ============ 模型选择框 ============
function currentCompareModelSearch() {
  const el = document.getElementById('dlModelSearch');
  return el ? (el.value || '').trim().toLowerCase() : '';
}
function filterCompareModels() { renderCompareModelList(); }

function renderCompareModelList() {
  const listEl = document.getElementById('dlModelList');
  if (!listEl) return;
  const q = currentCompareModelSearch();
  let items = compareAllModels;
  if (q) {
    items = items.filter(m =>
      (m.model_abbr_name || '').toLowerCase().includes(q) ||
      (m.orgName || '').toLowerCase().includes(q) ||
      (m.model_code || '').toLowerCase().includes(q)
    );
  }
  // 最多显示 60 条，避免列表过长
  const shown = items.slice(0, 60);
  if (shown.length === 0) {
    listEl.innerHTML = '<li class="dl-list-empty">无匹配模型</li>';
    return;
  }
  listEl.innerHTML = shown.map(m => {
    const code = m.model_code;
    const on = selectedCompareModels.has(code);
    return '<li class="dl-list-item' + (on ? ' dl-list-item--selected' : '') + '" data-code="' + escCompare(code) + '" onclick="toggleCompareModel(\'' + escCompare(code) + '\')">' +
      '<span class="dl-item-main"><span class="dl-item-name">' + escCompare(m.model_abbr_name) + '</span>' +
      '<span class="dl-item-sub">By ' + escCompare(m.orgName || '未知机构') + '</span></span>' +
      (on ? '<span class="dl-item-check">✓</span>' : '') +
    '</li>';
  }).join('');
}

function toggleCompareModel(code) {
  if (selectedCompareModels.has(code)) {
    selectedCompareModels.delete(code);
  } else {
    if (selectedCompareModels.size >= 10) {
      alert('最多选择 10 个模型');
      return;
    }
    selectedCompareModels.add(code);
    const m = compareAllModels.find(x => x.model_code === code);
    if (m) selectedModelInfo[code] = { name: m.model_abbr_name, org: m.orgName };
  }
  renderCompareModelList();
  updateModelSelectionUI();
}

function removeCompareModel(code) {
  selectedCompareModels.delete(code);
  renderCompareModelList();
  updateModelSelectionUI();
}

function updateModelSelectionUI() {
  const countEl = document.getElementById('dlModelCount');
  if (countEl) countEl.textContent = selectedCompareModels.size;
  const wrap = document.getElementById('dlSelectedModels');
  if (!wrap) return;
  if (selectedCompareModels.size === 0) {
    wrap.innerHTML = '<span class="dl-selected-empty">暂未选择模型</span>';
  } else {
    wrap.innerHTML = Array.from(selectedCompareModels).map(code => {
      const info = selectedModelInfo[code] || { name: code, org: '' };
      return '<span class="dl-chip">' + escCompare(info.name) +
        '<button class="dl-chip-x" onclick="removeCompareModel(\'' + escCompare(code) + '\')">&times;</button></span>';
    }).join('');
  }
  updateGenerateHint();
}

// ============ 评测基准选择框 ============
function currentCompareBenchSearch() {
  const el = document.getElementById('dlBenchSearch');
  return el ? (el.value || '').trim().toLowerCase() : '';
}
function filterCompareBench() { renderCompareBenchList(); }

function renderCompareBenchList() {
  const listEl = document.getElementById('dlBenchList');
  if (!listEl) return;
  const q = currentCompareBenchSearch();
  let items = compareAllBench;
  if (q) {
    items = items.filter(b =>
      (b.shortName || '').toLowerCase().includes(q) ||
      (b.fullName || '').toLowerCase().includes(q) ||
      (b.category || '').toLowerCase().includes(q)
    );
  }
  const shown = items.slice(0, 60);
  if (shown.length === 0) {
    listEl.innerHTML = '<li class="dl-list-empty">无匹配评测基准</li>';
    return;
  }
  listEl.innerHTML = shown.map(b => {
    const code = b.urlCode || b.benchmarkCode;
    const on = selectedCompareBench.has(code);
    return '<li class="dl-list-item' + (on ? ' dl-list-item--selected' : '') + '" data-code="' + escCompare(code) + '" onclick="toggleCompareBench(\'' + escCompare(code) + '\')">' +
      '<span class="dl-item-main"><span class="dl-item-name">' + escCompare(b.shortName) + '</span>' +
      '<span class="dl-item-sub">' + escCompare(b.category || '') + '</span></span>' +
      (on ? '<span class="dl-item-check">✓</span>' : '') +
    '</li>';
  }).join('');
}

function toggleCompareBench(code) {
  if (selectedCompareBench.has(code)) {
    selectedCompareBench.delete(code);
  } else {
    if (selectedCompareBench.size >= 8) {
      alert('最多选择 8 个评测基准');
      return;
    }
    selectedCompareBench.add(code);
    const b = compareAllBench.find(x => (x.urlCode || x.benchmarkCode) === code);
    if (b) selectedBenchInfo[code] = { name: b.shortName };
  }
  renderCompareBenchList();
  updateBenchSelectionUI();
}

function removeCompareBench(code) {
  selectedCompareBench.delete(code);
  renderCompareBenchList();
  updateBenchSelectionUI();
}

function updateBenchSelectionUI() {
  const countEl = document.getElementById('dlBenchCount');
  if (countEl) countEl.textContent = selectedCompareBench.size;
  const wrap = document.getElementById('dlSelectedBench');
  if (!wrap) return;
  if (selectedCompareBench.size === 0) {
    wrap.innerHTML = '<span class="dl-selected-empty">暂未选择评测基准</span>';
  } else {
    wrap.innerHTML = Array.from(selectedCompareBench).map(code => {
      const info = selectedBenchInfo[code] || { name: code };
      return '<span class="dl-chip dl-chip--bench">' + escCompare(info.name) +
        '<button class="dl-chip-x" onclick="removeCompareBench(\'' + escCompare(code) + '\')">&times;</button></span>';
    }).join('');
  }
}

// 生成按钮提示：至少选 2 个模型
function updateGenerateHint() {
  const btn = document.getElementById('dlGenerateBtn');
  const hint = document.getElementById('dlGenerateHint');
  if (!btn || !hint) return;
  if (selectedCompareModels.size >= 2) {
    btn.disabled = false;
    hint.style.display = 'none';
  } else {
    btn.disabled = true;
    hint.style.display = '';
  }
}

// ============ 生成对比：跳转到独立对比结果页 ============
function runModelCompare() {
  const modelCodes = Array.from(selectedCompareModels);
  if (modelCodes.length < 2) {
    const resultEl = document.getElementById('compareModelsResult');
    if (resultEl) resultEl.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><p>请至少选择 2 个模型</p></div>';
    return;
  }

  const benchCodes = Array.from(selectedCompareBench);
  // 用模型数字 ID 构建 modelInputString（与 DataLearner 对比页参数一致）
  const ids = modelCodes.map(c => {
    const m = compareAllModels.find(x => x.model_code === c);
    return (m && m.model_id != null) ? m.model_id : c;
  });
  const params = new URLSearchParams();
  params.set('modelInputString', ids.join(','));
  params.set('excludeParallel', 'true');
  if (benchCodes.length > 0) params.set('benchmark', benchCodes.join(','));
  window.location.href = 'model_compare.html?' + params.toString();
}

function renderModelCompareMatrix(matrix, benchCodes, benchMeta, selectedNames) {
  const resultEl = document.getElementById('compareModelsResult');
  const models = selectedNames.filter(n => matrix[n]);

  if (models.length === 0) {
    resultEl.innerHTML = '<div class="empty-state"><div class="icon">📭</div><p>所选基准暂未获取到模型榜单数据</p></div>';
    return;
  }

  const thead = '<th class="cmp-model-col">模型 / 机构</th>' +
    benchCodes.map(code => '<th class="cmp-score-col" title="' + escCompare((benchMeta[code] && benchMeta[code].shortName) || code) + '">' +
      escCompare((benchMeta[code] && benchMeta[code].shortName) || code) + '</th>').join('');

  const rows = models.map(name => {
    const m = matrix[name];
    const cells = benchCodes.map(code => {
      const v = m.scores[code];
      const cls = (v === null || v === undefined || v === '') ? 'cmp-na' : 'cmp-score';
      return '<td class="' + cls + '">' + fmtScore(v) + '</td>';
    }).join('');
    return '<tr>' +
      '<td class="cmp-model-name">' + escCompare(m.name) +
        (m.org ? '<div class="cmp-model-org">' + escCompare(m.org) + '</div>' : '') +
      '</td>' + cells + '</tr>';
  }).join('');

  const countSummary = models.length + ' 个模型 × ' + benchCodes.length + ' 个基准';
  resultEl.innerHTML =
    '<div class="compare-result-wrap">' +
      '<div class="compare-result-head">' +
        '<h3>🏆 模型评测得分对比</h3>' +
        '<span class="compare-result-count">' + countSummary + '</span>' +
      '</div>' +
      '<div class="bd-table-wrap"><table class="bd-table compare-matrix">' +
        '<thead><tr>' + thead + '</tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
      '</table></div>' +
      '<div class="compare-footnote">数据来源：DataLearner 大模型评测基准榜单（"-" 表示该模型未参与该基准评测）</div>' +
    '</div>';
}

// ============ 服务器硬件产品对比 ============
let compareAscendHw = [];      // 昇腾设备（左框）
let compareNonAscendHw = [];   // 非昇腾设备，如 NV（右框）
let selectedHwIds = new Set(); // 合并的选中集合（id 全局唯一）

async function initCompareHardware() {
  try {
    const resp = await fetch('/admin/api/homepage/hardware');
    if (resp.ok) {
      const data = await resp.json();
      compareAscendHw = data.hardware || [];
    }
  } catch (e) {
    console.warn('昇腾硬件数据加载失败:', e);
  }
  try {
    const resp = await fetch('/admin/api/homepage/nv-hardware');
    if (resp.ok) {
      const data = await resp.json();
      compareNonAscendHw = data.hardware || [];
    }
  } catch (e) {
    console.warn('非昇腾硬件数据加载失败:', e);
  }
  // 从对比结果页返回时，URL 携带 ids 参数，自动预选这些硬件
  try {
    const idsParam = new URLSearchParams(window.location.search).get('ids');
    if (idsParam) {
      idsParam.split(',').forEach(id => {
        id = (id || '').trim();
        if (id && (compareAscendHw.some(x => x.id === id) || compareNonAscendHw.some(x => x.id === id))) {
          if (selectedHwIds.size < 6) selectedHwIds.add(id);
        }
      });
    }
  } catch (e) { /* 忽略 URL 解析异常 */ }
  renderHwAscendList();
  renderHwNonAscendList();
  updateHwSelectionUI();
}

// 查找硬件（昇腾 + 非昇腾）
function findHardwareById(id) {
  return compareAscendHw.find(x => x.id === id) || compareNonAscendHw.find(x => x.id === id);
}

// ===== 左框：昇腾设备 =====
function currentHwAscendSearch() {
  const el = document.getElementById('dlHwAscendSearch');
  return el ? (el.value || '').trim().toLowerCase() : '';
}
function filterCompareHwAscend() { renderHwAscendList(); }

function renderHwAscendList() {
  const listEl = document.getElementById('dlHwAscendList');
  if (!listEl) return;
  const q = currentHwAscendSearch();
  let items = compareAscendHw;
  if (q) {
    items = items.filter(h =>
      (h.name || '').toLowerCase().includes(q) ||
      (h.type || '').toLowerCase().includes(q) ||
      (h.chip || '').toLowerCase().includes(q) ||
      (h.scenario || '').toLowerCase().includes(q)
    );
  }
  if (items.length === 0) {
    listEl.innerHTML = '<li class="dl-list-empty">无匹配昇腾设备</li>';
    return;
  }
  listEl.innerHTML = items.map(h => {
    const on = selectedHwIds.has(h.id);
    const sub = [h.type, h.chip].filter(Boolean).join(' · ');
    return '<li class="dl-list-item' + (on ? ' dl-list-item--selected' : '') + '" data-id="' + escCompare(h.id) + '" onclick="toggleHardware(\'' + escCompare(h.id) + '\')">' +
      '<span class="dl-item-main"><span class="dl-item-name">' + escCompare(h.name) + '</span>' +
      (sub ? '<span class="dl-item-sub">' + escCompare(sub) + '</span>' : '') + '</span>' +
      (on ? '<span class="dl-item-check">✓</span>' : '') +
    '</li>';
  }).join('');
}

// ===== 右框：非昇腾设备 =====
function currentHwNonAscendSearch() {
  const el = document.getElementById('dlHwNonAscendSearch');
  return el ? (el.value || '').trim().toLowerCase() : '';
}
function filterCompareHwNonAscend() { renderHwNonAscendList(); }

function renderHwNonAscendList() {
  const listEl = document.getElementById('dlHwNonAscendList');
  if (!listEl) return;
  const q = currentHwNonAscendSearch();
  let items = compareNonAscendHw;
  if (q) {
    items = items.filter(h =>
      (h.name || '').toLowerCase().includes(q) ||
      (h.type || '').toLowerCase().includes(q) ||
      (h.chip || '').toLowerCase().includes(q) ||
      (h.scenario || '').toLowerCase().includes(q)
    );
  }
  if (items.length === 0) {
    listEl.innerHTML = '<li class="dl-list-empty">无匹配非昇腾设备</li>';
    return;
  }
  listEl.innerHTML = items.map(h => {
    const on = selectedHwIds.has(h.id);
    const sub = [h.type, h.chip].filter(Boolean).join(' · ');
    return '<li class="dl-list-item' + (on ? ' dl-list-item--selected' : '') + '" data-id="' + escCompare(h.id) + '" onclick="toggleHardware(\'' + escCompare(h.id) + '\')">' +
      '<span class="dl-item-main"><span class="dl-item-name">' + escCompare(h.name) + '</span>' +
      (sub ? '<span class="dl-item-sub">' + escCompare(sub) + '</span>' : '') + '</span>' +
      (on ? '<span class="dl-item-check">✓</span>' : '') +
    '</li>';
  }).join('');
}

function toggleHardware(id) {
  if (selectedHwIds.has(id)) {
    selectedHwIds.delete(id);
  } else {
    if (selectedHwIds.size >= 6) { alert('最多选择 6 个硬件产品'); return; }
    selectedHwIds.add(id);
  }
  renderHwAscendList();
  renderHwNonAscendList();
  updateHwSelectionUI();
}

function removeHardware(id) {
  selectedHwIds.delete(id);
  renderHwAscendList();
  renderHwNonAscendList();
  updateHwSelectionUI();
}

function updateHwSelectionUI() {
  const ascendCountEl = document.getElementById('dlHwAscendCount');
  if (ascendCountEl) {
    ascendCountEl.textContent = Array.from(selectedHwIds).filter(id => compareAscendHw.some(x => x.id === id)).length;
  }
  const nonAscendCountEl = document.getElementById('dlHwNonAscendCount');
  if (nonAscendCountEl) {
    nonAscendCountEl.textContent = Array.from(selectedHwIds).filter(id => compareNonAscendHw.some(x => x.id === id)).length;
  }
  renderSelectedChips('dlSelectedHwAscend', compareAscendHw);
  renderSelectedChips('dlSelectedHwNonAscend', compareNonAscendHw);
  updateHwGenerateHint();
}

function renderSelectedChips(wrapId, pool) {
  const wrap = document.getElementById(wrapId);
  if (!wrap) return;
  const selectedInPool = Array.from(selectedHwIds).filter(id => pool.some(x => x.id === id));
  if (selectedInPool.length === 0) {
    const emptyText = (wrapId === 'dlSelectedHwAscend') ? '暂未选择昇腾设备' : '暂未选择非昇腾设备';
    wrap.innerHTML = '<span class="dl-selected-empty">' + emptyText + '</span>';
  } else {
    wrap.innerHTML = selectedInPool.map(id => {
      const h = pool.find(x => x.id === id);
      const name = h ? h.name : id;
      return '<span class="dl-chip dl-chip--hw">' + escCompare(name) +
        '<button class="dl-chip-x" onclick="removeHardware(\'' + escCompare(id) + '\')">×</button></span>';
    }).join('');
  }
}

function updateHwGenerateHint() {
  const btn = document.getElementById('dlHwGenerateBtn');
  const hint = document.getElementById('dlHwGenerateHint');
  if (!btn || !hint) return;
  if (selectedHwIds.size >= 2) { btn.disabled = false; hint.style.display = 'none'; }
  else { btn.disabled = true; hint.style.display = ''; }
}

function runHardwareCompare() {
  const resultEl = document.getElementById('compareHardwareResult');
  const loading = document.getElementById('compareHardwareLoading');
  const ids = Array.from(selectedHwIds);
  if (ids.length < 2) {
    if (resultEl) resultEl.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><p>请至少选择 2 个硬件产品</p></div>';
    return;
  }
  if (ids.length > 6) {
    if (resultEl) resultEl.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><p>最多选择 6 个硬件产品</p></div>';
    return;
  }
  // 跳转到独立的硬件对比结果页（与大模型对比一致），携带选中硬件 id
  const params = new URLSearchParams();
  params.set('ids', ids.join(','));
  window.location.href = 'hardware_compare.html?' + params.toString();
}

function renderHardwareCompare(selected) {
  const resultEl = document.getElementById('compareHardwareResult');
  if (selected.length === 0) {
    resultEl.innerHTML = '<div class="empty-state"><div class="icon">📭</div><p>未找到所选硬件产品</p></div>';
    return;
  }

  const hwTypeCls = t => (t === '中心训练硬件' ? 'type-train' : 'type-infer');

  // ===== 0. 总结性结论 =====
  function parseFlops(s) {
    if (!s) return null;
    const m = String(s).match(/([\d.]+)\s*(P|T)?\s*FLOPS/i);
    if (!m) return null;
    let n = parseFloat(m[1]);
    const unit = (m[2] || '').toUpperCase();
    if (unit === 'P') n = n * 1000; // 统一换算为 TFLOPS 以便比较
    return n;
  }
  function hardwareConclusionHtml(list) {
    const esc = escCompare;
    const isAscend = h => /atlas/i.test(h.id || '') || /昇腾|Atlas/i.test(h.chip || '') || (h.tags || []).some(t => /昇腾|Atlas/i.test(t));
    const isNvidia = h => /nvidia/i.test(h.id || '') || /nvidia/i.test(h.chip || '') || (h.tags || []).some(t => /nvidia/i.test(t));
    const ascendList = list.filter(isAscend);
    const nvidiaList = list.filter(isNvidia);
    const otherList = list.filter(h => !isAscend(h) && !isNvidia(h));

    // 内存容量解析（GB）
    function parseMemGB(s) {
      if (!s) return null;
      const m = String(s).match(/([\d.]+)\s*(T|G)?B/i);
      if (!m) return null;
      let n = parseFloat(m[1]);
      const unit = (m[2] || 'G').toUpperCase();
      if (unit === 'T') n = n * 1024;
      return n;
    }
    const typeCnt = {};
    list.forEach(h => {
      const t = h.type || '未分类';
      typeCnt[t] = (typeCnt[t] || 0) + 1;
    });
    const typeText = Object.keys(typeCnt).map(t => typeCnt[t] + ' 款「' + t + '」').join('、');

    // 生态总览
    const eco = [];
    if (ascendList.length) eco.push('昇腾（Ascend）生态 ' + ascendList.length + ' 款');
    if (nvidiaList.length) eco.push('NVIDIA 生态 ' + nvidiaList.length + ' 款');
    if (otherList.length) eco.push('其他 ' + otherList.length + ' 款');
    const ecoText = eco.length ? '本次对比覆盖 ' + eco.join('、') + '。' : '';

    // 算力梯队（FP16）
    const perfList = list.map(h => ({ h, v: parseFlops(h.fp16Perf) }))
      .filter(x => x.v != null).sort((a, b) => b.v - a.v);
    let perfText = '';
    if (perfList.length >= 2) {
      const top = perfList[0], bottom = perfList[perfList.length - 1];
      perfText = '从 FP16 算力看，' + top.h.name + ' 是本次对比的性能标杆（约 ' + top.v + ' TFLOPS）';
      if (bottom.h.name !== top.h.name) {
        const ratio = bottom.v > 0 ? (top.v / bottom.v).toFixed(1) : null;
        perfText += '，而 ' + bottom.h.name + ' 相对最轻量（约 ' + bottom.v + ' TFLOPS）' + (ratio ? '，两者相差约 ' + ratio + ' 倍' : '');
      }
      perfText += '。若面向超大模型训练/高并发推理，可优先锁定算力靠前的型号；若以低成本、边缘或轻负载为目标，则算力适中者性价比更高。';
    } else if (perfList.length === 1) {
      perfText = '本次对比中 ' + perfList[0].h.name + ' 提供约 ' + perfList[0].v + ' TFLOPS 的 FP16 算力，是当前唯一可量化算力标的。';
    }

    // 内存/显存分析
    const memList = list.map(h => ({ h, v: parseMemGB(h.memory) })).filter(x => x.v != null).sort((a, b) => b.v - a.v);
    let memText = '';
    if (memList.length) {
      const big = memList[0];
      memText = '内存/显存方面，' + big.h.name + ' 容量最充裕（' + esc(big.h.memory) + '）';
      if (memList.length >= 2 && memList[1].h.name !== big.h.name) {
        memText += '，其次为 ' + memList[1].h.name + '（' + esc(memList[1].h.memory) + '）';
      }
      memText += '。显存/片上内存容量直接决定可装载的模型参数量与批量大小，是推理吞吐和长上下文能力的关键约束。';
    }

    // 互联分析
    const interList = list.filter(h => h.interconnect);
    let interText = '';
    if (interList.length) {
      interText = '互联层面，' + interList.map(h => esc(h.name) + ' 采用 ' + esc(h.interconnect)).join('；') + '。互联带宽决定了多卡/多节点协同训练与推理的扩展效率，是集群场景的核心指标。';
    }

    // 类型分组建议（以产品定位 type 为准，避免按 scenario 关键字造成推理/训练重复归类）
    const trainHw = list.filter(h => /训练/.test(h.type || ''));
    const inferHw = list.filter(h => /推理/.test(h.type || ''));
    const cardHw = list.filter(h => /卡/.test(h.type || ''));
    const sugg = [];
    if (trainHw.length) {
      sugg.push('面向「训练」负载，建议优先评估 ' + trainHw.map(h => esc(h.name)).join('、') + '，重点看算力规模与互联带宽是否匹配模型参数量与并行策略');
    }
    if (inferHw.length) {
      sugg.push('面向「推理」场景，建议关注 ' + inferHw.map(h => esc(h.name)).join('、') + ' 的显存容量、单卡吞吐与能效，兼顾并发与成本');
    }
    if (cardHw.length) {
      sugg.push('作为「加速卡」形态，' + cardHw.map(h => esc(h.name)).join('、') + ' 更适合存量服务器 PCIe 扩展与灵活横向扩容，需核对主机 PCIe 通道与散热余量');
    }
    const suggText = sugg.length ? sugg.join('；') : '';

    // 差异化亮点
    const featText = list.map(h => {
      const feat = (h.features && h.features.length ? h.features : h.tags || []).slice(0, 3).join('、');
      return feat ? esc(h.name) + ' 主打 ' + esc(feat) : esc(h.name);
    }).join('；');

    return '<div class="hw-compare-block">' +
      '<div class="hw-block-head"><h3>💡 对比总结</h3><span class="compare-result-count">售前顾问视角</span></div>' +
      '<div class="hw-conclusion-body">' +
        '<p>本次对比共涉及 ' + list.length + ' 款服务器硬件（' + typeText + '）。' + ecoText + '</p>' +
        (perfText ? '<p>' + perfText + '</p>' : '') +
        (memText ? '<p>' + memText + '</p>' : '') +
        (interText ? '<p>' + interText + '</p>' : '') +
        (suggText ? '<p>选型导向上，' + suggText + '。</p>' : '') +
        (featText ? '<p>产品差异化方面，' + featText + '。</p>' : '') +
        '<p class="hw-conclusion-tip">温馨提示：以上为基于已收录规格的售前分析，实际选型请结合具体业务负载、机房功耗散热、采购预算与厂商官方最新公告综合评估。</p>' +
      '</div>' +
    '</div>';
  }
  const conclusionHtml = hardwareConclusionHtml(selected);

  // ===== 1. 产品概览卡片 =====
  const overviewCards = selected.map(h => {
    const params = [];
    if (h.chip) params.push(['芯片', h.chip]);
    if (h.chipCount) params.push(['芯片数量', h.chipCount]);
    if (h.fp16Perf) params.push(['FP16 算力', h.fp16Perf]);
    if (h.memory) params.push(['内存', h.memory]);
    const paramHtml = params.map(([k, v]) =>
      '<div class="hwc-item"><div class="hwc-label">' + k + '</div><div class="hwc-value">' + escCompare(v) + '</div></div>'
    ).join('');
    const tags = (h.features && h.features.length ? h.features : h.tags || []).slice(0, 5);
    const tagHtml = tags.length ? '<div class="hwc-tags">' + tags.map(t => '<span class="hwc-tag">' + escCompare(t) + '</span>').join('') + '</div>' : '';
    return '<div class="hw-overview-card">' +
      '<div class="hwc-head">' +
        '<span class="hwc-type hw-badge" data-type="' + escCompare(h.type || '') + '">' + escCompare(h.type || '—') + '</span>' +
      '</div>' +
      '<h4 class="hwc-name">' + escCompare(h.name) + '</h4>' +
      (h.formFactor ? '<div class="hwc-form">' + escCompare(h.formFactor) + '</div>' : '') +
      '<div class="hwc-grid">' + paramHtml + '</div>' +
      tagHtml +
    '</div>';
  }).join('');

  // ===== 2. 核心规格对比表 =====
  const coreSpecs = [
    ['形态', h => h.formFactor],
    ['芯片', h => h.chip],
    ['芯片数量', h => h.chipCount],
    ['FP16 算力', h => h.fp16Perf],
    ['FP32 算力', h => h.fp32Perf],
    ['内存', h => h.memory],
    ['互联', h => h.interconnect],
    ['适用场景', h => h.scenario],
  ];
  const coreRows = coreSpecs.map(([label, getter]) => {
    const cells = selected.map(h => {
      const v = getter(h);
      return '<td>' + (v ? escCompare(v) : '<span class="cmp-na">—</span>') + '</td>';
    }).join('');
    return '<tr><td class="cmp-spec-label">' + label + '</td>' + cells + '</tr>';
  }).join('');

  // ===== 3. 推荐模型对比 =====
  const recRows = selected.map(h => {
    return '<tr><td class="cmp-spec-label">' + escCompare(h.name) + '</td>' +
      '<td>' +
      (h.recommended ? escCompare(h.recommended) : '<span class="cmp-na">—</span>') +
      '</td></tr>';
  }).join('');

  // ===== 4. 详细规格逐项对比（detailSpecs 公共字段） =====
  const dsOrder = [
    // 昇腾通用字段
    ['npuModule', 'NPU 模组与互联'], ['aiProcessor', 'AI 处理器'],
    ['aiPerf', 'AI 算力（单 AI 处理器）'], ['aiPerfTotal', 'AI 算力（整机）'],
    ['fp16Single', 'FP16 张量算力（单 AI 处理器）'], ['fp32Single', 'FP32 张量算力（单 AI 处理器）'],
    ['fp16Total', 'FP16 张量算力'], ['fp32Total', 'FP32 张量算力'],
    ['hf32Single', 'HF32 张量算力（单 AI 处理器）'], ['hf32Total', 'HF32 张量算力'],
    ['fp16bf16Single', 'FP16/BF16 张量算力（单 AI 处理器）'], ['fp16bf16Total', 'FP16/BF16 张量算力'],
    ['fp8Single', 'FP8/HiF8/mxFP8 张量算力（单 AI 处理器）'], ['fp8Total', 'FP8/HiF8/mxFP8 张量算力'],
    ['int8Single', 'INT8 张量算力（单 AI 处理器）'], ['int8Total', 'INT8 张量算力'],
    ['mxfp4Single', 'mxFP4 张量算力（单 AI 处理器）'], ['mxfp4Total', 'mxFP4 张量算力'],
    ['hf32', 'HF32 算力'], ['fp32', 'FP32 算力'], ['fp16bf16', 'FP16/BF16 算力'],
    ['fp8', 'FP8/HiF8/mxFP8 算力'], ['int8', 'INT8 算力'], ['mxfp4', 'mxFP4 算力'],
    ['onChipMemory', '片上内存'], ['gpuMemory', 'GPU 显存'], ['memoryBandwidth', 'GPU 显存带宽'], ['memorySpec', '内存规格'],
    ['cpu', 'CPU 处理器'], ['cpuCores', 'CPU 核心数'], ['cpuPerf', 'CPU 算力'], ['systemMemory', '系统内存'],
    ['formDetail', '基本形态'],
    ['intraNodeInterconnect', '框内互联'], ['interNodeInterconnect', '框间互联'], ['cardInterconnect', '卡间互连'],
    ['highSpeedPort', '高速端口'], ['pcieInterface', 'PCIe 接口'],
    ['network', '交换网络'], ['networkCard', '网络接口卡'], ['ioCard', '10GE/25GE 接口卡'], ['codec', '编解码能力'],
    ['virtualization', '虚拟化实例'],
    ['storage', '存储'], ['pcieSlots', 'PCIe 扩展槽位'], ['interfaces', '接口'],
    ['management', '系统管理'], ['clusterExtend', '集群扩展'],
    ['fan', '风扇'], ['powerConsumption', '功耗'], ['modulePower', '模块功耗'],
    ['cooling', '液冷/散热'], ['gpu', '显卡'], ['security', '安全特性'],
    ['environment', '环境规格'],
    // NV 加速卡 / HGX / GB 服务器字段
    ['fp64', 'FP64 算力'], ['fp64TensorCore', 'FP64 张量算力'],
    ['tf32', 'TF32 张量算力'], ['bf16TensorCore', 'BFLOAT16 张量算力'], ['fp16TensorCore', 'FP16 张量算力'],
    ['int8TensorCore', 'INT8 张量算力'], ['nvfp4', 'NVFP4 张量算力'], ['fp4', 'FP4 张量算力'],
    ['gpuMemory', 'GPU 显存'], ['memoryBandwidth', '显存带宽'], ['decoder', '解码器'],
    ['maxTdp', '最大功耗 (TDP)'], ['mig', 'Multi-Instance GPU (MIG)'], ['interconnectDetail', '互联'],
    ['nvlink', 'NVIDIA NVLink'], ['nvlinkSwitch', 'NVLink 交换系统'], ['gpuToGpuBandwidth', 'NVLink GPU 到 GPU 带宽'],
    ['nvlinkBandwidth', 'NVLink 总带宽'], ['networkBandwidth', '网络带宽'], ['attentionPerf', '注意力性能'],
    ['config', '配置'], ['cpuMemory', 'CPU 内存 | 带宽'], ['gpuMemoryBandwidth', 'GPU 显存 | 带宽'],
    ['fastMemory', '快速内存'],
    ['serverOptions', '服务器选项'], ['aiEnterprise', 'NVIDIA AI Enterprise'],
  ];
  const dsKeys = dsOrder.filter(([key]) => selected.some(h => (h.detailSpecs || {})[key]));
  let dsHtml = '';
  if (dsKeys.length) {
    const dsRows = dsKeys.map(([key, label]) => {
      const cells = selected.map(h => {
        const v = (h.detailSpecs || {})[key];
        return '<td>' + (v ? '<div class="ds-text">' + escCompare(v) + '</div>' : '<span class="cmp-na">—</span>') + '</td>';
      }).join('');
      return '<tr><td class="cmp-spec-label">' + label + '</td>' + cells + '</tr>';
    }).join('');
    dsHtml =
      '<div class="hw-compare-block">' +
        '<div class="hw-block-head"><h3>📋 详细规格逐项对比</h3>' +
        '<span class="compare-result-count">仅展示所选产品均含有的规格项</span></div>' +
        '<div class="bd-table-wrap"><table class="bd-table compare-hw-table">' +
          '<thead><tr>' + '<th class="cmp-spec-label">规格项</th>' + selected.map(h => '<th>' + escCompare(h.name) + '</th>').join('') + '</tr></thead>' +
          '<tbody>' + dsRows + '</tbody>' +
        '</table></div>' +
      '</div>';
  }

  const thead = '<th class="cmp-spec-label">规格项</th>' +
    selected.map(h => '<th>' + escCompare(h.name) + '</th>').join('');

  resultEl.innerHTML =
    '<div class="compare-result-wrap hw-compare-report">' +
      '<div class="compare-result-head">' +
        '<h3>🖥️ 服务器硬件产品规格对比</h3>' +
        '<span class="compare-result-count">共 ' + selected.length + ' 款产品</span>' +
      '</div>' +

      conclusionHtml +

      '<div class="hw-compare-block">' +
        '<div class="hw-block-head"><h3>✨ 产品概览</h3><span class="compare-result-count">核心参数一览</span></div>' +
        '<div class="hw-overview-grid">' + overviewCards + '</div>' +
      '</div>' +

      '<div class="hw-compare-block">' +
        '<div class="hw-block-head"><h3>📊 核心规格对比</h3><span class="compare-result-count">关键参数并排对照</span></div>' +
        '<div class="bd-table-wrap"><table class="bd-table compare-hw-table">' +
          '<thead><tr>' + thead + '</tr></thead>' +
          '<tbody>' + coreRows + '</tbody>' +
        '</table></div>' +
      '</div>' +

      '<div class="hw-compare-block">' +
        '<div class="hw-block-head"><h3>🎯 推荐模型</h3><span class="compare-result-count">各产品适用大模型</span></div>' +
        '<div class="bd-table-wrap"><table class="bd-table compare-hw-table compare-rec-table">' +
          '<thead><tr>' + '<th class="cmp-spec-label">产品</th>' + '<th>推荐模型</th>' + '</tr></thead>' +
          '<tbody>' + recRows + '</tbody>' +
        '</table></div>' +
      '</div>' +

      dsHtml +

      '<div class="compare-footnote">数据来源：华为企业业务官网 · 昇腾计算产品线（仅供参考，请以官方最新公告为准）</div>' +
    '</div>';
}

// ---------- 初始化 ----------
function initCompare() {
  initCompareModels();
  initCompareHardware();
}
if (typeof window.initCompare === 'undefined') {
  window.initCompare = initCompare;
}
// 仅在包含对比选择 UI（大模型或硬件列表）的页面上自动初始化；
// 独立对比结果页（如 hardware_compare.html）无选择列表，跳过初始化以避免多余请求。
document.addEventListener('DOMContentLoaded', function () {
  var hasCompareUI = document.getElementById('dlHwAscendList') || document.getElementById('dlModelList');
  if (hasCompareUI) initCompare();
});
