# Backend Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce coupling and duplicated code in the backend without introducing complex abstractions. Each task is a self-contained refactor with no behavior change visible to the frontend (response shapes, event names, and DB schema stay identical).

**Architecture:** Seven independent refactors applied in dependency order: (1) row→Pydantic conversion via `model_validate`, (2) generalize enrichment DB helpers, (3) API error-envelope decorator, (4) move app shutdown logic into the API object, (5) collapse repeated finalize blocks in `LRCLibService.fetch_and_embed`, (6) move the lyrics batch loop into `EnrichmentScheduler` so the scheduler is the single owner of batch enrichment, (7) parameterize the scheduler's per-kind timer pair into a single dict.

**Tech Stack:** Python 3 stdlib (`functools.wraps`, `threading.Timer`), Pydantic 2 `model_validate`, pytest + pytest-mock, sqlite3 stdlib.

---

## File Map

| File | Change |
|---|---|
| `src/database/database.py` | `_row_to_track` shrinks to `Track.model_validate(dict(row))`; add `get_tracks_to_enrich(kind, ...)` and `set_enrichment_status(track_id, kind, status)`; delete `get_tracks_to_enrich_lyrics`, `get_tracks_to_enrich_artwork`, `update_lyrics_status`, `update_lyrics_fetched_at`, `update_artwork_status` |
| `src/api/api.py` | Add `_api_method` decorator + `_raw_api_method`; rewrite every JS-callable method's body to drop the try/except; add `persist_state()` + `shutdown()` |
| `app.py` | `on_closing` becomes `api.shutdown()` |
| `src/services/lrclib_service.py` | `fetch_and_embed` uses inner `_finalize(status)` helper; remove `_run_batch`, `fetch_missing_lyrics`, `_running` (moved to scheduler) |
| `src/services/enrichment_scheduler.py` | Owns both batch loops via one generic `_run_batch`; timers stored in `_timers` dict; one `_schedule(kind)` instead of two |
| `tests/test_database.py` | Replace tests of removed functions with tests of new `get_tracks_to_enrich(kind=…)` and `set_enrichment_status(…, kind=…)` |
| `tests/test_api.py` | One new test per envelope-decorator branch; new tests for `persist_state` + `shutdown` |
| `tests/test_lrclib_service.py` | Delete batch-loop tests (`_run_batch`, `fetch_missing_lyrics`, `_running`); fetch-and-embed tests stay |
| `tests/test_enrichment_scheduler.py` | New tests for `run_lyrics` end-to-end batch (now owned by scheduler) and timer-dict refactor |

---

## Task 1: Simplify `_row_to_track` via Pydantic `model_validate`

**Files:**
- Modify: `src/database/database.py:97-119`
- Test: `tests/test_database.py`

### Context

`_row_to_track` manually unpacks every column and parses ISO datetime strings. Pydantic 2 `model_validate` accepts a dict and parses `datetime` fields natively from ISO strings. Column names already match `Track` field names.

- [ ] **Step 1: Add regression test that round-trips every datetime field**

Add at end of `tests/test_database.py`:

```python
def test_row_to_track_parses_all_datetime_fields(db_conn):
    """Use raw SQL for setup so the test survives Task 2 (which removes update_lyrics_fetched_at / update_artwork_status)."""
    init_db(db_conn)
    ts_iso = "2025-06-01T12:00:00"
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    db_conn.execute(
        "UPDATE tracks SET date_downloaded=?, lyrics_fetched_at=?, artwork_fetched_at=?, artwork_status='embedded' WHERE id=?",
        (ts_iso, ts_iso, ts_iso, tid),
    )
    db_conn.commit()
    t = get_track(db_conn, tid)
    expected = datetime.fromisoformat(ts_iso)
    assert t.date_downloaded == expected
    assert t.lyrics_fetched_at == expected
    assert t.artwork_fetched_at == expected
```

- [ ] **Step 2: Run the test to confirm it passes today**

```
.venv/Scripts/python.exe -m pytest tests/test_database.py::test_row_to_track_parses_all_datetime_fields -v
```

Expected: PASS (proves the contract is real).

- [ ] **Step 3: Replace `_row_to_track` body with `model_validate`**

Replace lines 97-119 of `src/database/database.py`:

```python
def _row_to_track(row: sqlite3.Row) -> Track:
    """Convert a raw DB row to a Track. Pydantic parses ISO datetime strings natively."""
    return Track.model_validate(dict(row))
```

