# Metadata Enrichment Design

## Goal

Automatically enrich downloaded tracks with missing lyrics and album artwork via background threads, with retry-cooldown logic, configurable auto-repeat intervals, and manual triggers from the Settings page.

## Architecture

Two independent enrichment threads (lyrics, artwork) coordinated by a new `EnrichmentScheduler` service. Individual services (`LRCLibService`, `CoverArtService`) do the actual work; the scheduler owns timing and concurrency guards. All state lives in the `tracks` table — no separate job queue.

## Tech Stack

- `threading.Timer` for auto-repeat scheduling (no new dependencies)
- SQLite `datetime()` arithmetic for cooldown filtering
- `event_bus.emit()` for progress events to frontend
- Pydantic + existing `Track` model extended with new fields

---

## Section 1 — Data Model

### DB schema changes

Three new columns added to `tracks` via `ALTER TABLE` migration in `init_db()`:

```sql
ALTER TABLE tracks ADD COLUMN artwork_status    TEXT NOT NULL DEFAULT 'not_fetched';
ALTER TABLE tracks ADD COLUMN lyrics_fetched_at  TEXT;   -- ISO datetime of last lyrics attempt
ALTER TABLE tracks ADD COLUMN artwork_fetched_at TEXT;   -- ISO datetime of last artwork attempt
```

`init_db()` runs three `ALTER TABLE tracks ADD COLUMN` statements, each wrapped in `try/except sqlite3.OperationalError` to be idempotent on databases that already have the columns.

### New enum

```python
# src/models/enums.py
class ArtworkStatus(str, Enum):
    NOT_FETCHED = "not_fetched"
    EMBEDDED    = "embedded"
    NOT_FOUND   = "not_found"
```

### Track model changes

```python
# src/models/track.py — three new optional fields
artwork_status:    ArtworkStatus = ArtworkStatus.NOT_FETCHED
lyrics_fetched_at:  datetime | None = None
artwork_fetched_at: datetime | None = None
```

`_row_to_track()` in `database.py` parses both new datetime columns from ISO strings (same pattern as `date_downloaded`).

### New DB functions in `database.py`

```python
def update_artwork_status(
    conn, track_id: int, status: str, fetched_at: datetime
) -> None: ...

def update_lyrics_fetched_at(conn, track_id: int, fetched_at: datetime) -> None: ...

def get_tracks_to_enrich_lyrics(conn, retry_not_found_after_days: int) -> list[Track]:
    """Return tracks with lyrics_status = not_fetched, plus not_found tracks
    whose lyrics_fetched_at is older than retry_not_found_after_days days.
    Only tracks with download_status = 'completed' are included."""

def get_tracks_to_enrich_artwork(conn, retry_not_found_after_days: int) -> list[Track]:
    """Same logic but for artwork_status / artwork_fetched_at."""
```

SQL for `get_tracks_to_enrich_lyrics`:

```sql
SELECT * FROM tracks
WHERE download_status = 'completed'
  AND file_status = 'available'
  AND (
    lyrics_status = 'not_fetched'
    OR (
      lyrics_status = 'not_found'
      AND (
        lyrics_fetched_at IS NULL
        OR datetime(lyrics_fetched_at) < datetime('now', '-? days')
      )
    )
  )
```

Same pattern for artwork (`artwork_status`, `artwork_fetched_at`).

---

## Section 2 — Service Changes

### `CoverArtService`

`fetch_and_embed(track_id)` now writes status to DB on every exit path:

| Outcome | `artwork_status` written | `artwork_fetched_at` |
|---|---|---|
| URL fetched + embedded | `embedded` | `now()` |
| No URL from Last.fm | `not_found` | `now()` |
| Download error | `not_found` | `now()` |
| Embed error | `not_found` | `now()` |

Return type changes from `bool` to `str` (the `ArtworkStatus` value written), for parity with `LRCLibService.fetch_and_embed()`. `fetch_and_embed_async()` signature is unchanged — still `-> None` (ignores return value).

### `LRCLibService`

