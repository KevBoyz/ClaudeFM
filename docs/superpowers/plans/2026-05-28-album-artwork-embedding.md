# Album Artwork Embedding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each audio download, fetch the album/artist cover image from Last.fm and embed it into the audio file's metadata tags (M4A `covr` tag, MP3 `APIC` frame).

**Architecture:** A new `CoverArtService` (mirroring `LRCLibService` in structure) owns the orchestration: look up the track in the DB, ask `LastFMService` for a cover URL, download the image bytes via `CoverArtFetcher`, then write them with `CoverArtEmbedder`. `api.py` replaces the single `_lyrics_hook()` with a composite `_post_download_hook()` that chains artwork + lyrics.

**Tech Stack:** `pylast` (already used) for cover URL, `urllib.request` (stdlib) for HTTP download, `mutagen` (already used by lrclib) for tag writing.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/services/cover_art_service.py` | `CoverArtFetcher`, `CoverArtEmbedder`, `CoverArtService` |
| Create | `tests/test_cover_art_service.py` | Unit tests for all three classes |
| Modify | `src/services/lastfm_service.py` | Add `get_cover_image_url(artist, album)` |
| Modify | `tests/test_lastfm_service.py` | Tests for new method |
| Modify | `src/database/config_manager.py` | Add `auto_fetch_artwork: true` to `DEFAULTS` |
| Modify | `src/api/api.py` | Add `_get_cover_art()`, `_post_download_hook()`; replace `_lyrics_hook()` callsites |
| Modify | `src/interface/scripts/pages/settings.js` | Add `auto_fetch_artwork` toggle |

---

## Task 1: CoverArtEmbedder — write cover art to M4A and MP3

**Files:**
- Create: `src/services/cover_art_service.py`
- Create: `tests/test_cover_art_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cover_art_service.py
import pytest
from unittest.mock import MagicMock, call, patch
from src.services.cover_art_service import CoverArtEmbedder


def test_embed_m4a_writes_covr_tag(mocker):
    mock_mp4_cls = mocker.patch('src.services.cover_art_service.MP4')
    mock_cover_cls = mocker.patch('src.services.cover_art_service.MP4Cover')
    mock_audio = MagicMock()
    mock_audio.tags = {}
    mock_mp4_cls.return_value = mock_audio

    CoverArtEmbedder().embed('/music/song.m4a', b'img_bytes')

    mock_mp4_cls.assert_called_once_with('/music/song.m4a')
    mock_cover_cls.assert_called_once_with(b'img_bytes', imageformat=mock_cover_cls.FORMAT_JPEG)
    assert mock_audio.tags['covr'] == [mock_cover_cls.return_value]
    mock_audio.save.assert_called_once()


def test_embed_m4a_adds_tags_when_none(mocker):
    mock_mp4_cls = mocker.patch('src.services.cover_art_service.MP4')
    mocker.patch('src.services.cover_art_service.MP4Cover')
    mock_audio = MagicMock()
    mock_audio.tags = None
    mock_mp4_cls.return_value = mock_audio

    CoverArtEmbedder().embed('/music/song.m4a', b'img')

    mock_audio.add_tags.assert_called_once()


def test_embed_mp3_adds_apic_frame(mocker):
    mock_id3_cls = mocker.patch('src.services.cover_art_service.ID3')
    mock_apic_cls = mocker.patch('src.services.cover_art_service.APIC')
    mock_audio = MagicMock()
    mock_id3_cls.return_value = mock_audio

    CoverArtEmbedder().embed('/music/song.mp3', b'img_bytes')

    mock_apic_cls.assert_called_once_with(mime='image/jpeg', type=3, desc='Cover', data=b'img_bytes')
    mock_audio.add.assert_called_once_with(mock_apic_cls.return_value)
    mock_audio.save.assert_called_once_with('/music/song.mp3')


def test_embed_mp3_creates_new_id3_when_no_header(mocker):
    from mutagen.id3 import ID3NoHeaderError
    mock_id3_cls = mocker.patch('src.services.cover_art_service.ID3')
    mocker.patch('src.services.cover_art_service.APIC')
    fresh_audio = MagicMock()
    # First call (with file_path) raises; second call (empty constructor) returns fresh_audio
    mock_id3_cls.side_effect = [ID3NoHeaderError, fresh_audio]

    CoverArtEmbedder().embed('/music/song.mp3', b'img')

    assert mock_id3_cls.call_count == 2
    fresh_audio.add.assert_called_once()
    fresh_audio.save.assert_called_once_with('/music/song.mp3')


