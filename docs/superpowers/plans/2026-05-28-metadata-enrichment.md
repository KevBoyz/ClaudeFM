# Metadata Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic background enrichment of lyrics and album artwork for downloaded tracks, with cooldown-based retry logic, configurable auto-repeat intervals, manual triggers from Settings, and topbar progress tracking.

**Architecture:** A new `EnrichmentScheduler` service coordinates two independent enrichment threads (lyrics via `LRCLibService`, artwork via `CoverArtService`). The DB gains three new columns (`artwork_status`, `lyrics_fetched_at`, `artwork_fetched_at`) to enable cooldown filtering. `threading.Timer` handles auto-repeat scheduling with settings read at fire time.

**Tech Stack:** Python `threading.Timer` + daemon threads, SQLite `datetime()` arithmetic, existing `event_bus.emit()` for frontend events, `pytest-mock` for service mocks in tests.

---

## File Map

| File | Change |
|---|---|
| `src/models/enums.py` | Add `ArtworkStatus` enum |
| `src/models/track.py` | Add `artwork_status`, `lyrics_fetched_at`, `artwork_fetched_at` fields |
| `src/database/database.py` | Schema migration + 4 new functions + `_row_to_track` update |
| `src/database/config_manager.py` | 4 new default keys |
| `src/services/cover_art_service.py` | Write `artwork_status` + `artwork_fetched_at` to DB; return status string |
| `src/services/lrclib_service.py` | Write `lyrics_fetched_at`; update batch to use new query + emit `enrichment_lyrics_started` |
| `src/services/enrichment_scheduler.py` | **New** — coordinates periodic enrichment for both services |
| `src/api/api.py` | Lazy-init `EnrichmentScheduler`; 2 new API methods; `save_setting` hook |
| `src/interface/scripts/api.js` | 2 new entries |
| `src/interface/scripts/pages/settings.js` | New "Enrichment" section with buttons + toggles + number inputs |
| `src/interface/scripts/topbar.js` | Track lyrics + artwork enrichment activity in badge and panel |
| `tests/test_database.py` | New tests for 4 new DB functions |
| `tests/test_cover_art_service.py` | Tests for `artwork_status` + `artwork_fetched_at` writes |
| `tests/test_lrclib_service.py` | Tests for `lyrics_fetched_at` writes + new batch query usage |
| `tests/test_enrichment_scheduler.py` | **New** — scheduler delegation + artwork batch logic tests |
| `src/services/cover_art_service.py` | Add `CoverArtEmbedder.read_bytes()` + `CoverArtService.get_cover_bytes()` |
| `src/api/api.py` | Add `get_track_artwork()` — reads embedded bytes, returns base64 data URL |
| `src/interface/scripts/components.js` | `trackCard()` marks embedded thumbs; `loadArtwork()` lazy-loads them |
| `src/interface/scripts/pages/*.js` | Call `loadArtwork(container)` after each track list render |

---

## Task 1: DB Foundations

**Files:**
- Modify: `src/models/enums.py`
- Modify: `src/models/track.py`
- Modify: `src/database/database.py`
- Modify: `src/database/config_manager.py`
- Test: `tests/test_database.py`

### Context

`tracks` table needs three new columns. `_row_to_track` must read them. Four new query functions are needed. The test `db_conn` fixture (in `tests/conftest.py`) provides a raw in-memory SQLite connection without calling `init_db` — every test calls `init_db(db_conn)` itself.

- [ ] **Step 1: Write failing tests for the 4 new DB functions**

