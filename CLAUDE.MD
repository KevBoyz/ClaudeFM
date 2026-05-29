# ClaudeFM

Desktop music player for Windows: search Last.fm → download from YouTube → play locally via pywebview.

## Stack

| Layer | Package | Note |
|---|---|---|
| UI | pywebview 6.2.1 | HTML/CSS/JS SPA, js_api bridge |
| Audio | sounddevice 0.5.1 | Playback via PortAudio blocking write loop |
| Metadata | pylast 5.3.0 | Last.fm API, 30-day cache |
| Download | yt-dlp 2024.5.27 | ThreadPoolExecutor, concurrency=2 |
| Audio convert | imageio[ffmpeg] | pip dep, not vendored binary |
| Lyrics | lrcup | LRCLIB API + mutagen tag embed |
| DB | sqlite3 stdlib | WAL + FK + `check_same_thread=False` |
| Models | pydantic 2.13.4 | Mirror DB schema exactly |
| Tags | mutagen 1.47.0 | Audio file metadata r/w |
| Tests | pytest 8.2.0 + pytest-mock 3.14.0 | 245 tests, 15 modules |

## Commands

```powershell
# Run
python app.py

# Test (MUST use this exact format — allowlisted in .claude/settings.json)
.venv/Scripts/python.exe -m pytest tests/ -v
.venv/Scripts/python.exe -m pytest tests/test_foo.py -v

# Setup
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Directory Structure

```
app.py                          # Entry point: init DB, quick scan, pywebview window
src/
  models/
    track.py                    # Track (Pydantic) — mirrors tracks table, incl. lyrics_status, artwork_status, *_fetched_at
    playlist.py                 # Playlist + PlaylistTrack
    artist.py                   # Last.fm result, no DB persistence
    album.py                    # Last.fm result, no DB persistence
  database/
    database.py                 # Schema (5 tables) + all CRUD
    config_manager.py           # Key/value settings with DEFAULTS dict
    file_manager.py             # quick_scan (blocking) + start_background_scan
  services/
    lastfm_service.py           # pylast search + cache table + get_artist_top_tracks + get_cover_image_url
    youtube_service.py          # yt-dlp download + sanitize_filename + ThreadPoolExecutor
    player_service.py           # sounddevice playback + Queue + seek + volume + threading.Lock
    lrclib_service.py           # LRCLIB fetch + mutagen embed + async batch fetch + enrichment query
    cover_art_service.py        # Last.fm cover art fetch + mutagen embed/read (M4A/MP3) + DB status writes
    enrichment_scheduler.py     # Periodic enrichment coordinator: lyrics + artwork batches via threading.Timer
  api/
    api.py                      # ClaudeFMAPI — all methods callable from JS via pywebview js_api
  utils/
    logger.py                   # Session-based rotating logger (10 sessions)
    event_bus.py                # Singleton: emit(type, payload) → window.evaluate_js
  interface/
    home.html                   # Single HTML entry point — loads all scripts/styles
    scripts/
      player.js                 # Player state machine + queue + event dispatch
      player-bar.js             # Bottom playback bar UI
      downloads.js              # Download queue tracking + history
      lyrics.js / lyrics-panel.js # Lyrics fetch + panel open/close
      topbar.js                 # Activity badge (downloads + lyrics + enrichment), notification panel
      sidebar.js                # Nav + search results rendering
      context-menu.js           # Right-click actions
      components.js             # Shared: trackCard(), artistCard(), albumCard(), loadArtwork(), _localIdx
      keyboard.js               # Space/arrow shortcuts
      router.js                 # Hash-based SPA router
      pages/                    # home, library, artists, albums, playlists, playlist-detail,
                                #   lastfm-artist, lastfm-album, settings
    styles/                     # Per-component CSS files
tests/                          # pytest suite, conftest.py has db_conn + tmp_music_dir fixtures
docs/superpowers/specs/         # Design + lyrics + frontend specs
docs/superpowers/plans/         # Implementation plans
```

## Database Schema

```
tracks          — id, title, artist, album, duration, file_path, audio_format,
                  youtube_url, date_downloaded, download_status, download_error,
                  file_status, lyrics_status (not_fetched|not_found|plain_text|synchronized|instrumental),
                  artwork_status (not_fetched|embedded|not_found),
                  lyrics_fetched_at (ISO datetime), artwork_fetched_at (ISO datetime)