def test_embed_unsupported_format_raises():
    with pytest.raises(ValueError, match="Unsupported format"):
        CoverArtEmbedder().embed('/music/song.flac', b'img')
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/Scripts/python.exe -m pytest tests/test_cover_art_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.services.cover_art_service'`

- [ ] **Step 3: Create `src/services/cover_art_service.py` with `CoverArtEmbedder`**

```python
import sqlite3
import threading
import urllib.request
from pathlib import Path

from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, APIC, ID3NoHeaderError

from src.database.database import get_track
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
    pass  # filled in Task 2


class CoverArtService:
    pass  # filled in Task 4
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/Scripts/python.exe -m pytest tests/test_cover_art_service.py -v
```

Expected: 5 tests pass (the `ID3NoHeaderError` test is a basic smoke test at this point).

- [ ] **Step 5: Commit**

```bash
git add src/services/cover_art_service.py tests/test_cover_art_service.py
git commit -m "feat(cover-art): add CoverArtEmbedder for M4A and MP3"
```

---

## Task 2: CoverArtFetcher — download image bytes from URL

**Files:**
- Modify: `src/services/cover_art_service.py`
- Modify: `tests/test_cover_art_service.py`

- [ ] **Step 1: Add failing tests**

```python
# Add to tests/test_cover_art_service.py
from src.services.cover_art_service import CoverArtFetcher


def test_fetcher_returns_bytes(mocker):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'fake_image'
    mocker.patch(
        'src.services.cover_art_service.urllib.request.urlopen',
        return_value=mock_resp,
    )
    result = CoverArtFetcher().fetch_bytes('http://example.com/cover.jpg')
    assert result == b'fake_image'
    mock_resp.close.assert_called_once()


def test_fetcher_sends_user_agent(mocker):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b''
    captured = {}

    def fake_urlopen(req, timeout):
        captured['req'] = req
        return mock_resp

    mocker.patch('src.services.cover_art_service.urllib.request.urlopen', side_effect=fake_urlopen)
    CoverArtFetcher().fetch_bytes('http://example.com/img.jpg')
    assert 'User-Agent' in captured['req'].headers


def test_fetcher_propagates_exceptions(mocker):
    mocker.patch(
        'src.services.cover_art_service.urllib.request.urlopen',
        side_effect=OSError("timeout"),
    )
    with pytest.raises(OSError):
        CoverArtFetcher().fetch_bytes('http://bad.url/img.jpg')
```

- [ ] **Step 2: Run to verify they fail**

```
.venv/Scripts/python.exe -m pytest tests/test_cover_art_service.py::test_fetcher_returns_bytes -v
```

Expected: `AttributeError: CoverArtFetcher has no attribute 'fetch_bytes'`

- [ ] **Step 3: Replace the `CoverArtFetcher` stub**

```python
class CoverArtFetcher:
    """Download raw image bytes from a URL."""

    def fetch_bytes(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "ClaudeFM/1.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        try:
            return resp.read()
        finally:
            resp.close()
```

- [ ] **Step 4: Run to verify they pass**

```
.venv/Scripts/python.exe -m pytest tests/test_cover_art_service.py -v
```

Expected: all fetcher tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/services/cover_art_service.py tests/test_cover_art_service.py
git commit -m "feat(cover-art): add CoverArtFetcher for image download"
```

---

## Task 3: LastFMService.get_cover_image_url

**Files:**
- Modify: `src/services/lastfm_service.py`
- Modify: `tests/test_lastfm_service.py`

- [ ] **Step 1: Add failing tests**

```python
# Add to tests/test_lastfm_service.py
import pylast


