const LyricsPanel = (() => {
  function render() {
    document.getElementById('lyrics-panel').innerHTML = `
      <div class="lyrics-header">
        <h3>Lyrics</h3>
        <button class="lyrics-fetch-btn hidden" id="lp-fetch">Fetch</button>
        <button class="lyrics-close" id="lp-close">✕</button>
      </div>
      <div class="lyrics-body" id="lp-body">
        <p class="lyrics-empty">Select a track to see lyrics.</p>
      </div>`;

    document.getElementById('lp-close').onclick = () => lyrics.close();
    document.getElementById('lp-fetch').onclick = async () => {
      const id = lyrics.state.track_id;
      if (id) {
        const btn = document.getElementById('lp-fetch');
        btn.textContent = '⏳'; btn.disabled = true;
        await lyrics.fetch(id);
        btn.textContent = 'Fetch'; btn.disabled = false;
      }
    };

    document.addEventListener('lyrics:changed', e => _update(e.detail));
  }

  function _update(state) {
    const panel = document.getElementById('lyrics-panel');
    const body  = document.getElementById('lp-body');
    const fetch = document.getElementById('lp-fetch');
    if (!panel) return;

    panel.classList.toggle('open', state.panelOpen);
    if (!fetch || !body) return;

    const noLyrics = state.status === 'not_fetched' || state.status === 'not_found';
    fetch.classList.toggle('hidden', !noLyrics);

    if (!state.track_id) {
      body.innerHTML = '<p class="lyrics-empty">Select a track to see lyrics.</p>';
    } else if (state.status === 'synchronized' && state.lines?.length) {
      body.innerHTML = state.lines.map(l => `<div class="lyric-line">${l.text}</div>`).join('');
    } else if (state.status === 'plain_text' && state.text) {
      body.innerHTML = state.text.split('\n').map(l => `<div class="lyric-line">${l}</div>`).join('');
    } else if (state.status === 'instrumental') {
      body.innerHTML = '<p class="lyrics-empty">Instrumental</p>';
    } else if (state.status === 'not_found') {
      body.innerHTML = '<p class="lyrics-empty">Lyrics not found. <button class="lyrics-fetch-btn" onclick="lyrics.fetch(lyrics.state.track_id)">Retry</button></p>';
    } else {
      body.innerHTML = '<p class="lyrics-empty">Lyrics not fetched yet.</p>';
    }
  }

  return { render };
})();
