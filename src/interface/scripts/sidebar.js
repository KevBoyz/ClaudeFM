const Sidebar = (() => {
  let _source  = 'lastfm';
  let _type    = 'track';
  let _results = [];

  function render() {
    const el = document.getElementById('sidebar');
    el.innerHTML = `
      <div class="sidebar-inner">
        <div class="sidebar-search-row">
          <input id="sb-input" type="text" placeholder="Search..." />
          <button id="sb-go">🔍</button>
        </div>
        <div class="sidebar-toggles">
          <button class="sidebar-toggle-btn ${_source==='lastfm'?'active':''}" id="sb-lastfm">Last.fm</button>
          <button class="sidebar-toggle-btn ${_source==='local' ?'active':''}" id="sb-local">Local</button>
        </div>
        <div class="sidebar-radios">
          ${['artist','track','album'].map(t =>
            `<label><input type="radio" name="sbtype" value="${t}" ${_type===t?'checked':''}> ${t[0].toUpperCase()+t.slice(1)}</label>`
          ).join('')}
        </div>
        <div class="sidebar-results" id="sb-results"></div>
      </div>`;

    document.getElementById('sb-go').addEventListener('click', _search);
    document.getElementById('sb-input').addEventListener('keydown', e => { if (e.key === 'Enter') _search(); });
    document.getElementById('sb-lastfm').addEventListener('click', () => { _source='lastfm'; render(); });
    document.getElementById('sb-local').addEventListener('click',  () => { _source='local';  render(); });
    document.querySelectorAll('[name=sbtype]').forEach(r =>
      r.addEventListener('change', e => { _type = e.target.value; }));
    _renderResults();
  }

  async function _search() {
    const query = document.getElementById('sb-input')?.value?.trim();
    if (!query) return;
    const btn = document.getElementById('sb-go');
    if (btn) { btn.textContent = '⏳'; btn.disabled = true; }
    try {
      if (_source === 'local') {
        _results = (await api.search_local(query)).map(t => ({ ...t, _src: 'local' }));
      } else {
        _results = (await api.search_lastfm(query, _type)).map(r => ({ ...r, _src: 'lastfm' }));
      }
    } catch (e) {
      toast.show('Search failed: ' + e.message, 'error', 4000);
      _results = [];
    }
    if (btn) { btn.textContent = '🔍'; btn.disabled = false; }
    _renderResults();
  }

  function _renderResults() {
    const container = document.getElementById('sb-results');
    if (!container) return;
    if (!_results.length) {
      container.innerHTML = '<div style="color:var(--color-text_secondary);font-size:.8rem;padding:8px">No results.</div>';
      return;
    }
    container.innerHTML = _results.map(r => {
      if (_type === 'artist') {
        const name = (r.name || r.artist || '').replace(/'/g, "\\'");
        return `<div class="sidebar-result-item" onclick="router.navigate('lastfm/artist',{name:'${name}'})">
          <div class="sidebar-result-info"><div class="sidebar-result-title">${r.name || r.artist}</div></div></div>`;
      }
      if (_type === 'album') {
        const title  = (r.title || r.album || '').replace(/'/g, "\\'");
        const artist = (r.artist || '').replace(/'/g, "\\'");
        return `<div class="sidebar-result-item">
          <div class="sidebar-result-info" onclick="router.navigate('lastfm/album',{title:'${title}',artist:'${artist}'})" style="cursor:pointer">
            <div class="sidebar-result-title">${r.title || r.album}</div>
            <div class="sidebar-result-sub">${r.artist || ''}</div>
          </div>
          <button class="sidebar-dl-btn" data-title="${(r.title||'').replace(/"/g,'&quot;')}"
            data-artist="${(r.artist||'').replace(/"/g,'&quot;')}"
            data-album="${(r.album||'').replace(/"/g,'&quot;')}">⬇</button></div>`;
      }
      // track
      const isLocal = r._src === 'local';
      const downloaded = isLocal && r.download_status === 'completed' && r.file_status === 'available';
      return `
        <div class="sidebar-result-item" ${isLocal ? `data-track-id="${r.id}"` : ''}>
          <div class="sidebar-result-info" onclick="${isLocal ? `player.play(${r.id},[${r.id}])` : ''}">
            <div class="sidebar-result-title">${r.title}</div>
            <div class="sidebar-result-sub">${r.artist}</div>
          </div>
          ${!isLocal
            ? `<button class="sidebar-dl-btn" data-title="${(r.title||'').replace(/"/g,'&quot;')}" data-artist="${(r.artist||'').replace(/"/g,'&quot;')}">⬇</button>`
            : (downloaded ? '<span style="color:var(--color-success)">✓</span>' : '')}
        </div>`;
    }).join('');

    container.querySelectorAll('.sidebar-dl-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        btn.disabled = true; btn.textContent = '⏳';
        try {
          await downloads.queueLastfm(btn.dataset.title, btn.dataset.artist, btn.dataset.album || null);
        } catch (e) {
          toast.show('Download failed: ' + e.message, 'error', 4000);
          btn.disabled = false; btn.textContent = '⬇';
        }
      });
    });
  }

  return { render };
})();
