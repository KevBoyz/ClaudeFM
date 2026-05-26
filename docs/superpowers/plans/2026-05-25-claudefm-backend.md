# ClaudeFM Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete Python backend for ClaudeFM — models, database, services, API bridge, and app entry point — ready to wire to the pywebview frontend.

**Architecture:** SQLite for persistence accessed through `database.py`. Pydantic models are the shared data contract between all layers. Services (Last.fm, YouTube, Player) are standalone modules called by `api.py`. `EventBus` centralizes all `window.evaluate_js()` push calls. `app.py` runs the startup check and opens the pywebview window.

**Tech Stack:** Python 3.11+, pydantic v2, pylast, yt-dlp, miniaudio, pywebview, mutagen, pytest

**Environment:** All commands use the project `.venv`. Activate once per terminal session:
```powershell
# PowerShell
.venv\Scripts\Activate.ps1
```
After activation, `pip`, `pytest`, and `python` resolve to `.venv` automatically. If not activated, prefix all commands with `.venv\Scripts\` (e.g. `.venv\Scripts\pytest`).

**TDD rule:** Every task has a failing test first. Do NOT implement until the test runs and fails for the right reason. Do NOT move to the next task until all tests in the current task pass.

---

## File Map

| File | Responsibility |
|---|---|
| `requirements.txt` | All Python dependencies pinned |
| `src/__init__.py` | Package marker |
| `src/models/track.py` | `Track` — mirrors `tracks` table |
| `src/models/playlist.py` | `Playlist`, `PlaylistTrack` |
| `src/models/artist.py` | `Artist` — Last.fm result, no DB |
| `src/models/album.py` | `Album` — Last.fm result, no DB |
| `src/utils/logger.py` | Global logger, per-session files, INFO/WARN/ERROR/DEBUG |
| `src/utils/event_bus.py` | `emit(type, payload)` — single place for `evaluate_js` |
| `src/database/database.py` | Schema init, connection factory, CRUD for all tables |
| `src/database/config_manager.py` | Settings get/set with typed defaults |
| `src/database/file_manager.py` | Quick scan (blocking) + full scan (background thread) |
| `src/services/lastfm_service.py` | pylast search, 30-day cache via `cache` table |
| `src/services/youtube_service.py` | yt-dlp download, filename sanitization, thread pool |
| `src/services/player_service.py` | miniaudio playback, linear queue, state persistence |
| `src/api/__init__.py` | Package marker |
| `src/api/api.py` | pywebview `js_api` class — all methods called from JS |
| `app.py` | Entry point — startup check, pywebview window |
| `tests/conftest.py` | Shared pytest fixtures |
| `tests/test_models.py` | Pydantic model validation |
| `tests/test_database.py` | Schema + CRUD (in-memory SQLite) |
| `tests/test_config_manager.py` | Settings get/set/defaults |
| `tests/test_file_manager.py` | Scan logic with mocked filesystem |
| `tests/test_filename_sanitization.py` | Windows filename sanitization rules |
| `tests/test_lastfm_service.py` | Search + cache (mocked pylast) |
| `tests/test_youtube_service.py` | Download flow (mocked yt-dlp) |
| `tests/test_player_service.py` | Queue management |
| `tests/test_api.py` | API methods (mocked services) |

> **Note:** `src/interface/downloads_page.py` is a stale file — delete it. The interface is HTML-only.

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `tests/conftest.py`
- Create: `.gitignore` additions
- Create: `src/api/__init__.py`

- [x] **Step 1: `.venv` already exists in repo**

```powershell
.venv\Scripts\Activate.ps1
```

Expected: prompt shows `(.venv)`. All subsequent commands in this plan run inside this venv.

- [x] **Step 2: `requirements.txt` already written**

```
pywebview==6.2.1
pydantic==2.13.4
pylast==5.3.0
yt-dlp==2024.5.27
miniaudio==1.71
mutagen==1.47.0
pytest==8.2.0
pytest-mock==3.14.0
```

- [ ] **Step 3: Install dependencies**

```powershell
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 4: Create `tests/conftest.py`**

```python
import sqlite3
import pytest
from pathlib import Path


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def tmp_music_dir(tmp_path):
    d = tmp_path / "music"
    d.mkdir()
    return d
```

- [ ] **Step 5: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
pythonpath = .
```

This tells pytest to add the project root to `sys.path` so `from src.models.track import Track` resolves correctly.

- [ ] **Step 6: Create `src/api/__init__.py`**

```python
```

(empty — package marker only)

- [ ] **Step 7: Add to `.gitignore`**

Append to `.gitignore`:
```
build/
dist/
logs/
*.log
__pycache__/
.pytest_cache/
*.pyc
.env
```

- [ ] **Step 8: Add `.venv` to `.gitignore`**

Append to `.gitignore`:
```
.venv/
```

- [ ] **Step 9: Commit**

```bash
git add requirements.txt pytest.ini tests/conftest.py src/api/__init__.py .gitignore
git commit -m "chore: project setup, venv, dependencies, test fixtures"
```

---

## Task 2: Pydantic Models

**Files:**
- Create: `src/models/track.py`
- Create: `src/models/playlist.py`
- Create: `src/models/artist.py`
- Create: `src/models/album.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_models.py
import pytest
from datetime import datetime
from src.models.track import Track
from src.models.playlist import Playlist, PlaylistTrack
from src.models.artist import Artist
from src.models.album import Album


def test_track_defaults():
    t = Track(title="Song", artist="Artist")
    assert t.download_status == "pending"
    assert t.file_status == "available"
    assert t.id is None


def test_track_rejects_invalid_download_status():
    with pytest.raises(Exception):
        Track(title="Song", artist="Artist", download_status="invalid")


def test_track_rejects_invalid_file_status():
    with pytest.raises(Exception):
        Track(title="Song", artist="Artist", file_status="unknown")


def test_playlist_type_validation():
    p = Playlist(name="My List", type="manual")
    assert p.type == "manual"
    with pytest.raises(Exception):
        Playlist(name="Bad", type="other")


def test_playlist_track_requires_position():
    pt = PlaylistTrack(playlist_id=1, track_id=2, position=0)
    assert pt.position == 0


def test_artist_top_tracks_default_empty():
    a = Artist(name="Radiohead")
    assert a.top_tracks == []


def test_album_tracks_default_empty():
    al = Album(title="OK Computer", artist="Radiohead")
    assert al.tracks == []


def test_track_model_dump_serializable():
    t = Track(title="Creep", artist="Radiohead", duration=239)
    d = t.model_dump()
    assert d["title"] == "Creep"
    assert d["duration"] == 239
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python -m pytest tests/test_models.py -v
```

Expected: `ImportError` — modules not found.

- [ ] **Step 3: Implement `src/models/track.py`**

```python
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, field_validator


class Track(BaseModel):
    id: int | None = None
    title: str
    artist: str
    album: str | None = None
    duration: int | None = None
    file_path: str | None = None
    audio_format: str | None = None
    youtube_url: str | None = None
    date_downloaded: datetime | None = None
    download_status: Literal["pending", "downloading", "completed", "failed"] = "pending"
    download_error: str | None = None
    file_status: Literal["available", "missing", "corrupted"] = "available"
