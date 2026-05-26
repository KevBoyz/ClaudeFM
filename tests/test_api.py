# tests/test_api.py
import json
from unittest.mock import MagicMock, patch
from src.database.database import init_db, insert_track
from src.database.config_manager import set_setting
from src.models.track import Track
from src.api.api import ClaudeFMAPI


def _make_api(db_conn, tmp_path):
    set_setting(db_conn, "download_folder", str(tmp_path))
    set_setting(db_conn, "lastfm_api_key", "fakekey")
    api = ClaudeFMAPI(db_conn)
    return api


def test_get_library_returns_tracks(db_conn, tmp_path):
    init_db(db_conn)
    insert_track(db_conn, Track(title="Song A", artist="Artist X"))
    api = _make_api(db_conn, tmp_path)
    result = api.get_library("{}")
    parsed = json.loads(result)
    assert len(parsed) == 1
    assert parsed[0]["title"] == "Song A"


def test_get_settings_returns_dict(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_settings())
    assert "audio_format" in result
    assert result["audio_format"] == "m4a"


def test_save_setting_persists(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    api.save_setting("audio_format", "mp3")
    result = json.loads(api.get_settings())
    assert result["audio_format"] == "mp3"


def test_create_playlist(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.create_playlist("My Mix", "manual"))
    assert result["success"] is True
    assert "id" in result


def test_get_playlists_returns_list(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    api.create_playlist("Test", "manual")
    result = json.loads(api.get_playlists())
    assert len(result) == 1
    assert result[0]["name"] == "Test"
