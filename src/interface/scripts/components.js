// Shared card builder functions — used by all page scripts.

// Pages set this before rendering so track card onclick uses correct queue.
let _pageQueue = [];
function setPageQueue(ids) { _pageQueue = ids; }

function _fmtDur(sec) {
  if (!sec) return '';
  return `${Math.floor(sec/60)}:${String(Math.floor(sec%60)).padStart(2,'0')}`;
}

function trackCard(track) {
  const downloaded = track.download_status === 'completed' && track.file_status === 'available';
  const downloading = track.download_status === 'downloading';
  const missing = track.file_status === 'missing' || track.file_status === 'corrupted';
  const hasLyrics = track.lyrics_status === 'synchronized' || track.lyrics_status === 'plain_text';
  const dur = _fmtDur(track.duration);

  let action = '';
  if (downloading) {
    action = '<button class="track-card-action" disabled>⏳</button>';
  } else if (downloaded && !missing) {
    action = '<button class="track-card-action done" disabled>✓</button>';
  } else {
    action = `<button class="track-card-action"
      onclick="event.stopPropagation();downloads.queue(${track.id})">⬇</button>`;
  }

  return `<div class="track-card" data-track-id="${track.id}"
      onclick="player.play(${track.id}, _pageQueue)">
    <div class="track-card-thumb">♪</div>
    <div class="track-card-info">
      <div class="track-card-title">${track.title}</div>
      <div class="track-card-sub">${track.artist}${track.album ? ' · ' + track.album : ''}</div>
    </div>
    <div class="track-card-right">
      ${hasLyrics ? '<span class="track-card-lyrics-badge">🎵</span>' : ''}
      ${dur ? `<span class="track-card-dur">${dur}</span>` : ''}
      ${action}
    </div>
  </div>`;
}

function artistCard(name, trackCount) {
  const safe = (name||'').replace(/'/g,"\\'");
  return `<div class="media-card" onclick="router.navigate('artists',{artist:'${safe}'})">
    <div class="media-card-thumb">👤</div>
    <div class="media-card-name">${name}</div>
    <div class="media-card-sub">${trackCount} track${trackCount!==1?'s':''}</div>
  </div>`;
}

function albumCard(album, artist, trackCount, onclick) {
  return `<div class="media-card" onclick="${onclick||''}">
    <div class="media-card-thumb">💿</div>
    <div class="media-card-name">${album}</div>
    <div class="media-card-sub">${artist}</div>
    <div class="media-card-sub">${trackCount} track${trackCount!==1?'s':''}</div>
  </div>`;
}