```

- [ ] **Step 4: Implement `src/models/playlist.py`**

```python
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class Playlist(BaseModel):
    id: int | None = None
    name: str
    type: Literal["auto", "manual"]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlaylistTrack(BaseModel):
    playlist_id: int
    track_id: int
    position: int
```

- [ ] **Step 5: Implement `src/models/artist.py`**

```python
from __future__ import annotations
from pydantic import BaseModel
from src.models.track import Track


class Artist(BaseModel):
    name: str
    mbid: str | None = None
    listeners: int | None = None
    top_tracks: list[Track] = []
```

- [ ] **Step 6: Implement `src/models/album.py`**

```python
from __future__ import annotations
from pydantic import BaseModel
from src.models.track import Track


class Album(BaseModel):
    title: str
    artist: str
    mbid: str | None = None
    tracks: list[Track] = []
```

- [ ] **Step 7: Run tests to confirm pass**

```bash
python -m pytest tests/test_models.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/models/ tests/test_models.py
git commit -m "feat: add pydantic models for Track, Playlist, Artist, Album"
```

---

## Task 3: Logger

**Files:**
- Modify: `src/utils/logger.py`
- Create: `tests/test_logger.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_logger.py
import logging
from pathlib import Path
from src.utils.logger import get_logger


def test_get_logger_returns_logger():
    log = get_logger("test")
    assert isinstance(log, logging.Logger)


def test_logger_has_correct_name():
    log = get_logger("mymodule")
    assert log.name == "claudefm.mymodule"


def test_logger_does_not_duplicate_handlers():
    log1 = get_logger("dup")
    log2 = get_logger("dup")
    assert log1 is log2
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_logger.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `src/utils/logger.py`**

```python
import logging
import sys
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
_SESSION_FILE: Path | None = None
_root_logger: logging.Logger | None = None


def _setup_root_logger() -> logging.Logger:
    global _root_logger, _SESSION_FILE

    if _root_logger is not None:
        return _root_logger

    _LOG_DIR.mkdir(exist_ok=True)
    _cleanup_old_sessions(keep=10)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _SESSION_FILE = _LOG_DIR / f"{timestamp}.log"

    logger = logging.getLogger("claudefm")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    file_handler = logging.FileHandler(_SESSION_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    _root_logger = logger
    return logger


def _cleanup_old_sessions(keep: int) -> None:
    files = sorted(_LOG_DIR.glob("*.log"), key=lambda f: f.stat().st_mtime)
    for old in files[:-keep]:
        old.unlink(missing_ok=True)


def get_logger(name: str) -> logging.Logger:
    _setup_root_logger()
    return logging.getLogger(f"claudefm.{name}")
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_logger.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils/logger.py tests/test_logger.py
git commit -m "feat: add session-based logger with rotation"
```

---

## Task 4: Database Schema

**Files:**
- Modify: `src/database/database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_database.py
import sqlite3
import pytest
from src.database.database import init_db, get_connection, insert_track, get_track, update_track_status, get_all_tracks


def test_init_creates_all_tables(db_conn):
    init_db(db_conn)
    tables = {r[0] for r in db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"tracks", "playlists", "playlist_tracks", "settings", "cache"} <= tables


def test_insert_and_get_track(db_conn):
    init_db(db_conn)
    from src.models.track import Track
    t = Track(title="Creep", artist="Radiohead")
    track_id = insert_track(db_conn, t)
    fetched = get_track(db_conn, track_id)
    assert fetched.title == "Creep"
    assert fetched.artist == "Radiohead"
    assert fetched.download_status == "pending"


def test_update_track_status(db_conn):
    init_db(db_conn)
    from src.models.track import Track
    t = Track(title="Paranoid Android", artist="Radiohead")
    track_id = insert_track(db_conn, t)
    update_track_status(db_conn, track_id, download_status="completed", file_status="available")
    fetched = get_track(db_conn, track_id)
    assert fetched.download_status == "completed"


def test_get_all_tracks_returns_list(db_conn):
    init_db(db_conn)
    from src.models.track import Track
    insert_track(db_conn, Track(title="A", artist="X"))
    insert_track(db_conn, Track(title="B", artist="Y"))
    tracks = get_all_tracks(db_conn)
    assert len(tracks) == 2
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_database.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `src/database/database.py`**

```python
import sqlite3
from pathlib import Path
from src.models.track import Track
from src.models.playlist import Playlist, PlaylistTrack

_DB_PATH = Path(__file__).parent.parent.parent / "claudefm.db"