def test_get_cover_image_url_with_album(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    mock_album = MagicMock()
    mock_album.get_cover_image.return_value = 'https://cdn.com/cover.jpg'
    with patch.object(svc, '_get_network') as mock_net:
        mock_net.return_value.get_album.return_value = mock_album
        url = svc.get_cover_image_url('Radiohead', 'OK Computer')
    assert url == 'https://cdn.com/cover.jpg'
    mock_net.return_value.get_album.assert_called_once_with('Radiohead', 'OK Computer')
    mock_album.get_cover_image.assert_called_once_with(pylast.SIZE_EXTRA_LARGE)


def test_get_cover_image_url_falls_back_to_artist(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    mock_artist = MagicMock()
    mock_artist.get_cover_image.return_value = 'https://cdn.com/artist.jpg'
    with patch.object(svc, '_get_network') as mock_net:
        mock_net.return_value.get_artist.return_value = mock_artist
        url = svc.get_cover_image_url('Radiohead')
    assert url == 'https://cdn.com/artist.jpg'


def test_get_cover_image_url_returns_none_without_api_key(db_conn):
    init_db(db_conn)
    svc = LastFMService(db_conn, api_key='')
    assert svc.get_cover_image_url('Radiohead', 'OK Computer') is None


def test_get_cover_image_url_returns_none_on_api_error(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    with patch.object(svc, '_get_network') as mock_net:
        mock_net.return_value.get_album.side_effect = Exception('API error')
        url = svc.get_cover_image_url('Radiohead', 'OK Computer')
    assert url is None


def test_get_cover_image_url_returns_none_when_empty_string(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    mock_album = MagicMock()
    mock_album.get_cover_image.return_value = ''
    with patch.object(svc, '_get_network') as mock_net:
        mock_net.return_value.get_album.return_value = mock_album
        url = svc.get_cover_image_url('Radiohead', 'OK Computer')
    assert url is None
```

- [ ] **Step 2: Run to verify they fail**

```
.venv/Scripts/python.exe -m pytest tests/test_lastfm_service.py::test_get_cover_image_url_with_album -v
```

Expected: `AttributeError: 'LastFMService' object has no attribute 'get_cover_image_url'`

- [ ] **Step 3: Add `get_cover_image_url` to `LastFMService`**

Add after `get_album_tracks` in `src/services/lastfm_service.py`:

```python
    def get_cover_image_url(self, artist: str, album: str | None = None) -> str | None:
        """Return extra-large cover image URL for an album or artist, or None on failure."""
        if not self._api_key:
            return None
        try:
            net = self._get_network()
            if album:
                url = net.get_album(artist, album).get_cover_image(pylast.SIZE_EXTRA_LARGE)
            else:
                url = net.get_artist(artist).get_cover_image(pylast.SIZE_EXTRA_LARGE)
            return url or None
        except Exception as e:
            log.warning(f"get_cover_image_url {artist!r}/{album!r}: {e}")
            return None
```

- [ ] **Step 4: Run to verify they pass**

```
.venv/Scripts/python.exe -m pytest tests/test_lastfm_service.py -v
```

Expected: all tests pass including the 5 new ones.

- [ ] **Step 5: Commit**

```bash
git add src/services/lastfm_service.py tests/test_lastfm_service.py
git commit -m "feat(cover-art): add get_cover_image_url to LastFMService"
```

---

## Task 4: CoverArtService — orchestration

**Files:**
- Modify: `src/services/cover_art_service.py`
- Modify: `tests/test_cover_art_service.py`

- [ ] **Step 1: Add failing tests**

```python
# Add to tests/test_cover_art_service.py
from src.services.cover_art_service import CoverArtService
from src.database.database import init_db, insert_track
from src.models.track import Track


def test_service_fetches_and_embeds_cover(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="Karma Police", artist="Radiohead", album="OK Computer",
        download_status="completed", file_status="available", file_path="/tmp/song.m4a",
    ))
    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = 'https://cdn.com/cover.jpg'
    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.return_value = b'img'
    svc._embedder = MagicMock()

    result = svc.fetch_and_embed(tid)

    assert result is True
    mock_lastfm.get_cover_image_url.assert_called_once_with("Radiohead", "OK Computer")
    svc._fetcher.fetch_bytes.assert_called_once_with('https://cdn.com/cover.jpg')
    svc._embedder.embed.assert_called_once_with("/tmp/song.m4a", b'img')


def test_service_uses_artist_only_when_no_album(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="Creep", artist="Radiohead",
        download_status="completed", file_status="available", file_path="/tmp/s.m4a",
    ))
    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = 'https://cdn.com/artist.jpg'
    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.return_value = b'img'
    svc._embedder = MagicMock()

    svc.fetch_and_embed(tid)

    mock_lastfm.get_cover_image_url.assert_called_once_with("Radiohead", None)


def test_service_returns_false_when_no_url(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="T", artist="A", download_status="completed",
        file_status="available", file_path="/tmp/s.m4a",
    ))
    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = None
    svc = CoverArtService(db_conn, mock_lastfm)
    svc._embedder = MagicMock()

    assert svc.fetch_and_embed(tid) is False
    svc._embedder.embed.assert_not_called()


def test_service_returns_false_when_no_file_path(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="T", artist="A"))
    mock_lastfm = MagicMock()
    svc = CoverArtService(db_conn, mock_lastfm)

    assert svc.fetch_and_embed(tid) is False
    mock_lastfm.get_cover_image_url.assert_not_called()


