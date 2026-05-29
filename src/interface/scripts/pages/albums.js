const albumsPage = (() => {
  const SORT_OPTIONS = [
    { label: 'Title A–Z',    fn: (a, b) => a.album.localeCompare(b.album)   },
    { label: 'Title Z–A',    fn: (a, b) => b.album.localeCompare(a.album)   },
    { label: 'Artist A–Z',   fn: (a, b) => a.artist.localeCompare(b.artist) },
    { label: 'Most tracks',  fn: (a, b) => b.track_count - a.track_count    },
  ];
  let _sortIdx = 0;
  let _data    = [];

  async function render(container, params = {}) {
    if (params.album) return _renderDetail(container, params.album, params.artist || '');

    container.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">Albums</h1>
        <div class="page-controls">
          <select id="alb-sort">
            ${SORT_OPTIONS.map((o, i) =>
              `<option value="${i}" ${_sortIdx===i?'selected':''}>${o.label}</option>`
            ).join('')}
          </select>
        </div>
      </div>
      <div id="alb-skeleton" class="page-skeleton"></div>
      <div class="card-grid" id="alb-grid"></div>`;

    document.getElementById('alb-sort').addEventListener('change', e => {
      _sortIdx = parseInt(e.target.value); _render();
    });

    try {
      _data = await api.get_albums();
    } catch (e) {
      document.getElementById('alb-grid').innerHTML = `<div class="error-state">${e.message}</div>`;
      return;
    }
    _render();
  }

  function _render() {
    const skeleton = document.getElementById('alb-skeleton');
    const grid     = document.getElementById('alb-grid');
    if (skeleton) skeleton.style.display = 'none';
    if (!grid) return;
    const sorted = [..._data].sort(SORT_OPTIONS[_sortIdx].fn);
    if (!sorted.length) {
      grid.innerHTML = '<div class="empty-state">No albums in your library.</div>';
      return;
    }
    grid.innerHTML = sorted.map(a => {
      const al = _jsStr(a.album);
      const ar = _jsStr(a.artist);
      return albumCard(a.album, a.artist, a.track_count,
        `router.navigate('albums',{album:'${al}',artist:'${ar}'})`);
    }).join('');
  }

  async function _renderDetail(container, album, artist) {
    container.innerHTML = `
      <div class="page-header">
        <button class="back-btn" onclick="router.back()">← Back</button>
        <div class="media-card-thumb" style="width:80px;height:80px;font-size:2rem;display:flex;align-items:center;justify-content:center;background:var(--color-bg_highlight);border-radius:8px">💿</div>
        <div>
          <h1 class="page-title">${album}</h1>
          <div class="page-subtitle">${artist}</div>
          <div class="page-subtitle" id="alb-det-count"></div>
        </div>
      </div>
      <div id="alb-det-skeleton" class="page-skeleton"></div>
      <div class="track-list" id="alb-tracks"></div>`;

    let tracks;
    try {
      tracks = await api.get_tracks_by_album(album, artist);
    } catch (e) {
      document.getElementById('alb-tracks').innerHTML = `<div class="error-state">${e.message}</div>`;
      return;
    }

    const skeleton = document.getElementById('alb-det-skeleton');
    const list     = document.getElementById('alb-tracks');
    const countEl  = document.getElementById('alb-det-count');
    if (skeleton) skeleton.style.display = 'none';
    if (countEl)  countEl.textContent = `${tracks.length} track${tracks.length !== 1 ? 's' : ''}`;
    if (!list) return;
    if (!tracks.length) {
      list.innerHTML = '<div class="empty-state">No tracks for this album.</div>';
      return;
    }
    setPageQueue(tracks.map(t => t.id));
    list.innerHTML = tracks.map(t => trackCard(t)).join('');
    loadArtwork(list);
  }

  function destroy() {}

  router.register('albums', (c, p) => albumsPage.render(c, p));

  return { render, destroy };
})();