`fetch_and_embed(track_id)` writes `lyrics_fetched_at = now()` on every exit path that currently writes `lyrics_status` (i.e., all paths except the early-return `None` for missing track/file_path).

`fetch_missing_lyrics()` signature changes:
```python
def fetch_missing_lyrics(self, retry_not_found_after_days: int = 7) -> None
```

`_run_batch()` uses `get_tracks_to_enrich_lyrics(conn, retry_not_found_after_days)` instead of `get_tracks_without_lyrics()`. Emits `enrichment_lyrics_started` with `{ "total": N }` before the loop begins. Existing `lyrics_progress` and `lyrics_fetch_complete` events are unchanged.

---

## Section 3 — EnrichmentScheduler

New file: `src/services/enrichment_scheduler.py`

```python
class EnrichmentScheduler:
    def __init__(self, conn, lrclib_service: LRCLibService, cover_art_service: CoverArtService) -> None:
        self._conn = conn
        self._lrclib = lrclib_service
        self._cover_art = cover_art_service
        self._lyrics_timer: threading.Timer | None = None
        self._artwork_timer: threading.Timer | None = None
        self._artwork_running = threading.Event()

    def run_lyrics(self) -> None:
        """Trigger a manual lyrics enrichment batch (non-blocking)."""

    def run_artwork(self) -> None:
        """Trigger a manual artwork enrichment batch (non-blocking)."""

    def apply_settings(self) -> None:
        """Read settings from DB and reconfigure auto-repeat timers."""

    def shutdown(self) -> None:
        """Cancel any pending timers (called on app close)."""
```

**Lyrics batch:** delegates to `self._lrclib.fetch_missing_lyrics(retry_not_found_after_days)`. Uses `LRCLibService._running` Event as concurrency guard (already exists). After batch completes, if `enrich_repeat_lyrics == 'true'`, schedules next run via `threading.Timer(interval_seconds, self.run_lyrics)`.

**Artwork batch:** `EnrichmentScheduler` owns `_artwork_running` Event. Runs in daemon thread. Calls `get_tracks_to_enrich_artwork()`, iterates, calls `cover_art_service.fetch_and_embed()` per track, emits `enrichment_artwork_progress` per track and `enrichment_artwork_complete` at end. After completion, schedules next run if `enrich_repeat_artwork == 'true'`.

**`apply_settings()`:** cancels both timers, re-reads `enrich_repeat_lyrics`, `enrich_repeat_artwork`, `enrich_interval_days` from DB, reschedules if enabled. Called by `ClaudeFMAPI.save_setting()` after any setting is saved.

**Events emitted:**

| Event | Payload | Emitter |
|---|---|---|
| `enrichment_lyrics_started` | `{ "total": int }` | `LRCLibService._run_batch` |
| `lyrics_progress` | `{ "track_id", "status" }` | existing — unchanged |
| `lyrics_fetch_complete` | counters dict | existing — unchanged |
| `enrichment_artwork_started` | `{ "total": int }` | `EnrichmentScheduler._run_artwork_batch` |
| `enrichment_artwork_progress` | `{ "track_id", "status" }` | `EnrichmentScheduler._run_artwork_batch` |
| `enrichment_artwork_complete` | `{ "embedded", "not_found", "errors" }` | `EnrichmentScheduler._run_artwork_batch` |

**Integration in `api.py`:**

```python
self._enrichment: EnrichmentScheduler | None = None

def _get_enrichment(self) -> EnrichmentScheduler:
    if self._enrichment is None:
        self._enrichment = EnrichmentScheduler(
            self._conn, self._get_lrclib(), self._get_cover_art()
        )
    return self._enrichment

def run_enrichment_lyrics(self) -> str: ...   # calls _get_enrichment().run_lyrics()
def run_enrichment_artwork(self) -> str: ...  # calls _get_enrichment().run_artwork()
```

`save_setting()` calls `self._get_enrichment().apply_settings()` after persisting to DB.

**New config defaults:**