def test_service_returns_false_on_fetch_error(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="T", artist="A", download_status="completed",
        file_status="available", file_path="/tmp/s.m4a",
    ))
    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = 'https://cdn.com/img.jpg'
    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.side_effect = OSError("network error")
    svc._embedder = MagicMock()

    assert svc.fetch_and_embed(tid) is False
    svc._embedder.embed.assert_not_called()


def test_service_returns_false_on_embed_error(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="T", artist="A", download_status="completed",
        file_status="available", file_path="/tmp/s.m4a",
    ))
    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = 'https://cdn.com/img.jpg'
    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.return_value = b'img'
    svc._embedder = MagicMock()
    svc._embedder.embed.side_effect = Exception("mutagen error")

    assert svc.fetch_and_embed(tid) is False


def test_service_fetch_and_embed_async_runs_in_thread(db_conn, mocker):
    init_db(db_conn)
    mock_lastfm = MagicMock()
    svc = CoverArtService(db_conn, mock_lastfm)
    mock_embed = mocker.patch.object(svc, 'fetch_and_embed')
    svc.fetch_and_embed_async(99)
    import time; time.sleep(0.05)
    mock_embed.assert_called_once_with(99)
```

- [ ] **Step 2: Run to verify they fail**

```
.venv/Scripts/python.exe -m pytest tests/test_cover_art_service.py::test_service_fetches_and_embeds_cover -v
```

Expected: `AttributeError: 'CoverArtService' has no attribute 'fetch_and_embed'`

- [ ] **Step 3: Replace the `CoverArtService` stub**

```python
class CoverArtService:
    """Fetch a cover image URL from Last.fm, download the bytes, and embed into the audio file."""

    def __init__(self, conn: sqlite3.Connection, lastfm_service) -> None:
        self._conn = conn
        self._lastfm = lastfm_service
        self._fetcher = CoverArtFetcher()
        self._embedder = CoverArtEmbedder()

    def fetch_and_embed(self, track_id: int) -> bool:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return False

        url = self._lastfm.get_cover_image_url(track.artist, track.album)
        if not url:
            log.debug(f"No cover art URL for track {track_id} ({track.artist!r}/{track.album!r})")
            return False

        try:
            image_data = self._fetcher.fetch_bytes(url)
        except Exception as e:
            log.warning(f"Failed to download cover art for track {track_id}: {e}")
            return False

        try:
            self._embedder.embed(track.file_path, image_data)
        except Exception as e:
            log.warning(f"Failed to embed cover art for track {track_id}: {e}")
            return False

        return True

    def fetch_and_embed_async(self, track_id: int) -> None:
        threading.Thread(target=self.fetch_and_embed, args=(track_id,), daemon=True).start()
```

- [ ] **Step 4: Run all cover art tests to verify they pass**

```
.venv/Scripts/python.exe -m pytest tests/test_cover_art_service.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run full suite to confirm no regressions**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/services/cover_art_service.py tests/test_cover_art_service.py
git commit -m "feat(cover-art): add CoverArtService orchestration"
```

---

## Task 5: Wire into api.py and config_manager.py

**Files:**
- Modify: `src/database/config_manager.py` (lines 20–35, `DEFAULTS` dict)
- Modify: `src/api/api.py` (lines 4–11 imports, lines 45–66 `__init__`/lazy getters, lines 68–77 hook)

- [ ] **Step 1: Add `auto_fetch_artwork` to `DEFAULTS` in `config_manager.py`**

In `src/database/config_manager.py`, add `"auto_fetch_artwork": "true"` to the `DEFAULTS` dict, after `"auto_fetch_lyrics"`:

```python
DEFAULTS: dict[str, str] = {
    "lastfm_api_key": "",
    "download_folder": _windows_music_folder(),
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
    "auto_fetch_lyrics": "true",
    "auto_fetch_artwork": "true",
    "player_volume": "1.0",
}
```

- [ ] **Step 2: Add `CoverArtService` import to `api.py`**

In `src/api/api.py`, add to the imports block (after `LRCLibService`):

```python
from src.services.cover_art_service import CoverArtService
```

- [ ] **Step 3: Add `_cover_art` instance variable and lazy getter**

In `ClaudeFMAPI.__init__` (around line 50), add `self._cover_art`:

```python
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._player = PlayerService()
        self._youtube: YouTubeService | None = None
        self._lastfm: LastFMService | None = None
        self._lrclib: LRCLibService | None = None
        self._cover_art: CoverArtService | None = None
