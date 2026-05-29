# tests/test_lrclib_service.py
import threading
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from src.database.database import init_db, insert_track, get_track, set_enrichment_status, update_track_status
from src.models.enums import LyricsStatus
from src.models.track import Track
from src.services.lrclib_service import LRCLibService


def _make_track(db_conn, **kwargs):
    defaults = dict(
        title="Creep", artist="Radiohead", album="Pablo Honey",
        duration=238, file_path="/tmp/creep.m4a",
        download_status="completed", file_status="available",
    )
    defaults.update(kwargs)
    return insert_track(db_conn, Track(**defaults))


def _make_lrclib_result(synced=None, plain=None, instrumental=False):
    r = MagicMock()
    r.instrumental = instrumental
    r.syncedLyrics = synced
    r.plainLyrics = plain
    return r


# ── fetch_and_embed ──────────────────────────────────────────────────────────

def test_fetch_and_embed_synced_lyrics(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)
    result = _make_lrclib_result(synced="[00:01.00] I'm a creep", plain="I'm a creep")

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile") as MockAF:
        MockLRC.return_value.get.return_value = result
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(track_id)

    assert status == "synchronized"
    assert get_track(db_conn, track_id).lyrics_status == "synchronized"
    MockAF.return_value.set_lyrics.assert_called_once_with(
        state="synced", lyrics="[00:01.00] I'm a creep"
    )


def test_fetch_and_embed_plain_lyrics_only(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)
    result = _make_lrclib_result(synced=None, plain="I'm a creep")

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile") as MockAF:
        MockLRC.return_value.get.return_value = result
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(track_id)

    assert status == "plain_text"
    assert get_track(db_conn, track_id).lyrics_status == "plain_text"
    MockAF.return_value.set_lyrics.assert_called_once_with(
        state="unsynced", lyrics="I'm a creep"
    )


def test_fetch_and_embed_instrumental(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)
    result = _make_lrclib_result(instrumental=True)

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile") as MockAF:
        MockLRC.return_value.get.return_value = result
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(track_id)

    assert status == "instrumental"
    assert get_track(db_conn, track_id).lyrics_status == "instrumental"
    MockAF.return_value.set_lyrics.assert_not_called()


def test_fetch_and_embed_get_none_search_succeeds(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)
    result = _make_lrclib_result(synced="[00:01.00] I'm a creep")

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile"):
        MockLRC.return_value.get.return_value = None
        MockLRC.return_value.search.return_value = [result]
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(track_id)

    assert status == "synchronized"
    MockLRC.return_value.search.assert_called_once_with(track="Creep", artist="Radiohead")