playlists       — id, name, type (auto|manual), created_at, updated_at
playlist_tracks — playlist_id, track_id, position
settings        — key, value (text; all values stored as strings)
cache           — key, response, cached_at, expires_at (Last.fm 30-day cache)
```

DB file: `claudefm.db` at project root (gitignored).

## Config Defaults (`config_manager.DEFAULTS`)

| Key | Default |
|---|---|
| `audio_format` | `m4a` |
| `search_results_limit` | `5` |
| `download_concurrency` | `2` |
| `theme` | `dark` |
| `cache_enabled` | `true` |
| `sidebar_collapsed` | `false` |
| `auto_fetch_lyrics` | `true` |
| `auto_fetch_artwork` | `true` |
| `player_volume` | `1.0` |
| `enrich_repeat_lyrics` | `false` |
| `enrich_repeat_artwork` | `false` |
| `enrich_interval_days` | `1` |
| `enrich_retry_not_found_days` | `7` |

## API Response Format

All `ClaudeFMAPI` methods return JSON strings:
```json
{"success": true, "data": {...}}
{"success": false, "error": "message"}
```

Exceptions (return raw structure, no `success` wrapper): `get_library`, `get_artists`, `get_albums`, `get_tracks_by_artist`, `get_tracks_by_album`, `search_local`, `search_lastfm`, `get_artist_top_tracks`, `get_album_tracks`, `get_playlists`, `get_playlist_tracks`, `get_position`, `get_player_state`, `get_settings`, `check_internet`.

Push events via `event_bus.emit(type, payload)` → `window.evaluate_js("onEvent({...})")`. Format is flat — `type` and payload fields at the same level.

## Architecture Decisions

| Decision | Reason |
|---|---|
| `check_same_thread=False` on SQLite | YouTubeService + file_manager use connection from background threads |
| `_ALLOWED_ORDER_BY` whitelist in `get_all_tracks` | Prevent SQL injection via f-string interpolation |
| `event_bus` singleton for all `evaluate_js` calls | No module calls `evaluate_js` directly — testable, decoupled from window lifecycle |
| Lazy init of `YouTubeService` + `LastFMService` + `LRCLibService` in `api.py` | Avoids init at startup before settings are configured |
| `threading.Lock` in `PlayerService` | `_position` and `_paused` accessed from playback thread and API thread |
| `YouTubeService.shutdown(wait=False)` in `on_closing` | Prevents executor leak on app close |
| `imageio[ffmpeg]` not vendored binary | pip dep is simpler, no vendor dir needed |
| Pydantic models mirror DB schema exactly | No conversion logic between layers; `date_downloaded` parsed from ISO string in `_row_to_track` |
| `auto` playlists capped at 15 | `delete_oldest_auto_playlist` called before inserting 16th |
| Seek via stream restart (ffmpeg `-ss`) | sounddevice has no mid-stream seek; kill proc, restart ffmpeg with `-ss offset` |
| Volume via PCM array scaling | No sounddevice volume API; apply `array.array('h')` 16-bit scaling before each write |
| Pause writes silence to stream | Keeps stream alive; real data not consumed so position doesn't advance while paused |
| `_stop_event` + `_proc` stored on service | `play()` terminates old proc immediately to unblock `stdout.read()` in old thread |
| `on_complete` callback in `YouTubeService.queue_download` | Allows `LRCLibService.fetch_and_embed_async` to be injected post-download without coupling layers |
| `_active` set + `threading.Lock` in `YouTubeService` | Prevents concurrent workers downloading the same track_id (e.g. album batch) |
| `insert_track` dedup by title+artist | `SELECT` before `INSERT` returns existing id; prevents duplicate rows on concurrent album downloads |
| `_post_download_hook()` on `ClaudeFMAPI` | Composite callback chaining artwork + lyrics after download; replaces `_lyrics_hook()`; checks both `auto_fetch_artwork` and `auto_fetch_lyrics` settings at call time |
| `CoverArtService` lazy init in `api.py` | Same pattern as `LRCLibService`; avoids init before Last.fm API key is configured |
| `playlist_tracks` `ON DELETE CASCADE` on `track_id` | Deleting a track from `tracks` auto-removes all playlist entries — no manual cleanup needed |
| `is_paused` property on `PlayerService` | Thread-safe read via `_lock`; avoids external modules accessing `_paused` directly |
| PortAudio reinit before each `_playback_thread` | `sd._terminate()` + `sd._initialize()` forces PortAudio to pick up OS default device changes (headphones connected after app start) |
| JS runtime auto-detection in `_run_ytdlp` | `shutil.which` checks node/deno/phantomjs at download time; passes to yt-dlp if found to enable full format support |
| `_localIdx` Map in `components.js` | O(1) local availability check per search result; avoids N API calls when rendering Last.fm results |
| `player:changed` listener in `components.js` | Updates `.playing` class on visible track cards without re-rendering the list |
| `artwork_status` + `artwork_fetched_at` columns on `tracks` | Mirrors `lyrics_status` pattern; enables cooldown-based retry without a separate job queue |
| `EnrichmentScheduler` standalone service | Owns timer lifecycle; `LRCLibService` / `CoverArtService` do the work, scheduler owns timing — clear separation |
| `threading.Timer` for auto-repeat in `EnrichmentScheduler` | No new deps; timer re-reads settings at fire time so interval changes take effect without restart |
| `save_setting()` calls `apply_settings()` | Ensures timer reconfiguration is immediate after any setting change from the UI |
| `get_track_artwork` returns base64 data URL | Avoids exposing file paths to JS; works cross-platform without a local HTTP server |
| `loadArtwork(container)` lazy-loads via `data-artwork` attr | One API call per visible embedded track; `delete thumb.dataset.artwork` prevents double-load on re-render |
