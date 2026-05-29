const api = (() => {
  let _ready = false;
  const _queue = [];

  function _call(method, ...args) {
    return new Promise((resolve, reject) => {
      const invoke = () => {
        window.pywebview.api[method](...args)
          .then(raw => {
            const result = JSON.parse(raw);
            if (result !== null && typeof result === 'object' && result.success === false) {
              reject(new Error(result.error || 'API error'));
            } else {
              resolve(result);
            }
          })
          .catch(reject);
      };
      if (_ready) invoke();
      else _queue.push(invoke);
    });
  }

  window.addEventListener('pywebviewready', () => {
    _ready = true;
    _queue.forEach(fn => fn());
    _queue.length = 0;
  });

  // Python calls window.onEvent({type, ...fields}) via evaluate_js
  window.onEvent = (event) => {
    document.dispatchEvent(new CustomEvent('claudefm:event', { detail: event }));
  };

  // Convenience: subscribe to a specific event type
  function on(type, handler) {
    document.addEventListener('claudefm:event', e => {
      if (e.detail.type === type) handler(e.detail);
    });
  }

  return {
    on,

    // Library
    get_library:          (filters = {}) => _call('get_library', JSON.stringify(filters)),
    get_track:            (id)            => _call('get_track', id),
    get_artists:          ()              => _call('get_artists'),
    get_albums:           ()              => _call('get_albums'),
    search_local:         (query)         => _call('search_local', query),
    get_tracks_by_artist: (artist)        => _call('get_tracks_by_artist', artist),
    get_tracks_by_album:  (album, artist) => _call('get_tracks_by_album', album, artist),
    remove_from_library:  (id)            => _call('remove_from_library', id),

    // Last.fm
    search_lastfm:          (query, type)          => _call('search_lastfm', query, type),
    get_artist_top_tracks:  (name)                 => _call('get_artist_top_tracks', name),
    get_album_tracks:       (album, artist)        => _call('get_album_tracks', album, artist),

    // Downloads
    queue_download:          (id)                  => _call('queue_download', id),
    download_lastfm_track:   (title, artist, album)=> _call('download_lastfm_track', title, artist, album || null),
    check_internet:          ()                    => _call('check_internet'),

    // Playback
    play:            (id, context = {})  => _call('play', id, JSON.stringify(context)),
    pause:           ()                  => _call('pause'),
    resume:          ()                  => _call('resume'),
    stop:            ()                  => _call('stop'),
    next_track:      ()                  => _call('next_track'),
    prev_track:      ()                  => _call('prev_track'),
    seek:            (pos)               => _call('seek', pos),
    get_position:    ()                  => _call('get_position'),
    set_volume:      (level)             => _call('set_volume', level),
    get_player_state:()                  => _call('get_player_state'),

    // Playlists
    get_playlists:          ()                    => _call('get_playlists'),
    get_playlist_tracks:    (id)                  => _call('get_playlist_tracks', id),
    create_playlist:        (name)                => _call('create_playlist', name),
    rename_playlist:        (id, name)            => _call('rename_playlist', id, name),
    delete_playlist:        (id)                  => _call('delete_playlist', id),
    add_to_playlist:        (pid, tid)            => _call('add_to_playlist', pid, tid),
    remove_from_playlist:   (pid, tid)            => _call('remove_from_playlist', pid, tid),

    // Lyrics
    fetch_lyrics:           (id)  => _call('fetch_lyrics', id),
    fetch_missing_lyrics:   ()    => _call('fetch_missing_lyrics'),
    get_lyrics:             (id)  => _call('get_lyrics', id),
    run_enrichment_lyrics:  ()    => _call('run_enrichment_lyrics'),
    run_enrichment_artwork: ()    => _call('run_enrichment_artwork'),

    // Settings
    get_settings:             ()         => _call('get_settings'),
    save_setting:             (key, val) => _call('save_setting', key, String(val)),
    rescan_library:           ()         => _call('rescan_library'),
    check_lastfm_connection:  ()         => _call('check_lastfm_connection'),
  };
})();