Add to `tests/test_database.py`. Import the four new functions at the top (they don't exist yet, so the import will fail).

```python
# Add to the existing import block at the top of tests/test_database.py:
from src.database.database import (
    init_db, insert_track, get_track, update_track_status, get_all_tracks,
    update_lyrics_status, get_tracks_without_lyrics,
    get_tracks_by_artist, get_tracks_by_album, get_all_artists, get_all_albums,
    search_tracks_local, delete_track,
    insert_playlist, get_all_playlists, get_auto_playlist_count,
    delete_oldest_auto_playlist, get_playlist_tracks, delete_playlist,
    update_playlist_name, add_track_to_playlist, remove_track_from_playlist,
    update_artwork_status, update_lyrics_fetched_at,
    get_tracks_to_enrich_lyrics, get_tracks_to_enrich_artwork,
)
from datetime import datetime
```

Then add these tests at the end of the file:

```python
# ── update_lyrics_fetched_at ───────────────────────────────────────────────────

def test_update_lyrics_fetched_at_writes_timestamp(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    ts = datetime(2025, 1, 15, 10, 0, 0)
    update_lyrics_fetched_at(db_conn, tid, ts)
    track = get_track(db_conn, tid)
    assert track.lyrics_fetched_at == ts


# ── update_artwork_status ──────────────────────────────────────────────────────

def test_update_artwork_status_writes_status_and_timestamp(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    ts = datetime(2025, 1, 15, 10, 0, 0)
    update_artwork_status(db_conn, tid, "embedded", ts)
    track = get_track(db_conn, tid)
    assert track.artwork_status == "embedded"
    assert track.artwork_fetched_at == ts


# ── get_tracks_to_enrich_lyrics ────────────────────────────────────────────────

def test_get_tracks_to_enrich_lyrics_includes_not_fetched(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed")
    result = get_tracks_to_enrich_lyrics(db_conn, retry_not_found_after_days=7)
    assert any(t.id == tid for t in result)


def test_get_tracks_to_enrich_lyrics_excludes_synchronized(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed")
    update_lyrics_status(db_conn, tid, "synchronized")
    result = get_tracks_to_enrich_lyrics(db_conn, retry_not_found_after_days=7)
    assert not any(t.id == tid for t in result)


def test_get_tracks_to_enrich_lyrics_excludes_not_downloaded(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="A", artist="X"))  # download_status = pending
    result = get_tracks_to_enrich_lyrics(db_conn, retry_not_found_after_days=7)
    assert result == []


def test_get_tracks_to_enrich_lyrics_retries_not_found_after_cooldown(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed")
    update_lyrics_status(db_conn, tid, "not_found")
    db_conn.execute(
        "UPDATE tracks SET lyrics_fetched_at=datetime('now','-8 days') WHERE id=?", (tid,)
    )
    db_conn.commit()
    result = get_tracks_to_enrich_lyrics(db_conn, retry_not_found_after_days=7)
    assert any(t.id == tid for t in result)


def test_get_tracks_to_enrich_lyrics_skips_not_found_within_cooldown(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed")
    update_lyrics_status(db_conn, tid, "not_found")
    db_conn.execute(
        "UPDATE tracks SET lyrics_fetched_at=datetime('now','-3 days') WHERE id=?", (tid,)
    )
    db_conn.commit()
    result = get_tracks_to_enrich_lyrics(db_conn, retry_not_found_after_days=7)
    assert not any(t.id == tid for t in result)


# ── get_tracks_to_enrich_artwork ───────────────────────────────────────────────

def test_get_tracks_to_enrich_artwork_includes_not_fetched(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed")
    result = get_tracks_to_enrich_artwork(db_conn, retry_not_found_after_days=7)
    assert any(t.id == tid for t in result)


def test_get_tracks_to_enrich_artwork_excludes_embedded(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed")
    update_artwork_status(db_conn, tid, "embedded", datetime(2025, 1, 1))
    result = get_tracks_to_enrich_artwork(db_conn, retry_not_found_after_days=7)
    assert not any(t.id == tid for t in result)


def test_get_tracks_to_enrich_artwork_excludes_not_downloaded(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="A", artist="X"))
    result = get_tracks_to_enrich_artwork(db_conn, retry_not_found_after_days=7)
    assert result == []


def test_get_tracks_to_enrich_artwork_retries_not_found_after_cooldown(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed")
    update_artwork_status(db_conn, tid, "not_found", datetime(2025, 1, 1))
    db_conn.execute(
        "UPDATE tracks SET artwork_fetched_at=datetime('now','-8 days') WHERE id=?", (tid,)
    )
    db_conn.commit()
    result = get_tracks_to_enrich_artwork(db_conn, retry_not_found_after_days=7)
    assert any(t.id == tid for t in result)


def test_get_tracks_to_enrich_artwork_skips_not_found_within_cooldown(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed")
    update_artwork_status(db_conn, tid, "not_found", datetime(2025, 1, 1))
    db_conn.execute(
        "UPDATE tracks SET artwork_fetched_at=datetime('now','-3 days') WHERE id=?", (tid,)
    )
    db_conn.commit()
    result = get_tracks_to_enrich_artwork(db_conn, retry_not_found_after_days=7)
    assert not any(t.id == tid for t in result)
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/Scripts/python.exe -m pytest tests/test_database.py -v -k "enrich or artwork_status or lyrics_fetched"
```

Expected: `ImportError` — `update_artwork_status`, `update_lyrics_fetched_at`, `get_tracks_to_enrich_lyrics`, `get_tracks_to_enrich_artwork` not defined.

- [ ] **Step 3: Add `ArtworkStatus` enum**

In `src/models/enums.py`, add after `LyricsStatus`:

```python
class ArtworkStatus(str, Enum):
    NOT_FETCHED = "not_fetched"
    EMBEDDED    = "embedded"
    NOT_FOUND   = "not_found"
```

- [ ] **Step 4: Add 3 new fields to `Track` model**

In `src/models/track.py`, update the imports and add fields:

```python
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field
from src.models.enums import DownloadStatus, FileStatus, LyricsStatus, ArtworkStatus


class Track(BaseModel):
    id: int | None = None
    title: str = Field(min_length=1)
    artist: str = Field(min_length=1)
    album: str | None = None
    duration: int | None = None
    file_path: str | None = None
    audio_format: str | None = None
    youtube_url: str | None = None
    date_downloaded: datetime | None = None
    download_status: DownloadStatus = DownloadStatus.PENDING
    download_error: str | None = None
    file_status: FileStatus = FileStatus.AVAILABLE
    lyrics_status: LyricsStatus = LyricsStatus.NOT_FETCHED
    artwork_status: ArtworkStatus = ArtworkStatus.NOT_FETCHED
    lyrics_fetched_at: datetime | None = None
    artwork_fetched_at: datetime | None = None
```

- [ ] **Step 5: Update `init_db` and `_row_to_track` in `database.py`**

In `src/database/database.py`:

**Update `init_db`** — add the three new columns to the `CREATE TABLE IF NOT EXISTS tracks` statement and add `ALTER TABLE` migration for existing databases.

Replace the `CREATE TABLE IF NOT EXISTS tracks` block (lines 34–48) with:

```python
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
            file_status     TEXT NOT NULL DEFAULT 'available',
            lyrics_status   TEXT NOT NULL DEFAULT 'not_fetched',
            artwork_status   TEXT NOT NULL DEFAULT 'not_fetched',
            lyrics_fetched_at  TEXT,
            artwork_fetched_at TEXT
        );
```

Then, after `conn.executescript(...)` and `conn.commit()`, add the migration block:

```python
    # Migrate existing databases that predate these columns.
    for col_def in [
        "artwork_status    TEXT NOT NULL DEFAULT 'not_fetched'",
        "lyrics_fetched_at  TEXT",
        "artwork_fetched_at TEXT",
    ]:
        try:
            conn.execute(f"ALTER TABLE tracks ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
```

**Update `_row_to_track`** — replace the full function:

```python
def _row_to_track(row: sqlite3.Row) -> Track:
    date_dl = row["date_downloaded"]
    lfa = row["lyrics_fetched_at"]
    afa = row["artwork_fetched_at"]
    return Track(
        id=row["id"],
        title=row["title"],
        artist=row["artist"],
        album=row["album"],
        duration=row["duration"],
        file_path=row["file_path"],
        audio_format=row["audio_format"],
        youtube_url=row["youtube_url"],
        date_downloaded=datetime.fromisoformat(date_dl) if date_dl else None,
        download_status=row["download_status"],
        download_error=row["download_error"],
        file_status=row["file_status"],
        lyrics_status=row["lyrics_status"],
        artwork_status=row["artwork_status"],
        lyrics_fetched_at=datetime.fromisoformat(lfa) if lfa else None,
        artwork_fetched_at=datetime.fromisoformat(afa) if afa else None,
    )
```

- [ ] **Step 6: Add 4 new DB functions to `database.py`**

Add these functions after `update_lyrics_status`:

```python
def update_lyrics_fetched_at(conn: sqlite3.Connection, track_id: int, fetched_at: datetime) -> None:
    conn.execute(
        "UPDATE tracks SET lyrics_fetched_at=? WHERE id=?",
        (fetched_at.isoformat(), track_id),
    )
    conn.commit()


def update_artwork_status(
    conn: sqlite3.Connection, track_id: int, status: str, fetched_at: datetime
) -> None:
    conn.execute(
        "UPDATE tracks SET artwork_status=?, artwork_fetched_at=? WHERE id=?",
        (status, fetched_at.isoformat(), track_id),
    )
    conn.commit()


def get_tracks_to_enrich_lyrics(
    conn: sqlite3.Connection, retry_not_found_after_days: int
) -> list[Track]:
    rows = conn.execute(
        """SELECT * FROM tracks
           WHERE download_status = 'completed'
             AND file_status = 'available'
             AND (
               lyrics_status = 'not_fetched'
               OR (
                 lyrics_status = 'not_found'
                 AND (
                   lyrics_fetched_at IS NULL
                   OR datetime(lyrics_fetched_at) < datetime('now', ? || ' days')
                 )
               )
             )""",
        (f"-{retry_not_found_after_days}",),
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def get_tracks_to_enrich_artwork(
    conn: sqlite3.Connection, retry_not_found_after_days: int
) -> list[Track]:
    rows = conn.execute(
        """SELECT * FROM tracks
           WHERE download_status = 'completed'
             AND file_status = 'available'
             AND (
               artwork_status = 'not_fetched'
               OR (
                 artwork_status = 'not_found'
                 AND (
                   artwork_fetched_at IS NULL
                   OR datetime(artwork_fetched_at) < datetime('now', ? || ' days')
                 )
               )
             )""",
        (f"-{retry_not_found_after_days}",),
    ).fetchall()
    return [_row_to_track(r) for r in rows]
```

- [ ] **Step 7: Add 4 new defaults to `config_manager.py`**

In `src/database/config_manager.py`, add to the `DEFAULTS` dict:

```python
    "enrich_repeat_lyrics":        "false",
    "enrich_repeat_artwork":       "false",
    "enrich_interval_days":        "1",
    "enrich_retry_not_found_days": "7",
```

- [ ] **Step 8: Run tests**

```
.venv/Scripts/python.exe -m pytest tests/test_database.py -v
```

Expected: all tests pass (including the 12 new ones and all 30 existing ones).

- [ ] **Step 9: Commit**

```bash
git add src/models/enums.py src/models/track.py src/database/database.py src/database/config_manager.py tests/test_database.py
git commit -m "feat(db): add artwork_status, lyrics_fetched_at, artwork_fetched_at columns and enrichment query functions"
```

---

## Task 2: CoverArtService Status Writes

**Files:**
- Modify: `src/services/cover_art_service.py`
- Modify: `tests/test_cover_art_service.py`

### Context

`CoverArtService.fetch_and_embed()` currently returns `bool` and writes nothing to the DB. It needs to write `artwork_status` and `artwork_fetched_at` on every exit path, and return the `ArtworkStatus` string written.

`fetch_and_embed_async()` signature stays `-> None` (ignores the return value).

Test file already exists at `tests/test_cover_art_service.py`. Add new tests at the bottom.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cover_art_service.py`:

```python
# Add to imports at top of the file:
from datetime import datetime
from unittest.mock import patch, MagicMock
from src.database.database import init_db, insert_track, get_track
from src.database.config_manager import DEFAULTS


def test_fetch_and_embed_writes_embedded_status(db_conn, tmp_path):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="Song", artist="Artist", album="Album"))

    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = "https://example.com/cover.jpg"

    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.return_value = b"JPEG_DATA"
    svc._embedder = MagicMock()

    result = svc.fetch_and_embed(tid)

    track = get_track(db_conn, tid)
    assert result == "embedded"
    assert track.artwork_status == "embedded"
    assert track.artwork_fetched_at is not None


