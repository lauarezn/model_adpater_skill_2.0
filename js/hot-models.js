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

// 渲染排行榜卡片
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

  // 计算各指标最大值，用于进度条比例
  var maxDownloads = 1, maxLikes = 1, maxTrend = 1;
  models.forEach(function (m) {
    var dl = m.downloads != null ? m.downloads : 0;
    var lk = m.likes != null ? m.likes : 0;
    var tr = m.trending_score != null ? m.trending_score : 0;
    if (dl > maxDownloads) maxDownloads = dl;
    if (lk > maxLikes) maxLikes = lk;
    if (tr > maxTrend) maxTrend = tr;
  });

  var cards = models.map(function (m) {
    var rank = m.rank || '-';
    var medal = rank <= 3
      ? '<span class="hot-medal">' + ['🥇', '🥈', '🥉'][rank - 1] + '</span>'
      : '';
    var dev = m.developer || '-';
    var name = m.model_name || m.model_id || '-';
    var tag = m.pipeline_zh || m.pipeline_tag || '-';
    var downloads = m.downloads_display || m.downloads || 0;
    var likes = m.likes != null ? m.likes : 0;
    var trend = m.trending_score != null ? m.trending_score : 0;
    var dlPct = Math.round(((m.downloads != null ? m.downloads : 0) / maxDownloads) * 100);
    var lkPct = Math.round(((m.likes != null ? m.likes : 0) / maxLikes) * 100);
    var trPct = Math.round(((m.trending_score != null ? m.trending_score : 0) / maxTrend) * 100);
    var url = m.hf_url || ('https://hf-mirror.com/' + (m.model_id || ''));

    return '<div class="hot-card">' +
      '<div class="hot-card-rank">' +
        '<span class="hot-rank-num">' + rank + '</span>' +
        medal +
      '</div>' +
      '<div class="hot-card-body">' +
        '<div class="hot-card-head">' +
          '<a class="hot-card-title" href="' + url + '" target="_blank" rel="noopener" title="' + escapeHtml(m.model_id || '') + '">' +
            '<span class="hot-card-name">' + escapeHtml(name) + '</span>' +
            '<span class="hot-card-dev">' + escapeHtml(dev) + '</span>' +
          '</a>' +
          '<span class="hot-card-tag">' + escapeHtml(tag) + '</span>' +
        '</div>' +
        '<div class="hot-card-stats">' +
          '<div class="hot-stat">' +
            '<span class="hot-stat-icon">⬇️</span>' +
            '<span class="hot-stat-label">下载</span>' +
            '<span class="hot-stat-value">' + escapeHtml(String(downloads)) + '</span>' +
            '<div class="hot-stat-bar"><div class="hot-stat-bar-fill hot-bar-downloads" style="width:' + dlPct + '%"></div></div>' +
          '</div>' +
          '<div class="hot-stat">' +
            '<span class="hot-stat-icon">👍</span>' +
            '<span class="hot-stat-label">点赞</span>' +
            '<span class="hot-stat-value">' + escapeHtml(String(likes)) + '</span>' +
            '<div class="hot-stat-bar"><div class="hot-stat-bar-fill hot-bar-likes" style="width:' + lkPct + '%"></div></div>' +
          '</div>' +
          '<div class="hot-stat">' +
            '<span class="hot-stat-icon">🔥</span>' +
            '<span class="hot-stat-label">热度</span>' +
            '<span class="hot-stat-value">' + escapeHtml(String(trend)) + '</span>' +
            '<div class="hot-stat-bar"><div class="hot-stat-bar-fill hot-bar-trend" style="width:' + trPct + '%"></div></div>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</div>';
  }).join('');

  container.innerHTML =
    '<div class="hot-card-list">' + cards + '</div>' +
    '<div class="hot-ranking-count">共展示 <b>' + models.length + '</b> 个最热模型' +
      (total ? ' / 全部 <b>' + total + '</b>' : '') + '</div>';
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
