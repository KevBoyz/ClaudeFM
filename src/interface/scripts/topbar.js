const Topbar = (() => {
  const _lyricsFetching = {};
  const _lyricsHistory  = [];
  const _lyricsEnriching  = { active: false, total: 0, done: 0 };
  const _artworkEnriching = { active: false, total: 0, done: 0 };

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
          <button class="download-badge" id="dl-badge" onclick="Topbar.togglePanel()">
            ⬇ <span class="download-badge-count" id="dl-count">0</span>
          </button>
        </div>
      </div>`;

    if (sidebarCollapsed) document.getElementById('sidebar').classList.add('collapsed');

    document.getElementById('sidebar-toggle').addEventListener('click', () => {
      const collapsed = document.getElementById('sidebar').classList.toggle('collapsed');
      api.save_setting('sidebar_collapsed', collapsed ? 'true' : 'false');
    });

    document.addEventListener('downloads:changed', () => _updateBadge());
  }

  function _updateBadge() {
    const countEl = document.getElementById('dl-count');
    const total = downloads.activeCount()
      + Object.keys(_lyricsFetching).length
      + (_lyricsEnriching.active  ? 1 : 0)
      + (_artworkEnriching.active ? 1 : 0);
    if (!countEl) return;
    const panel = document.getElementById('download-panel');
    const panelOpen = panel && !panel.classList.contains('hidden');
    countEl.classList.toggle('hidden', total === 0 || panelOpen);
    countEl.textContent = total || '';
    _renderPanel();
  }

  function togglePanel() {
    const panel = document.getElementById('download-panel');
    panel.classList.toggle('hidden');
    if (!panel.classList.contains('hidden')) {
      const countEl = document.getElementById('dl-count');
      if (countEl) countEl.classList.add('hidden');
      _renderPanel();
    }
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
        <div class="download-row-info">
          <div class="download-row-title">${d.title || 'Track ' + d.track_id}</div>
          ${d.artist ? `<div class="download-row-sub">${d.artist}</div>` : ''}
        </div>
        ${d.status === 'completed'
          ? '<span class="download-status-ok">✓</span>'
          : `<span class="download-status-err" title="${d.error || ''}">✗</span>`}
      </div>`).join('');

    const lyricsActiveRows = Object.values(_lyricsFetching).map(d => `
      <div class="download-row">
        <div class="download-row-info">
          <div class="download-row-title">${d.title || 'Track ' + d.track_id}</div>
          ${d.artist ? `<div class="download-row-sub">${d.artist}</div>` : ''}
        </div>
        <span style="font-size:.8rem;color:var(--color-text_secondary)">🎵 Fetching…</span>
      </div>`).join('');

    const _lyricsStatusLabel = s => s === 'synchronized' ? 'Synced' : s === 'plain_text' ? 'Found'
      : s === 'instrumental' ? 'Instrumental' : s === 'not_found' ? 'Not found' : 'Error';
    const lyricsHistRows = _lyricsHistory.slice(0, 10).map(d => {
      const ok = d.status === 'synchronized' || d.status === 'plain_text' || d.status === 'instrumental';
      return `<div class="download-row">
        <div class="download-row-info">
          <div class="download-row-title">${d.title || 'Track ' + d.track_id}</div>
          ${d.artist ? `<div class="download-row-sub">${d.artist}</div>` : ''}
        </div>
        <span class="${ok ? 'download-status-ok' : 'download-status-err'}">${ok ? '✓' : '✗'} ${_lyricsStatusLabel(d.status)}</span>
      </div>`;
    }).join('');

    const lyricsEnrichRow = _lyricsEnriching.active
      ? `<div class="download-row">
           <div class="download-row-info">
             <div class="download-row-title">Enriching lyrics</div>
             <div class="download-row-sub">${_lyricsEnriching.done}/${_lyricsEnriching.total} tracks</div>
           </div>
           <span style="font-size:.8rem;color:var(--color-text_secondary)">Running...</span>
         </div>`
      : '';

    const artworkEnrichRow = _artworkEnriching.active
      ? `<div class="download-row">
           <div class="download-row-info">
             <div class="download-row-title">Enriching artwork</div>
             <div class="download-row-sub">${_artworkEnriching.done}/${_artworkEnriching.total} tracks</div>
           </div>
           <span style="font-size:.8rem;color:var(--color-text_secondary)">Running...</span>
         </div>`
      : '';

    const hasActivity = activeRows || histRows || lyricsActiveRows || lyricsHistRows || lyricsEnrichRow || artworkEnrichRow;
    panel.innerHTML = `
      ${activeRows       ? `<div class="download-panel-section">Downloading</div>${activeRows}` : ''}
      ${lyricsActiveRows ? `<div class="download-panel-section">Fetching lyrics</div>${lyricsActiveRows}` : ''}
      ${lyricsEnrichRow  ? `<div class="download-panel-section">Enriching lyrics</div>${lyricsEnrichRow}` : ''}
      ${artworkEnrichRow ? `<div class="download-panel-section">Enriching artwork</div>${artworkEnrichRow}` : ''}
      ${histRows         ? `<div class="download-panel-section">Downloads</div>${histRows}` : ''}
      ${lyricsHistRows   ? `<div class="download-panel-section">Lyrics</div>${lyricsHistRows}` : ''}
      ${!hasActivity     ? '<div style="padding:16px;color:var(--color-text_secondary);font-size:.875rem">No activity</div>' : ''}`;
  }

  document.addEventListener('lyrics:fetch_start', e => {
    _lyricsFetching[e.detail.track_id] = e.detail;
    _updateBadge();
  });
  document.addEventListener('lyrics:fetch_end', e => {
    delete _lyricsFetching[e.detail.track_id];
    _lyricsHistory.unshift(e.detail);
    _updateBadge();
  });

  document.addEventListener('claudefm:event', e => {
    const ev = e.detail;
    if (ev.type === 'enrichment_lyrics_started') {
      _lyricsEnriching.active = true;
      _lyricsEnriching.total  = ev.total || 0;
      _lyricsEnriching.done   = 0;
      _updateBadge();
    } else if (ev.type === 'lyrics_fetch_complete') {
      _lyricsEnriching.active = false;
      _updateBadge();
    } else if (ev.type === 'enrichment_artwork_started') {
      _artworkEnriching.active = true;
      _artworkEnriching.total  = ev.total || 0;
      _artworkEnriching.done   = 0;
      _updateBadge();
    } else if (ev.type === 'enrichment_artwork_progress') {
      _artworkEnriching.done = Math.min(_artworkEnriching.done + 1, _artworkEnriching.total);
      _updateBadge();
    } else if (ev.type === 'enrichment_artwork_complete') {
      _artworkEnriching.active = false;
      const { embedded = 0, not_found = 0, errors = 0 } = ev;
      if (embedded + not_found + errors > 0) {
        toast.show(`Artwork: ${embedded} embedded, ${not_found} not found${errors ? `, ${errors} errors` : ''}`, 'info', 5000);
      }
      _updateBadge();
    }
  });

  document.addEventListener('click', e => {
    const panel = document.getElementById('download-panel');
    if (panel && !panel.classList.contains('hidden') &&
        !panel.contains(e.target) && !e.target.closest('#dl-badge'))
      panel.classList.add('hidden');
  });

  return { render, togglePanel };
})();
