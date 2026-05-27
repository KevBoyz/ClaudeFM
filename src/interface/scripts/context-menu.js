const contextMenu = (() => {
  const _el = document.getElementById('context-menu');

  function hide() { _el.classList.add('hidden'); _el.innerHTML = ''; }

  function _pos(x, y) {
    const pw = window.innerWidth, ph = window.innerHeight;
    _el.style.left = (x + 200 > pw ? pw - 208 : x) + 'px';
    _el.style.top  = (y + 260 > ph ? ph - 268 : y) + 'px';
  }

  function _item(label, onClick, cls = '') {
    const btn = document.createElement('button');
    btn.className = `ctx-item ${cls}`.trim();
    btn.textContent = label;
    btn.addEventListener('click', () => { hide(); onClick(); });
    return btn;
  }

  function _sep() {
    const d = document.createElement('div');
    d.className = 'ctx-separator';
    return d;
  }

  async function show(x, y, track) {
    hide();
    const downloaded = track.download_status === 'completed' && track.file_status === 'available';
    const noLyrics   = track.lyrics_status === 'not_fetched' || track.lyrics_status === 'not_found';

    _el.appendChild(_item('Play', () => player.play(track.id, [track.id])));

    if (!downloaded) {
      _el.appendChild(_sep());
      _el.appendChild(_item('Download', () => downloads.queue(track.id)));
    }

    _el.appendChild(_sep());

    // Playlist submenu
    const sub = document.createElement('div');
    sub.className = 'ctx-submenu';
    const subBtn = document.createElement('button');
    subBtn.className = 'ctx-item';
    subBtn.textContent = 'Add to playlist';
    const subList = document.createElement('div');
    subList.className = 'ctx-submenu-list';
    try {
      const pls = await api.get_playlists();
      pls.filter(p => p.type === 'manual').forEach(p => {
        subList.appendChild(_item(p.name, () => api.add_to_playlist(p.id, track.id)));
      });
      subList.appendChild(_sep());
      subList.appendChild(_item('New playlist...', async () => {
        const name = await modal.prompt('Playlist name:', 'My Playlist');
        if (name) {
          const res = await api.create_playlist(name);
          await api.add_to_playlist(res.id, track.id);
          toast.show(`Added to "${name}"`, 'success', 2000);
        }
      }));
    } catch (_) {}
    sub.appendChild(subBtn);
    sub.appendChild(subList);
    _el.appendChild(sub);

    if (noLyrics) {
      _el.appendChild(_sep());
      _el.appendChild(_item('Fetch lyrics', () => lyrics.fetch(track.id)));
    }

    if (downloaded) {
      _el.appendChild(_sep());
      _el.appendChild(_item('Remove from library', async () => {
        if (await modal.confirm(`Remove "${track.title}" from library? The file will not be deleted.`, 'Remove track', 'Remove')) {
          toast.show('Remove not yet implemented', 'warning', 3000);
        }
      }, 'danger'));
    }

    _pos(x, y);
    _el.classList.remove('hidden');
  }

  document.addEventListener('contextmenu', async e => {
    const card = e.target.closest('[data-track-id]');
    if (!card) { hide(); return; }
    e.preventDefault();
    try {
      const result = await api.get_track(parseInt(card.dataset.trackId));
      await show(e.clientX, e.clientY, result.data);
    } catch (err) { console.error('ctx error', err); }
  });

  document.addEventListener('click', () => hide());
  document.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });

  return { show, hide };
})();
