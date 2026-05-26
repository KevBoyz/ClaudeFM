# tests/test_database.py
import sqlite3
import pytest
from src.database.database import init_db, get_connection, insert_track, get_track, update_track_status, get_all_tracks, update_lyrics_status, get_tracks_without_lyrics


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


def test_lyrics_status_default_not_fetched(db_conn):
    init_db(db_conn)
    from src.models.track import Track
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    fetched = get_track(db_conn, track_id)
    assert fetched.lyrics_status == "not_fetched"


def test_update_lyrics_status(db_conn):
    init_db(db_conn)
    from src.models.track import Track
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    update_lyrics_status(db_conn, track_id, "synchronized")
    fetched = get_track(db_conn, track_id)
    assert fetched.lyrics_status == "synchronized"


def test_get_tracks_without_lyrics_filters_correctly(db_conn):
    init_db(db_conn)
    from src.models.track import Track
    id1 = insert_track(db_conn, Track(title="A", artist="X"))
    id2 = insert_track(db_conn, Track(title="B", artist="X"))
    id3 = insert_track(db_conn, Track(title="C", artist="X"))
    update_lyrics_status(db_conn, id2, "synchronized")
    update_lyrics_status(db_conn, id3, "not_found")
    result = get_tracks_without_lyrics(db_conn)
    ids = [t.id for t in result]
    assert id1 in ids
    assert id2 not in ids
    assert id3 not in ids
