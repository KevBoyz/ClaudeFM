const artistsPage = (() => {
  const SORT_OPTIONS = [
    { label: 'Name A–Z',    fn: (a, b) => a.artist.localeCompare(b.artist) },
    { label: 'Name Z–A',    fn: (a, b) => b.artist.localeCompare(a.artist) },
    { label: 'Most tracks', fn: (a, b) => b.track_count - a.track_count   },
  ];
  let _sortIdx = 0;
  let _data    = [];

  async function render(container, params = {}) {
    if (params.artist) return _renderDetail(container, params.artist);

    container.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">Artists</h1>
        <div class="page-controls">
          <select id="art-sort">
            ${SORT_OPTIONS.map((o, i) =>
              `<option value="${i}" ${_sortIdx===i?'selected':''}>${o.label}</option>`
            ).join('')}
          </select>
        </div>
      </div>
      <div id="art-skeleton" class="page-skeleton"></div>
      <div class="card-grid" id="art-grid"></div>`;

    document.getElementById('art-sort').addEventListener('change', e => {
      _sortIdx = parseInt(e.target.value); _render();
    });

    try {
      _data = await api.get_artists();
    } catch (e) {
      document.getElementById('art-grid').innerHTML = `<div class="error-state">${e.message}</div>`;
      return;
    }
    _render();
  }

  function _render() {
    const skeleton = document.getElementById('art-skeleton');
    const grid     = document.getElementById('art-grid');
    if (skeleton) skeleton.style.display = 'none';
    if (!grid) return;
    const sorted = [..._data].sort(SORT_OPTIONS[_sortIdx].fn);
    if (!sorted.length) {
      grid.innerHTML = '<div class="empty-state">No artists in your library.</div>';
      return;
    }
    grid.innerHTML = sorted.map(a => artistCard(a.artist, a.track_count)).join('');
  }

  async function _renderDetail(container, artist) {
    container.innerHTML = `
      <div class="page-header">
        <button class="back-btn" onclick="router.back()">← Back</button>
        <div>
          <h1 class="page-title" id="art-name">${artist}</h1>
          <div class="page-subtitle" id="art-sub"></div>
        </div>
      </div>
      <div id="art-det-skeleton" class="page-skeleton"></div>
      <div class="track-list" id="art-tracks"></div>`;

    let tracks;
    try {
      tracks = await api.get_tracks_by_artist(artist);
    } catch (e) {
      document.getElementById('art-tracks').innerHTML = `<div class="error-state">${e.message}</div>`;
      return;
    }

    const skeleton = document.getElementById('art-det-skeleton');
    const list     = document.getElementById('art-tracks');
    const sub      = document.getElementById('art-sub');
    if (skeleton) skeleton.style.display = 'none';
    if (sub) sub.textContent = `${tracks.length} track${tracks.length !== 1 ? 's' : ''}`;
    if (!list) return;
    if (!tracks.length) {
      list.innerHTML = '<div class="empty-state">No tracks for this artist.</div>';
      return;
    }
    setPageQueue(tracks.map(t => t.id));
    list.innerHTML = tracks.map(t => trackCard(t)).join('');
    loadArtwork(list);
  }

  function destroy() {}

  router.register('artists', (c, p) => artistsPage.render(c, p));

  return { render, destroy };
})();
