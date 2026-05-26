# tests/test_api.py
import json
from unittest.mock import MagicMock, patch
from src.database.database import init_db, insert_track, update_lyrics_status
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


# ── Lyrics API ────────────────────────────────────────────────────────────────

def test_fetch_lyrics_returns_lyrics_status(db_conn, tmp_path):
    init_db(db_conn)
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead", file_path="/tmp/creep.m4a"))
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.LRCLibService") as MockSvc:
        MockSvc.return_value.fetch_and_embed.return_value = "synchronized"
        result = json.loads(api.fetch_lyrics(track_id))

    assert result["success"] is True
    assert result["data"]["lyrics_status"] == "synchronized"


def test_fetch_lyrics_unknown_track(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.LRCLibService") as MockSvc:
        MockSvc.return_value.fetch_and_embed.return_value = None
        result = json.loads(api.fetch_lyrics(9999))

    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_fetch_missing_lyrics_returns_ok(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.LRCLibService") as MockSvc:
        result = json.loads(api.fetch_missing_lyrics())

    assert result["success"] is True
    MockSvc.return_value.fetch_missing_lyrics.assert_called_once()


def test_get_lyrics_returns_text_and_status(db_conn, tmp_path):
    init_db(db_conn)
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead", file_path="/tmp/creep.m4a"))
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.LRCLibService") as MockSvc:
        MockSvc.return_value.get_lyrics.return_value = {
            "lyrics": "[00:01.00] I'm a creep",
            "lyrics_status": "synchronized",
        }
        result = json.loads(api.get_lyrics(track_id))

    assert result["success"] is True
    assert result["data"]["lyrics"] == "[00:01.00] I'm a creep"
    assert result["data"]["lyrics_status"] == "synchronized"


def test_get_lyrics_no_lyrics(db_conn, tmp_path):
    init_db(db_conn)
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead", file_path="/tmp/creep.m4a"))
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.LRCLibService") as MockSvc:
        MockSvc.return_value.get_lyrics.return_value = {
            "lyrics": None,
            "lyrics_status": "not_fetched",
        }
        result = json.loads(api.get_lyrics(track_id))

    assert result["success"] is True
    assert result["data"]["lyrics"] is None


def test_get_lyrics_track_not_found(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.LRCLibService") as MockSvc:
        MockSvc.return_value.get_lyrics.return_value = None
        result = json.loads(api.get_lyrics(9999))

    assert result["success"] is False


def test_queue_download_wires_async_hook_when_auto_fetch_enabled(db_conn, tmp_path):
    init_db(db_conn)
    set_setting(db_conn, "auto_fetch_lyrics", "true")
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.LRCLibService") as MockSvc, \
         patch("src.api.api.YouTubeService") as MockYT:
        expected_hook = MockSvc.return_value.fetch_and_embed_async
        api.queue_download(track_id)

    MockYT.return_value.queue_download.assert_called_once_with(
        track_id, on_complete=expected_hook
    )


def test_queue_download_no_hook_when_auto_fetch_disabled(db_conn, tmp_path):
    init_db(db_conn)
    set_setting(db_conn, "auto_fetch_lyrics", "false")
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.LRCLibService"), \
         patch("src.api.api.YouTubeService") as MockYT:
        api.queue_download(track_id)

    MockYT.return_value.queue_download.assert_called_once_with(
        track_id, on_complete=None
    )
