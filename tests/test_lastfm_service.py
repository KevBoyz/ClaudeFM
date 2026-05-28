# tests/test_lastfm_service.py
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import pylast
from src.database.database import init_db
from src.services.lastfm_service import LastFMService


def _make_service(db_conn, api_key="fakekey"):
    return LastFMService(db_conn, api_key)


def test_search_returns_empty_list_when_no_api_key(db_conn):
    init_db(db_conn)
    svc = LastFMService(db_conn, api_key="")
    result = svc.search("radiohead", "artist")
    assert result == []


def test_cache_hit_skips_api_call(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    cached = json.dumps([{"name": "Radiohead", "type": "artist"}])
    expires = (datetime.now() + timedelta(days=1)).isoformat()
    db_conn.execute(
        "INSERT INTO cache (key, response, cached_at, expires_at) VALUES (?,?,?,?)",
        ("search:artist:radiohead", cached, datetime.now().isoformat(), expires),
    )
    db_conn.commit()
    with patch("pylast.LastFMNetwork") as mock_net:
        result = svc.search("radiohead", "artist")
    mock_net.assert_not_called()
    assert result[0]["name"] == "Radiohead"


def test_expired_cache_calls_api(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    cached = json.dumps([{"name": "Old"}])
    expired = (datetime.now() - timedelta(days=1)).isoformat()
    db_conn.execute(
        "INSERT INTO cache (key, response, cached_at, expires_at) VALUES (?,?,?,?)",
        ("search:artist:radiohead", cached, expired, expired),
    )
    db_conn.commit()
    mock_result = MagicMock()
    mock_result.get_name.return_value = "Radiohead"
    mock_result.get_mbid.return_value = "abc123"
    mock_result.get_listener_count.return_value = 5000000
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.search_for_artist.return_value.get_next_page.return_value = [mock_result]
        result = svc.search("radiohead", "artist")
    assert len(result) > 0


# ── Cache internals ───────────────────────────────────────────────────────────

def test_cache_key_normalizes_to_lowercase(db_conn):
    svc = _make_service(db_conn)
    key = svc._cache.key("Search", "ARTIST", "Radiohead")
    assert key == "search:artist:radiohead"


def test_cache_key_joins_parts_with_colon(db_conn):
    svc = _make_service(db_conn)
    assert svc._cache.key("a", "b", "c") == "a:b:c"


def test_get_cache_returns_none_when_missing(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    assert svc._cache.get("nonexistent:key") is None


def test_set_cache_and_get_cache_roundtrip(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    data = [{"type": "artist", "name": "Radiohead"}]
    svc._cache.set("test:key", data)
    result = svc._cache.get("test:key")
    assert result == data


def test_get_cache_deletes_expired_entry(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    expired = (datetime.now() - timedelta(days=1)).isoformat()
    db_conn.execute(
        "INSERT INTO cache (key, response, cached_at, expires_at) VALUES (?,?,?,?)",
        ("old:key", json.dumps([{"x": 1}]), expired, expired),
    )
    db_conn.commit()
    result = svc._cache.get("old:key")
    assert result is None
    row = db_conn.execute("SELECT key FROM cache WHERE key='old:key'").fetchone()
    assert row is None


def test_set_cache_upserts_existing_key(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    svc._cache.set("k", [{"v": 1}])
    svc._cache.set("k", [{"v": 2}])
    result = svc._cache.get("k")
    assert result == [{"v": 2}]


# ── Search with mocked network ────────────────────────────────────────────────

def test_search_artists_returns_formatted_results(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    mock_artist = MagicMock()
    mock_artist.get_name.return_value = "Radiohead"
    mock_artist.get_mbid.return_value = "abc123"
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.search_for_artist.return_value.get_next_page.return_value = [mock_artist]
        result = svc.search("radiohead", "artist", limit=1)
    assert len(result) == 1
    assert result[0]["type"] == "artist"
    assert result[0]["name"] == "Radiohead"
    assert result[0]["mbid"] == "abc123"


def test_search_tracks_returns_formatted_results(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    mock_track = MagicMock()
    mock_track.get_name.return_value = "Creep"
    mock_track.get_artist.return_value.get_name.return_value = "Radiohead"
    mock_track.get_mbid.return_value = "xyz"
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.search_for_track.return_value.get_next_page.return_value = [mock_track]
        result = svc.search("creep", "track", limit=1)
    assert result[0]["type"] == "track"
    assert result[0]["title"] == "Creep"
    assert result[0]["artist"] == "Radiohead"


def test_search_albums_returns_formatted_results(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    mock_album = MagicMock()
    mock_album.get_name.return_value = "OK Computer"
    mock_album.get_artist.return_value.get_name.return_value = "Radiohead"
    mock_album.get_mbid.return_value = "abc"
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.search_for_album.return_value.get_next_page.return_value = [mock_album]
        result = svc.search("ok computer", "album", limit=1)
    assert result[0]["type"] == "album"
    assert result[0]["title"] == "OK Computer"
    assert result[0]["artist"] == "Radiohead"


def test_search_caches_api_results(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    mock_artist = MagicMock()
    mock_artist.get_name.return_value = "Radiohead"
    mock_artist.get_mbid.return_value = "abc"
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.search_for_artist.return_value.get_next_page.return_value = [mock_artist]
        svc.search("radiohead", "artist")
        svc.search("radiohead", "artist")  # second call should hit cache
    assert mock_net.call_count == 1


def test_search_api_exception_returns_empty_list(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.search_for_artist.side_effect = Exception("Network error")
        result = svc.search("anything", "artist")
    assert result == []


# ── get_artist_top_tracks ─────────────────────────────────────────────────────

def test_get_artist_top_tracks_cache_hit(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    cached = [{"type": "track", "title": "Creep", "artist": "Radiohead"}]
    svc._cache.set("top_tracks:radiohead", cached)
    with patch.object(svc, "_get_network") as mock_net:
        result = svc.get_artist_top_tracks("Radiohead")
    mock_net.assert_not_called()
    assert result == cached


def test_get_artist_top_tracks_fetches_from_api(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    mock_item = MagicMock()
    mock_item.item.get_name.return_value = "Creep"
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.get_artist.return_value.get_top_tracks.return_value = [mock_item]
        result = svc.get_artist_top_tracks("Radiohead", limit=1)
    assert len(result) == 1
    assert result[0]["title"] == "Creep"
    assert result[0]["artist"] == "Radiohead"


def test_get_artist_top_tracks_api_error_returns_empty(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.get_artist.side_effect = Exception("API error")
        result = svc.get_artist_top_tracks("Nobody")
    assert result == []


# ── get_album_tracks ──────────────────────────────────────────────────────────

def test_get_album_tracks_cache_hit(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    cached = [{"type": "track", "title": "Creep", "artist": "Radiohead", "album": "Pablo Honey"}]
    svc._cache.set("album_tracks:radiohead:pablo honey", cached)
    with patch.object(svc, "_get_network") as mock_net:
        result = svc.get_album_tracks("Pablo Honey", "Radiohead")
    mock_net.assert_not_called()
    assert result == cached


def test_get_album_tracks_fetches_from_api(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    mock_track = MagicMock()
    mock_track.get_name.return_value = "Creep"
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.get_album.return_value.get_tracks.return_value = [mock_track]
        result = svc.get_album_tracks("Pablo Honey", "Radiohead")
    assert len(result) == 1
    assert result[0]["title"] == "Creep"
    assert result[0]["album"] == "Pablo Honey"


def test_get_album_tracks_api_error_returns_empty(db_conn):
    init_db(db_conn)
    svc = _make_service(db_conn)
    with patch.object(svc, "_get_network") as mock_net:
        mock_net.return_value.get_album.side_effect = Exception("API error")
        result = svc.get_album_tracks("Ghost Album", "Nobody")
    assert result == []


# ── get_cover_image_url ───────────────────────────────────────────────────────

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
