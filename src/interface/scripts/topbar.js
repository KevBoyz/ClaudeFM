const Topbar = (() => {
  const ROUTES = [
    { label: 'Home',      route: 'home' },
    { label: 'Artists',   route: 'artists' },
    { label: 'Albums',    route: 'albums' },
    { label: 'Playlists', route: 'playlists' },
    { label: 'Downloads', route: 'downloads' },
    { label: 'Settings',  route: 'settings' },
  ];

  function render(sidebarCollapsed = false) {
    const el = document.getElementById('topbar');
    el.innerHTML = `
      <div class="topbar-inner">
        <button class="topbar-logo" id="sidebar-toggle">≡ ClaudeFM</button>
        <nav class="topbar-nav">
          ${ROUTES.map(r => `
            <button class="topbar-nav-link" data-route="${r.route}"
              onclick="router.navigate('${r.route}')">${r.label}</button>
          `).join('')}
        </nav>
        <div class="topbar-right">
          <button class="download-badge hidden" id="dl-badge" onclick="Topbar.togglePanel()">
            ⬇ <span class="download-badge-count" id="dl-count">0</span>
          </button>
        </div>
      </div>`;

    if (sidebarCollapsed) document.getElementById('sidebar').classList.add('collapsed');

    document.getElementById('sidebar-toggle').addEventListener('click', () => {
      const collapsed = document.getElementById('sidebar').classList.toggle('collapsed');
      api.save_setting('sidebar_collapsed', collapsed ? 'true' : 'false');
    });

    document.addEventListener('downloads:changed', e => _updateBadge(e.detail.count));
  }

  function _updateBadge(count) {
    const badge = document.getElementById('dl-badge');
    const countEl = document.getElementById('dl-count');
    if (!badge) return;
    badge.classList.toggle('hidden', count === 0);
    if (countEl) countEl.textContent = count;
    _renderPanel();
  }

  function togglePanel() {
    const panel = document.getElementById('download-panel');
    panel.classList.toggle('hidden');
    if (!panel.classList.contains('hidden')) _renderPanel();
  }

  function _renderPanel() {
    const panel = document.getElementById('download-panel');
    if (!panel || panel.classList.contains('hidden')) return;
    const activeRows = Object.values(downloads.active).map(d => `
      <div class="download-row">
        <div class="download-row-info">
          <div class="download-row-title">${d.title || 'Track ' + d.track_id}</div>
          <div class="download-row-sub">${d.artist || ''}</div>
        </div>
        <div class="progress-bar-wrap">
          <div class="progress-bar-fill" style="width:${d.percent}%"></div>
        </div>
      </div>`).join('');
    const histRows = downloads.history.slice(0, 10).map(d => `
      <div class="download-row">
        <div class="download-row-info"><div class="download-row-title">Track ${d.track_id}</div></div>
        ${d.status === 'completed'
          ? '<span class="download-status-ok">✓</span>'
          : `<span class="download-status-err" title="${d.error || ''}">✗</span>`}
      </div>`).join('');
    panel.innerHTML = `
      ${activeRows ? `<div class="download-panel-section">Active</div>${activeRows}` : ''}
      ${histRows   ? `<div class="download-panel-section">Completed</div>${histRows}` : ''}
      ${!activeRows && !histRows ? '<div style="padding:16px;color:var(--color-text_secondary);font-size:.875rem">No downloads</div>' : ''}`;
  }

  document.addEventListener('downloads:changed', () => _renderPanel());
  document.addEventListener('click', e => {
    const panel = document.getElementById('download-panel');
    if (panel && !panel.classList.contains('hidden') &&
        !panel.contains(e.target) && !e.target.closest('#dl-badge'))
      panel.classList.add('hidden');
  });

  return { render, togglePanel };
})();
