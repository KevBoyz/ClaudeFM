# ClaudeFM

Desktop music player for Windows. Search metadata via Last.fm, download audio from YouTube, play locally.

## Stack

| Layer | Tech |
|---|---|
| UI | pywebview (HTML/CSS/JS) |
| Audio playback | miniaudio |
| Metadata | pylast (Last.fm API) |
| Download | yt-dlp + ffmpeg |
| Database | SQLite |
| Data models | pydantic v2 |
| Backend | Python 3.11+ |

## How it works

1. Search artist/track/album on Last.fm
2. Download audio from YouTube as m4a (or mp3)
3. Play from local library via miniaudio
4. All state persisted in SQLite (`claudefm.db`)

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

49 tests across 11 modules covering models, database, services, API bridge, and utilities.

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
    player_service.py           # miniaudio playback + linear queue
  api/
    api.py                      # pywebview js_api — all methods callable from JS
  utils/
    logger.py                   # Session-based rotating logger
    event_bus.py                # Centralised window.evaluate_js push events
  interface/                    # HTML/CSS/JS frontend (WIP)
tests/                          # pytest suite
```

## Configuration defaults

| Key | Default |
|---|---|
| `audio_format` | `m4a` |
| `search_results_limit` | `5` |
| `download_concurrency` | `2` |
| `theme` | `dark` |
| `cache_enabled` | `true` |