def test_fetch_and_embed_writes_not_found_when_no_url(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="Song", artist="Artist", album="Album"))

    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = None

    svc = CoverArtService(db_conn, mock_lastfm)
    result = svc.fetch_and_embed(tid)

    track = get_track(db_conn, tid)
    assert result == "not_found"
    assert track.artwork_status == "not_found"
    assert track.artwork_fetched_at is not None


def test_fetch_and_embed_writes_not_found_on_download_error(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="Song", artist="Artist", album="Album"))

    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = "https://example.com/cover.jpg"

    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.side_effect = OSError("network error")

    result = svc.fetch_and_embed(tid)

    track = get_track(db_conn, tid)
    assert result == "not_found"
    assert track.artwork_status == "not_found"
    assert track.artwork_fetched_at is not None
```

Note: you'll need to check what `Track` and `CoverArtService` imports look like in the existing test file and add to the existing imports, not duplicate them.

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/Scripts/python.exe -m pytest tests/test_cover_art_service.py::test_fetch_and_embed_writes_embedded_status tests/test_cover_art_service.py::test_fetch_and_embed_writes_not_found_when_no_url tests/test_cover_art_service.py::test_fetch_and_embed_writes_not_found_on_download_error -v
```

Expected: FAIL — `fetch_and_embed` returns `bool`, not `"embedded"`.

- [ ] **Step 3: Update `CoverArtService.fetch_and_embed()` in `cover_art_service.py`**

Replace the full function. New imports needed: `datetime`, `update_artwork_status`, `ArtworkStatus`.

```python
import sqlite3
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, APIC, ID3NoHeaderError

from src.database.database import get_track, update_artwork_status
from src.models.enums import ArtworkStatus
from src.utils.logger import get_logger

log = get_logger("cover_art")


class CoverArtEmbedder:
    """Write cover art image bytes into audio file tags (M4A or MP3)."""

    def embed(self, file_path: str, image_data: bytes) -> None:
        ext = Path(file_path).suffix.lower()
        if ext == '.m4a':
            audio = MP4(file_path)
            if audio.tags is None:
                audio.add_tags()
            audio.tags['covr'] = [MP4Cover(image_data, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
        elif ext == '.mp3':
            try:
                audio = ID3(file_path)
            except ID3NoHeaderError:
                audio = ID3()
            audio.add(APIC(mime='image/jpeg', type=3, desc='Cover', data=image_data))
            audio.save(file_path)
        else:
            raise ValueError(f"Unsupported format: {ext}")


class CoverArtFetcher:
    """Download raw image bytes from a URL."""

    def fetch_bytes(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "ClaudeFM/1.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        try:
            return resp.read()
        finally:
            resp.close()


class CoverArtService:
    """Fetch a cover image URL from Last.fm, download the bytes, and embed into the audio file."""

    def __init__(self, conn: sqlite3.Connection, lastfm_service) -> None:
        self._conn = conn
        self._lastfm = lastfm_service
        self._fetcher = CoverArtFetcher()
        self._embedder = CoverArtEmbedder()

    def fetch_and_embed(self, track_id: int) -> str:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return ArtworkStatus.NOT_FOUND

        url = self._lastfm.get_cover_image_url(track.artist, track.album)
        if not url:
            log.debug(f"No cover art URL for track {track_id} ({track.artist!r}/{track.album!r})")
            update_artwork_status(self._conn, track_id, ArtworkStatus.NOT_FOUND, datetime.now())
            return ArtworkStatus.NOT_FOUND

        try:
            image_data = self._fetcher.fetch_bytes(url)
        except Exception as e:
            log.warning(f"Failed to download cover art for track {track_id}: {e}")
            update_artwork_status(self._conn, track_id, ArtworkStatus.NOT_FOUND, datetime.now())
            return ArtworkStatus.NOT_FOUND

        try:
            self._embedder.embed(track.file_path, image_data)
        except Exception as e:
            log.warning(f"Failed to embed cover art for track {track_id}: {e}")
            update_artwork_status(self._conn, track_id, ArtworkStatus.NOT_FOUND, datetime.now())
            return ArtworkStatus.NOT_FOUND

        update_artwork_status(self._conn, track_id, ArtworkStatus.EMBEDDED, datetime.now())
        return ArtworkStatus.EMBEDDED

    def fetch_and_embed_async(self, track_id: int) -> None:
        threading.Thread(target=self.fetch_and_embed, args=(track_id,), daemon=True).start()
```

- [ ] **Step 4: Run all cover art tests**

```
.venv/Scripts/python.exe -m pytest tests/test_cover_art_service.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/services/cover_art_service.py tests/test_cover_art_service.py
git commit -m "feat(cover-art): write artwork_status and artwork_fetched_at to DB after each attempt"
```

---

## Task 3: LRCLibService Timestamps and Enrichment Query

**Files:**
- Modify: `src/services/lrclib_service.py`
- Modify: `tests/test_lrclib_service.py`

### Context

`LRCLibService.fetch_and_embed()` must write `lyrics_fetched_at = datetime.now()` on every exit path that currently writes `lyrics_status`. `fetch_missing_lyrics()` gets a `retry_not_found_after_days: int = 7` parameter and uses `get_tracks_to_enrich_lyrics` instead of `get_tracks_without_lyrics`. `_run_batch()` emits `enrichment_lyrics_started` before the loop.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_lrclib_service.py` at the bottom:

```python
# Add to imports at top if not already present:
from datetime import datetime
from src.database.database import init_db, insert_track, get_track, update_track_status
from src.models.enums import LyricsStatus


def test_fetch_and_embed_writes_lyrics_fetched_at_on_not_found(db_conn, mocker):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed",
                        file_path="/fake/a.m4a", file_status="available")

    svc = LRCLibService(db_conn)
    svc._fetcher = mocker.Mock()
    svc._fetcher.get.return_value = None
    svc._fetcher.search.return_value = None

    svc.fetch_and_embed(tid)

    track = get_track(db_conn, tid)
    assert track.lyrics_fetched_at is not None


