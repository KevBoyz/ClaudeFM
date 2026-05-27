const downloadsPage = (() => {
  function render(container) {
    container.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">Downloads</h1>
      </div>
      <div id="dp-content"></div>`;

    document.addEventListener('downloads:changed', _update);
    _update();
  }

  function _update() {
    const content = document.getElementById('dp-content');
    if (!content) return;

    const active  = Object.values(downloads.active);
    const history = downloads.history;

    const activeHtml = active.length
      ? active.map(d => `
          <div class="download-row" style="padding:12px 0">
            <div class="download-row-info">
              <div class="download-row-title">${d.title || 'Track ' + d.track_id}</div>
              <div class="download-row-sub">${d.artist || ''}</div>
            </div>
            <div class="progress-bar-wrap" style="width:120px">
              <div class="progress-bar-fill" style="width:${d.percent}%"></div>
            </div>
            <span style="font-size:.875rem;color:var(--color-text_secondary);width:36px">${d.percent}%</span>
          </div>`).join('')
      : '<div class="empty-state" style="padding:24px 0;text-align:left;color:var(--color-text_secondary);font-size:.875rem">No active downloads.</div>';

    const histHtml = history.length
      ? history.map(d => `
          <div class="download-row" style="padding:12px 0">
            <div class="download-row-info">
              <div class="download-row-title">Track ${d.track_id}</div>
            </div>
            ${d.status === 'completed'
              ? '<span class="download-status-ok">✓ Completed</span>'
              : `<span class="download-status-err" title="${d.error || ''}">✗ ${d.error || 'Failed'}</span>`}
          </div>`).join('')
      : '<div class="empty-state" style="padding:24px 0;text-align:left;color:var(--color-text_secondary);font-size:.875rem">No download history this session.</div>';

    content.innerHTML = `
      <h2 style="margin-bottom:12px;font-size:1.1rem">Active</h2>
      <div style="border-bottom:1px solid var(--color-border)">${activeHtml}</div>
      <h2 style="margin:24px 0 12px;font-size:1.1rem">History</h2>
      ${histHtml}`;
  }

  function destroy() {
    document.removeEventListener('downloads:changed', _update);
  }

  router.register('downloads', (c, p) => downloadsPage.render(c, p));

  return { render, destroy };
})();