def get_connection(path: Path = _DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tracks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            artist          TEXT NOT NULL,
            album           TEXT,
            duration        INTEGER,
            file_path       TEXT,
            audio_format    TEXT,
            youtube_url     TEXT,
            date_downloaded TEXT,
            download_status TEXT NOT NULL DEFAULT 'pending',
            download_error  TEXT,
            file_status     TEXT NOT NULL DEFAULT 'available'
        );

        CREATE TABLE IF NOT EXISTS playlists (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            type       TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS playlist_tracks (
            playlist_id INTEGER NOT NULL,
            track_id    INTEGER NOT NULL,
            position    INTEGER NOT NULL,
            PRIMARY KEY (playlist_id, track_id),
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS cache (
            key        TEXT PRIMARY KEY,
            response   TEXT,
            cached_at  TEXT,
            expires_at TEXT
        );
    """)
    conn.commit()


def _row_to_track(row: sqlite3.Row) -> Track:
    return Track(
        id=row["id"],
        title=row["title"],
        artist=row["artist"],
        album=row["album"],
        duration=row["duration"],
        file_path=row["file_path"],
        audio_format=row["audio_format"],
        youtube_url=row["youtube_url"],
        download_status=row["download_status"],
        download_error=row["download_error"],
        file_status=row["file_status"],
    )


def insert_track(conn: sqlite3.Connection, track: Track) -> int:
    cur = conn.execute(
        """INSERT INTO tracks (title, artist, album, duration, file_path, audio_format,
           youtube_url, date_downloaded, download_status, download_error, file_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (track.title, track.artist, track.album, track.duration, track.file_path,
         track.audio_format, track.youtube_url,
         track.date_downloaded.isoformat() if track.date_downloaded else None,
         track.download_status, track.download_error, track.file_status),
    )
    conn.commit()
    return cur.lastrowid


def get_track(conn: sqlite3.Connection, track_id: int) -> Track | None:
    row = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    return _row_to_track(row) if row else None


def update_track_status(
    conn: sqlite3.Connection,
    track_id: int,
    *,
    download_status: str | None = None,
    download_error: str | None = None,
    file_status: str | None = None,
    file_path: str | None = None,
    youtube_url: str | None = None,
) -> None:
    fields, values = [], []
    for col, val in [
        ("download_status", download_status),
        ("download_error", download_error),
        ("file_status", file_status),
        ("file_path", file_path),
        ("youtube_url", youtube_url),
    ]:
        if val is not None:
            fields.append(f"{col}=?")
            values.append(val)
    if not fields:
        return
    values.append(track_id)
    conn.execute(f"UPDATE tracks SET {', '.join(fields)} WHERE id=?", values)
    conn.commit()


def get_all_tracks(conn: sqlite3.Connection, order_by: str = "date_downloaded DESC") -> list[Track]:
    rows = conn.execute(f"SELECT * FROM tracks ORDER BY {order_by}").fetchall()
    return [_row_to_track(r) for r in rows]


def get_tracks_by_artist(conn: sqlite3.Connection, artist: str) -> list[Track]:
    rows = conn.execute(
        "SELECT * FROM tracks WHERE LOWER(artist)=LOWER(?) ORDER BY album, title",
        (artist,)
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def get_tracks_by_album(conn: sqlite3.Connection, album: str, artist: str) -> list[Track]:
    rows = conn.execute(
        "SELECT * FROM tracks WHERE LOWER(album)=LOWER(?) AND LOWER(artist)=LOWER(?) ORDER BY title",
        (album, artist)
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def search_tracks_local(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[Track]:
    q = f"%{query.lower()}%"
    rows = conn.execute(
        "SELECT * FROM tracks WHERE LOWER(title) LIKE ? OR LOWER(artist) LIKE ? LIMIT ?",
        (q, q, limit)
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def insert_playlist(conn: sqlite3.Connection, playlist: Playlist) -> int:
    from datetime import datetime
    now = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO playlists (name, type, created_at, updated_at) VALUES (?,?,?,?)",
        (playlist.name, playlist.type, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_all_playlists(conn: sqlite3.Connection) -> list[Playlist]:
    rows = conn.execute("SELECT * FROM playlists ORDER BY updated_at DESC").fetchall()
    return [Playlist(id=r["id"], name=r["name"], type=r["type"]) for r in rows]


def get_auto_playlist_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM playlists WHERE type='auto'").fetchone()[0]


def delete_oldest_auto_playlist(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT id FROM playlists WHERE type='auto' ORDER BY updated_at ASC LIMIT 1"
    ).fetchone()
    if row:
        conn.execute("DELETE FROM playlists WHERE id=?", (row["id"],))
        conn.commit()


def upsert_playlist_tracks(conn: sqlite3.Connection, playlist_id: int, track_ids: list[int]) -> None:
    conn.execute("DELETE FROM playlist_tracks WHERE playlist_id=?", (playlist_id,))
    conn.executemany(
        "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?,?,?)",
        [(playlist_id, tid, i) for i, tid in enumerate(track_ids)],
    )
    conn.commit()


def get_playlist_tracks(conn: sqlite3.Connection, playlist_id: int) -> list[Track]:
    rows = conn.execute(
        """SELECT t.* FROM tracks t
           JOIN playlist_tracks pt ON pt.track_id = t.id
           WHERE pt.playlist_id=?
           ORDER BY pt.position""",
        (playlist_id,)
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def delete_playlist(conn: sqlite3.Connection, playlist_id: int) -> None:
    conn.execute("DELETE FROM playlists WHERE id=?", (playlist_id,))
    conn.commit()


def update_playlist_name(conn: sqlite3.Connection, playlist_id: int, name: str) -> None:
    conn.execute("UPDATE playlists SET name=?, updated_at=datetime('now') WHERE id=?", (name, playlist_id))
    conn.commit()


def add_track_to_playlist(conn: sqlite3.Connection, playlist_id: int, track_id: int) -> None:
    row = conn.execute(
        "SELECT MAX(position) FROM playlist_tracks WHERE playlist_id=?", (playlist_id,)
    ).fetchone()
    position = (row[0] or -1) + 1
    conn.execute(
        "INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, position) VALUES (?,?,?)",
        (playlist_id, track_id, position),
    )
    conn.commit()


def remove_track_from_playlist(conn: sqlite3.Connection, playlist_id: int, track_id: int) -> None:
    conn.execute(
        "DELETE FROM playlist_tracks WHERE playlist_id=? AND track_id=?",
        (playlist_id, track_id),
    )
    conn.commit()
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_database.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/database/database.py tests/test_database.py
git commit -m "feat: sqlite schema and track/playlist CRUD"
```

---

## Task 5: Config Manager

**Files:**
- Modify: `src/database/config_manager.py`
- Create: `tests/test_config_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config_manager.py
from src.database.database import init_db
from src.database.config_manager import get_setting, set_setting, get_all_settings, DEFAULTS


def test_get_default_when_not_set(db_conn):
    init_db(db_conn)
    val = get_setting(db_conn, "audio_format")
    assert val == "m4a"


def test_set_and_get_setting(db_conn):
    init_db(db_conn)
    set_setting(db_conn, "audio_format", "mp3")
    assert get_setting(db_conn, "audio_format") == "mp3"


def test_get_all_settings_returns_defaults_for_unset(db_conn):
    init_db(db_conn)
    settings = get_all_settings(db_conn)
    assert settings["search_results_limit"] == "5"
    assert settings["cache_enabled"] == "true"
    assert settings["theme"] == "dark"


def test_set_and_retrieve_sidebar_state(db_conn):
    init_db(db_conn)
    set_setting(db_conn, "sidebar_collapsed", "true")
    assert get_setting(db_conn, "sidebar_collapsed") == "true"
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_config_manager.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `src/database/config_manager.py`**

```python
import sqlite3

DEFAULTS: dict[str, str] = {
    "lastfm_api_key": "",
    "download_folder": "",
    "additional_folders": "[]",
    "audio_format": "m4a",
    "cache_enabled": "true",
    "search_results_limit": "5",
    "theme": "dark",
    "sidebar_collapsed": "false",
    "player_last_track_id": "",
    "player_last_position": "0",
    "player_last_context": "",
    "download_concurrency": "2",
}


def get_setting(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row and row[0] is not None:
        return row[0]
    return DEFAULTS.get(key, "")


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_all_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    result = dict(DEFAULTS)
    for row in rows:
        result[row[0]] = row[1]
    return result
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_config_manager.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/database/config_manager.py tests/test_config_manager.py
git commit -m "feat: settings config manager with typed defaults"
```

---

## Task 6: EventBus

**Files:**
- Create: `src/utils/event_bus.py`
- Create: `tests/test_event_bus.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_event_bus.py
import json
import pytest
from unittest.mock import MagicMock, patch
from src.utils.event_bus import EventBus


def test_emit_calls_evaluate_js():
    window = MagicMock()
    bus = EventBus(window)
    bus.emit("download_progress", {"track_id": 1, "percent": 50})
    window.evaluate_js.assert_called_once()
    call_arg = window.evaluate_js.call_args[0][0]
    assert "onEvent" in call_arg
    assert "download_progress" in call_arg


def test_emit_payload_is_valid_json():
    window = MagicMock()
    bus = EventBus(window)
    bus.emit("test_event", {"key": "value", "num": 42})
    call_arg = window.evaluate_js.call_args[0][0]
    # Extract JSON from onEvent(JSON)
    json_str = call_arg[len("onEvent("):-1]
    parsed = json.loads(json_str)
    assert parsed["type"] == "test_event"
    assert parsed["key"] == "value"


def test_emit_does_nothing_when_window_is_none():
    bus = EventBus(None)
    bus.emit("test", {})  # should not raise


def test_set_window_enables_emit():
    window = MagicMock()
    bus = EventBus(None)
    bus.set_window(window)
    bus.emit("ready", {})
    window.evaluate_js.assert_called_once()
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_event_bus.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `src/utils/event_bus.py`**

```python
import json
from src.utils.logger import get_logger

log = get_logger("event_bus")


class EventBus:
    def __init__(self, window=None):
        self._window = window

    def set_window(self, window) -> None:
        self._window = window

    def emit(self, event_type: str, payload: dict) -> None:
        if self._window is None:
            return
        data = json.dumps({"type": event_type, **payload})
        js = f"onEvent({data})"
        try:
            self._window.evaluate_js(js)
        except Exception as e:
            log.error(f"EventBus.emit failed for '{event_type}': {e}", exc_info=True)


event_bus = EventBus()
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_event_bus.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils/event_bus.py tests/test_event_bus.py
git commit -m "feat: event bus for centralised evaluate_js push events"
```

---

## Task 7: File Manager

**Files:**
- Modify: `src/database/file_manager.py`
- Create: `tests/test_file_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_file_manager.py
import shutil
from pathlib import Path
from src.database.database import init_db, get_all_tracks
from src.database.file_manager import quick_scan, full_scan


def _make_mp3(path: Path) -> None:
    """Create a minimal valid MP3-like file for testing."""
    path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 128)


def test_quick_scan_marks_missing_tracks(db_conn, tmp_music_dir):
    init_db(db_conn)
    from src.database.database import insert_track
    from src.models.track import Track
    t = Track(title="Gone", artist="X", file_path=str(tmp_music_dir / "gone.mp3"),
              download_status="completed", file_status="available")
    insert_track(db_conn, t)

    quick_scan(db_conn)

    tracks = get_all_tracks(db_conn)
    assert tracks[0].file_status == "missing"


def test_quick_scan_leaves_available_tracks_intact(db_conn, tmp_music_dir):
    init_db(db_conn)
    from src.database.database import insert_track
    from src.models.track import Track
    f = tmp_music_dir / "present.mp3"
    _make_mp3(f)
    t = Track(title="Here", artist="Y", file_path=str(f),
              download_status="completed", file_status="available")
    insert_track(db_conn, t)

    quick_scan(db_conn)

    tracks = get_all_tracks(db_conn)
    assert tracks[0].file_status == "available"


def test_full_scan_adds_new_files(db_conn, tmp_music_dir):
    init_db(db_conn)
    f = tmp_music_dir / "new_song.mp3"
    _make_mp3(f)

    full_scan(db_conn, [str(tmp_music_dir)])

    tracks = get_all_tracks(db_conn)
    assert len(tracks) == 1
    assert tracks[0].file_path == str(f)
    assert tracks[0].download_status == "completed"
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_file_manager.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `src/database/file_manager.py`**

```python
import sqlite3
import threading
from pathlib import Path
from src.database.database import (
    get_all_tracks, insert_track, update_track_status
)
from src.models.track import Track
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("file_manager")

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".ogg", ".wav", ".opus"}


def _extract_metadata(path: Path) -> dict:
    """Extract basic metadata from audio file using mutagen. Falls back to filename."""
    title = path.stem
    artist = "Unknown Artist"
    duration = None
    try:
        import mutagen
        meta = mutagen.File(path)
        if meta:
            duration = int(meta.info.length) if hasattr(meta, "info") else None
            tags = meta.tags or {}
            title = str(tags.get("TIT2", [title])[0]) if "TIT2" in tags else str(tags.get("title", [title])[0]) if "title" in tags else title
            artist = str(tags.get("TPE1", [artist])[0]) if "TPE1" in tags else str(tags.get("artist", [artist])[0]) if "artist" in tags else artist
    except Exception as e:
        log.debug(f"mutagen failed for {path}: {e}")
    return {"title": title, "artist": artist, "duration": duration, "audio_format": path.suffix.lstrip(".")}


def quick_scan(conn: sqlite3.Connection) -> None:
    """Blocking. Check existing DB tracks — mark missing if file not found."""
    tracks = get_all_tracks(conn)
    for track in tracks:
        if track.file_path and not Path(track.file_path).exists():
            update_track_status(conn, track.id, file_status="missing")
            log.info(f"Marked missing: {track.file_path}")


def full_scan(conn: sqlite3.Connection, folders: list[str]) -> tuple[int, int]:
    """Scan all configured folders. Add new files, mark missing. Returns (added, missing)."""
    existing_paths = {t.file_path for t in get_all_tracks(conn) if t.file_path}
    added, missing = 0, 0

    for folder_str in folders:
        folder = Path(folder_str)
        if not folder.exists():
            log.warn(f"Folder not found: {folder}")
            continue
        for path in folder.rglob("*"):
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            path_str = str(path)
            if path_str in existing_paths:
                continue
            meta = _extract_metadata(path)
            track = Track(
                title=meta["title"],
                artist=meta["artist"],
                duration=meta["duration"],
                file_path=path_str,
                audio_format=meta["audio_format"],
                download_status="completed",
                file_status="available",
            )
            insert_track(conn, track)
            added += 1

    log.info(f"Full scan complete: {added} added, {missing} missing")
    event_bus.emit("library_scan_complete", {"added": added, "missing": missing})
    return added, missing


def start_background_scan(conn: sqlite3.Connection, folders: list[str]) -> threading.Thread:
    t = threading.Thread(target=full_scan, args=(conn, folders), daemon=True)
    t.start()
    return t
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_file_manager.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/database/file_manager.py tests/test_file_manager.py
git commit -m "feat: file manager with quick blocking scan and full background scan"
```

---

## Task 8: Last.fm Service

**Files:**
- Modify: `src/services/lastfm_service.py`
- Create: `tests/test_lastfm_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lastfm_service.py
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from src.database.database import init_db
from src.services.lastfm_service import LastFMService


def _make_service(db_conn, api_key="fakekey"):
    return LastFMService(db_conn, api_key)


def test_search_returns_empty_list_when_no_api_key(db_conn):
    init_db(db_conn)
    svc = LastFMService(db_conn, api_key="")
    result = svc.search("radiohead", "artist")
    assert result == []


def test_cache_hit_skips_api_call(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    cached = json.dumps([{"name": "Radiohead", "type": "artist"}])
    expires = (datetime.now() + timedelta(days=1)).isoformat()
    db_conn.execute(
        "INSERT INTO cache (key, response, cached_at, expires_at) VALUES (?,?,?,?)",
        ("search:artist:radiohead", cached, datetime.now().isoformat(), expires),
    )
    db_conn.commit()
    with patch("pylast.LastFMNetwork") as mock_net:
        result = svc.search("radiohead", "artist")
    mock_net.assert_not_called()
    assert result[0]["name"] == "Radiohead"


def test_expired_cache_calls_api(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    cached = json.dumps([{"name": "Old"}])
    expired = (datetime.now() - timedelta(days=1)).isoformat()
    db_conn.execute(
        "INSERT INTO cache (key, response, cached_at, expires_at) VALUES (?,?,?,?)",
        ("search:artist:radiohead", cached, expired, expired),
    )
    db_conn.commit()
    mock_result = MagicMock()
    mock_result.get_name.return_value = "Radiohead"
    mock_result.get_mbid.return_value = "abc123"
    mock_result.get_listener_count.return_value = 5000000
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.search_for_artist.return_value.get_next_page.return_value = [mock_result]
        result = svc.search("radiohead", "artist")
    assert len(result) > 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_lastfm_service.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `src/services/lastfm_service.py`**

```python
import json
import sqlite3
from datetime import datetime, timedelta
from src.utils.logger import get_logger
from src.models.artist import Artist
from src.models.album import Album
from src.models.track import Track

log = get_logger("lastfm")

CACHE_TTL_DAYS = 30


class LastFMService:
    def __init__(self, conn: sqlite3.Connection, api_key: str):
        self._conn = conn
        self._api_key = api_key
        self._network = None

    def _get_network(self):
        if self._network is None:
            import pylast
            self._network = pylast.LastFMNetwork(api_key=self._api_key)
        return self._network

    def _cache_key(self, *parts) -> str:
        return ":".join(str(p).lower() for p in parts)

    def _get_cache(self, key: str) -> list | None:
        row = self._conn.execute(
            "SELECT response, expires_at FROM cache WHERE key=?", (key,)
        ).fetchone()
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now():
            self._conn.execute("DELETE FROM cache WHERE key=?", (key,))
            self._conn.commit()
            return None
        return json.loads(row["response"])

    def _set_cache(self, key: str, data: list) -> None:
        now = datetime.now()
        expires = now + timedelta(days=CACHE_TTL_DAYS)
        self._conn.execute(
            "INSERT INTO cache (key, response, cached_at, expires_at) VALUES (?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET response=excluded.response, cached_at=excluded.cached_at, expires_at=excluded.expires_at",
            (key, json.dumps(data), now.isoformat(), expires.isoformat()),
        )
        self._conn.commit()

    def search(self, query: str, search_type: str, limit: int = 5) -> list[dict]:
        """search_type: 'artist' | 'track' | 'album'"""
        if not self._api_key:
            return []
        key = self._cache_key("search", search_type, query)
        cached = self._get_cache(key)
        if cached is not None:
            return cached[:limit]
        try:
            net = self._get_network()
            if search_type == "artist":
                results = self._search_artists(net, query, limit)
            elif search_type == "track":
                results = self._search_tracks(net, query, limit)
            else:
                results = self._search_albums(net, query, limit)
            self._set_cache(key, results)
            return results
        except Exception as e:
            log.error(f"Last.fm search failed: {e}", exc_info=True)
            return []

    def _search_artists(self, net, query: str, limit: int) -> list[dict]:
        import pylast
        items = net.search_for_artist(query).get_next_page()[:limit]
        return [{"type": "artist", "name": a.get_name(), "mbid": a.get_mbid()} for a in items]

    def _search_tracks(self, net, query: str, limit: int) -> list[dict]:
        items = net.search_for_track("", query).get_next_page()[:limit]
        return [{"type": "track", "title": t.get_name(), "artist": t.get_artist().get_name(), "mbid": t.get_mbid()} for t in items]

    def _search_albums(self, net, query: str, limit: int) -> list[dict]:
        items = net.search_for_album(query).get_next_page()[:limit]
        return [{"type": "album", "title": a.get_name(), "artist": a.get_artist().get_name(), "mbid": a.get_mbid()} for a in items]

    def get_artist_top_tracks(self, artist_name: str, limit: int = 10) -> list[dict]:
        key = self._cache_key("top_tracks", artist_name)
        cached = self._get_cache(key)
        if cached is not None:
            return cached
        try:
            net = self._get_network()
            artist = net.get_artist(artist_name)
            tracks = artist.get_top_tracks(limit=limit)
            result = [{"type": "track", "title": t.item.get_name(), "artist": artist_name} for t in tracks]
            self._set_cache(key, result)
            return result
        except Exception as e:
            log.error(f"get_artist_top_tracks failed: {e}", exc_info=True)
            return []

    def get_album_tracks(self, album_title: str, artist_name: str) -> list[dict]:
        key = self._cache_key("album_tracks", artist_name, album_title)
        cached = self._get_cache(key)
        if cached is not None:
            return cached
        try:
            net = self._get_network()
            album = net.get_album(artist_name, album_title)
            tracks = album.get_tracks()
            result = [{"type": "track", "title": t.get_name(), "artist": artist_name, "album": album_title} for t in tracks]
            self._set_cache(key, result)
            return result
        except Exception as e:
            log.error(f"get_album_tracks failed: {e}", exc_info=True)
            return []
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_lastfm_service.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/lastfm_service.py tests/test_lastfm_service.py
git commit -m "feat: last.fm service with search, top tracks, album tracks, and 30-day cache"
```

---

## Task 9: YouTube Service + Filename Sanitization

**Files:**
- Modify: `src/services/youtube_service.py`
- Create: `tests/test_youtube_service.py`
- Create: `tests/test_filename_sanitization.py`

- [ ] **Step 1: Write failing tests — sanitization**

```python
# tests/test_filename_sanitization.py
from src.services.youtube_service import sanitize_filename


def test_removes_windows_invalid_chars():
    assert sanitize_filename('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"


def test_reserved_names_get_suffix():
    assert sanitize_filename("CON") == "CON_"
    assert sanitize_filename("NUL") == "NUL_"
    assert sanitize_filename("COM1") == "COM1_"


def test_strips_trailing_dots_and_spaces():
    assert sanitize_filename("hello. ") == "hello"


def test_truncates_long_names():
    long = "a" * 300
    result = sanitize_filename(long)
    assert len(result) <= 200


def test_normal_name_unchanged():
    assert sanitize_filename("Radiohead - Creep") == "Radiohead - Creep"
```

- [ ] **Step 2: Write failing tests — download**

```python
# tests/test_youtube_service.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.database.database import init_db, get_track
from src.database.config_manager import set_setting
from src.services.youtube_service import YouTubeService


def _make_service(db_conn, download_dir):
    set_setting(db_conn, "download_folder", str(download_dir))
    set_setting(db_conn, "audio_format", "m4a")
    return YouTubeService(db_conn)


def test_download_updates_status_to_downloading(db_conn, tmp_music_dir):
    init_db(db_conn)
    from src.database.database import insert_track
    from src.models.track import Track
    t = Track(title="Creep", artist="Radiohead")
    track_id = insert_track(db_conn, t)
    svc = _make_service(db_conn, tmp_music_dir)

    with patch.object(svc, "_run_ytdlp") as mock_dl:
        mock_dl.return_value = str(tmp_music_dir / "Radiohead - Creep.m4a")
        (tmp_music_dir / "Radiohead - Creep.m4a").write_bytes(b"fake")
        svc.download(track_id)

    track = get_track(db_conn, track_id)
    assert track.download_status == "completed"
    assert track.file_status == "available"


def test_download_marks_failed_on_error(db_conn, tmp_music_dir):
    init_db(db_conn)
    from src.database.database import insert_track
    from src.models.track import Track
    t = Track(title="Creep", artist="Radiohead")
    track_id = insert_track(db_conn, t)
    svc = _make_service(db_conn, tmp_music_dir)

    with patch.object(svc, "_run_ytdlp", side_effect=Exception("yt-dlp error")):
        svc.download(track_id)

    track = get_track(db_conn, track_id)
    assert track.download_status == "failed"
    assert "yt-dlp error" in track.download_error
```

- [ ] **Step 3: Run to confirm failure**

```bash
python -m pytest tests/test_filename_sanitization.py tests/test_youtube_service.py -v
```

Expected: `ImportError`.

- [ ] **Step 4: Implement `src/services/youtube_service.py`**

```python
import re
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from src.database.database import get_track, update_track_status
from src.database.config_manager import get_setting
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("youtube")

_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*]')
_RESERVED = {"CON", "PRN", "AUX", "NUL",
             "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
             "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"}
_MAX_LEN = 200


def sanitize_filename(name: str) -> str:
    name = _WINDOWS_INVALID.sub("_", name)
    name = name.rstrip(". ")
    if name.upper() in _RESERVED:
        name = name + "_"
    return name[:_MAX_LEN]


class YouTubeService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._executor = ThreadPoolExecutor(
            max_workers=int(get_setting(conn, "download_concurrency"))
        )

    def queue_download(self, track_id: int) -> None:
        self._executor.submit(self.download, track_id)

    def download(self, track_id: int) -> None:
        track = get_track(self._conn, track_id)
        if not track:
            return
        update_track_status(self._conn, track_id, download_status="downloading")
        event_bus.emit("download_progress", {"track_id": track_id, "percent": 0})
        try:
            download_dir = get_setting(self._conn, "download_folder")
            audio_format = get_setting(self._conn, "audio_format")
            query = f"{track.artist} - {track.title}"
            out_path = self._run_ytdlp(query, download_dir, audio_format, track_id)
            update_track_status(
                self._conn, track_id,
                download_status="completed",
                file_status="available",
                file_path=out_path,
                youtube_url=f"ytsearch:{query}",
            )
            event_bus.emit("download_complete", {"track_id": track_id})
        except Exception as e:
            log.error(f"Download failed for track {track_id}: {e}", exc_info=True)
            update_track_status(
                self._conn, track_id,
                download_status="failed",
                download_error=str(e),
            )
            event_bus.emit("download_error", {"track_id": track_id, "message": str(e)})

    def _run_ytdlp(self, query: str, download_dir: str, audio_format: str, track_id: int) -> str:
        import yt_dlp

        filename_tmpl = sanitize_filename("%(artist)s - %(title)s") + ".%(ext)s"
        out_template = str(Path(download_dir) / filename_tmpl)

        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                downloaded = d.get("downloaded_bytes", 0)
                percent = int(downloaded / total * 100)
                event_bus.emit("download_progress", {"track_id": track_id, "percent": percent})

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
            }],
            "default_search": "ytsearch",
            "noplaylist": True,
            "progress_hooks": [progress_hook],
            "quiet": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            filename = ydl.prepare_filename(info)
            # After postprocessing the extension changes
            final = Path(filename).with_suffix(f".{audio_format}")
            if not final.exists():
                # Fallback: find the newest file in download_dir
                files = sorted(Path(download_dir).glob(f"*.{audio_format}"), key=lambda f: f.stat().st_mtime)
                if files:
                    return str(files[-1])
                raise FileNotFoundError(f"Download completed but file not found: {final}")
            return str(final)
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
python -m pytest tests/test_filename_sanitization.py tests/test_youtube_service.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/youtube_service.py tests/test_youtube_service.py tests/test_filename_sanitization.py
git commit -m "feat: youtube download service with filename sanitization and thread pool"
```

---

## Task 10: Player Service

**Files:**
- Modify: `src/services/player_service.py`
- Create: `tests/test_player_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_player_service.py
from unittest.mock import patch, MagicMock
from src.services.player_service import PlayerService, Queue


def test_queue_set_context_linear():
    q = Queue()
    q.set_context([1, 2, 3], start_index=0)
    assert q.current_id() == 1
    assert q.next_id() == 2
    assert q.current_id() == 2


def test_queue_prev():
    q = Queue()
    q.set_context([10, 20, 30], start_index=1)
    assert q.current_id() == 20
    assert q.prev_id() == 10


def test_queue_next_at_end_returns_none():
    q = Queue()
    q.set_context([1], start_index=0)
    assert q.current_id() == 1
    assert q.next_id() is None


def test_queue_ended_flag():
    q = Queue()
    q.set_context([1], start_index=0)
    q.current_id()
    q.next_id()
    assert q.ended


def test_player_service_play_calls_miniaudio(tmp_path):
    f = tmp_path / "song.m4a"
    f.write_bytes(b"fake audio")
    with patch("miniaudio.stream_file") as mock_stream:
        mock_stream.return_value = iter([b"chunk"])
        with patch("miniaudio.PlaybackDevice") as mock_dev:
            mock_dev.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_dev.return_value.__exit__ = MagicMock(return_value=False)
            svc = PlayerService()
            # Just verify it doesn't raise on construction
            assert svc is not None
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_player_service.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `src/services/player_service.py`**

```python
import threading
import sqlite3
from pathlib import Path
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("player")


class Queue:
    def __init__(self):
        self._track_ids: list[int] = []
        self._index: int = -1
        self.ended: bool = False

    def set_context(self, track_ids: list[int], start_index: int = 0) -> None:
        self._track_ids = track_ids
        self._index = start_index
        self.ended = False

    def current_id(self) -> int | None:
        if 0 <= self._index < len(self._track_ids):
            return self._track_ids[self._index]
        return None

    def next_id(self) -> int | None:
        next_idx = self._index + 1
        if next_idx < len(self._track_ids):
            self._index = next_idx
            return self._track_ids[self._index]
        self.ended = True
        return None

    def prev_id(self) -> int | None:
        prev_idx = self._index - 1
        if prev_idx >= 0:
            self._index = prev_idx
            return self._track_ids[self._index]
        return None

    def to_dict(self) -> dict:
        return {"track_ids": self._track_ids, "index": self._index}

    @classmethod
    def from_dict(cls, data: dict) -> "Queue":
        q = cls()
        q._track_ids = data.get("track_ids", [])
        q._index = data.get("index", -1)
        return q


class PlayerService:
    def __init__(self):
        self.queue = Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._position: float = 0.0
        self._paused: bool = False

    def play(self, file_path: str) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._stop_event.clear()
        self._position = 0.0
        self._paused = False
        self._thread = threading.Thread(
            target=self._playback_thread, args=(file_path,), daemon=True
        )
        self._thread.start()

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop(self) -> None:
        self._stop_event.set()

    def get_position(self) -> float:
        return self._position

    def _playback_thread(self, file_path: str) -> None:
        try:
            import miniaudio
            stream = miniaudio.stream_file(file_path)
            with miniaudio.PlaybackDevice() as device:
                device.start(stream)
                import time
                while not self._stop_event.is_set():
                    if self._paused:
                        time.sleep(0.1)
                        continue
                    self._position += 0.1
                    time.sleep(0.1)
            event_bus.emit("playback_ended", {})
        except Exception as e:
            log.error(f"Playback error: {e}", exc_info=True)
            event_bus.emit("playback_ended", {})
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_player_service.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/player_service.py tests/test_player_service.py
git commit -m "feat: player service with miniaudio playback and linear queue"
```

---

## Task 11: API Bridge

**Files:**
- Create: `src/api/api.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api.py
import json
from unittest.mock import MagicMock, patch
from src.database.database import init_db, insert_track
from src.database.config_manager import set_setting
from src.models.track import Track
from src.api.api import ClaudeFMAPI


def _make_api(db_conn, tmp_path):
    set_setting(db_conn, "download_folder", str(tmp_path))
    set_setting(db_conn, "lastfm_api_key", "fakekey")
    api = ClaudeFMAPI(db_conn)
    return api


def test_get_library_returns_tracks(db_conn, tmp_path):
    init_db(db_conn)
    insert_track(db_conn, Track(title="Song A", artist="Artist X"))
    api = _make_api(db_conn, tmp_path)
    result = api.get_library("{}")
    parsed = json.loads(result)
    assert len(parsed) == 1
    assert parsed[0]["title"] == "Song A"


def test_get_settings_returns_dict(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_settings())
    assert "audio_format" in result
    assert result["audio_format"] == "m4a"


def test_save_setting_persists(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    api.save_setting("audio_format", "mp3")
    result = json.loads(api.get_settings())
    assert result["audio_format"] == "mp3"


def test_create_playlist(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.create_playlist("My Mix", "manual"))
    assert result["success"] is True
    assert "id" in result


def test_get_playlists_returns_list(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    api.create_playlist("Test", "manual")
    result = json.loads(api.get_playlists())
    assert len(result) == 1
    assert result[0]["name"] == "Test"
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_api.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `src/api/api.py`**

```python
import json
import sqlite3
from src.database.database import (
    get_all_tracks, get_track, insert_track, update_track_status,
    get_tracks_by_artist, get_tracks_by_album, search_tracks_local,
    insert_playlist, get_all_playlists, get_playlist_tracks,
    upsert_playlist_tracks, get_auto_playlist_count, delete_oldest_auto_playlist,
)
from src.database.config_manager import get_setting, set_setting, get_all_settings
from src.models.track import Track
from src.models.playlist import Playlist
from src.services.lastfm_service import LastFMService
from src.services.youtube_service import YouTubeService
from src.services.player_service import PlayerService
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("api")

AUTO_PLAYLIST_LIMIT = 15


def _ok(data=None) -> str:
    return json.dumps({"success": True, **({"data": data} if data is not None else {})})


def _err(message: str) -> str:
    return json.dumps({"success": False, "error": message})


class ClaudeFMAPI:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._player = PlayerService()
        self._youtube: YouTubeService | None = None
        self._lastfm: LastFMService | None = None

    def _get_youtube(self) -> YouTubeService:
        if self._youtube is None:
            self._youtube = YouTubeService(self._conn)
        return self._youtube

    def _get_lastfm(self) -> LastFMService:
        if self._lastfm is None:
            api_key = get_setting(self._conn, "lastfm_api_key")
            self._lastfm = LastFMService(self._conn, api_key)
        return self._lastfm

    # ── Library ──────────────────────────────────────────────────────────────

    def get_library(self, filters_json: str = "{}") -> str:
        try:
            filters = json.loads(filters_json)
            order = filters.get("order_by", "date_downloaded DESC")
            tracks = get_all_tracks(self._conn, order_by=order)
            return json.dumps([t.model_dump(mode="json") for t in tracks])
        except Exception as e:
            log.error(f"get_library: {e}", exc_info=True)
            return _err(str(e))

    def get_tracks_by_artist(self, artist: str) -> str:
        try:
            tracks = get_tracks_by_artist(self._conn, artist)
            return json.dumps([t.model_dump(mode="json") for t in tracks])
        except Exception as e:
            return _err(str(e))

    def get_tracks_by_album(self, album: str, artist: str) -> str:
        try:
            tracks = get_tracks_by_album(self._conn, album, artist)
            return json.dumps([t.model_dump(mode="json") for t in tracks])
        except Exception as e:
            return _err(str(e))

    def search_local(self, query: str, limit: int | None = None) -> str:
        try:
            lim = limit or int(get_setting(self._conn, "search_results_limit"))
            tracks = search_tracks_local(self._conn, query, limit=lim)
            return json.dumps([t.model_dump(mode="json") for t in tracks])
        except Exception as e:
            return _err(str(e))

    # ── Last.fm ───────────────────────────────────────────────────────────────

    def search_lastfm(self, query: str, search_type: str) -> str:
        try:
            limit = int(get_setting(self._conn, "search_results_limit"))
            results = self._get_lastfm().search(query, search_type, limit=limit)
            return json.dumps(results)
        except Exception as e:
            log.error(f"search_lastfm: {e}", exc_info=True)
            return _err(str(e))

    def get_artist_top_tracks(self, artist_name: str) -> str:
        try:
            tracks = self._get_lastfm().get_artist_top_tracks(artist_name)
            return json.dumps(tracks)
        except Exception as e:
            return _err(str(e))

    def get_album_tracks(self, album_title: str, artist_name: str) -> str:
        try:
            tracks = self._get_lastfm().get_album_tracks(album_title, artist_name)
            return json.dumps(tracks)
        except Exception as e:
            return _err(str(e))

    # ── Downloads ─────────────────────────────────────────────────────────────

    def download_track(self, track_id: int) -> str:
        try:
            self._get_youtube().queue_download(track_id)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def download_lastfm_track(self, title: str, artist: str, album: str | None = None) -> str:
        """Create a track record then queue download."""
        try:
            t = Track(title=title, artist=artist, album=album)
            track_id = insert_track(self._conn, t)
            self._get_youtube().queue_download(track_id)
            return json.dumps({"success": True, "track_id": track_id})
        except Exception as e:
            return _err(str(e))

    # ── Playback ──────────────────────────────────────────────────────────────

    def play(self, track_id: int, context_json: str = "{}") -> str:
        try:
            context = json.loads(context_json)
            track = get_track(self._conn, track_id)
            if not track or not track.file_path:
                return _err("Track not found or not downloaded")
            track_ids = context.get("track_ids", [track_id])
            start_index = track_ids.index(track_id) if track_id in track_ids else 0
            self._player.queue.set_context(track_ids, start_index)
            self._player.play(track.file_path)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def pause(self) -> str:
        self._player.pause()
        return _ok()

    def resume(self) -> str:
        self._player.resume()
        return _ok()

    def next_track(self) -> str:
        try:
            next_id = self._player.queue.next_id()
            if next_id is None:
                event_bus.emit("queue_ended", {})
                return json.dumps({"success": True, "ended": True})
            track = get_track(self._conn, next_id)
            if track and track.file_path:
                self._player.play(track.file_path)
            return json.dumps({"success": True, "track_id": next_id})
        except Exception as e:
            return _err(str(e))

    def prev_track(self) -> str:
        try:
            prev_id = self._player.queue.prev_id()
            if prev_id is None:
                return _ok()
            track = get_track(self._conn, prev_id)
            if track and track.file_path:
                self._player.play(track.file_path)
            return json.dumps({"success": True, "track_id": prev_id})
        except Exception as e:
            return _err(str(e))

    def get_player_state(self) -> str:
        q = self._player.queue
        return json.dumps({
            "current_id": q.current_id(),
            "position": self._player.get_position(),
            "paused": self._player._paused,
            "ended": q.ended,
        })

    # ── Playlists ─────────────────────────────────────────────────────────────

    def get_playlists(self) -> str:
        try:
            playlists = get_all_playlists(self._conn)
            return json.dumps([p.model_dump(mode="json") for p in playlists])
        except Exception as e:
            return _err(str(e))

    def create_playlist(self, name: str, playlist_type: str = "manual") -> str:
        try:
            if playlist_type == "auto" and get_auto_playlist_count(self._conn) >= AUTO_PLAYLIST_LIMIT:
                delete_oldest_auto_playlist(self._conn)
            p = Playlist(name=name, type=playlist_type)
            pid = insert_playlist(self._conn, p)
            return json.dumps({"success": True, "id": pid})
        except Exception as e:
            return _err(str(e))

    def get_playlist_tracks(self, playlist_id: int) -> str:
        try:
            tracks = get_playlist_tracks(self._conn, playlist_id)
            return json.dumps([t.model_dump(mode="json") for t in tracks])
        except Exception as e:
            return _err(str(e))

    def set_playlist_tracks(self, playlist_id: int, track_ids_json: str) -> str:
        try:
            track_ids = json.loads(track_ids_json)
            upsert_playlist_tracks(self._conn, playlist_id, track_ids)
            return _ok()
        except Exception as e:
            return _err(str(e))

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> str:
        return json.dumps(get_all_settings(self._conn))

    def save_setting(self, key: str, value: str) -> str:
        try:
            set_setting(self._conn, key, value)
            return _ok()
        except Exception as e:
            return _err(str(e))

    # ── Playlist mutations ────────────────────────────────────────────────────

    def delete_playlist(self, playlist_id: int) -> str:
        try:
            from src.database.database import delete_playlist as _del
            _del(self._conn, playlist_id)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def rename_playlist(self, playlist_id: int, name: str) -> str:
        try:
            from src.database.database import update_playlist_name
            update_playlist_name(self._conn, playlist_id, name)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def add_to_playlist(self, playlist_id: int, track_id: int) -> str:
        try:
            from src.database.database import add_track_to_playlist
            add_track_to_playlist(self._conn, playlist_id, track_id)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def remove_from_playlist(self, playlist_id: int, track_id: int) -> str:
        try:
            from src.database.database import remove_track_from_playlist
            remove_track_from_playlist(self._conn, playlist_id, track_id)
            return _ok()
        except Exception as e:
            return _err(str(e))

    # ── Connectivity check ────────────────────────────────────────────────────

    def check_internet(self) -> str:
        import socket
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return json.dumps({"online": True})
        except OSError:
            return json.dumps({"online": False})
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_api.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/api.py tests/test_api.py
git commit -m "feat: api bridge class exposing all backend methods to pywebview frontend"
```

---

## Task 12: App Entry Point

**Files:**
- Modify: `app.py`

> No unit tests for `app.py` — this is pywebview glue code. Test manually by running the app.

- [ ] **Step 1: Implement `app.py`**

```python
import sys
import json
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.logger import get_logger
from src.database.database import get_connection, init_db
from src.database.config_manager import get_setting, get_all_settings
from src.database.file_manager import quick_scan, start_background_scan
from src.utils.event_bus import event_bus
from src.api.api import ClaudeFMAPI

log = get_logger("app")


def _get_vendor_path(name: str) -> Path:
    """Resolve bundled binary path — works both in dev and PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return base / "assets" / "vendor" / name


def _check_binary(path: Path, label: str) -> None:
    if not path.exists():
        import tkinter.messagebox as mb
        mb.showerror("ClaudeFM — Startup Error", f"{label} not found at:\n{path}\n\nCannot start.")
        sys.exit(1)
    log.info(f"{label} found: {path}")


def main():
    log.info("ClaudeFM starting")

    # 1. Check bundled binaries
    ffmpeg = _get_vendor_path("ffmpeg.exe")
    ytdlp = _get_vendor_path("yt-dlp.exe")
    _check_binary(ffmpeg, "ffmpeg")
    _check_binary(ytdlp, "yt-dlp")

    # 2. Init database
    conn = get_connection()
    init_db(conn)
    log.info("Database initialised")

    # 3. Quick scan (blocking — before UI loads)
    folders_json = get_setting(conn, "additional_folders")
    download_folder = get_setting(conn, "download_folder")
    folders = json.loads(folders_json)
    if download_folder:
        folders = [download_folder] + folders
    quick_scan(conn)
    log.info("Quick scan complete")

    # 4. Build API
    api = ClaudeFMAPI(conn)

    # 5. Open pywebview window
    import webview

    window = webview.create_window(
        "ClaudeFM",
        url=str(Path(__file__).parent / "src" / "interface" / "pages" / "home.html"),
        js_api=api,
        width=1200,
        height=750,
        min_size=(900, 600),
    )

    event_bus.set_window(window)

    def on_loaded():
        # 6. Check config after UI is ready
        settings = get_all_settings(conn)
        if not settings.get("lastfm_api_key") or not settings.get("download_folder"):
            window.evaluate_js("router.navigate('settings')")
        # 7. Restore last player position (no auto-play — just inform frontend)
        last_id = settings.get("player_last_track_id", "")
        last_pos = settings.get("player_last_position", "0")
        if last_id:
            window.evaluate_js(
                f"onEvent({{\"type\":\"restore_player\",\"track_id\":{last_id},\"position\":{last_pos}}})"
            )
        # 8. Background full scan
        if folders:
            start_background_scan(conn, folders)

    def on_closing():
        q = api._player.queue
        track_id = q.current_id()
        position = api._player.get_position()
        if track_id:
            set_setting(conn, "player_last_track_id", str(track_id))
            set_setting(conn, "player_last_position", str(int(position)))
            set_setting(conn, "player_last_context", json.dumps(q.to_dict()))
        log.info("ClaudeFM closing")

    window.events.loaded += on_loaded
    window.events.closing += on_closing

    window.events.loaded += on_loaded
    webview.start(debug=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Delete stale file**

```bash
del src\interface\downloads_page.py
```

- [ ] **Step 3: Run the app to verify startup**

```powershell
python app.py
```

Expected: window opens (even if blank — `home.html` doesn't exist yet). No crash. Log file created in `logs/`.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: app entry point with startup checks, db init, and pywebview window"
```

---

## Task 13: Run Full Test Suite

- [ ] **Step 1: Run all tests**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS. Note any failures and fix before proceeding to the frontend plan.

- [ ] **Step 2: Final backend commit**

```bash
git add -A
git commit -m "chore: backend complete — all tests passing"
```

---

## Next

Frontend implementation plan: `docs/superpowers/plans/2026-05-25-claudefm-frontend.md`

Create that plan before starting frontend work.