def test_fetch_and_embed_writes_lyrics_fetched_at_on_found(db_conn, mocker):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X", duration=200))
    update_track_status(db_conn, tid, download_status="completed",
                        file_path="/fake/a.m4a", file_status="available")

    result_mock = mocker.Mock()
    result_mock.instrumental = False
    result_mock.syncedLyrics = None
    result_mock.plainLyrics = "Some lyrics"

    svc = LRCLibService(db_conn)
    svc._fetcher = mocker.Mock()
    svc._fetcher.get.return_value = result_mock
    svc._embedder = mocker.Mock()

    svc.fetch_and_embed(tid)

    track = get_track(db_conn, tid)
    assert track.lyrics_fetched_at is not None


def test_fetch_missing_lyrics_uses_retry_not_found_query(db_conn, mocker):
    init_db(db_conn)

    mock_query = mocker.patch(
        "src.services.lrclib_service.get_tracks_to_enrich_lyrics",
        return_value=[],
    )

    svc = LRCLibService(db_conn)
    # Call _run_batch directly to avoid threading in tests
    svc._run_batch(retry_not_found_after_days=14)

    mock_query.assert_called_once_with(db_conn, retry_not_found_after_days=14)


def test_run_batch_emits_enrichment_lyrics_started(db_conn, mocker):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed",
                        file_path="/fake/a.m4a", file_status="available")

    emitted = []
    mocker.patch(
        "src.services.lrclib_service.event_bus.emit",
        side_effect=lambda t, p: emitted.append((t, p)),
    )

    svc = LRCLibService(db_conn)
    svc._fetcher = mocker.Mock()
    svc._fetcher.get.return_value = None
    svc._fetcher.search.return_value = None
    svc._embedder = mocker.Mock()

    svc._run_batch(retry_not_found_after_days=7)

    types = [e[0] for e in emitted]
    assert "enrichment_lyrics_started" in types
    started = next(e[1] for e in emitted if e[0] == "enrichment_lyrics_started")
    assert started["total"] == 1
```

- [ ] **Step 2: Run failing tests**

```
.venv/Scripts/python.exe -m pytest tests/test_lrclib_service.py -k "lyrics_fetched_at or retry_not_found or enrichment_lyrics" -v
```

Expected: FAIL.

- [ ] **Step 3: Update `lrclib_service.py`**

Full replacement of `src/services/lrclib_service.py`:

```python
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from lrcup import LRCLib, AudioFile
from lrcup.audio import UnsupportedSuffix
from src.database.database import (
    get_track, update_lyrics_status, update_lyrics_fetched_at,
    get_tracks_to_enrich_lyrics,
)
from src.models.enums import LyricsStatus
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("lrclib")


class LRCLibFetcher:
    """Thin wrapper around the lrcup LRCLib client, isolated for testability."""

    def __init__(self):
        self._client = LRCLib()

    def get(self, title: str, artist: str, album: str, duration: int):
        """Fetch lyrics by exact track metadata (preferred — duration-matched result)."""
        return self._client.get(track=title, artist=artist, album=album, duration=duration)

    def search(self, title: str, artist: str):
        """Fuzzy-search for lyrics and return the first result, or None if not found."""
        results = self._client.search(track=title, artist=artist)
        return results[0] if results else None


class LyricsEmbedder:
    """Read/write lyrics tags in audio files via lrcup's AudioFile abstraction."""

    def embed(self, file_path: str, state: str, lyrics: str) -> None:
        """Write lyrics to the file's tags (``state`` is ``'synced'`` or ``'unsynced'``)."""
        AudioFile(Path(file_path)).set_lyrics(state=state, lyrics=lyrics)

    def read(self, file_path: str) -> str | None:
        """Read embedded lyrics text from the file's tags, or None if absent."""
        return AudioFile(Path(file_path)).get_lyrics()


class LRCLibService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._running = threading.Event()
        self._fetcher = LRCLibFetcher()
        self._embedder = LyricsEmbedder()

    def fetch_and_embed(self, track_id: int) -> str | None:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return None

        now = datetime.now()
        result = None

        if track.duration is not None:
            try:
                result = self._fetcher.get(
                    track.title, track.artist, track.album or "", track.duration
                )
            except Exception:
                log.error(f"LRCLib.get failed for track {track_id}", exc_info=True)
                update_lyrics_status(self._conn, track_id, LyricsStatus.NOT_FETCHED)
                update_lyrics_fetched_at(self._conn, track_id, now)
                return LyricsStatus.NOT_FETCHED

        if result is None:
            try:
                result = self._fetcher.search(track.title, track.artist)
            except Exception:
                log.error(f"LRCLib.search failed for track {track_id}", exc_info=True)
                update_lyrics_status(self._conn, track_id, LyricsStatus.NOT_FETCHED)
                update_lyrics_fetched_at(self._conn, track_id, now)
                return LyricsStatus.NOT_FETCHED

        if result is None:
            update_lyrics_status(self._conn, track_id, LyricsStatus.NOT_FOUND)
            update_lyrics_fetched_at(self._conn, track_id, now)
            return LyricsStatus.NOT_FOUND

        if result.instrumental:
            update_lyrics_status(self._conn, track_id, LyricsStatus.INSTRUMENTAL)
            update_lyrics_fetched_at(self._conn, track_id, now)
            return LyricsStatus.INSTRUMENTAL

        if result.syncedLyrics is not None:
            lyrics, state, status = result.syncedLyrics, "synced", LyricsStatus.SYNCHRONIZED
        elif result.plainLyrics is not None:
            lyrics, state, status = result.plainLyrics, "unsynced", LyricsStatus.PLAIN_TEXT
        else:
            update_lyrics_status(self._conn, track_id, LyricsStatus.NOT_FOUND)
            update_lyrics_fetched_at(self._conn, track_id, now)
            return LyricsStatus.NOT_FOUND

        try:
            self._embedder.embed(track.file_path, state, lyrics)
        except UnsupportedSuffix:
            log.error(f"Unsupported format for track {track_id}: {track.file_path}")
            update_lyrics_status(self._conn, track_id, LyricsStatus.NOT_SUPPORTED)
            update_lyrics_fetched_at(self._conn, track_id, now)
            return LyricsStatus.NOT_SUPPORTED

        update_lyrics_status(self._conn, track_id, status)
        update_lyrics_fetched_at(self._conn, track_id, now)
        return status

    def fetch_and_embed_async(self, track_id: int) -> None:
        """Run ``fetch_and_embed`` in a daemon thread (fire-and-forget, used post-download)."""
        threading.Thread(target=self.fetch_and_embed, args=(track_id,), daemon=True).start()

    def fetch_missing_lyrics(self, retry_not_found_after_days: int = 7) -> None:
        """Start a batch lyrics fetch, if not already running."""
        if not self._running.is_set():
            self._running.set()
            threading.Thread(
                target=self._run_batch,
                args=(retry_not_found_after_days,),
                daemon=True,
            ).start()

    def _run_batch(self, retry_not_found_after_days: int = 7) -> None:
        tracks = get_tracks_to_enrich_lyrics(
            self._conn, retry_not_found_after_days=retry_not_found_after_days
        )
        event_bus.emit("enrichment_lyrics_started", {"total": len(tracks)})
        counters = {
            "synchronized": 0, "plain_text": 0, "instrumental": 0,
            "not_found": 0, "not_supported": 0, "errors": 0,
        }
        for track in tracks:
            status = LyricsStatus.NOT_FETCHED
            try:
                status = self.fetch_and_embed(track.id)
                if status == LyricsStatus.NOT_FETCHED:
                    counters["errors"] += 1
                elif status in counters:
                    counters[status] += 1
            except Exception:
                log.error(f"Unexpected error processing track {track.id}", exc_info=True)
                counters["errors"] += 1
            event_bus.emit("lyrics_progress", {"track_id": track.id, "status": status})
        self._running.clear()
        event_bus.emit("lyrics_fetch_complete", counters)

    def get_lyrics(self, track_id: int) -> dict | None:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return None
        try:
            text = self._embedder.read(track.file_path)
            return {"lyrics": text, "lyrics_status": track.lyrics_status}
        except Exception:
            log.error(f"get_lyrics failed for track {track_id}", exc_info=True)
            return None
