# tests/test_database.py
import sqlite3
import pytest
from src.database.database import init_db, get_connection, insert_track, get_track, update_track_status, get_all_tracks


def test_init_creates_all_tables(db_conn):
    init_db(db_conn)
    tables = {r[0] for r in db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"tracks", "playlists", "playlist_tracks", "settings", "cache"} <= tables


def test_insert_and_get_track(db_conn):
    init_db(db_conn)
    from src.models.track import Track
    t = Track(title="Creep", artist="Radiohead")
    track_id = insert_track(db_conn, t)
    fetched = get_track(db_conn, track_id)
    assert fetched.title == "Creep"
    assert fetched.artist == "Radiohead"
    assert fetched.download_status == "pending"


def test_update_track_status(db_conn):
    init_db(db_conn)
    from src.models.track import Track
    t = Track(title="Paranoid Android", artist="Radiohead")
    track_id = insert_track(db_conn, t)
    update_track_status(db_conn, track_id, download_status="completed", file_status="available")
    fetched = get_track(db_conn, track_id)
    assert fetched.download_status == "completed"


def test_get_all_tracks_returns_list(db_conn):
    init_db(db_conn)
    from src.models.track import Track
    insert_track(db_conn, Track(title="A", artist="X"))
    insert_track(db_conn, Track(title="B", artist="Y"))
    tracks = get_all_tracks(db_conn)
    assert len(tracks) == 2