| Key | Default |
|---|---|
| `enrich_repeat_lyrics` | `false` |
| `enrich_repeat_artwork` | `false` |
| `enrich_interval_days` | `1` |
| `enrich_retry_not_found_days` | `7` |

---

## Section 4 — Settings UI

New "Enrichment" section in `src/interface/scripts/pages/settings.js`, placed after the "Library" section:

```
┌─ Enrichment ──────────────────────────────────────────────────────────┐
│ Run lyrics search now            [ Run now ]                          │
│ Run artwork search now           [ Run now ]                          │
│ Auto-repeat lyrics search        [toggle]                             │
│ Auto-repeat artwork search       [toggle]                             │
│ Repeat interval (days)           [ 1 ]                                │
│ Skip not-found tracks for (days) [ 7 ]                                │
└───────────────────────────────────────────────────────────────────────┘
```

Element IDs: `set-enrich-run-lyrics`, `set-enrich-run-artwork`, `set-enrich-repeat-lyrics`, `set-enrich-repeat-artwork`, `set-enrich-interval`, `set-enrich-retry-days`.

"Run now" buttons call `api.run_enrichment_lyrics()` / `api.run_enrichment_artwork()` and disable for the duration of the `await`.

The four persistent fields (`enrich_repeat_lyrics`, `enrich_repeat_artwork`, `enrich_interval_days`, `enrich_retry_not_found_days`) are saved in the existing `Promise.all` block when "Save Settings" is clicked.

---

## Section 5 — Topbar

`topbar.js` extended with two new state objects:

```js
const _lyricsEnriching  = { active: false, total: 0, done: 0 };
const _artworkEnriching = { active: false, total: 0, done: 0 };
```

Badge count formula becomes:
```js
downloads.activeCount()
  + Object.keys(_lyricsFetching).length
  + (_lyricsEnriching.active  ? 1 : 0)
  + (_artworkEnriching.active ? 1 : 0)
```

Panel additions (shown only when active):
- `"Enriching lyrics (N/M)"` row
- `"Enriching artwork (N/M)"` row

Event listeners added:

| Event | Action |
|---|---|
| `enrichment_lyrics_started` | Set `_lyricsEnriching = { active: true, total: e.total, done: 0 }`, update badge |
| `lyrics_fetch_complete` | Clear `_lyricsEnriching.active`, update badge |
| `enrichment_artwork_started` | Set `_artworkEnriching = { active: true, total: e.total, done: 0 }`, update badge |
| `enrichment_artwork_progress` | Increment `_artworkEnriching.done`, update badge |
| `enrichment_artwork_complete` | Clear `_artworkEnriching.active`, toast "Artwork: X embedded, Y not found", update badge |

---

## Files Modified / Created

| File | Change |
|---|---|
| `src/models/enums.py` | Add `ArtworkStatus` |
| `src/models/track.py` | Add 3 new fields |
| `src/database/database.py` | Schema migration + 4 new functions + `_row_to_track` update |
| `src/database/config_manager.py` | 4 new defaults |
| `src/services/lrclib_service.py` | Write `lyrics_fetched_at`, update batch query, emit `enrichment_lyrics_started`, accept `retry_not_found_after_days` param |
| `src/services/cover_art_service.py` | Write `artwork_status` + `artwork_fetched_at`, return status string |
| `src/services/enrichment_scheduler.py` | **New** |
| `src/api/api.py` | Lazy-init `EnrichmentScheduler`, 2 new API methods, `save_setting` hook |
| `src/interface/scripts/api.js` | 2 new entries |
| `src/interface/scripts/pages/settings.js` | New "Enrichment" section |
| `src/interface/scripts/topbar.js` | Track enrichment activity in badge/panel |
| `tests/test_database.py` | New tests for 4 new DB functions |
| `tests/test_lrclib_service.py` | Tests for `lyrics_fetched_at` writes + new batch query |
| `tests/test_cover_art_service.py` | Tests for `artwork_status` writes |
| `tests/test_enrichment_scheduler.py` | **New** — scheduler logic tests |