```

- [ ] **Step 4: Run all lrclib tests**

```
.venv/Scripts/python.exe -m pytest tests/test_lrclib_service.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/services/lrclib_service.py tests/test_lrclib_service.py
git commit -m "feat(lrclib): write lyrics_fetched_at timestamp, use enrichment query for batch, emit enrichment_lyrics_started"
```

---

## Task 4: EnrichmentScheduler

**Files:**
- Create: `src/services/enrichment_scheduler.py`
- Create: `tests/test_enrichment_scheduler.py`

### Context

`EnrichmentScheduler` coordinates periodic enrichment for both lyrics and artwork. It owns a `threading.Timer` per thread. `run_lyrics()` delegates directly to `lrclib_service.fetch_missing_lyrics()` (which is already non-blocking). `run_artwork()` starts a daemon thread that calls `cover_art_service.fetch_and_embed()` per track sequentially. `apply_settings()` cancels and reschedules both timers based on current DB settings.

- [ ] **Step 1: Write failing tests**

Create `tests/test_enrichment_scheduler.py`:

```python
import sqlite3
import threading
import pytest
from unittest.mock import MagicMock, patch
from src.database.database import init_db, insert_track, update_track_status
from src.database.config_manager import set_setting
from src.models.track import Track
from src.models.enums import ArtworkStatus
from src.services.enrichment_scheduler import EnrichmentScheduler


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def svc(db_conn):
    init_db(db_conn)
    lrclib = MagicMock()
    cover_art = MagicMock()
    cover_art.fetch_and_embed.return_value = ArtworkStatus.EMBEDDED
    return EnrichmentScheduler(db_conn, lrclib, cover_art), lrclib, cover_art, db_conn


def test_run_lyrics_calls_fetch_missing_with_retry_days(svc):
    scheduler, lrclib, _, db_conn = svc
    set_setting(db_conn, "enrich_retry_not_found_days", "14")
    scheduler.run_lyrics()
    lrclib.fetch_missing_lyrics.assert_called_once_with(retry_not_found_after_days=14)


def test_run_lyrics_uses_default_retry_days(svc):
    scheduler, lrclib, _, _ = svc
    scheduler.run_lyrics()
    lrclib.fetch_missing_lyrics.assert_called_once_with(retry_not_found_after_days=7)


def test_run_artwork_processes_pending_tracks(svc):
    scheduler, _, cover_art, db_conn = svc
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed", file_status="available")

    scheduler._run_artwork_batch()

    cover_art.fetch_and_embed.assert_called_once_with(tid)


def test_run_artwork_skips_if_already_running(svc):
    scheduler, _, cover_art, db_conn = svc
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed", file_status="available")

    scheduler._artwork_running.set()
    scheduler.run_artwork()

    cover_art.fetch_and_embed.assert_not_called()
    scheduler._artwork_running.clear()


def test_apply_settings_schedules_lyrics_timer_when_enabled(svc):
    scheduler, _, _, db_conn = svc
    set_setting(db_conn, "enrich_repeat_lyrics", "true")
    set_setting(db_conn, "enrich_interval_days", "1")

    with patch("src.services.enrichment_scheduler.threading.Timer") as mock_timer_cls:
        mock_timer_cls.return_value = MagicMock()
        scheduler.apply_settings()
        assert mock_timer_cls.called


def test_apply_settings_no_timer_when_disabled(svc):
    scheduler, _, _, db_conn = svc
    set_setting(db_conn, "enrich_repeat_lyrics", "false")
    set_setting(db_conn, "enrich_repeat_artwork", "false")

    with patch("src.services.enrichment_scheduler.threading.Timer") as mock_timer_cls:
        scheduler.apply_settings()
        mock_timer_cls.assert_not_called()


def test_shutdown_cancels_active_timers(svc):
    scheduler, _, _, _ = svc
    mock_timer = MagicMock()
    scheduler._lyrics_timer = mock_timer
    scheduler._artwork_timer = mock_timer

    scheduler.shutdown()

    assert mock_timer.cancel.call_count == 2


