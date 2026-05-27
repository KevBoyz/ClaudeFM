const player = (() => {
  const state = {
    track: null,
    playing: false,
    position: 0,
    duration: 0,
    volume: 1.0,
    queue: [],
    queueIndex: 0,
    queueName: '',
  };

  let _positionTick = null;

  function _startTick() {
    if (_positionTick) return;
    _positionTick = setInterval(async () => {
      if (!state.playing) return;
      const { position } = await api.get_position();
      state.position = position;
      document.dispatchEvent(new CustomEvent('player:tick', { detail: { position } }));
    }, 1000);
  }

  function _stopTick() {
    clearInterval(_positionTick);
    _positionTick = null;
  }

  async function play(trackId, contextTrackIds = [], queueName = '') {
    const context = contextTrackIds.length ? { track_ids: contextTrackIds } : {};
    await api.play(trackId, context);
    const result = await api.get_track(trackId);
    state.track = result.data;
    state.queue = contextTrackIds.length ? contextTrackIds : [trackId];
    state.queueIndex = state.queue.indexOf(trackId);
    state.queueName = queueName;
    state.playing = true;
    state.position = 0;
    state.duration = state.track.duration || 0;
    _startTick();
    document.dispatchEvent(new CustomEvent('player:changed', { detail: { ...state } }));
  }

  async function pause() {
    await api.pause();
    state.playing = false;
    document.dispatchEvent(new CustomEvent('player:changed', { detail: { ...state } }));
  }

  async function resume() {
    await api.resume();
    state.playing = true;
    _startTick();
    document.dispatchEvent(new CustomEvent('player:changed', { detail: { ...state } }));
  }

  async function next() {
    const result = await api.next_track();
    if (result.ended) { onQueueEnded(); return; }
    if (result.track_id) {
      const t = await api.get_track(result.track_id);
      state.track = t.data;
      state.queueIndex = state.queue.indexOf(result.track_id);
      state.position = 0;
      state.duration = state.track.duration || 0;
      state.playing = true;
      document.dispatchEvent(new CustomEvent('player:changed', { detail: { ...state } }));
    }
  }

  async function prev() {
    const result = await api.prev_track();
    if (result.track_id) {
      const t = await api.get_track(result.track_id);
      state.track = t.data;
      state.queueIndex = state.queue.indexOf(result.track_id);
      state.position = 0;
      state.duration = state.track.duration || 0;
      document.dispatchEvent(new CustomEvent('player:changed', { detail: { ...state } }));
    }
  }

  async function seek(position) {
    await api.seek(position);
    state.position = position;
    document.dispatchEvent(new CustomEvent('player:tick', { detail: { position } }));
  }

  async function setVolume(level) {
    await api.set_volume(level);
    state.volume = level;
  }

  function onEnded() {
    next();
  }

  function onQueueEnded() {
    state.playing = false;
    _stopTick();
    document.dispatchEvent(new CustomEvent('player:ended', {}));
    document.dispatchEvent(new CustomEvent('player:changed', { detail: { ...state } }));
  }

  async function onRestore(trackId, position) {
    try {
      const result = await api.get_track(trackId);
      state.track = result.data;
      state.position = position;
      state.duration = state.track.duration || 0;
      state.playing = false;
      document.dispatchEvent(new CustomEvent('player:changed', { detail: { ...state } }));
    } catch (_) {}
  }

  api.on('playback_ended',  () => onEnded());
  api.on('queue_ended',     () => onQueueEnded());
  api.on('restore_player',  (e) => onRestore(e.track_id, e.position));
  api.on('playback_failed', (e) => {
    state.playing = false;
    _stopTick();
    toast.show(`Playback failed: ${e.message || 'cannot decode file'}`, 'error', 5000);
    document.dispatchEvent(new CustomEvent('player:changed', { detail: { ...state } }));
  });

  return { state, play, pause, resume, next, prev, seek, setVolume, onEnded, onQueueEnded, onRestore };
})();
