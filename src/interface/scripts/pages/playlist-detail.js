const playlistDetailPage = (() => {
  async function render(container, params = {}) {
    const id = parseInt(params.id);
    if (!id) return router.navigate('playlists');

    let playlist, tracks;
    try {
      const [pls, trks] = await Promise.all([
        api.get_playlists(),
        api.get_playlist_tracks(id),
      ]);
      playlist = pls.find(p => p.id === id);
      tracks   = trks;
    } catch (e) {
      container.innerHTML = `<div class="error-state">${e.message}</div>`;
      return;
    }

    if (!playlist) {
      container.innerHTML = '<div class="error-state">Playlist not found.</div>';
      return;
    }

    const isManual = playlist.type === 'manual';

    container.innerHTML = `
      <div class="page-header">
        <button class="back-btn" onclick="router.back()">← Back</button>
        <h1 class="page-title" id="pld-name">${playlist.name}</h1>
        ${isManual ? `
          <button class="btn btn-ghost" id="pld-rename">✏ Rename</button>
          <button class="btn btn-danger" id="pld-delete">🗑 Delete</button>
        ` : ''}
        ${tracks.length ? `<button class="btn btn-primary" style="margin-left:auto" id="pld-play-all">▶ Play All</button>` : ''}
      </div>
      <div class="track-list" id="pld-list"></div>`;

    _renderList(id, tracks, container);

    if (isManual) {
      document.getElementById('pld-rename')?.addEventListener('click', async () => {
        const name = await modal.prompt('New name:', playlist.name);
        if (!name) return;
        await api.rename_playlist(id, name);
        const h1 = document.getElementById('pld-name');
        if (h1) h1.textContent = name;
        playlist.name = name;
        toast.show('Playlist renamed', 'success', 2000);
      });

      document.getElementById('pld-delete')?.addEventListener('click', async () => {
        if (!await modal.confirm(`Delete "${playlist.name}"? This cannot be undone.`, 'Delete Playlist', 'Delete')) return;
        await api.delete_playlist(id);
        toast.show(`Deleted "${playlist.name}"`, 'success', 2000);
        router.navigate('playlists');
      });
    }

    document.getElementById('pld-play-all')?.addEventListener('click', () => {
      if (!tracks.length) return;
      player.play(tracks[0].id, tracks.map(t => t.id));
    });
  }

  function _renderList(playlistId, tracks, container) {
    const list = document.getElementById('pld-list');
    if (!list) return;
    if (!tracks.length) {
      list.innerHTML = '<div class="empty-state">This playlist is empty. Right-click any track to add it.</div>';
      return;
    }
    setPageQueue(tracks.map(t => t.id));
    list.innerHTML = tracks.map(t => {
      const card = trackCard(t);
      return card.replace(
        '</div>',
        `<button class="track-card-action" style="opacity:1"
          data-playlist-id="${playlistId}" data-track-id="${t.id}"
          title="Remove">×</button></div>`
      );
    }).join('');

    list.addEventListener('click', async e => {
      const btn = e.target.closest('[data-playlist-id]');
      if (!btn) return;
      e.stopPropagation();
      btn.disabled = true;
      try {
        await api.remove_from_playlist(parseInt(btn.dataset.playlistId), parseInt(btn.dataset.trackId));
        btn.closest('.track-card')?.remove();
        toast.show('Removed from playlist', 'success', 2000);
      } catch (_) {
        btn.disabled = false;
        toast.show('Failed to remove', 'error', 3000);
      }
    });
  }

  function destroy() {}

  return { render, destroy };
})();