def test_run_artwork_batch_emits_started_and_complete(svc, mocker):
    scheduler, _, _, db_conn = svc
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed", file_status="available")

    emitted = []
    mocker.patch(
        "src.services.enrichment_scheduler.event_bus.emit",
        side_effect=lambda t, p: emitted.append((t, p)),
    )

    scheduler._run_artwork_batch()

    types = [e[0] for e in emitted]
    assert "enrichment_artwork_started" in types
    assert "enrichment_artwork_progress" in types
    assert "enrichment_artwork_complete" in types

    started = next(e[1] for e in emitted if e[0] == "enrichment_artwork_started")
    assert started["total"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/Scripts/python.exe -m pytest tests/test_enrichment_scheduler.py -v
```

Expected: `ModuleNotFoundError` — `enrichment_scheduler` not found.

- [ ] **Step 3: Implement `EnrichmentScheduler`**

Create `src/services/enrichment_scheduler.py`:

```python
import sqlite3
import threading

from src.database.database import get_tracks_to_enrich_artwork, update_artwork_status
from src.database.config_manager import get_setting
from src.models.enums import ArtworkStatus
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("enrichment")


class EnrichmentScheduler:
    def __init__(self, conn: sqlite3.Connection, lrclib_service, cover_art_service) -> None:
        self._conn = conn
        self._lrclib = lrclib_service
        self._cover_art = cover_art_service
        self._lyrics_timer: threading.Timer | None = None
        self._artwork_timer: threading.Timer | None = None
        self._artwork_running = threading.Event()

    def run_lyrics(self) -> None:
        days = int(get_setting(self._conn, "enrich_retry_not_found_days") or "7")
        self._lrclib.fetch_missing_lyrics(retry_not_found_after_days=days)

    def run_artwork(self) -> None:
        if not self._artwork_running.is_set():
            self._artwork_running.set()
            threading.Thread(target=self._run_artwork_batch, daemon=True).start()

    def _run_artwork_batch(self) -> None:
        days = int(get_setting(self._conn, "enrich_retry_not_found_days") or "7")
        tracks = get_tracks_to_enrich_artwork(self._conn, retry_not_found_after_days=days)
        event_bus.emit("enrichment_artwork_started", {"total": len(tracks)})
        counters = {"embedded": 0, "not_found": 0, "errors": 0}
        for track in tracks:
            try:
                status = self._cover_art.fetch_and_embed(track.id)
                if status == ArtworkStatus.EMBEDDED:
                    counters["embedded"] += 1
                else:
                    counters["not_found"] += 1
            except Exception:
                log.error(f"Artwork enrichment failed for track {track.id}", exc_info=True)
                counters["errors"] += 1
            event_bus.emit("enrichment_artwork_progress", {"track_id": track.id})
        self._artwork_running.clear()
        event_bus.emit("enrichment_artwork_complete", counters)
        self._reschedule_artwork()

    def apply_settings(self) -> None:
        if self._lyrics_timer:
            self._lyrics_timer.cancel()
            self._lyrics_timer = None
        if self._artwork_timer:
            self._artwork_timer.cancel()
            self._artwork_timer = None
        if get_setting(self._conn, "enrich_repeat_lyrics") == "true":
            self._schedule_lyrics()
        if get_setting(self._conn, "enrich_repeat_artwork") == "true":
            self._schedule_artwork()

    def shutdown(self) -> None:
        if self._lyrics_timer:
            self._lyrics_timer.cancel()
        if self._artwork_timer:
            self._artwork_timer.cancel()

    def _interval_secs(self) -> float:
        return float(get_setting(self._conn, "enrich_interval_days") or "1") * 86400

    def _schedule_lyrics(self) -> None:
        self._lyrics_timer = threading.Timer(self._interval_secs(), self._on_lyrics_timer)
        self._lyrics_timer.daemon = True
        self._lyrics_timer.start()

    def _on_lyrics_timer(self) -> None:
        self.run_lyrics()
        if get_setting(self._conn, "enrich_repeat_lyrics") == "true":
            self._schedule_lyrics()

    def _schedule_artwork(self) -> None:
        self._artwork_timer = threading.Timer(self._interval_secs(), self.run_artwork)
        self._artwork_timer.daemon = True
        self._artwork_timer.start()

    def _reschedule_artwork(self) -> None:
        if get_setting(self._conn, "enrich_repeat_artwork") == "true":
            self._schedule_artwork()
```

- [ ] **Step 4: Run all enrichment scheduler tests**

```
.venv/Scripts/python.exe -m pytest tests/test_enrichment_scheduler.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/services/enrichment_scheduler.py tests/test_enrichment_scheduler.py
git commit -m "feat: add EnrichmentScheduler for periodic lyrics and artwork batch enrichment"
```

---

## Task 5: API Bridge

**Files:**
- Modify: `src/api/api.py`
- Modify: `src/interface/scripts/api.js`

### Context

Add lazy-init `_get_enrichment()`, two new API methods, and hook `save_setting()` to call `apply_settings()` after any setting is persisted. No new tests needed — the scheduler is already tested; `api.py` integration tests are not in the existing suite.

- [ ] **Step 1: Update `api.py`**

Add import at the top:
```python
from src.services.enrichment_scheduler import EnrichmentScheduler
```

Add `_enrichment` to `__init__`:
```python
self._enrichment: EnrichmentScheduler | None = None
```

Add lazy-init method after `_get_cover_art`:
```python
def _get_enrichment(self) -> EnrichmentScheduler:
    if self._enrichment is None:
        self._enrichment = EnrichmentScheduler(
            self._conn, self._get_lrclib(), self._get_cover_art()
        )
    return self._enrichment
```

Add two new API methods in the Lyrics section:
```python
def run_enrichment_lyrics(self) -> str:
    try:
        self._get_enrichment().run_lyrics()
        return _ok()
    except Exception as e:
        log.error(f"run_enrichment_lyrics: {e}", exc_info=True)
        return _err(str(e))

def run_enrichment_artwork(self) -> str:
    try:
        self._get_enrichment().run_artwork()
        return _ok()
    except Exception as e:
        log.error(f"run_enrichment_artwork: {e}", exc_info=True)
        return _err(str(e))
```

Update `save_setting()` to call `apply_settings()` after persisting:
```python
def save_setting(self, key: str, value: str) -> str:
    try:
        set_setting(self._conn, key, value)
        self._get_enrichment().apply_settings()
        return _ok()
    except Exception as e:
        return _err(str(e))
```

- [ ] **Step 2: Update `api.js`**

Add to the Lyrics section in `src/interface/scripts/api.js`:
```javascript
    // Enrichment
    run_enrichment_lyrics:  () => _call('run_enrichment_lyrics'),
    run_enrichment_artwork: () => _call('run_enrichment_artwork'),
```

- [ ] **Step 3: Run full test suite to check for regressions**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/api/api.py src/interface/scripts/api.js
git commit -m "feat(api): add run_enrichment_lyrics, run_enrichment_artwork; hook save_setting to apply_settings"
```

---

## Task 6: Settings UI

**Files:**
- Modify: `src/interface/scripts/pages/settings.js`

### Context

Add an "Enrichment" section below the existing "Library" section. Six new controls: 2 "Run now" buttons, 2 toggles, 2 number inputs. The number inputs save to `enrich_interval_days` and `enrich_retry_not_found_days`. All 4 persistent fields go into the existing `Promise.all` save block.

- [ ] **Step 1: Add "Enrichment" section HTML to `settings.js`**

In the `body.innerHTML` template, add after the closing `</div>` of the Library section (after the `set-autoart` row closing `</div></div></div>`):

```javascript
      <div class="settings-section">
        <h2>Enrichment</h2>
        <div class="settings-row">
          <span class="settings-label">Run lyrics search now</span>
          <div class="settings-field">
            <button class="btn btn-ghost" id="set-enrich-run-lyrics">Run now</button>
          </div>
        </div>
        <div class="settings-row">
          <span class="settings-label">Run artwork search now</span>
          <div class="settings-field">
            <button class="btn btn-ghost" id="set-enrich-run-artwork">Run now</button>
          </div>
        </div>
        <div class="settings-row">
          <span class="settings-label">Auto-repeat lyrics search</span>
          <div class="settings-field">
            <label class="settings-toggle">
              <input type="checkbox" id="set-enrich-repeat-lyrics" ${_settings.enrich_repeat_lyrics==='true'?'checked':''}>
              <span class="settings-toggle-track"></span>
            </label>
          </div>
        </div>
        <div class="settings-row">
          <span class="settings-label">Auto-repeat artwork search</span>
          <div class="settings-field">
            <label class="settings-toggle">
              <input type="checkbox" id="set-enrich-repeat-artwork" ${_settings.enrich_repeat_artwork==='true'?'checked':''}>
              <span class="settings-toggle-track"></span>
            </label>
          </div>
        </div>
        <div class="settings-row">
          <span class="settings-label">Repeat interval (days)</span>
          <div class="settings-field">
            <input type="number" id="set-enrich-interval" min="1" max="365"
              value="${parseInt(_settings.enrich_interval_days||'1')}" style="width:80px">
          </div>
        </div>
        <div class="settings-row">
          <span class="settings-label">Skip not-found tracks for (days)</span>
          <div class="settings-field">
            <input type="number" id="set-enrich-retry-days" min="1" max="365"
              value="${parseInt(_settings.enrich_retry_not_found_days||'7')}" style="width:80px">
          </div>
        </div>
      </div>
```

- [ ] **Step 2: Wire "Run now" button event listeners**

Add these two listeners after the `set-test` listener setup (around line 108):

```javascript
    document.getElementById('set-enrich-run-lyrics').addEventListener('click', async () => {
      const btn = document.getElementById('set-enrich-run-lyrics');
      btn.disabled = true;
      try {
        await api.run_enrichment_lyrics();
      } catch (e) {
        toast.show('Failed to start lyrics search: ' + e.message, 'error', 4000);
      }
      btn.disabled = false;
    });

    document.getElementById('set-enrich-run-artwork').addEventListener('click', async () => {
      const btn = document.getElementById('set-enrich-run-artwork');
      btn.disabled = true;
      try {
        await api.run_enrichment_artwork();
      } catch (e) {
        toast.show('Failed to start artwork search: ' + e.message, 'error', 4000);
      }
      btn.disabled = false;
    });
```

- [ ] **Step 3: Add 4 new fields to the `Promise.all` save block**

Inside the `Promise.all([...])` array in the `set-save` click handler, add:

```javascript
          api.save_setting('enrich_repeat_lyrics',        document.getElementById('set-enrich-repeat-lyrics').checked ? 'true' : 'false'),
          api.save_setting('enrich_repeat_artwork',       document.getElementById('set-enrich-repeat-artwork').checked ? 'true' : 'false'),
          api.save_setting('enrich_interval_days',        document.getElementById('set-enrich-interval').value),
          api.save_setting('enrich_retry_not_found_days', document.getElementById('set-enrich-retry-days').value),
```

- [ ] **Step 4: Run full test suite**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass (no Python changes in this task).

- [ ] **Step 5: Commit**

```bash
git add src/interface/scripts/pages/settings.js
git commit -m "feat(ui): add Enrichment section to Settings with run-now buttons, toggles, and interval inputs"
```

---

## Task 7: Topbar Activity Tracking

**Files:**
- Modify: `src/interface/scripts/topbar.js`

### Context

The topbar already tracks `_lyricsFetching` (per-track single fetches) and `_lyricsHistory`. We need two new state objects for batch enrichment runs. The badge count, `_renderPanel()`, and event listeners all need extending. No Python changes.

The frontend receives backend events via `api.on(type, handler)` — see how `lyrics.js` uses `api.on('lyrics_progress', ...)`. Topbar listens to `claudefm:event` CustomEvents directly (same mechanism, different path).

- [ ] **Step 1: Add enrichment state objects**

At the top of the `topbar.js` IIFE, after the `_lyricsHistory` declaration:

```javascript
  const _lyricsEnriching  = { active: false, total: 0, done: 0 };
  const _artworkEnriching = { active: false, total: 0, done: 0 };
```

- [ ] **Step 2: Update `_updateBadge` to include enrichment runs**

Replace the badge count line:
```javascript
    const total = downloads.activeCount() + Object.keys(_lyricsFetching).length;
```
with:
```javascript
    const total = downloads.activeCount()
      + Object.keys(_lyricsFetching).length
      + (_lyricsEnriching.active  ? 1 : 0)
      + (_artworkEnriching.active ? 1 : 0);
```

- [ ] **Step 3: Update `_renderPanel` to show enrichment rows**

Inside `_renderPanel()`, after the `lyricsActiveRows` block, add:

```javascript
    const lyricsEnrichRow = _lyricsEnriching.active
      ? `<div class="download-row">
           <div class="download-row-info">
             <div class="download-row-title">Enriching lyrics</div>
             <div class="download-row-sub">${_lyricsEnriching.done}/${_lyricsEnriching.total} tracks</div>
           </div>
           <span style="font-size:.8rem;color:var(--color-text_secondary)">🎵 Running…</span>
         </div>`
      : '';

    const artworkEnrichRow = _artworkEnriching.active
      ? `<div class="download-row">
           <div class="download-row-info">
             <div class="download-row-title">Enriching artwork</div>
             <div class="download-row-sub">${_artworkEnriching.done}/${_artworkEnriching.total} tracks</div>
           </div>
           <span style="font-size:.8rem;color:var(--color-text_secondary)">🖼 Running…</span>
         </div>`
      : '';
```

Update the `hasActivity` check and `panel.innerHTML` to include the new rows.

Replace:
```javascript
    const hasActivity = activeRows || histRows || lyricsActiveRows || lyricsHistRows;
    panel.innerHTML = `
      ${activeRows      ? `<div class="download-panel-section">Downloading</div>${activeRows}` : ''}
      ${lyricsActiveRows? `<div class="download-panel-section">Fetching lyrics</div>${lyricsActiveRows}` : ''}
      ${histRows        ? `<div class="download-panel-section">Downloads</div>${histRows}` : ''}
      ${lyricsHistRows  ? `<div class="download-panel-section">Lyrics</div>${lyricsHistRows}` : ''}
      ${!hasActivity    ? '<div style="padding:16px;color:var(--color-text_secondary);font-size:.875rem">No activity</div>' : ''}`;
```

with:
```javascript
    const hasActivity = activeRows || histRows || lyricsActiveRows || lyricsHistRows || lyricsEnrichRow || artworkEnrichRow;
    panel.innerHTML = `
      ${activeRows       ? `<div class="download-panel-section">Downloading</div>${activeRows}` : ''}
      ${lyricsActiveRows ? `<div class="download-panel-section">Fetching lyrics</div>${lyricsActiveRows}` : ''}
      ${lyricsEnrichRow  ? `<div class="download-panel-section">Enriching lyrics</div>${lyricsEnrichRow}` : ''}
      ${artworkEnrichRow ? `<div class="download-panel-section">Enriching artwork</div>${artworkEnrichRow}` : ''}
      ${histRows         ? `<div class="download-panel-section">Downloads</div>${histRows}` : ''}
      ${lyricsHistRows   ? `<div class="download-panel-section">Lyrics</div>${lyricsHistRows}` : ''}
      ${!hasActivity     ? '<div style="padding:16px;color:var(--color-text_secondary);font-size:.875rem">No activity</div>' : ''}`;
```

- [ ] **Step 4: Add event listeners for enrichment events**

Add after the existing `lyrics:fetch_end` listener:

```javascript
  document.addEventListener('claudefm:event', e => {
    const ev = e.detail;
    if (ev.type === 'enrichment_lyrics_started') {
      _lyricsEnriching.active = true;
      _lyricsEnriching.total  = ev.total || 0;
      _lyricsEnriching.done   = 0;
      _updateBadge();
    } else if (ev.type === 'lyrics_fetch_complete') {
      _lyricsEnriching.active = false;
      _updateBadge();
    } else if (ev.type === 'enrichment_artwork_started') {
      _artworkEnriching.active = true;
      _artworkEnriching.total  = ev.total || 0;
      _artworkEnriching.done   = 0;
      _updateBadge();
    } else if (ev.type === 'enrichment_artwork_progress') {
      _artworkEnriching.done = Math.min(_artworkEnriching.done + 1, _artworkEnriching.total);
      _updateBadge();
    } else if (ev.type === 'enrichment_artwork_complete') {
      _artworkEnriching.active = false;
      const { embedded = 0, not_found = 0, errors = 0 } = ev;
      if (embedded + not_found + errors > 0) {
        toast.show(`Artwork: ${embedded} embedded, ${not_found} not found${errors ? `, ${errors} errors` : ''}`, 'info', 5000);
      }
      _updateBadge();
    }
  });
```

- [ ] **Step 5: Run full test suite**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/interface/scripts/topbar.js
git commit -m "feat(topbar): track lyrics and artwork enrichment progress in badge and panel"
```

---

## Task 8: Display Embedded Cover Art on Track Cards

**Files:**
- Modify: `src/services/cover_art_service.py` — add `CoverArtEmbedder.read_bytes()` + `CoverArtService.get_cover_bytes()`
- Modify: `src/api/api.py` — add `get_track_artwork()` method
- Modify: `src/interface/scripts/api.js` — add `get_track_artwork` entry
- Modify: `src/interface/scripts/components.js` — lazy-load artwork after rendering track cards
- Test: `tests/test_cover_art_service.py`

### Context

`CoverArtService.fetch_and_embed()` writes image bytes into audio file tags (M4A `covr`, MP3 `APIC`). The frontend currently shows a `♪` placeholder for all tracks. This task reads those bytes back and serves them as base64 data URLs so track cards can display cover art.

**Read strategy:**
- M4A: `MP4(file_path).tags['covr'][0]` → `bytes(cover_data)`
- MP3: iterate `ID3(file_path).values()`, find first `APIC` frame → `.data`

**Display strategy:** `trackCard()` adds `data-artwork="${track.id}"` on the thumb when `track.artwork_status === 'embedded'`. After inserting HTML into the DOM, pages call `loadArtwork(container)` which fires one `api.get_track_artwork()` per pending thumb and sets `<img>` on success.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cover_art_service.py`:

```python
import base64
from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, APIC


def test_read_bytes_returns_bytes_from_m4a(tmp_path, mocker):
    fake_path = str(tmp_path / "test.m4a")
    image_bytes = b'\xff\xd8\xff\xe0JPEG_DATA'

    mock_mp4 = mocker.MagicMock()
    mock_cover = mocker.MagicMock()
    mock_cover.__bytes__ = mocker.MagicMock(return_value=image_bytes)
    mock_mp4.tags = {'covr': [mock_cover]}
    mocker.patch('src.services.cover_art_service.MP4', return_value=mock_mp4)

    embedder = CoverArtEmbedder()
    result = embedder.read_bytes(fake_path)
    assert result == image_bytes


def test_read_bytes_returns_none_when_no_covr_tag(tmp_path, mocker):
    fake_path = str(tmp_path / "test.m4a")
    mock_mp4 = mocker.MagicMock()
    mock_mp4.tags = {}
    mocker.patch('src.services.cover_art_service.MP4', return_value=mock_mp4)

    embedder = CoverArtEmbedder()
    result = embedder.read_bytes(fake_path)
    assert result is None


def test_read_bytes_returns_bytes_from_mp3(tmp_path, mocker):
    fake_path = str(tmp_path / "test.mp3")
    image_bytes = b'\xff\xd8\xff\xe0JPEG_DATA'

    mock_apic = mocker.MagicMock(spec=APIC)
    mock_apic.data = image_bytes
    mock_id3 = mocker.MagicMock()
    mock_id3.values.return_value = [mock_apic]
    mocker.patch('src.services.cover_art_service.ID3', return_value=mock_id3)
    mocker.patch('src.services.cover_art_service.ID3NoHeaderError', Exception)

    embedder = CoverArtEmbedder()
    result = embedder.read_bytes(fake_path)
    assert result == image_bytes


def test_get_cover_bytes_returns_bytes_when_embedded(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="Song", artist="Artist", album="Album",
                                      file_path="/fake/song.m4a"))
    update_track_status(db_conn, tid, download_status="completed")

    mock_lastfm = MagicMock()
    svc = CoverArtService(db_conn, mock_lastfm)
    image_bytes = b'\xff\xd8\xff\xe0JPEG'
    svc._embedder = MagicMock()
    svc._embedder.read_bytes.return_value = image_bytes

    result = svc.get_cover_bytes(tid)
    assert result == image_bytes


def test_get_cover_bytes_returns_none_for_missing_track(db_conn):
    init_db(db_conn)
    mock_lastfm = MagicMock()
    svc = CoverArtService(db_conn, mock_lastfm)
    assert svc.get_cover_bytes(9999) is None
```

- [ ] **Step 2: Run failing tests**

```
.venv/Scripts/python.exe -m pytest tests/test_cover_art_service.py -k "read_bytes or get_cover_bytes" -v
```

Expected: FAIL — `CoverArtEmbedder` has no `read_bytes`, `CoverArtService` has no `get_cover_bytes`.

- [ ] **Step 3: Add `read_bytes` to `CoverArtEmbedder` and `get_cover_bytes` to `CoverArtService`**

In `src/services/cover_art_service.py`, add `read_bytes` method to `CoverArtEmbedder` after `embed()`:

```python
    def read_bytes(self, file_path: str) -> bytes | None:
        ext = Path(file_path).suffix.lower()
        try:
            if ext == '.m4a':
                audio = MP4(file_path)
                if audio.tags and 'covr' in audio.tags:
                    return bytes(audio.tags['covr'][0])
            elif ext == '.mp3':
                try:
                    audio = ID3(file_path)
                except ID3NoHeaderError:
                    return None
                for tag in audio.values():
                    if isinstance(tag, APIC):
                        return tag.data
        except Exception as e:
            log.debug(f"read_bytes failed for {file_path}: {e}")
        return None
```

Add `get_cover_bytes` method to `CoverArtService` after `fetch_and_embed_async()`:

```python
    def get_cover_bytes(self, track_id: int) -> bytes | None:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return None
        return self._embedder.read_bytes(track.file_path)
```

- [ ] **Step 4: Run cover art tests**

```
.venv/Scripts/python.exe -m pytest tests/test_cover_art_service.py -v
```

Expected: all pass.

- [ ] **Step 5: Add `get_track_artwork` to `api.py`**

Add the import `import base64` at the top of `src/api/api.py`.

Add this method in the Lyrics section (or after `remove_from_library`):

```python
def get_track_artwork(self, track_id: int) -> str:
    try:
        image_bytes = self._get_cover_art().get_cover_bytes(track_id)
        if not image_bytes:
            return _err("No artwork")
        data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()
        return _ok({"data_url": data_url})
    except Exception as e:
        log.error(f"get_track_artwork: {e}", exc_info=True)
        return _err(str(e))
```

- [ ] **Step 6: Add `get_track_artwork` to `api.js`**

In the Library section of `src/interface/scripts/api.js`, add:

```javascript
    get_track_artwork:    (id)            => _call('get_track_artwork', id),
```

- [ ] **Step 7: Update `trackCard()` and add `loadArtwork()` in `components.js`**

In `trackCard()`, replace the static thumb:

```javascript
// OLD:
  return `<div class="track-card${playing ? ' playing' : ''}" data-track-id="${track.id}"
      onclick="player.play(${track.id}, _pageQueue)">
    <div class="track-card-thumb">♪</div>
```

with:

```javascript
// NEW:
  const hasArtwork = track.artwork_status === 'embedded';
  return `<div class="track-card${playing ? ' playing' : ''}" data-track-id="${track.id}"
      onclick="player.play(${track.id}, _pageQueue)">
    <div class="track-card-thumb"${hasArtwork ? ` data-artwork="${track.id}"` : ''}>♪</div>
```

Then add `loadArtwork()` function after `trackCard()`:

```javascript
async function loadArtwork(container) {
  const thumbs = (container || document).querySelectorAll('.track-card-thumb[data-artwork]');
  for (const thumb of thumbs) {
    const trackId = parseInt(thumb.dataset.artwork);
    delete thumb.dataset.artwork;  // prevent double-load on re-renders
    try {
      const result = await api.get_track_artwork(trackId);
      if (result?.data?.data_url) {
        thumb.innerHTML = `<img src="${result.data.data_url}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:4px">`;
      }
    } catch (_) {}
  }
}
```

- [ ] **Step 8: Call `loadArtwork` after rendering in all library pages**

Search for every place that renders track cards (calls `trackCard()`/`container.innerHTML = ...`) in the pages scripts. After each render, call `loadArtwork(container)`.

The pages that render track lists are: `home.js` (or similar), `library.js`, `artists.js` (artist detail), `albums.js` (album detail), `playlists.js` (playlist detail), `lastfm-artist.js`, `lastfm-album.js`.

Run this to find all render locations:

```
grep -r "trackCard\|innerHTML" src/interface/scripts/pages/ --include="*.js" -l
```

In each page, after the line that sets `container.innerHTML` (or appends track cards), add:

```javascript
loadArtwork(container);
```

- [ ] **Step 9: Run full test suite**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add src/services/cover_art_service.py src/api/api.py src/interface/scripts/api.js src/interface/scripts/components.js src/interface/scripts/pages/ tests/test_cover_art_service.py
git commit -m "feat: serve embedded cover art as base64 data URL and display on track cards"
```
