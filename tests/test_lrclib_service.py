# tests/test_lrclib_service.py
import threading
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from src.database.database import init_db, insert_track, get_track, update_lyrics_status, update_track_status
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


# ── _run_batch / fetch_missing_lyrics ───────────────────────────────────────

def test_fetch_missing_only_processes_not_fetched(db_conn):
    init_db(db_conn)
    id1 = _make_track(db_conn, title="A")
    id2 = _make_track(db_conn, title="B")
    update_lyrics_status(db_conn, id2, "synchronized")

    processed = []

    def fake_embed(tid):
        processed.append(tid)
        return "synchronized"

    with patch("src.services.lrclib_service.event_bus"):
        svc = LRCLibService(db_conn)
        with patch.object(svc, "fetch_and_embed", side_effect=fake_embed):
            svc._run_batch()

    assert id1 in processed
    assert id2 not in processed


def test_fetch_missing_runs_in_background(db_conn):
    init_db(db_conn)
    svc = LRCLibService(db_conn)
    called = threading.Event()

    def fake_batch(*args, **kwargs):
        called.set()

    with patch.object(svc, "_run_batch", side_effect=fake_batch):
        svc.fetch_missing_lyrics()

    assert called.wait(timeout=2), "fetch_missing_lyrics did not run in background"


def test_fetch_missing_second_call_ignored_while_running(db_conn):
    init_db(db_conn)
    svc = LRCLibService(db_conn)
    call_count = 0
    blocker = threading.Event()

    def slow_batch(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        blocker.wait(timeout=2)
        svc._running.clear()

    with patch.object(svc, "_run_batch", side_effect=slow_batch):
        svc.fetch_missing_lyrics()
        svc.fetch_missing_lyrics()

    blocker.set()
    import time; time.sleep(0.1)
    assert call_count == 1


def test_fetch_missing_emits_progress_per_track(db_conn):
    init_db(db_conn)
    id1 = _make_track(db_conn, title="A")
    id2 = _make_track(db_conn, title="B")

    def fake_embed(tid):
        return "synchronized"

    with patch("src.services.lrclib_service.event_bus") as mock_eb:
        svc = LRCLibService(db_conn)
        with patch.object(svc, "fetch_and_embed", side_effect=fake_embed):
            svc._run_batch()

    progress_calls = [
        c for c in mock_eb.emit.call_args_list
        if c.args[0] == "lyrics_progress"
    ]
    track_ids = [c.args[1]["track_id"] for c in progress_calls]
    assert id1 in track_ids
    assert id2 in track_ids


def test_fetch_missing_emits_complete_with_summary(db_conn):
    init_db(db_conn)
    _make_track(db_conn, title="A")
    _make_track(db_conn, title="B")

    results = iter(["synchronized", "plain_text"])

    def fake_embed(tid):
        return next(results)

    with patch("src.services.lrclib_service.event_bus") as mock_eb:
        svc = LRCLibService(db_conn)
        with patch.object(svc, "fetch_and_embed", side_effect=fake_embed):
            svc._run_batch()

    complete_call = [
        c for c in mock_eb.emit.call_args_list
        if c.args[0] == "lyrics_fetch_complete"
    ]
    assert len(complete_call) == 1
    payload = complete_call[0].args[1]
    assert payload["synchronized"] == 1
    assert payload["plain_text"] == 1
    assert payload["errors"] == 0


def test_fetch_missing_no_tracks(db_conn):
    init_db(db_conn)

    with patch("src.services.lrclib_service.event_bus") as mock_eb:
        svc = LRCLibService(db_conn)
        svc._run_batch()

    complete_call = [
        c for c in mock_eb.emit.call_args_list
        if c.args[0] == "lyrics_fetch_complete"
    ]
    assert len(complete_call) == 1
    payload = complete_call[0].args[1]
    assert all(v == 0 for v in payload.values())


def test_fetch_missing_per_track_exception_counted_as_error(db_conn):
    init_db(db_conn)
    _make_track(db_conn, title="A")

    def bad_embed(tid):
        raise RuntimeError("unexpected")

    with patch("src.services.lrclib_service.event_bus") as mock_eb:
        svc = LRCLibService(db_conn)
        with patch.object(svc, "fetch_and_embed", side_effect=bad_embed):
            svc._run_batch()

    complete_call = [
        c for c in mock_eb.emit.call_args_list
        if c.args[0] == "lyrics_fetch_complete"
    ]
    assert complete_call[0].args[1]["errors"] == 1


def test_fetch_missing_running_flag_cleared_after_completion(db_conn):
    init_db(db_conn)
    svc = LRCLibService(db_conn)

    with patch("src.services.lrclib_service.event_bus"):
        svc._run_batch()

    assert not svc._running.is_set()


# ── get_lyrics ────────────────────────────────────────────────────────────────

def test_get_lyrics_returns_embedded_text_and_status(db_conn):
    init_db(db_conn)
    track_id = _make_track(db_conn)
    update_lyrics_status(db_conn, track_id, "synchronized")

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
