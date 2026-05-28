# tests/test_file_manager.py
import threading
from pathlib import Path
from src.database.database import init_db, get_all_tracks, insert_track
from src.database.file_manager import quick_scan, full_scan, start_background_scan, _get_tag
from src.models.track import Track


def _make_mp3(path: Path) -> None:
    """Create a minimal valid MP3-like file for testing."""
    path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 128)


def test_quick_scan_marks_missing_tracks(db_conn, tmp_music_dir):
    init_db(db_conn)
    t = Track(title="Gone", artist="X", file_path=str(tmp_music_dir / "gone.mp3"),
              download_status="completed", file_status="available")
    insert_track(db_conn, t)

    quick_scan(db_conn)

    tracks = get_all_tracks(db_conn)
    assert tracks[0].file_status == "missing"


def test_quick_scan_leaves_available_tracks_intact(db_conn, tmp_music_dir):
    init_db(db_conn)
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


# ── _get_tag ──────────────────────────────────────────────────────────────────

def test_get_tag_returns_first_matching_key():
    tags = {"TIT2": ["My Song"], "title": ["Fallback"]}
    assert _get_tag(tags, "TIT2", "title", default="Default") == "My Song"


def test_get_tag_falls_back_to_second_key():
    tags = {"title": ["Fallback Title"]}
    assert _get_tag(tags, "TIT2", "title", default="Default") == "Fallback Title"


def test_get_tag_returns_default_when_no_key_found():
    assert _get_tag({}, "TIT2", "title", default="Unknown") == "Unknown"


def test_get_tag_converts_value_to_string():
    tags = {"TIT2": [42]}
    assert _get_tag(tags, "TIT2", default="x") == "42"


# ── full_scan edge cases ──────────────────────────────────────────────────────

def test_full_scan_skips_nonexistent_folder(db_conn, tmp_music_dir):
    init_db(db_conn)
    count = full_scan(db_conn, ["/does/not/exist/at/all"])
    assert count == 0
    assert get_all_tracks(db_conn) == []


def test_full_scan_skips_non_audio_files(db_conn, tmp_music_dir):
    init_db(db_conn)
    (tmp_music_dir / "readme.txt").write_text("not audio")
    (tmp_music_dir / "image.jpg").write_bytes(b"\xff\xd8\xff")
    count = full_scan(db_conn, [str(tmp_music_dir)])
    assert count == 0


def test_full_scan_does_not_duplicate_existing_track(db_conn, tmp_music_dir):
    init_db(db_conn)
    f = tmp_music_dir / "song.mp3"
    _make_mp3(f)
    full_scan(db_conn, [str(tmp_music_dir)])
    count = full_scan(db_conn, [str(tmp_music_dir)])
    assert count == 0
    assert len(get_all_tracks(db_conn)) == 1


def test_full_scan_scans_multiple_folders(db_conn, tmp_path):
    init_db(db_conn)
    folder_a = tmp_path / "a"
    folder_b = tmp_path / "b"
    folder_a.mkdir()
    folder_b.mkdir()
    _make_mp3(folder_a / "song1.mp3")
    _make_mp3(folder_b / "song2.mp3")
    count = full_scan(db_conn, [str(folder_a), str(folder_b)])
    assert count == 2
    assert len(get_all_tracks(db_conn)) == 2


def test_full_scan_returns_added_count(db_conn, tmp_music_dir):
    init_db(db_conn)
    _make_mp3(tmp_music_dir / "a.mp3")
    _make_mp3(tmp_music_dir / "b.mp3")
    count = full_scan(db_conn, [str(tmp_music_dir)])
    assert count == 2


# ── start_background_scan ─────────────────────────────────────────────────────

def test_start_background_scan_returns_daemon_thread(db_conn, tmp_music_dir):
    init_db(db_conn)
    t = start_background_scan(db_conn, [str(tmp_music_dir)])
    assert isinstance(t, threading.Thread)
    assert t.daemon is True
    t.join(timeout=5)
