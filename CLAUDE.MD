# ClaudeFM

Desktop music player for Windows: search Last.fm → download from YouTube → play locally via pywebview.

## Stack

| Layer | Package | Note |
|---|---|---|
| UI | pywebview 6.2.1 | HTML/CSS/JS SPA, js_api bridge |
| Audio | miniaudio 1.71 | Playback in daemon thread |
| Metadata | pylast 5.3.0 | Last.fm API, 30-day cache |
| Download | yt-dlp 2024.5.27 | ThreadPoolExecutor, concurrency=2 |
| Audio convert | imageio[ffmpeg] | pip dep, not vendored binary |
| Lyrics | lrcup | LRCLIB API + mutagen tag embed |
| DB | sqlite3 stdlib | WAL + FK + `check_same_thread=False` |
| Models | pydantic 2.13.4 | Mirror DB schema exactly |
| Tags | mutagen 1.47.0 | Audio file metadata r/w |
| Tests | pytest 8.2.0 + pytest-mock 3.14.0 | 93 tests, 13 modules |

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
    track.py                    # Track (Pydantic) — mirrors tracks table, incl. lyrics_status
    playlist.py                 # Playlist + PlaylistTrack
    artist.py                   # Last.fm result, no DB persistence
    album.py                    # Last.fm result, no DB persistence
  database/
    database.py                 # Schema (5 tables) + all CRUD
    config_manager.py           # Key/value settings with DEFAULTS dict
    file_manager.py             # quick_scan (blocking) + start_background_scan
  services/
    lastfm_service.py           # pylast search + cache table + get_artist_top_tracks
    youtube_service.py          # yt-dlp download + sanitize_filename + ThreadPoolExecutor
    player_service.py           # miniaudio playback + Queue + seek + volume + threading.Lock
    lrclib_service.py           # LRCLIB fetch + mutagen embed + async batch fetch
  api/
    api.py                      # ClaudeFMAPI — all methods callable from JS via pywebview js_api
  utils/
    logger.py                   # Session-based rotating logger (10 sessions)
    event_bus.py                # Singleton: emit(type, payload) → window.evaluate_js
  interface/                    # TODO: frontend not yet built (plan: docs/superpowers/plans/2026-05-26-frontend.md)
tests/                          # pytest suite, conftest.py has db_conn + tmp_music_dir fixtures
docs/superpowers/specs/         # Design + lyrics + frontend specs
docs/superpowers/plans/         # Implementation plans
```

## Database Schema

```
tracks          — id, title, artist, album, duration, file_path, audio_format,
                  youtube_url, date_downloaded, download_status, download_error,
                  file_status, lyrics_status (not_fetched|not_found|plain_text|synchronized|instrumental)
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
| `player_volume` | `1.0` |

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
| Seek via stream restart (`stream_file(path, seek_frame=N)`) | miniaudio has no mid-stream seek; restart from frame offset is the supported approach |
| Volume via PCM array scaling in `_audio_gen` | No miniaudio volume API; apply `array.array('h')` 16-bit scaling in the generator wrapper |
| Pause yields silence bytes in inner loop | Keeps stream position intact; consuming the next chunk would advance position while paused |
| `on_complete` callback in `YouTubeService.queue_download` | Allows `LRCLibService.fetch_and_embed_async` to be injected post-download without coupling layers |

## In Progress / Next Steps

1. **Frontend** — `src/interface/` empty
   - Plan: `docs/superpowers/plans/2026-05-26-frontend.md` (25 tasks)
   - Spec: `docs/superpowers/specs/2026-05-26-frontend.md`
   - Vanilla JS SPA, no framework, pywebview js_api bridge
