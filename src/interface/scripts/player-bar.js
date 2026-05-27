const PlayerBar = (() => {
  function _fmt(sec) {
    if (!sec || isNaN(sec)) return '0:00';
    return `${Math.floor(sec/60)}:${String(Math.floor(sec%60)).padStart(2,'0')}`;
  }

  function render() {
    document.getElementById('player-bar').innerHTML = `
      <div class="player-bar-inner">
        <div class="player-thumb">♪</div>
        <div class="player-info">
          <div class="player-title" id="pb-title">Nothing playing</div>
          <div class="player-artist" id="pb-artist"></div>
        </div>
        <span class="player-lyrics-icon" id="pb-lyric-icon" title="Lyrics">—</span>
        <div class="player-controls">
          <button class="player-btn" id="pb-prev">⏮</button>
          <button class="player-btn play-pause" id="pb-play">▶</button>
          <button class="player-btn" id="pb-next">⏭</button>
        </div>
        <div class="player-progress">
          <span class="player-time" id="pb-pos">0:00</span>
          <div class="progress-track" id="pb-bar">
            <div class="progress-fill" id="pb-fill" style="width:0%"></div>
          </div>
          <span class="player-time" id="pb-dur">0:00</span>
        </div>
        <div class="player-volume">
          <span class="volume-icon">🔊</span>
          <input type="range" id="pb-vol" min="0" max="100" value="100" />
        </div>
        <button class="player-open-lyrics" id="pb-open-lyrics">♪</button>
      </div>`;

    document.getElementById('pb-prev').onclick = () => player.prev();
    document.getElementById('pb-next').onclick = () => player.next();
    document.getElementById('pb-play').onclick = () => player.state.playing ? player.pause() : player.resume();
    document.getElementById('pb-bar').addEventListener('click', e => {
      const frac = e.offsetX / e.currentTarget.offsetWidth;
      player.seek(frac * (player.state.duration || 0));
    });
    document.getElementById('pb-vol').addEventListener('input', e => {
      player.setVolume(parseInt(e.target.value) / 100);
    });
    document.getElementById('pb-vol').addEventListener('change', e => {
      api.save_setting('player_volume', (parseInt(e.target.value) / 100).toFixed(2));
    });
    document.getElementById('pb-lyric-icon').onclick = () => {
      const s = player.state.track?.lyrics_status;
      if (s === 'synchronized' || s === 'plain_text') lyrics.open(player.state.track.id);
    };
    document.getElementById('pb-open-lyrics').onclick = () => {
      if (player.state.track) lyrics.open(player.state.track.id);
    };

    document.addEventListener('player:changed', e => _update(e.detail));
    document.addEventListener('player:tick',    e => _tick(e.detail.position));
  }

  function _update(s) {
    const t = s.track;
    const el = id => document.getElementById(id);
    if (!el('pb-title')) return;
    el('pb-title').textContent   = t ? t.title  : 'Nothing playing';
    el('pb-artist').textContent  = t ? t.artist : '';
    el('pb-play').textContent    = s.playing ? '⏸' : '▶';
    const icon = el('pb-lyric-icon');
    const has = t?.lyrics_status === 'synchronized' || t?.lyrics_status === 'plain_text';
    icon.textContent = t?.lyrics_status === 'instrumental' ? '🎸'
                     : has ? '🎵' : '—';
    icon.className = 'player-lyrics-icon' + (has ? ' has-lyrics' : '');
    _tick(s.position, s.duration);
  }

  function _tick(position, duration) {
    const dur = duration ?? player.state.duration;
    const el = id => document.getElementById(id);
    if (!el('pb-pos')) return;
    el('pb-pos').textContent = _fmt(position);
    el('pb-dur').textContent = _fmt(dur);
    el('pb-fill').style.width = dur > 0 ? `${Math.min(100, (position/dur)*100)}%` : '0%';
  }

  return { render };
})();
