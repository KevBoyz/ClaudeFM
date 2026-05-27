const lyrics = (() => {
  const state = {
    track_id: null,
    text: null,
    status: null,
    panelOpen: false,
    lines: [],   // [{time: float, text: string}] — only for synchronized
  };

  function _parseLrc(text) {
    const re = /\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)/;
    return text.split('\n')
      .map(line => { const m = line.match(re); return m
        ? { time: parseInt(m[1])*60 + parseInt(m[2]) + parseInt(m[3].padEnd(3,'0'))/1000, text: m[4].trim() }
        : null; })
      .filter(Boolean)
      .sort((a, b) => a.time - b.time);
  }

  async function open(trackId) {
    state.track_id = trackId;
    state.panelOpen = true;
    const result = await api.get_lyrics(trackId);
    state.text   = result.data.lyrics || null;
    state.status = result.data.lyrics_status;
    state.lines  = state.status === 'synchronized' && state.text ? _parseLrc(state.text) : [];
    document.dispatchEvent(new CustomEvent('lyrics:changed', { detail: { ...state } }));
  }

  function close() {
    state.panelOpen = false;
    document.dispatchEvent(new CustomEvent('lyrics:changed', { detail: { ...state } }));
  }

  async function fetch(trackId, title, artist) {
    document.dispatchEvent(new CustomEvent('lyrics:fetch_start', { detail: { track_id: trackId, title, artist } }));
    const result = await api.fetch_lyrics(trackId);
    const status = result?.data?.lyrics_status ?? (result?.success === false ? 'error' : null);
    document.dispatchEvent(new CustomEvent('lyrics:fetch_end', { detail: { track_id: trackId, title, artist, status } }));
    if (state.track_id === trackId) await open(trackId);
    document.dispatchEvent(new CustomEvent('lyrics:track_updated', { detail: { track_id: trackId } }));
  }

  async function fetchMissing() { await api.fetch_missing_lyrics(); }

  function syncHighlight(position) {
    if (state.status !== 'synchronized' || !state.lines.length) return;
    let active = 0;
    for (let i = 0; i < state.lines.length; i++) {
      if (state.lines[i].time <= position) active = i;
    }
    document.querySelectorAll('.lyric-line').forEach((el, i) => {
      el.classList.toggle('active', i === active);
    });
    const el = document.querySelector('.lyric-line.active');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function onProgress(e) {
    document.dispatchEvent(new CustomEvent('lyrics:track_updated', { detail: e }));
    const card = document.querySelector(`.track-card[data-track-id="${e.track_id}"]`);
    if (!card) return;
    const badge = card.querySelector('.track-card-lyrics-badge');
    const hasLyrics = e.status === 'synchronized' || e.status === 'plain_text';
    if (hasLyrics && !badge) {
      const right = card.querySelector('.track-card-right');
      if (right) {
        const span = document.createElement('span');
        span.className = 'track-card-lyrics-badge';
        span.textContent = '🎵';
        right.prepend(span);
      }
    } else if (!hasLyrics && badge) {
      badge.remove();
    }
  }

  function onFetchComplete(e) {
    const { synchronized: s = 0, plain_text: p = 0, not_found: n = 0, errors: err = 0 } = e;
    toast.show(`Lyrics: ${s + p} found, ${n} not found, ${err} errors`, 'info', 5000);
  }

  api.on('lyrics_progress',      onProgress);
  api.on('lyrics_fetch_complete', onFetchComplete);

  document.addEventListener('player:tick', e => {
    if (state.panelOpen) syncHighlight(e.detail.position);
  });

  document.addEventListener('player:changed', e => {
    const t = e.detail.track;
    if (state.panelOpen && t && t.id !== state.track_id) open(t.id);
  });

  return { state, open, close, fetch, fetchMissing, syncHighlight, onProgress, onFetchComplete };
})();