def test_fetch_and_embed_both_fail(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile"):
        MockLRC.return_value.get.return_value = None
        MockLRC.return_value.search.return_value = []
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(track_id)

    assert status == "not_found"
    assert get_track(db_conn, track_id).lyrics_status == "not_found"


def test_fetch_and_embed_no_duration_skips_get(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn, duration=None)
    result = _make_lrclib_result(synced="[00:01.00] line")

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile"):
        MockLRC.return_value.search.return_value = [result]
        svc = LRCLibService(db_conn)
        svc.fetch_and_embed(track_id)

    MockLRC.return_value.get.assert_not_called()
    MockLRC.return_value.search.assert_called_once()


def test_fetch_and_embed_network_error_on_get(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile"):
        MockLRC.return_value.get.side_effect = Exception("network error")
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(track_id)

    assert status == "not_fetched"
    assert get_track(db_conn, track_id).lyrics_status == "not_fetched"


def test_fetch_and_embed_network_error_on_search(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn, duration=None)

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile"):
        MockLRC.return_value.search.side_effect = Exception("network error")
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(track_id)

    assert status == "not_fetched"
    assert get_track(db_conn, track_id).lyrics_status == "not_fetched"


def test_fetch_and_embed_no_file_path(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn, file_path=None)

    with patch("src.services.lrclib_service.LRCLib") as MockLRC:
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(track_id)

    assert status is None
    MockLRC.return_value.get.assert_not_called()


def test_fetch_and_embed_track_not_in_db(db_conn):
    init_db(db_conn)

    with patch("src.services.lrclib_service.LRCLib") as MockLRC:
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(9999)

    assert status is None
    MockLRC.return_value.get.assert_not_called()


def test_fetch_and_embed_unsupported_format(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn, file_path="/tmp/creep.wav")
    result = _make_lrclib_result(synced="[00:01.00] line")

    from lrcup.audio import UnsupportedSuffix

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile") as MockAF:
        MockLRC.return_value.get.return_value = result
        MockAF.return_value.set_lyrics.side_effect = UnsupportedSuffix("unsupported")
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(track_id)

    assert status == "not_supported"
    assert get_track(db_conn, track_id).lyrics_status == "not_supported"


def test_fetch_and_embed_no_lyrics_fields(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)
    result = _make_lrclib_result(synced=None, plain=None)

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile"):
        MockLRC.return_value.get.return_value = result
        svc = LRCLibService(db_conn)
        status = svc.fetch_and_embed(track_id)

    assert status == "not_found"


def test_fetch_and_embed_album_none_passes_empty_string(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn, album=None, duration=120)
    result = _make_lrclib_result(synced="[00:01.00] line")

    with patch("src.services.lrclib_service.LRCLib") as MockLRC, \
         patch("src.services.lrclib_service.AudioFile"):
        MockLRC.return_value.get.return_value = result
        svc = LRCLibService(db_conn)
        svc.fetch_and_embed(track_id)

    MockLRC.return_value.get.assert_called_once_with(
        track="Creep", artist="Radiohead", album="", duration=120
    )


# ── fetch_and_embed_async ────────────────────────────────────────────────────

def test_fetch_and_embed_async_spawns_daemon_thread(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)
    done = threading.Event()

    def fake_embed(tid):
        done.set()

    svc = LRCLibService(db_conn)
    with patch.object(svc, "fetch_and_embed", side_effect=fake_embed):
        svc.fetch_and_embed_async(track_id)

    assert done.wait(timeout=2), "fetch_and_embed_async did not call fetch_and_embed"


# ── get_lyrics ────────────────────────────────────────────────────────────────

def test_get_lyrics_returns_embedded_text_and_status(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)
    set_enrichment_status(db_conn, track_id, "lyrics", "synchronized")

    with patch("src.services.lrclib_service.AudioFile") as MockAF:
        MockAF.return_value.get_lyrics.return_value = "[00:01.00] I'm a creep"
        svc = LRCLibService(db_conn)
        result = svc.get_lyrics(track_id)

    assert result == {"lyrics": "[00:01.00] I'm a creep", "lyrics_status": "synchronized"}


def test_get_lyrics_no_tag_returns_none_lyrics(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)

    with patch("src.services.lrclib_service.AudioFile") as MockAF:
        MockAF.return_value.get_lyrics.return_value = None
        svc = LRCLibService(db_conn)
        result = svc.get_lyrics(track_id)

    assert result["lyrics"] is None
    assert result["lyrics_status"] == "not_fetched"


def test_get_lyrics_no_file_path(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn, file_path=None)

    svc = LRCLibService(db_conn)
    result = svc.get_lyrics(track_id)

    assert result is None


def test_get_lyrics_track_not_found(db_conn):
    init_db(db_conn)

    svc = LRCLibService(db_conn)
    result = svc.get_lyrics(9999)

    assert result is None


def test_get_lyrics_file_error_returns_none(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)

    with patch("src.services.lrclib_service.AudioFile") as MockAF:
        MockAF.return_value.get_lyrics.side_effect = Exception("io error")
        svc = LRCLibService(db_conn)
        result = svc.get_lyrics(track_id)

    assert result is None


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


