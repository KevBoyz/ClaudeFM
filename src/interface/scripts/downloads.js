const downloads = (() => {
  const active = {};   // track_id → {track_id, percent}
  const history = [];  // [{track_id, status, error}]

  function activeCount() { return Object.keys(active).length; }

  async function queue(trackId, title, artist) {
    await api.queue_download(trackId);
    active[trackId] = { track_id: trackId, percent: 0, title, artist };
    _notify();
  }

  async function queueLastfm(title, artist, album) {
    const result = await api.download_lastfm_track(title, artist, album);
    const trackId = result.track_id;
    active[trackId] = { track_id: trackId, percent: 0, title, artist };
    _notify();
    return trackId;
  }

  function onProgress(e) {
    if (active[e.track_id]) {
      active[e.track_id].percent = e.percent;
    } else {
      active[e.track_id] = { track_id: e.track_id, percent: e.percent };
    }
    _notify();
  }

  function onComplete(e) {
    const info = active[e.track_id] || {};
    delete active[e.track_id];
    history.unshift({ track_id: e.track_id, status: 'completed', title: info.title, artist: info.artist });
    _notify();
    toast.show('Download complete', 'success', 3000);
    document.dispatchEvent(new CustomEvent('library:changed'));
  }

  function onError(e) {
    const info = active[e.track_id] || {};
    delete active[e.track_id];
    history.unshift({ track_id: e.track_id, status: 'error', error: e.message, title: info.title, artist: info.artist });
    _notify();
    toast.show('Download failed', 'error', 5000);
  }

  function _notify() {
    document.dispatchEvent(new CustomEvent('downloads:changed', {
      detail: { active: { ...active }, history: [...history], count: activeCount() }
    }));
  }

  api.on('download_progress', onProgress);
  api.on('download_complete', onComplete);
  api.on('download_error',    onError);

  return { active, history, activeCount, queue, queueLastfm, onProgress, onComplete, onError };
})();
