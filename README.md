# ClaudeFM

Desktop music player for Windows. Search metadata via Last.fm, download audio from YouTube, play locally.

## Stack

| Layer | Tech |
|---|---|
| UI | pywebview 6.2.1 (HTML/CSS/JS SPA) |
| Audio playback | sounddevice 0.5.1 (PortAudio) |
| Metadata | pylast 5.3.0 (Last.fm API) |
| Download | yt-dlp + imageio[ffmpeg] |
| Lyrics | lrcup (LRCLIB API) + mutagen |
| Database | SQLite (WAL mode) |
| Data models | pydantic v2 |
| Backend | Python 3.11+ |

## How it works

1. Search artist/track/album on Last.fm via the sidebar
2. Download audio from YouTube as m4a or mp3
3. Lyrics fetched automatically from LRCLIB after download (if enabled)
4. Play from local library with seek, volume, and queue control
5. All state persisted in SQLite (`claudefm.db`)

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

Requires a Last.fm API key and a download folder — configure on first launch in Settings.

## Test

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

93 tests across 13 modules covering models, database, services, API bridge, and utilities.

## Project structure

```
app.py                          # Entry point
src/
  models/                       # Pydantic models (Track, Playlist, Artist, Album)
  database/
    database.py                 # SQLite schema + CRUD
    config_manager.py           # Settings key/value store
    file_manager.py             # Library scan (quick + background)
  services/
    lastfm_service.py           # Last.fm search with 30-day cache
    youtube_service.py          # yt-dlp download + filename sanitization
    player_service.py           # sounddevice playback + seek + volume + queue
    lrclib_service.py           # LRCLIB lyrics fetch + mutagen embed
  api/
    api.py                      # pywebview js_api — all methods callable from JS
  utils/
    logger.py                   # Session-based rotating logger
    event_bus.py                # Centralised push events (evaluate_js)
  interface/                    # HTML/CSS/JS SPA (home, library, artists, albums, playlists, settings)
tests/                          # pytest suite
docs/superpowers/               # Specs and implementation plans
```

## Configuration defaults

| Key | Default |
|---|---|
| `audio_format` | `m4a` |
| `search_results_limit` | `5` |
| `download_concurrency` | `2` |
| `theme` | `dark` |
| `cache_enabled` | `true` |
| `auto_fetch_lyrics` | `true` |
| `player_volume` | `1.0` |
