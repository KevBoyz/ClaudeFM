const homePage = (() => {
  const SORT_OPTIONS = [
    { label: 'Most recent', value: 'date_downloaded DESC' },
    { label: 'Oldest',      value: 'date_downloaded ASC'  },
    { label: 'Title A–Z',   value: 'title ASC'            },
    { label: 'Title Z–A',   value: 'title DESC'           },
    { label: 'Artist A–Z',  value: 'artist ASC'           },
    { label: 'Duration',    value: 'duration ASC'         },
  ];
  let _orderBy = 'date_downloaded DESC';
  let _format  = '';
  let _tracks  = [];

  async function render(container) {
    container.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">Library</h1>
        <div class="page-controls">
          <select id="home-sort">
            ${SORT_OPTIONS.map(o =>
              `<option value="${o.value}" ${_orderBy===o.value?'selected':''}>${o.label}</option>`
            ).join('')}
          </select>
          <select id="home-fmt">
            <option value="">All</option>
            <option value="m4a" ${_format==='m4a'?'selected':''}>m4a</option>
            <option value="mp3" ${_format==='mp3'?'selected':''}>mp3</option>
          </select>
        </div>
      </div>
      <div id="home-skeleton" class="page-skeleton"></div>
      <div class="track-list" id="home-list"></div>`;

    document.getElementById('home-sort').addEventListener('change', e => { _orderBy = e.target.value; _load(); });
    document.getElementById('home-fmt').addEventListener('change',  e => { _format  = e.target.value; _load(); });
    document.addEventListener('library:changed',       _load);
    document.addEventListener('library:scan_complete', _onScan);
    await _load();
  }

  async function _load() {
    const filters = {
      order_by: _orderBy,
      ...(_format ? { audio_format: _format } : {}),
    };
    try {
      _tracks = await api.get_library(filters);
    } catch (e) {
      _tracks = [];
      const list = document.getElementById('home-list');
      if (list) list.innerHTML = `<div class="error-state">Failed to load library: ${e.message}</div>`;
      return;
    }
    _render();
  }

  function _render() {
    const skeleton = document.getElementById('home-skeleton');
    const list     = document.getElementById('home-list');
    if (skeleton) skeleton.style.display = 'none';
    if (!list) return;
    if (!_tracks.length) {
      list.innerHTML = '<div class="empty-state">No tracks yet. Search for music or configure a folder in Settings.</div>';
      return;
    }
    setPageQueue(_tracks.map(t => t.id));
    list.innerHTML = _tracks.map(t => trackCard(t)).join('');
    loadArtwork(list);
  }

  function _onScan(e) {
    const { added = 0, missing = 0 } = e.detail || {};
    toast.show(`Library updated: ${added} added, ${missing} missing`, 'info', 4000);
    _load();
  }

  function destroy() {
    document.removeEventListener('library:changed',       _load);
    document.removeEventListener('library:scan_complete', _onScan);
  }

  router.register('home', (c, p) => homePage.render(c, p));

  return { render, destroy };
})();
