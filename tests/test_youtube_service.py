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