```

After `_get_lrclib` (around line 66), add:

```python
    def _get_cover_art(self) -> CoverArtService:
        if self._cover_art is None:
            self._cover_art = CoverArtService(self._conn, self._get_lastfm())
        return self._cover_art
```

- [ ] **Step 4: Replace `_lyrics_hook` with `_post_download_hook`**

Replace the entire `_lyrics_hook` method (lines 68–77) with:

```python
    def _post_download_hook(self):
        """Return a combined callback that runs artwork + lyrics fetching after a download.

        Checks the auto_fetch_artwork and auto_fetch_lyrics settings at call time
        so settings changes take effect on the next download without restarting.
        """
        hooks = []
        if get_setting(self._conn, "auto_fetch_artwork") == "true":
            hooks.append(self._get_cover_art().fetch_and_embed_async)
        if get_setting(self._conn, "auto_fetch_lyrics") == "true":
            hooks.append(self._get_lrclib().fetch_and_embed_async)
        if not hooks:
            return None
        def combined(track_id: int) -> None:
            for h in hooks:
                h(track_id)
        return combined
```

- [ ] **Step 5: Update the two callsites**

Both `queue_download` and `download_lastfm_track` call `on_complete=self._lyrics_hook()`. Replace both with `on_complete=self._post_download_hook()`:

```python
    def queue_download(self, track_id: int) -> str:
        try:
            self._get_youtube().queue_download(track_id, on_complete=self._post_download_hook())
            return _ok()
        except Exception as e:
            log.error(f"queue_download: {e}", exc_info=True)
            return _err(str(e))

    def download_lastfm_track(self, title: str, artist: str, album: str | None = None) -> str:
        """Insert a track stub from Last.fm metadata and immediately queue a download.

        The returned payload includes ``track_id`` so the frontend can track
        download progress events without a separate lookup.
        """
        try:
            t = Track(title=title, artist=artist, album=album)
            track_id = insert_track(self._conn, t)
            self._get_youtube().queue_download(track_id, on_complete=self._post_download_hook())
            return json.dumps({"success": True, "track_id": track_id})
        except Exception as e:
            return _err(str(e))
```

- [ ] **Step 6: Run full test suite to verify no regressions**

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/database/config_manager.py src/api/api.py
git commit -m "feat(cover-art): wire CoverArtService into download pipeline"
```

---

## Task 6: Settings UI toggle

**Files:**
- Modify: `src/interface/scripts/pages/settings.js`

- [ ] **Step 1: Add the toggle HTML row**

In `settings.js`, inside the `<div class="settings-section">` for Library, add the `auto_fetch_artwork` row directly after the `auto_fetch_lyrics` row (after the closing `</div>` of that row, before the closing `</div>` of the section):

```html
        <div class="settings-row">
          <span class="settings-label">Auto-embed cover art</span>
          <div class="settings-field">
            <label class="settings-toggle">
              <input type="checkbox" id="set-autoart" ${_settings.auto_fetch_artwork==='true'?'checked':''}>
              <span class="settings-toggle-track"></span>
            </label>
          </div>
        </div>
```

- [ ] **Step 2: Add to the save handler's Promise.all**

In the `set-save` click handler, add `auto_fetch_artwork` to the `Promise.all` array:

```javascript
        await Promise.all([
          api.save_setting('lastfm_api_key',       document.getElementById('set-apikey').value.trim()),
          api.save_setting('download_folder',       newFolder),
          api.save_setting('audio_format',          fmt),
          api.save_setting('auto_fetch_lyrics',     document.getElementById('set-autolyr').checked ? 'true' : 'false'),
          api.save_setting('auto_fetch_artwork',    document.getElementById('set-autoart').checked ? 'true' : 'false'),
          api.save_setting('search_results_limit',  document.getElementById('set-limit').value),
          api.save_setting('cache_enabled',         document.getElementById('set-cache').checked ? 'true' : 'false'),
          api.save_setting('theme',                 document.getElementById('set-theme').value),
        ]);
```

- [ ] **Step 3: Commit**

```bash
git add src/interface/scripts/pages/settings.js
git commit -m "feat(cover-art): add auto_fetch_artwork toggle to settings UI"
```

---

## Verification

After all tasks complete, run the full test suite one final time:

```
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all tests pass. Then launch the app (`python app.py`), download a track from Last.fm, and verify the downloaded file has a cover image embedded (visible in Windows Explorer thumbnail or any audio player).
