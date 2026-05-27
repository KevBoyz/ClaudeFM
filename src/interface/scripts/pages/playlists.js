const playlistsPage = (() => {
  let _playlists = [];

  async function render(container) {
    container.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">Playlists</h1>
        <div class="page-controls">
          <button class="btn btn-primary" id="pl-new">+ New Playlist</button>
        </div>
      </div>
      <div id="pl-skeleton" class="page-skeleton"></div>
      <div id="pl-content"></div>`;

    document.getElementById('pl-new').addEventListener('click', async () => {
      const name = await modal.prompt('Playlist name:', 'My Playlist');
      if (!name) return;
      try {
        await api.create_playlist(name);
        toast.show(`Playlist "${name}" created`, 'success', 2000);
        await _load(document.getElementById('pl-content'));
      } catch (e) {
        toast.show('Failed to create playlist', 'error', 4000);
      }
    });

    await _load(document.getElementById('pl-content'));
  }

  async function _load(content) {
    if (!content) return;
    const sk = document.getElementById('pl-skeleton');
    try {
      _playlists = await api.get_playlists();
    } catch (e) {
      content.innerHTML = `<div class="error-state">${e.message}</div>`;
      if (sk) sk.style.display = 'none';
      return;
    }
    if (sk) sk.style.display = 'none';

    const auto   = _playlists.filter(p => p.type === 'auto');
    const manual = _playlists.filter(p => p.type === 'manual');

    const cardHtml = (p) => `
      <div class="media-card" onclick="router.navigate('playlists',{id:${p.id}})">
        <div class="media-card-thumb">♫</div>
        <div class="media-card-name">${p.name}</div>
        <div class="media-card-sub">${p.type === 'auto' ? 'Context' : 'Playlist'}</div>
      </div>`;

    content.innerHTML = `
      ${auto.length ? `
        <h2 style="margin-bottom:12px;font-size:1.1rem">Recent Contexts</h2>
        <div class="card-grid" style="margin-bottom:32px">${auto.map(cardHtml).join('')}</div>` : ''}
      ${manual.length ? `
        <h2 style="margin-bottom:12px;font-size:1.1rem">Your Playlists</h2>
        <div class="card-grid">${manual.map(cardHtml).join('')}</div>` : ''}
      ${!auto.length && !manual.length
        ? '<div class="empty-state">No playlists yet. Create one with the button above.</div>'
        : ''}`;
  }

  function destroy() {}

  router.register('playlists', (c, p) => {
    if (p && p.id) return playlistDetailPage.render(c, p);
    return playlistsPage.render(c, p);
  });

  return { render, destroy };
})();
