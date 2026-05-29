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
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed", file_status="available")
    scheduler._lyrics_running.set()
    scheduler.run_lyrics()
    lrclib.fetch_and_embed.assert_not_called()
    scheduler._lyrics_running.clear()


def test_run_lyrics_per_track_exception_counted_as_error(svc, mocker):
    scheduler, lrclib, _, db_conn = svc
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, tid, download_status="completed", file_status="available")
    lrclib.fetch_and_embed.side_effect = RuntimeError("boom")

    emitted = []
    mocker.patch(
        "src.services.enrichment_scheduler.event_bus.emit",
        side_effect=lambda t, p: emitted.append((t, p)),
    )

    scheduler._run_lyrics_batch()

    complete = next(e[1] for e in emitted if e[0] == "lyrics_fetch_complete")
    assert complete["errors"] == 1
