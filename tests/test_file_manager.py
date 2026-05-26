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
