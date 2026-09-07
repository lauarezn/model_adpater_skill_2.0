// ============ 最热模型排行榜（实时抓取 hf-mirror）============
// 依赖后端接口 /admin/api/hot-models

// 排行榜视图切换：list = 模型清单，hot = 最热排行
function switchGlobalView(view) {
  var listView = document.getElementById('globalListView');
  var hotView = document.getElementById('hotRankingView');
  if (!listView || !hotView) return;

  var isHot = view === 'hot';
  listView.style.display = isHot ? 'none' : '';
  hotView.style.display = isHot ? '' : 'none';

  if (isHot) {
    loadHotRanking();
  }
}

// 加载最热模型排行榜数据并渲染
function loadHotRanking() {
  var container = document.getElementById('hotRankingContainer');
  var emptyEl = document.getElementById('hotRankingEmpty');
  var loadingEl = document.getElementById('hotRankingLoading');
  var updatedEl = document.getElementById('hotRankingUpdated');
  if (!container) return;

  var sortEl = document.getElementById('hotSortSelect');
  var limitEl = document.getElementById('hotLimitSelect');
  var sort = sortEl ? sortEl.value : 'trending';
  var limit = limitEl ? limitEl.value : '30';

  // 显示加载态
  if (loadingEl) loadingEl.style.display = '';
  if (emptyEl) emptyEl.style.display = 'none';

  fetch('/admin/api/hot-models?sort=' + encodeURIComponent(sort) + '&limit=' + encodeURIComponent(limit))
    .then(function (resp) {
      if (!resp.ok) {
        throw new Error('HTTP ' + resp.status);
      }
      return resp.json();
    })
    .then(function (data) {
      if (loadingEl) loadingEl.style.display = 'none';
      if (!data || !data.success) {
        showHotError(data && data.error ? data.error : '加载失败');
        return;
      }
      if (updatedEl && data.fetched_at) {
        updatedEl.textContent = '更新时间：' + formatHotTime(data.fetched_at);
      }
      renderHotRanking(data.models, data.total);
    })
    .catch(function (err) {
      if (loadingEl) loadingEl.style.display = 'none';
      showHotError('抓取 hf-mirror 数据失败：' + err.message);
    });
}

function showHotError(msg) {
  var emptyEl = document.getElementById('hotRankingEmpty');
  var msgEl = document.getElementById('hotRankingErrorMsg');
  if (!emptyEl) return;
  if (msgEl) msgEl.textContent = msg;
  emptyEl.style.display = 'block';
}

// 渲染排行榜表格
function renderHotRanking(models, total) {
  var container = document.getElementById('hotRankingContainer');
  var emptyEl = document.getElementById('hotRankingEmpty');
  if (!container) return;

  if (!models || models.length === 0) {
    if (emptyEl) {
      var msgEl = document.getElementById('hotRankingErrorMsg');
      if (msgEl) msgEl.textContent = '暂无模型数据';
      emptyEl.style.display = 'block';
    }
    container.innerHTML = '';
    return;
  }

  var rows = models.map(function (m) {
    var rank = m.rank || '-';
    var medal = rank <= 3
      ? '<span class="hot-rank-medal">' + ['🥇', '🥈', '🥉'][rank - 1] + '</span>'
      : '';
    var dev = m.developer || '-';
    var name = m.model_name || m.model_id || '-';
    var tag = m.pipeline_zh || m.pipeline_tag || '-';
    var downloads = m.downloads_display || m.downloads || 0;
    var likes = m.likes != null ? m.likes : 0;
    var trend = m.trending_score != null ? m.trending_score : 0;
    var url = m.hf_url || ('https://hf-mirror.com/' + (m.model_id || ''));

    return '<tr>' +
      '<td class="hot-rank">' + rank + medal + '</td>' +
      '<td class="hot-model">' +
        '<a href="' + url + '" target="_blank" rel="noopener" title="' + escapeHtml(m.model_id || '') + '">' +
          '<span class="hot-dev">' + escapeHtml(dev) + '</span>' +
          '<span class="hot-name">' + escapeHtml(name) + '</span>' +
        '</a>' +
      '</td>' +
      '<td class="hot-tag">' + escapeHtml(tag) + '</td>' +
      '<td class="hot-downloads">' + escapeHtml(String(downloads)) + '</td>' +
      '<td class="hot-likes">' + escapeHtml(String(likes)) + '</td>' +
      '<td class="hot-trend">' + escapeHtml(String(trend)) + '</td>' +
      '</tr>';
  }).join('');

  container.innerHTML =
    '<div class="hot-ranking-table-wrap">' +
      '<table class="hot-ranking-table">' +
        '<thead>' +
          '<tr>' +
            '<th>排名</th>' +
            '<th>模型（开发商/名称）</th>' +
            '<th>任务类型</th>' +
            '<th>下载量</th>' +
            '<th>点赞</th>' +
            '<th>热度分</th>' +
          '</tr>' +
        '</thead>' +
        '<tbody>' + rows + '</tbody>' +
      '</table>' +
    '</div>' +
    '<div class="hot-ranking-count">共展示 <b>' + models.length + '</b> 个最热模型</div>';
}

// 工具函数：格式化时间（UTC ISO -> 本地）
function formatHotTime(isoStr) {
  if (!isoStr) return '';
  try {
    var d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  } catch (e) {
    return isoStr;
  }
}

function escapeHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
