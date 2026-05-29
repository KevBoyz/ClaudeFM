# tests/test_api.py
import json
from unittest.mock import MagicMock, patch
from src.database.database import init_db, insert_track, set_enrichment_status, get_all_tracks
from src.database.config_manager import set_setting
from src.models.track import Track
from src.models.playlist import Playlist
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
    set_setting(db_conn, "auto_fetch_artwork", "true")
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.LRCLibService") as MockLrclib, \
         patch("src.api.api.CoverArtService") as MockCoverArt, \
         patch("src.api.api.LastFMService"), \
         patch("src.api.api.YouTubeService") as MockYT:
        lrclib_hook = MockLrclib.return_value.fetch_and_embed_async
        artwork_hook = MockCoverArt.return_value.fetch_and_embed_async
        api.queue_download(track_id)

    call_kwargs = MockYT.return_value.queue_download.call_args
    combined = call_kwargs.kwargs["on_complete"]
    assert combined is not None
    combined(track_id)
    artwork_hook.assert_called_once_with(track_id)
    lrclib_hook.assert_called_once_with(track_id)


def test_queue_download_no_hook_when_auto_fetch_disabled(db_conn, tmp_path):
    init_db(db_conn)
    set_setting(db_conn, "auto_fetch_lyrics", "false")
    set_setting(db_conn, "auto_fetch_artwork", "false")
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    api = _make_api(db_conn, tmp_path)

    with patch("src.api.api.LRCLibService"), \
         patch("src.api.api.YouTubeService") as MockYT:
        api.queue_download(track_id)

    MockYT.return_value.queue_download.assert_called_once_with(
        track_id, on_complete=None
    )


# ── Library queries ───────────────────────────────────────────────────────────

def test_get_track_returns_track(db_conn, tmp_path):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_track(tid))
    assert result["success"] is True
    assert result["data"]["title"] == "Creep"


def test_get_track_not_found(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_track(9999))
    assert result["success"] is False


def test_get_artists_returns_list(db_conn, tmp_path):
    init_db(db_conn)
    insert_track(db_conn, Track(title="A", artist="Radiohead"))
    insert_track(db_conn, Track(title="B", artist="Radiohead"))
    insert_track(db_conn, Track(title="C", artist="Linkin Park"))
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_artists())
    assert len(result) == 2


def test_get_albums_returns_list(db_conn, tmp_path):
    init_db(db_conn)
    insert_track(db_conn, Track(title="A", artist="Radiohead", album="OK Computer"))
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_albums())
    assert len(result) == 1
    assert result[0]["album"] == "OK Computer"


def test_get_tracks_by_artist(db_conn, tmp_path):
    init_db(db_conn)
    insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    insert_track(db_conn, Track(title="Numb", artist="Linkin Park"))
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_tracks_by_artist("Radiohead"))
    assert len(result) == 1
    assert result[0]["title"] == "Creep"


def test_get_tracks_by_album(db_conn, tmp_path):
    init_db(db_conn)
    insert_track(db_conn, Track(title="Creep", artist="Radiohead", album="Pablo Honey"))
    insert_track(db_conn, Track(title="Numb", artist="Linkin Park", album="Hybrid Theory"))
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_tracks_by_album("Pablo Honey", "Radiohead"))
    assert len(result) == 1
    assert result[0]["title"] == "Creep"


def test_search_local_uses_limit_from_settings(db_conn, tmp_path):
    init_db(db_conn)
    for i in range(10):
        insert_track(db_conn, Track(title=f"Song {i}", artist="X"))
    set_setting(db_conn, "search_results_limit", "3")
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.search_local("Song"))
    assert len(result) == 3


def test_search_local_with_explicit_limit(db_conn, tmp_path):
    init_db(db_conn)
    for i in range(5):
        insert_track(db_conn, Track(title=f"Track {i}", artist="X"))
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.search_local("Track", limit=2))
    assert len(result) == 2


# ── Last.fm delegation ────────────────────────────────────────────────────────