- [ ] **Step 4: Run full test suite**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add src/database/database.py tests/test_database.py
git commit -m "refactor(db): replace _row_to_track manual unpack with Pydantic model_validate"
```

---

## Task 2: Generalize enrichment DB helpers

**Files:**
- Modify: `src/database/database.py:195-260`
- Modify: `src/services/lrclib_service.py`
- Modify: `src/services/cover_art_service.py`
- Test: `tests/test_database.py`

### Context

`get_tracks_to_enrich_lyrics` + `get_tracks_to_enrich_artwork` differ only by column name. `update_lyrics_status` + `update_lyrics_fetched_at` + `update_artwork_status` are three setters that callers always invoke together. Consolidate into `get_tracks_to_enrich(kind)` and `set_enrichment_status(track_id, kind, status)` (always writes `fetched_at=now()`). Whitelist `kind` to `"lyrics" | "artwork"` to keep SQL injection-safe.

- [ ] **Step 1: Write failing tests for the new generalized functions**

Add to `tests/test_database.py`:

```python
def test_get_tracks_to_enrich_lyrics_kind(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed")
    result = get_tracks_to_enrich(db_conn, kind="lyrics", retry_not_found_after_days=7)
    assert any(t.id == tid for t in result)


def test_get_tracks_to_enrich_artwork_kind(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed")
    result = get_tracks_to_enrich(db_conn, kind="artwork", retry_not_found_after_days=7)
    assert any(t.id == tid for t in result)


def test_get_tracks_to_enrich_rejects_unknown_kind(db_conn):
    init_db(db_conn)
    with pytest.raises(ValueError):
        get_tracks_to_enrich(db_conn, kind="bogus", retry_not_found_after_days=7)


def test_set_enrichment_status_lyrics_writes_status_and_now(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    set_enrichment_status(db_conn, tid, kind="lyrics", status="synchronized")
    t = get_track(db_conn, tid)
    assert t.lyrics_status == "synchronized"
    assert t.lyrics_fetched_at is not None


def test_set_enrichment_status_artwork_writes_status_and_now(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    set_enrichment_status(db_conn, tid, kind="artwork", status="embedded")
    t = get_track(db_conn, tid)
    assert t.artwork_status == "embedded"
    assert t.artwork_fetched_at is not None
```

Add the imports at the top:

```python
from src.database.database import (
    ...,
    get_tracks_to_enrich, set_enrichment_status,
)
```

- [ ] **Step 2: Run failing tests**

```
.venv/Scripts/python.exe -m pytest tests/test_database.py -v -k "enrich"
```

Expected: ImportError on `get_tracks_to_enrich` and `set_enrichment_status`.

- [ ] **Step 3: Add new generalized functions**

Add to `src/database/database.py` (above the existing per-kind functions):

```python
_ENRICHMENT_KINDS = {"lyrics", "artwork"}


def get_tracks_to_enrich(
    conn: sqlite3.Connection, kind: str, retry_not_found_after_days: int
) -> list[Track]:
    """Return tracks pending enrichment for ``kind`` ('lyrics' or 'artwork')."""
    if kind not in _ENRICHMENT_KINDS:
        raise ValueError(f"unknown enrichment kind: {kind!r}")
    status_col = f"{kind}_status"
    ts_col = f"{kind}_fetched_at"
    rows = conn.execute(
        f"""SELECT * FROM tracks
            WHERE download_status = 'completed'
              AND file_status = 'available'
              AND (
                {status_col} = 'not_fetched'
                OR (
                  {status_col} = 'not_found'
                  AND (
                    {ts_col} IS NULL
                    OR datetime({ts_col}) < datetime('now', ? || ' days')
                  )
                )
              )""",
        (f"-{retry_not_found_after_days}",),
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def set_enrichment_status(
    conn: sqlite3.Connection, track_id: int, kind: str, status: str
) -> None:
    """Write ``status`` + ``fetched_at=now()`` for the given enrichment ``kind``."""
    if kind not in _ENRICHMENT_KINDS:
        raise ValueError(f"unknown enrichment kind: {kind!r}")
    status_col = f"{kind}_status"
    ts_col = f"{kind}_fetched_at"
    conn.execute(
        f"UPDATE tracks SET {status_col}=?, {ts_col}=? WHERE id=?",
        (status, datetime.now().isoformat(), track_id),
    )
    conn.commit()
```

- [ ] **Step 4: Run new tests to verify they pass**

```
.venv/Scripts/python.exe -m pytest tests/test_database.py -v -k "enrich"
```

Expected: all PASS.

- [ ] **Step 5: Migrate `cover_art_service.py` to the new helper**

Replace the two `update_artwork_status(...)` calls in `src/services/cover_art_service.py` with:

```python
from src.database.database import get_track, set_enrichment_status, update_track_album
```

and replace each `update_artwork_status(self._conn, track_id, ArtworkStatus.X, datetime.now())` with:

```python
set_enrichment_status(self._conn, track_id, "artwork", ArtworkStatus.X)
```

- [ ] **Step 6: Migrate `lrclib_service.py` to the new helper**

In `src/services/lrclib_service.py`, replace the import block:

```python
from src.database.database import (
    get_track, set_enrichment_status, get_tracks_to_enrich,
)
```

Replace every `update_lyrics_status(self._conn, track_id, X)` + `update_lyrics_fetched_at(self._conn, track_id, now)` pair with:

```python
set_enrichment_status(self._conn, track_id, "lyrics", X)
```

Replace `get_tracks_to_enrich_lyrics(self._conn, retry_not_found_after_days=days)` with:

```python
get_tracks_to_enrich(self._conn, kind="lyrics", retry_not_found_after_days=days)
```

- [ ] **Step 7: Migrate `enrichment_scheduler.py` to the new helper**

In `src/services/enrichment_scheduler.py`, replace:

```python
from src.database.database import get_tracks_to_enrich
```

and replace `get_tracks_to_enrich_artwork(self._conn, retry_not_found_after_days=days)` with:

```python
get_tracks_to_enrich(self._conn, kind="artwork", retry_not_found_after_days=days)
```

- [ ] **Step 8: Delete the old per-kind functions**

Remove from `src/database/database.py`:
- `update_lyrics_status`
- `update_lyrics_fetched_at`
- `update_artwork_status`
- `get_tracks_to_enrich_lyrics`
- `get_tracks_to_enrich_artwork`

- [ ] **Step 9: Update existing tests to use the new helpers**

In `tests/test_database.py`, replace every:
- `update_lyrics_status(db_conn, tid, X)` → `set_enrichment_status(db_conn, tid, "lyrics", X)`
- `update_artwork_status(db_conn, tid, X, ts)` → use `set_enrichment_status(db_conn, tid, "artwork", X)` AND, where the test asserts on `artwork_fetched_at == ts`, change the assertion to `t.artwork_fetched_at is not None` (the helper writes `now()` not a passed-in `ts`)
- `update_lyrics_fetched_at(db_conn, tid, ts)` → same migration
- `get_tracks_to_enrich_lyrics(db_conn, retry_not_found_after_days=N)` → `get_tracks_to_enrich(db_conn, kind="lyrics", retry_not_found_after_days=N)`
- `get_tracks_to_enrich_artwork(db_conn, retry_not_found_after_days=N)` → `get_tracks_to_enrich(db_conn, kind="artwork", retry_not_found_after_days=N)`

Drop the obsolete tests:
- `test_update_lyrics_fetched_at_writes_timestamp` (covered by `test_set_enrichment_status_lyrics_writes_status_and_now`)
- `test_update_artwork_status_writes_status_and_timestamp` (covered by `test_set_enrichment_status_artwork_writes_status_and_now`)

Update import block: remove `update_lyrics_status`, `update_lyrics_fetched_at`, `update_artwork_status`, `get_tracks_to_enrich_lyrics`, `get_tracks_to_enrich_artwork`.

- [ ] **Step 10: Update `tests/test_lrclib_service.py` and `tests/test_cover_art_service.py`**

In both files, replace `update_lyrics_status` / `update_artwork_status` imports + call sites with `set_enrichment_status`. Update assertions on `lyrics_fetched_at`/`artwork_fetched_at` to check truthiness, not equality with a passed-in timestamp.

- [ ] **Step 11: Run full suite**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 12: Commit**

```
git add src/database/database.py src/services/lrclib_service.py src/services/cover_art_service.py src/services/enrichment_scheduler.py tests/
git commit -m "refactor(db): generalize enrichment helpers behind kind parameter"
```

---

## Task 3: API error-envelope decorator

**Files:**
- Modify: `src/api/api.py`
- Test: `tests/test_api.py`

### Context

~35 JS-callable methods on `ClaudeFMAPI` share the same shape:

```python
def foo(self, x):
    try:
        ...do work...
        return _ok(data)         # or json.dumps([...]) for raw array methods
    except Exception as e:
        log.error(f"foo: {e}", exc_info=True)
        return _err(str(e))
```

Introduce two decorators:
- `@_api_method` — body returns a Python value or `None`; decorator wraps in `_ok(value)` (`_ok()` if `None`); catches `Exception`, logs at error level, returns `_err(str(e))`.
- `@_api_method(raw=True)` — body returns a dict or list that already has the final JSON shape; decorator only `json.dumps`-it and handles exceptions (returning `_err` JSON string).

Raise plain `ValueError` from a method body to surface a user-facing error without logging at error level (`_err` returned directly).

- [ ] **Step 1: Write tests for the decorator branches**

Add to `tests/test_api.py`:

```python
def test_api_method_wraps_dict_return_in_ok(db_conn, tmp_path):
    """A method returning a dict should be wrapped as {"success": True, "data": <dict>}."""
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_position())  # raw method — returns {"position": X}
    assert "position" in result  # raw mode still works


def test_api_method_wraps_exception_as_err(db_conn, tmp_path):
    """A method raising should return {"success": False, "error": <msg>}."""
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.delete_track", side_effect=RuntimeError("kaboom")):
        result = json.loads(api.remove_from_library(1))
    assert result["success"] is False
    assert "kaboom" in result["error"]


def test_api_method_value_error_returns_err_without_stack(db_conn, tmp_path, caplog):
    """ValueError should produce _err but not log at ERROR level."""
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.get_track", side_effect=ValueError("bad input")):
        result = json.loads(api.get_track(1))
    assert result["success"] is False
    assert "bad input" in result["error"]
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert not error_records  # ValueError is user-facing, not logged as error
```

- [ ] **Step 2: Run new tests — they should pass *now* because nothing changes the response shape**

```
.venv/Scripts/python.exe -m pytest tests/test_api.py -v -k "api_method"
```

Expected: PASS (current code already produces these shapes via try/except).

- [ ] **Step 3: Add the decorators at the top of `src/api/api.py`**

Insert after the imports, before `class ClaudeFMAPI`:

```python
from functools import wraps


def _api_method(_fn=None, *, raw: bool = False):
    """Wrap a JS-callable method so its body can raise/return naturally.

    - body returns ``None`` → ``_ok()``
    - body returns any other value → ``_ok(value)`` (or ``json.dumps(value)`` if ``raw``)
    - body raises ``ValueError`` → ``_err(str(e))`` (not logged at ERROR)
    - body raises anything else → ``_err(str(e))`` + ``log.error(..., exc_info=True)``
    """
    def decorate(fn):
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            try:
                value = fn(self, *args, **kwargs)
            except ValueError as e:
                return _err(str(e))
            except Exception as e:
                log.error(f"{fn.__name__}: {e}", exc_info=True)
                return _err(str(e))
            if raw:
                return json.dumps(value)
            if value is None:
                return _ok()
            return _ok(value)
        return wrapper

    return decorate if _fn is None else decorate(_fn)
```

- [ ] **Step 4: Apply the decorator method-by-method**

Rewrite each JS-callable method. Examples below — repeat the pattern for every public method on `ClaudeFMAPI`.

**Standard envelope** (replace `_ok`/`_err` body):

```python
@_api_method
def remove_from_library(self, track_id: int):
    delete_track(self._conn, track_id)

@_api_method
def get_track(self, track_id: int):
    track = get_track(self._conn, track_id)
    if not track:
        raise ValueError("Track not found")
    return track.model_dump(mode="json")

@_api_method
def fetch_lyrics(self, track_id: int):
    status = self._get_lrclib().fetch_and_embed(track_id)
    if status is None:
        raise ValueError("Track not found")
    return {"lyrics_status": status}
```

**Raw output** (was returning `json.dumps([...])` or a non-envelope dict):

```python
@_api_method(raw=True)
def get_library(self, filters_json: str = "{}"):
    filters = json.loads(filters_json)
    order = filters.get("order_by", "date_downloaded DESC")
    fmt = filters.get("audio_format")
    tracks = get_all_tracks(self._conn, order_by=order, audio_format=fmt)
    return [t.model_dump(mode="json") for t in tracks]

@_api_method(raw=True)
def get_position(self):
    return {"position": self._player.get_position()}

@_api_method(raw=True)
def get_player_state(self):
    q = self._player.queue
    return {
        "current_id": q.current_id(),
        "position": self._player.get_position(),
        "paused": self._player.is_paused,
        "volume": self._player.get_volume(),
        "ended": q.ended,
    }

@_api_method(raw=True)
def check_internet(self):
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return {"online": True}
    except OSError:
        return {"online": False}
```

**Methods that returned `{"success": True, "track_id": id}`** — keep using raw mode to preserve the wire shape:

```python
@_api_method(raw=True)
def create_playlist(self, name: str, playlist_type: str = "manual"):
    if playlist_type == "auto" and get_auto_playlist_count(self._conn) >= AUTO_PLAYLIST_LIMIT:
        delete_oldest_auto_playlist(self._conn)
    p = Playlist(name=name, type=playlist_type)
    pid = insert_playlist(self._conn, p)
    return {"success": True, "id": pid}

@_api_method(raw=True)
def download_lastfm_track(self, title: str, artist: str, album: str | None = None):
    t = Track(title=title, artist=artist, album=album)
    track_id = insert_track(self._conn, t)
    self._get_youtube().queue_download(track_id, on_complete=self._post_download_hook())
    return {"success": True, "track_id": track_id}

@_api_method(raw=True)
def next_track(self):
    while True:
        next_id = self._player.queue.next_id()
        if next_id is None:
            event_bus.emit("queue_ended", {})
            return {"success": True, "ended": True}
        track = get_track(self._conn, next_id)
        if track and track.file_path and track.file_status == "available":
            self._player.play(track.file_path)
            return {"success": True, "track_id": next_id}
        log.debug(f"Skipping unplayable track {next_id} (status={getattr(track, 'file_status', None)})")
```

(Apply same `prev_track` treatment.)

**Methods that return raw arrays** (`get_artists`, `get_albums`, `get_tracks_by_artist`, `get_tracks_by_album`, `search_local`, `search_lastfm`, `get_artist_top_tracks`, `get_album_tracks`, `get_playlists`, `get_playlist_tracks`, `get_settings`):

```python
@_api_method(raw=True)
def get_artists(self):
    return get_all_artists(self._conn)

@_api_method(raw=True)
def get_albums(self):
    return get_all_albums(self._conn)

@_api_method(raw=True)
def get_tracks_by_artist(self, artist: str):
    return [t.model_dump(mode="json") for t in get_tracks_by_artist(self._conn, artist)]
```

…and so on. Apply uniformly to every JS-callable public method on `ClaudeFMAPI`. Do not decorate `__init__` or private helpers (`_get_youtube`, `_get_lastfm`, `_get_lrclib`, `_get_cover_art`, `_get_enrichment`, `_post_download_hook`).

- [ ] **Step 5: Run full test suite**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass (response shapes are preserved exactly).

- [ ] **Step 6: Commit**

```
git add src/api/api.py tests/test_api.py
git commit -m "refactor(api): collapse try/except boilerplate behind _api_method decorator"
```

---

## Task 4: Move shutdown / persist logic from `app.py` into `ClaudeFMAPI`

**Files:**
- Modify: `src/api/api.py`
- Modify: `app.py:73-85`
- Test: `tests/test_api.py`

### Context

`app.py:on_closing` reaches into `api._player.queue`, `api._youtube`, `api._enrichment` — bypassing the public seam. Move the lifecycle ops onto `ClaudeFMAPI` so `app.py` only orchestrates.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
def test_persist_state_writes_current_track_id_and_position(db_conn, tmp_path):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X", file_path="/a.m4a"))
    api = _make_api(db_conn, tmp_path)
    api._player.queue.set_context([tid], start_index=0)
    api.persist_state()
    from src.database.config_manager import get_setting
    assert get_setting(db_conn, "player_last_track_id") == str(tid)
    assert get_setting(db_conn, "player_last_position") == "0"


def test_persist_state_noop_when_queue_empty(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    api.persist_state()  # must not raise


def test_shutdown_persists_then_shuts_down_youtube(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    api._youtube = MagicMock()
    api.shutdown()
    api._youtube.shutdown.assert_called_once_with(wait=False)
```

- [ ] **Step 2: Run failing tests**

```
.venv/Scripts/python.exe -m pytest tests/test_api.py -v -k "persist_state or shutdown"
```

Expected: AttributeError for `persist_state` and `shutdown`.

- [ ] **Step 3: Implement the methods on `ClaudeFMAPI`**

Add to `src/api/api.py` (after the lazy-getter helpers, before the section comment for Library):

```python
def persist_state(self) -> None:
    """Write the current playback state to settings so the next session can restore it."""
    q = self._player.queue
    track_id = q.current_id()
    if track_id is None:
        return
    set_setting(self._conn, "player_last_track_id", str(track_id))
    set_setting(self._conn, "player_last_position", str(int(self._player.get_position())))
    set_setting(self._conn, "player_last_context", json.dumps(q.to_dict()))

def shutdown(self) -> None:
    """Persist player state and tear down background workers. Idempotent."""
    self.persist_state()
    if self._youtube is not None:
        self._youtube.shutdown(wait=False)
    if self._enrichment is not None:
        self._enrichment.shutdown()
    self._conn.close()
```

These are lifecycle methods, **not** JS-callable — do not decorate them with `@_api_method`.

- [ ] **Step 4: Trim `app.py:on_closing` to call `api.shutdown()`**

Replace the body of `on_closing` in `app.py`:

```python
def on_closing():
    """Persist playback state and shut down workers before the window closes."""
    api.shutdown()
    log.info("ClaudeFM closing")
```

Remove the now-dead `import json` if `app.py` no longer needs it elsewhere — check `additional_folders` parsing still uses it. (It does. Keep the import.)

- [ ] **Step 5: Run tests**

```
.venv/Scripts/python.exe -m pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```
git add src/api/api.py app.py tests/test_api.py
git commit -m "refactor(api): move shutdown and persist_state out of app.py into ClaudeFMAPI"
```

---

## Task 5: Collapse repeated finalize blocks in `LRCLibService.fetch_and_embed`

**Files:**
- Modify: `src/services/lrclib_service.py:82-144`
- Test: `tests/test_lrclib_service.py` (no test changes — existing coverage exercises every branch)

### Context

`fetch_and_embed` has six identical 1-line `set_enrichment_status(self._conn, track_id, "lyrics", X); return X` patterns (after Task 2). Lift into one nested helper for readability and to prevent future drift (e.g. someone forgets the `set_enrichment_status` call before a `return`).

- [ ] **Step 1: Rewrite `fetch_and_embed`**

Replace the method body in `src/services/lrclib_service.py`:

```python
def fetch_and_embed(self, track_id: int) -> str | None:
    track = get_track(self._conn, track_id)
    if not track or not track.file_path:
        return None

    def finalize(status: str) -> str:
        set_enrichment_status(self._conn, track_id, "lyrics", status)
        return status

    result = None
    if track.duration is not None:
        try:
            result = self._fetcher.get(track.title, track.artist, track.album or "", track.duration)
        except Exception:
            log.error(f"LRCLib.get failed for track {track_id}", exc_info=True)
            return finalize(LyricsStatus.NOT_FETCHED)

    if result is None:
        try:
            result = self._fetcher.search(track.title, track.artist)
        except Exception:
            log.error(f"LRCLib.search failed for track {track_id}", exc_info=True)
            return finalize(LyricsStatus.NOT_FETCHED)

    if result is None:
        return finalize(LyricsStatus.NOT_FOUND)

    if result.instrumental:
        return finalize(LyricsStatus.INSTRUMENTAL)

    if result.syncedLyrics is not None:
        lyrics, state, status = result.syncedLyrics, "synced", LyricsStatus.SYNCHRONIZED
    elif result.plainLyrics is not None:
        lyrics, state, status = result.plainLyrics, "unsynced", LyricsStatus.PLAIN_TEXT
    else:
        return finalize(LyricsStatus.NOT_FOUND)

    try:
        self._embedder.embed(track.file_path, state, lyrics)
    except UnsupportedSuffix:
        log.error(f"Unsupported format for track {track_id}: {track.file_path}")
        return finalize(LyricsStatus.NOT_SUPPORTED)
    except Exception as e:
        log.error(f"Failed to embed lyrics for track {track_id}: {e}", exc_info=True)
        return finalize(LyricsStatus.NOT_FETCHED)

    return finalize(status)
```

- [ ] **Step 2: Run existing lyrics tests to confirm no regression**

```
.venv/Scripts/python.exe -m pytest tests/test_lrclib_service.py -v
```

Expected: PASS (test set is unchanged; behavior identical).

- [ ] **Step 3: Commit**

```
git add src/services/lrclib_service.py
git commit -m "refactor(lrclib): collapse finalize blocks in fetch_and_embed"
```

---

## Task 6: Move the lyrics batch loop into `EnrichmentScheduler`

**Files:**
- Modify: `src/services/lrclib_service.py`
- Modify: `src/services/enrichment_scheduler.py`
- Modify: `src/api/api.py`
- Test: `tests/test_lrclib_service.py`
- Test: `tests/test_enrichment_scheduler.py`

### Context

`LRCLibService` currently owns its batch loop (`_run_batch`, `fetch_missing_lyrics`, `_running` event). `CoverArtService` does not — `EnrichmentScheduler` runs its batch. Asymmetric. Goal: scheduler owns all batch coordination; per-track services expose only `fetch_and_embed(track_id)`. Behavior preserved: event names, counters, single-flight guard.

- [ ] **Step 1: Write tests for the new scheduler-owned lyrics batch**

In `tests/test_enrichment_scheduler.py`:

```python
def test_run_lyrics_emits_started_progress_complete(svc, mocker):
    scheduler, lrclib, _, db_conn = svc
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed", file_status="available")
    lrclib.fetch_and_embed.return_value = "synchronized"

    emitted = []
    mocker.patch(
        "src.services.enrichment_scheduler.event_bus.emit",
        side_effect=lambda t, p: emitted.append((t, p)),
    )

    scheduler._run_lyrics_batch()

    types = [e[0] for e in emitted]
    assert "enrichment_lyrics_started" in types
    assert "lyrics_progress" in types
    assert "lyrics_fetch_complete" in types
    complete = next(e[1] for e in emitted if e[0] == "lyrics_fetch_complete")
    assert complete["synchronized"] == 1


def test_run_lyrics_skips_if_already_running(svc):
    scheduler, lrclib, _, db_conn = svc
    insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, 1, download_status="completed", file_status="available")
    scheduler._lyrics_running.set()
    scheduler.run_lyrics()
    lrclib.fetch_and_embed.assert_not_called()
    scheduler._lyrics_running.clear()


def test_run_lyrics_per_track_exception_counted_as_error(svc, mocker):
    scheduler, lrclib, _, db_conn = svc
    insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, 1, download_status="completed", file_status="available")
    lrclib.fetch_and_embed.side_effect = RuntimeError("boom")

    emitted = []
    mocker.patch(
        "src.services.enrichment_scheduler.event_bus.emit",
        side_effect=lambda t, p: emitted.append((t, p)),
    )

    scheduler._run_lyrics_batch()

    complete = next(e[1] for e in emitted if e[0] == "lyrics_fetch_complete")
    assert complete["errors"] == 1
```

Update the `svc` fixture so `lrclib` is a `MagicMock` that responds to `fetch_and_embed` and is no longer expected to expose `fetch_missing_lyrics`. (Existing fixture already uses `MagicMock()`, no change needed.)

- [ ] **Step 2: Run failing tests**

```
.venv/Scripts/python.exe -m pytest tests/test_enrichment_scheduler.py -v -k "run_lyrics"
```

Expected: `AttributeError` on `_lyrics_running` / `_run_lyrics_batch`.

- [ ] **Step 3: Implement the scheduler-owned lyrics batch + generic loop**

In `src/services/enrichment_scheduler.py`, replace the file with:

```python
import sqlite3
import threading

from src.database.database import get_tracks_to_enrich
from src.database.config_manager import get_setting
from src.models.enums import ArtworkStatus, LyricsStatus
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("enrichment")

# Per-kind config: (started_event, progress_event, complete_event, counter_keys)
_BATCH_EVENTS = {
    "lyrics": (
        "enrichment_lyrics_started",
        "lyrics_progress",
        "lyrics_fetch_complete",
        ("synchronized", "plain_text", "instrumental", "not_found", "not_supported", "errors"),
    ),
    "artwork": (
        "enrichment_artwork_started",
        "enrichment_artwork_progress",
        "enrichment_artwork_complete",
        ("embedded", "not_found", "errors"),
    ),
}


class EnrichmentScheduler:
    def __init__(self, conn: sqlite3.Connection, lrclib_service, cover_art_service) -> None:
        self._conn = conn
        self._lrclib = lrclib_service
        self._cover_art = cover_art_service
        self._timers: dict[str, threading.Timer] = {}
        self._lyrics_running = threading.Event()
        self._artwork_running = threading.Event()

    # ── Public triggers ──────────────────────────────────────────────────────

    def run_lyrics(self) -> None:
        if self._lyrics_running.is_set():
            return
        self._lyrics_running.set()
        threading.Thread(target=self._run_lyrics_batch, daemon=True).start()

    def run_artwork(self) -> None:
        if self._artwork_running.is_set():
            return
        self._artwork_running.set()
        threading.Thread(target=self._run_artwork_batch, daemon=True).start()

    # ── Batch loops ──────────────────────────────────────────────────────────

    def _run_lyrics_batch(self) -> None:
        try:
            self._run_batch("lyrics", self._lrclib.fetch_and_embed)
            self._reschedule("lyrics")
        finally:
            self._lyrics_running.clear()

    def _run_artwork_batch(self) -> None:
        try:
            self._run_batch("artwork", self._cover_art.fetch_and_embed)
            self._reschedule("artwork")
        finally:
            self._artwork_running.clear()

    def _run_batch(self, kind: str, fetch_fn) -> None:
        days = int(get_setting(self._conn, "enrich_retry_not_found_days") or "7")
        tracks = get_tracks_to_enrich(self._conn, kind=kind, retry_not_found_after_days=days)
        started, progress, complete, counter_keys = _BATCH_EVENTS[kind]
        counters = {k: 0 for k in counter_keys}
        event_bus.emit(started, {"total": len(tracks)})
        for track in tracks:
            status = None
            try:
                status = fetch_fn(track.id)
                counters[self._bucket(kind, status)] += 1
            except Exception:
                log.error(f"{kind} enrichment failed for track {track.id}", exc_info=True)
                counters["errors"] += 1
            payload = {"track_id": track.id}
            if kind == "lyrics":
                # Preserve original payload shape: lyrics emits status, artwork does not.
                payload["status"] = status
            event_bus.emit(progress, payload)
        event_bus.emit(complete, counters)

    @staticmethod
    def _bucket(kind: str, status) -> str:
        """Map a per-track fetch return value to its counter bucket.

        Preserves the original per-kind semantics:
        - lyrics: NOT_FETCHED / None / unknown -> ``errors``; everything else uses its own bucket.
        - artwork: EMBEDDED -> ``embedded``; everything else -> ``not_found``.
        """
        if kind == "lyrics":
            if status in (None, LyricsStatus.NOT_FETCHED, LyricsStatus.NOT_FETCHED.value):
                return "errors"
            return status if status in _BATCH_EVENTS["lyrics"][3] else "errors"
        # artwork
        if status in (ArtworkStatus.EMBEDDED, ArtworkStatus.EMBEDDED.value):
            return "embedded"
        return "not_found"

    # ── Timer management ─────────────────────────────────────────────────────

    def apply_settings(self) -> None:
        for kind, timer in list(self._timers.items()):
            timer.cancel()
        self._timers.clear()
        if get_setting(self._conn, "enrich_repeat_lyrics") == "true":
            self._schedule("lyrics")
        if get_setting(self._conn, "enrich_repeat_artwork") == "true":
            self._schedule("artwork")

    def shutdown(self) -> None:
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()

    def _schedule(self, kind: str) -> None:
        runner = self.run_lyrics if kind == "lyrics" else self.run_artwork
        timer = threading.Timer(self._interval_secs(), runner)
        timer.daemon = True
        self._timers[kind] = timer
        timer.start()

    def _reschedule(self, kind: str) -> None:
        flag = "enrich_repeat_lyrics" if kind == "lyrics" else "enrich_repeat_artwork"
        if get_setting(self._conn, flag) == "true":
            self._schedule(kind)

    def _interval_secs(self) -> float:
        return float(get_setting(self._conn, "enrich_interval_days") or "1") * 86400
```

- [ ] **Step 4: Strip the batch loop from `LRCLibService`**

In `src/services/lrclib_service.py`, delete:
- `self._running = threading.Event()` from `__init__`
- `fetch_missing_lyrics` method
- `_run_batch` method
- `import threading` (no longer needed if no other use; check first)
- the `from src.database.database import ... get_tracks_to_enrich` import (no longer needed here)
- the `from src.utils.event_bus import event_bus` import (no longer needed here)

Keep: `fetch_and_embed`, `fetch_and_embed_async`, `get_lyrics`.

The class should now look like:

```python
class LRCLibService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._fetcher = LRCLibFetcher()
        self._embedder = LyricsEmbedder()

    def fetch_and_embed(self, track_id: int) -> str | None:
        ...  # body from Task 5 unchanged

    def fetch_and_embed_async(self, track_id: int) -> None:
        threading.Thread(target=self.fetch_and_embed, args=(track_id,), daemon=True).start()

    def get_lyrics(self, track_id: int) -> dict | None:
        ...  # unchanged
```

Re-add `import threading` (still needed for `fetch_and_embed_async`).

- [ ] **Step 5: Update `ClaudeFMAPI.fetch_missing_lyrics` to call the scheduler**

In `src/api/api.py`, change:

```python
@_api_method
def fetch_missing_lyrics(self):
    self._get_enrichment().run_lyrics()
```

(Was previously calling `self._get_lrclib().fetch_missing_lyrics()`.) The frontend-facing behavior is identical — same event names, same single-flight guard.

- [ ] **Step 6: Delete obsolete LRCLibService tests**

In `tests/test_lrclib_service.py`, delete:
- `test_fetch_missing_only_processes_not_fetched`
- `test_fetch_missing_runs_in_background`
- `test_fetch_missing_second_call_ignored_while_running`
- `test_fetch_missing_emits_progress_per_track`
- `test_fetch_missing_emits_complete_with_summary`
- `test_fetch_missing_no_tracks`
- `test_fetch_missing_per_track_exception_counted_as_error`
- `test_fetch_missing_running_flag_cleared_after_completion`
- `test_fetch_missing_lyrics_uses_retry_not_found_query`
- `test_run_batch_emits_enrichment_lyrics_started`

(All batch-loop behavior is now owned by `EnrichmentScheduler`; equivalent tests already added in Step 1.)

Remove the now-unused imports at the top of `tests/test_lrclib_service.py`:

```python
# Drop:
#   import threading
#   from src.services.lrclib_service import LRCLibService  -> keep
# Keep everything else used by surviving fetch_and_embed + get_lyrics tests.
```

- [ ] **Step 7: Update `tests/test_api.py::test_fetch_missing_lyrics_returns_ok`**

It currently patches `LRCLibService.fetch_missing_lyrics`. Repoint it to `EnrichmentScheduler.run_lyrics`:

```python
def test_fetch_missing_lyrics_returns_ok(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.EnrichmentScheduler") as MockSched:
        result = json.loads(api.fetch_missing_lyrics())

    assert result["success"] is True
    MockSched.return_value.run_lyrics.assert_called_once()
```

- [ ] **Step 8: Drop the obsolete `test_run_lyrics_calls_fetch_missing_with_retry_days` and `test_run_lyrics_uses_default_retry_days` from `tests/test_enrichment_scheduler.py`**

The scheduler no longer delegates to `lrclib.fetch_missing_lyrics`. The new tests added in Step 1 cover the contract.

- [ ] **Step 9: Run full test suite**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```
git add src/services/lrclib_service.py src/services/enrichment_scheduler.py src/api/api.py tests/
git commit -m "refactor(enrichment): move lyrics batch loop into EnrichmentScheduler"
```

---

## Task 7: Parameterize the per-kind timer pair into `_timers` dict

**Files:**
- Modify: `tests/test_enrichment_scheduler.py`

### Context

After Task 6, `EnrichmentScheduler` already stores timers in `self._timers: dict[str, threading.Timer]` and uses `_schedule(kind)` instead of `_schedule_lyrics`/`_schedule_artwork`. The remaining work is to fix any tests that still poke the deleted attributes `_lyrics_timer` / `_artwork_timer`.

- [ ] **Step 1: Update `test_shutdown_cancels_active_timers`**

Replace in `tests/test_enrichment_scheduler.py`:

```python
def test_shutdown_cancels_active_timers(svc):
    scheduler, _, _, _ = svc
    mock_timer = MagicMock()
    scheduler._timers = {"lyrics": mock_timer, "artwork": mock_timer}

    scheduler.shutdown()

    assert mock_timer.cancel.call_count == 2
    assert scheduler._timers == {}
```

- [ ] **Step 2: Run scheduler tests**

```
.venv/Scripts/python.exe -m pytest tests/test_enrichment_scheduler.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```
git add tests/test_enrichment_scheduler.py
git commit -m "test(enrichment): update timer-dict expectations after scheduler refactor"
```

---

## Final verification

- [ ] **Run the full test suite one last time**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: 245+ tests pass (count may shift up or down by 5-10 as obsolete tests are removed and new ones added).

- [ ] **Smoke-test the app**

```
.venv/Scripts/python.exe app.py
```

Manually verify:
- App launches; library page lists tracks.
- Play a track; pause/resume works; next/prev works.
- Open Settings; toggle "Auto-fetch lyrics" off then on; confirm persists.
- Trigger "Fetch missing lyrics" from Settings — observe topbar activity badge update.
- Close the window — relaunch — verify last track + position restored.

- [ ] **Update `CLAUDE.md`**

Update the "Architecture Decisions" table to reflect:
- `_api_method` decorator (note the rationale + raw mode)
- `EnrichmentScheduler` owns both lyrics and artwork batch loops
- `set_enrichment_status(track_id, kind, status)` + `get_tracks_to_enrich(kind)` generalized helpers

Update the directory-structure section if any public-method-count comments now drift.

```
git add CLAUDE.md
git commit -m "docs(claude): record backend refactor decisions"
```
