const lastfmArtistPage = (() => {
  async function render(container, params = {}) {
    const name = params.name || '';
    container.innerHTML = `
      <div class="page-header">
        <button class="back-btn" onclick="router.back()">← Back</button>
        <div>
          <h1 class="page-title">${name} <span style="font-size:.875rem;font-weight:400;color:var(--color-text_secondary)">(Last.fm)</span></h1>
        </div>
      </div>
      <div id="lfa-skeleton" class="page-skeleton"></div>
      <div id="lfa-content"></div>`;

    let topTracks, albums;
    try {
      [topTracks, albums] = await Promise.all([
        api.get_artist_top_tracks(name),
        api.search_lastfm(name, 'album'),
      ]);
    } catch (e) {
      document.getElementById('lfa-content').innerHTML = `<div class="error-state">${e.message}</div>`;
      const sk = document.getElementById('lfa-skeleton');
      if (sk) sk.style.display = 'none';
      return;
    }

    const sk = document.getElementById('lfa-skeleton');
    if (sk) sk.style.display = 'none';
    const content = document.getElementById('lfa-content');
    if (!content) return;

    const tracksHtml = topTracks.length
      ? topTracks.map(t => {
          const avail = isAvailable(t.title || t.name, name);
          return `<div class="sidebar-result-item">
            <div class="sidebar-result-info">
              <div class="sidebar-result-title">${t.title || t.name}</div>
              <div class="sidebar-result-sub">${name}</div>
            </div>
            ${avail
              ? '<span style="color:var(--color-success)">✓</span>'
              : `<button class="sidebar-dl-btn"
                  data-title="${(t.title||t.name||'').replace(/"/g,'&quot;')}"
                  data-artist="${name.replace(/"/g,'&quot;')}">⬇</button>`}
          </div>`;
        }).join('')
      : '<div class="empty-state" style="text-align:left">No tracks found.</div>';

    const albumsHtml = albums.length
      ? `<div class="card-grid">${albums.map(a => {
          const al = (a.title||a.album||'').replace(/'/g,"\\'");
          const ar = (a.artist||name).replace(/'/g,"\\'");
          return `<div class="media-card">
            <div class="media-card-thumb" onclick="router.navigate('lastfm/album',{title:'${al}',artist:'${ar}'})">💿</div>
            <div class="media-card-name" onclick="router.navigate('lastfm/album',{title:'${al}',artist:'${ar}'})">${a.title||a.album}</div>
            <div class="media-card-sub">${a.artist||name}</div>
            <button class="sidebar-dl-btn" style="margin-top:6px;width:100%"
              data-dl-album-title="${(a.title||a.album||'').replace(/"/g,'&quot;')}"
              data-dl-album-artist="${(a.artist||name).replace(/"/g,'&quot;')}">⬇ All</button>
          </div>`;
        }).join('')}</div>`
      : '<div class="empty-state" style="text-align:left">No albums found.</div>';

    content.innerHTML = `
      <h2 style="margin-bottom:12px;font-size:1.1rem">Top Tracks</h2>
      <div class="track-list" id="lfa-tracks">${tracksHtml}</div>
      <h2 style="margin:24px 0 12px;font-size:1.1rem">Discography</h2>
      ${albumsHtml}`;

    content.querySelectorAll('.sidebar-dl-btn[data-title]').forEach(btn => {
      btn.addEventListener('click', async () => {
        btn.disabled = true; btn.textContent = '⏳';
        try {
          await downloads.queueLastfm(btn.dataset.title, btn.dataset.artist, null);
        } catch (e) {
          toast.show('Download failed: ' + e.message, 'error', 4000);
          btn.disabled = false; btn.textContent = '⬇';
        }
      });
    });

    content.querySelectorAll('[data-dl-album-title]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const title  = btn.dataset.dlAlbumTitle;
        const artist = btn.dataset.dlAlbumArtist;
        btn.disabled = true; btn.textContent = '⏳';
        try {
          const tracks = await api.get_album_tracks(title, artist);
          await Promise.all(tracks.map(t =>
            downloads.queueLastfm(t.title || t.name, artist, title)
          ));
          toast.show(`Queued ${tracks.length} track${tracks.length!==1?'s':''}`, 'success', 3000);
        } catch (e) {
          toast.show('Download failed: ' + e.message, 'error', 4000);
        }
        btn.disabled = false; btn.textContent = '⬇ All';
      });
    });
  }

  function destroy() {}

  router.register('lastfm/artist', (c, p) => lastfmArtistPage.render(c, p));

  return { render, destroy };
})();
