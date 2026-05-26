# tests/test_lastfm_service.py
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
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