def test_search_lastfm_delegates_to_service(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.LastFMService") as MockLFM:
        MockLFM.return_value.search.return_value = [{"type": "artist", "name": "Radiohead"}]
        result = json.loads(api.search_lastfm("radiohead", "artist"))
    assert len(result) == 1
    assert result[0]["name"] == "Radiohead"


def test_get_artist_top_tracks_delegates_to_service(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.LastFMService") as MockLFM:
        MockLFM.return_value.get_artist_top_tracks.return_value = [
            {"type": "track", "title": "Creep", "artist": "Radiohead"}
        ]
        result = json.loads(api.get_artist_top_tracks("Radiohead"))
    assert len(result) == 1
    assert result[0]["title"] == "Creep"


def test_get_album_tracks_delegates_to_service(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.LastFMService") as MockLFM:
        MockLFM.return_value.get_album_tracks.return_value = [
            {"type": "track", "title": "Creep", "artist": "Radiohead", "album": "Pablo Honey"}
        ]
        result = json.loads(api.get_album_tracks("Pablo Honey", "Radiohead"))
    assert len(result) == 1


# ── Downloads ─────────────────────────────────────────────────────────────────

def test_download_lastfm_track_inserts_and_queues(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.YouTubeService"), patch("src.api.api.LRCLibService"):
        result = json.loads(api.download_lastfm_track("Creep", "Radiohead", "Pablo Honey"))
    assert result["success"] is True
    assert "track_id" in result
    tracks = get_all_tracks(db_conn)
    assert len(tracks) == 1
    assert tracks[0].title == "Creep"
    assert tracks[0].artist == "Radiohead"


# ── Playback ──────────────────────────────────────────────────────────────────

def test_play_starts_playback(db_conn, tmp_path):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X", file_path="/music/a.m4a"))
    api = _make_api(db_conn, tmp_path)
    with patch.object(api._player, "play") as mock_play:
        result = json.loads(api.play(tid))
    assert result["success"] is True
    mock_play.assert_called_once_with("/music/a.m4a")


def test_play_returns_error_when_track_not_found(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.play(9999))
    assert result["success"] is False


def test_play_returns_error_when_no_file_path(db_conn, tmp_path):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.play(tid))
    assert result["success"] is False


def test_pause_sets_paused_state(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.pause())
    assert result["success"] is True
    assert api._player.is_paused is True


def test_resume_clears_paused_state(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    api.pause()
    result = json.loads(api.resume())
    assert result["success"] is True
    assert api._player.is_paused is False


def test_get_position_returns_zero_initially(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_position())
    assert result["position"] == 0.0


def test_set_volume(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.set_volume(0.5))
    assert result["success"] is True
    state = json.loads(api.get_player_state())
    assert state["volume"] == 0.5


def test_get_player_state_returns_all_fields(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    result = json.loads(api.get_player_state())
    assert "current_id" in result
    assert "position" in result
    assert "paused" in result
    assert "volume" in result
    assert "ended" in result


def test_seek_delegates_to_player(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch.object(api._player, "seek") as mock_seek:
        result = json.loads(api.seek(30.0))
    assert result["success"] is True
    mock_seek.assert_called_once_with(30.0)


def test_next_track_returns_ended_when_queue_exhausted(db_conn, tmp_path):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X", file_path="/a.m4a"))
    api = _make_api(db_conn, tmp_path)
    api._player.queue.set_context([tid], start_index=0)
    with patch.object(api._player, "play"):
        result = json.loads(api.next_track())
    assert result["success"] is True
    assert result.get("ended") is True


def test_next_track_plays_next(db_conn, tmp_path):
    init_db(db_conn)
    tid1 = insert_track(db_conn, Track(title="A", artist="X", file_path="/a.m4a"))
    tid2 = insert_track(db_conn, Track(title="B", artist="Y", file_path="/b.m4a"))
    api = _make_api(db_conn, tmp_path)
    api._player.queue.set_context([tid1, tid2], start_index=0)
    with patch.object(api._player, "play"):
        result = json.loads(api.next_track())
    assert result["success"] is True
    assert result["track_id"] == tid2


def test_prev_track_at_start_returns_ok(db_conn, tmp_path):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="A", artist="X", file_path="/a.m4a"))
    api = _make_api(db_conn, tmp_path)
    api._player.queue.set_context([tid], start_index=0)
    result = json.loads(api.prev_track())
    assert result["success"] is True


def test_prev_track_plays_previous(db_conn, tmp_path):
    init_db(db_conn)
    tid1 = insert_track(db_conn, Track(title="A", artist="X", file_path="/a.m4a"))
    tid2 = insert_track(db_conn, Track(title="B", artist="Y", file_path="/b.m4a"))
    api = _make_api(db_conn, tmp_path)
    api._player.queue.set_context([tid1, tid2], start_index=1)
    with patch.object(api._player, "play"):
        result = json.loads(api.prev_track())
    assert result["success"] is True
    assert result["track_id"] == tid1


# ── Playlist mutations ────────────────────────────────────────────────────────

def test_get_playlist_tracks(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    pid = json.loads(api.create_playlist("Mix", "manual"))["id"]
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    api.add_to_playlist(pid, tid)
    result = json.loads(api.get_playlist_tracks(pid))
    assert len(result) == 1
    assert result[0]["title"] == "A"


def test_delete_playlist(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    pid = json.loads(api.create_playlist("Temp", "manual"))["id"]
    result = json.loads(api.delete_playlist(pid))
    assert result["success"] is True
    assert json.loads(api.get_playlists()) == []


def test_rename_playlist(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    pid = json.loads(api.create_playlist("Old", "manual"))["id"]
    result = json.loads(api.rename_playlist(pid, "New"))
    assert result["success"] is True
    assert json.loads(api.get_playlists())[0]["name"] == "New"


def test_add_and_remove_from_playlist(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    pid = json.loads(api.create_playlist("Mix", "manual"))["id"]
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    assert json.loads(api.add_to_playlist(pid, tid))["success"] is True
    assert len(json.loads(api.get_playlist_tracks(pid))) == 1
    assert json.loads(api.remove_from_playlist(pid, tid))["success"] is True
    assert len(json.loads(api.get_playlist_tracks(pid))) == 0


def test_create_auto_playlist_enforces_limit(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    ids = []
    for i in range(15):
        r = json.loads(api.create_playlist(f"Auto {i}", "auto"))
        ids.append(r["id"])
    db_conn.execute("UPDATE playlists SET updated_at='2020-01-01' WHERE id=?", (ids[0],))
    db_conn.commit()
    json.loads(api.create_playlist("Auto 16", "auto"))
    auto = [p for p in json.loads(api.get_playlists()) if p["type"] == "auto"]
    assert len(auto) == 15
    assert ids[0] not in [p["id"] for p in auto]


# ── Settings ──────────────────────────────────────────────────────────────────

def test_rescan_library_starts_scan_when_folder_set(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.start_background_scan") as mock_scan:
        result = json.loads(api.rescan_library())
    assert result["success"] is True
    mock_scan.assert_called_once()


def test_rescan_library_skips_scan_when_no_folder(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    set_setting(db_conn, "download_folder", "")
    with patch("src.api.api.start_background_scan") as mock_scan:
        result = json.loads(api.rescan_library())
    assert result["success"] is True
    mock_scan.assert_not_called()


# ── Internet check ────────────────────────────────────────────────────────────

def test_check_internet_online(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("socket.create_connection"):
        result = json.loads(api.check_internet())
    assert result["online"] is True


def test_check_internet_offline(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("socket.create_connection", side_effect=OSError):
        result = json.loads(api.check_internet())
    assert result["online"] is False


# ── _api_method decorator ─────────────────────────────────────────────────────

def test_api_method_returns_err_on_exception(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.log") as mock_log, \
         patch("src.api.api.delete_track", side_effect=RuntimeError("kaboom")):
        result = json.loads(api.remove_from_library(1))
    assert result["success"] is False
    assert "kaboom" in result["error"]
    mock_log.error.assert_called_once()
    msg, *_ = mock_log.error.call_args.args
    assert "remove_from_library" in msg and "kaboom" in msg


def test_api_method_value_error_returns_err_without_error_log(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.log") as mock_log, \
         patch("src.api.api.get_track", side_effect=ValueError("bad input")):
        result = json.loads(api.get_track(1))
    assert result["success"] is False
    assert "bad input" in result["error"]
    # ValueError is user-facing; should not log at ERROR level
    mock_log.error.assert_not_called()


# ── Last.fm connection check ──────────────────────────────────────────────────

def test_check_lastfm_connection_success(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.LastFMService") as MockLFM:
        MockLFM.return_value.search.return_value = []
        result = json.loads(api.check_lastfm_connection())
    assert result["success"] is True


def test_check_lastfm_connection_failure(db_conn, tmp_path):
    init_db(db_conn)
    api = _make_api(db_conn, tmp_path)
    with patch("src.api.api.LastFMService") as MockLFM:
        MockLFM.return_value.search.side_effect = Exception("Network error")
        result = json.loads(api.check_lastfm_connection())
    assert result["success"] is False
