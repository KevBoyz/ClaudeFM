const lastfmAlbumPage = (() => {
  async function render(container, params = {}) {
    const title  = params.title  || '';
    const artist = params.artist || '';
    container.innerHTML = `
      <div class="page-header">
        <button class="back-btn" onclick="router.back()">← Back</button>
        <div class="media-card-thumb" style="width:80px;height:80px;font-size:2rem;display:flex;align-items:center;justify-content:center;background:var(--color-bg_highlight);border-radius:8px">💿</div>
        <div>
          <h1 class="page-title">${title}</h1>
          <div class="page-subtitle">${artist}</div>
          <div class="page-subtitle" id="lfalb-count"></div>
        </div>
      </div>
      <div id="lfalb-skeleton" class="page-skeleton"></div>
      <div id="lfalb-content"></div>`;

    let tracks;
    try {
      tracks = await api.get_album_tracks(title, artist);
    } catch (e) {
      document.getElementById('lfalb-content').innerHTML = `<div class="error-state">${e.message}</div>`;
      const sk = document.getElementById('lfalb-skeleton');
      if (sk) sk.style.display = 'none';
      return;
    }

    const sk = document.getElementById('lfalb-skeleton');
    if (sk) sk.style.display = 'none';
    const content  = document.getElementById('lfalb-content');
    const countEl  = document.getElementById('lfalb-count');
    if (!content) return;
    if (countEl) countEl.textContent = `${tracks.length} track${tracks.length !== 1 ? 's' : ''}`;

    const rows = tracks.map((t, i) => {
      const trackTitle = t.title || t.name || '';
      const avail = isAvailable(trackTitle, artist);
      return `<div class="sidebar-result-item" style="padding:8px 0">
        <span style="color:var(--color-text_secondary);font-size:.8rem;width:24px;flex-shrink:0">${i + 1}</span>
        <div class="sidebar-result-info">
          <div class="sidebar-result-title">${trackTitle}</div>
          <div class="sidebar-result-sub">${artist}</div>
        </div>
        ${avail
          ? '<span style="color:var(--color-success)">✓</span>'
          : `<button class="sidebar-dl-btn"
              data-title="${trackTitle.replace(/"/g,'&quot;')}"
              data-artist="${artist.replace(/"/g,'&quot;')}"
              data-album="${title.replace(/"/g,'&quot;')}">⬇</button>`}
      </div>`;
    }).join('');

    content.innerHTML = `
      <div style="margin-bottom:16px">
        <button class="btn btn-primary" id="lfalb-dl-all">⬇ Download All</button>
      </div>
      <div class="track-list">${rows}</div>`;

    content.querySelectorAll('.sidebar-dl-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        btn.disabled = true; btn.textContent = '⏳';
        try {
          await downloads.queueLastfm(btn.dataset.title, btn.dataset.artist, btn.dataset.album || null);
          btn.textContent = '✓'; btn.classList.add('done');
        } catch (e) {
          toast.show('Download failed: ' + e.message, 'error', 4000);
          btn.disabled = false; btn.textContent = '⬇';
        }
      });
    });

    document.getElementById('lfalb-dl-all').addEventListener('click', async () => {
      const dlAll = document.getElementById('lfalb-dl-all');
      dlAll.disabled = true; dlAll.textContent = '⏳ Queuing…';
      try {
        const btns = content.querySelectorAll('.sidebar-dl-btn:not(.done):not([disabled])');
        await Promise.all([...btns].map(btn =>
          downloads.queueLastfm(btn.dataset.title, btn.dataset.artist, btn.dataset.album || null)
            .then(() => { btn.textContent = '✓'; btn.classList.add('done'); })
            .catch(() => {})
        ));
        toast.show(`Queued album: ${title}`, 'success', 3000);
      } catch (e) {
        toast.show('Download failed: ' + e.message, 'error', 4000);
      }
      dlAll.disabled = false; dlAll.textContent = '⬇ Download All';
    });
  }

  function destroy() {}

  router.register('lastfm/album', (c, p) => lastfmAlbumPage.render(c, p));

  return { render, destroy };
})();
