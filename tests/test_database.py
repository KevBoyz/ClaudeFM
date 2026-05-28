# tests/test_database.py
import pytest
from src.database.database import (
    init_db, insert_track, get_track, update_track_status, get_all_tracks,
    update_lyrics_status, get_tracks_without_lyrics,
    get_tracks_by_artist, get_tracks_by_album, get_all_artists, get_all_albums,
    search_tracks_local,
    insert_playlist, get_all_playlists, get_auto_playlist_count,
    delete_oldest_auto_playlist, get_playlist_tracks, delete_playlist,
    update_playlist_name, add_track_to_playlist, remove_track_from_playlist,
)
from src.models.track import Track
from src.models.playlist import Playlist


def test_init_creates_all_tables(db_conn):
    init_db(db_conn)
    tables = {r[0] for r in db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"tracks", "playlists", "playlist_tracks", "settings", "cache"} <= tables


def test_insert_and_get_track(db_conn):
    init_db(db_conn)
    t = Track(title="Creep", artist="Radiohead")
    track_id = insert_track(db_conn, t)
    fetched = get_track(db_conn, track_id)
    assert fetched.title == "Creep"
    assert fetched.artist == "Radiohead"
    assert fetched.download_status == "pending"


def test_update_track_status(db_conn):
    init_db(db_conn)
    t = Track(title="Paranoid Android", artist="Radiohead")
    track_id = insert_track(db_conn, t)
    update_track_status(db_conn, track_id, download_status="completed", file_status="available")
    fetched = get_track(db_conn, track_id)
    assert fetched.download_status == "completed"


def test_get_all_tracks_returns_list(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="A", artist="X"))
    insert_track(db_conn, Track(title="B", artist="Y"))
    tracks = get_all_tracks(db_conn)
    assert len(tracks) == 2


def test_lyrics_status_default_not_fetched(db_conn):
    init_db(db_conn)
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    fetched = get_track(db_conn, track_id)
    assert fetched.lyrics_status == "not_fetched"


def test_update_lyrics_status(db_conn):
    init_db(db_conn)
    track_id = insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    update_lyrics_status(db_conn, track_id, "synchronized")
    fetched = get_track(db_conn, track_id)
    assert fetched.lyrics_status == "synchronized"


def test_get_tracks_without_lyrics_filters_correctly(db_conn):
    init_db(db_conn)
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


# ── insert_track dedup ─────────────────────────────────────────────────────────

def test_insert_track_dedup_returns_existing_id(db_conn):
    init_db(db_conn)
    t = Track(title="Creep", artist="Radiohead")
    id1 = insert_track(db_conn, t)
    id2 = insert_track(db_conn, t)
    assert id1 == id2
    assert len(get_all_tracks(db_conn)) == 1


# ── update_track_status edge cases ────────────────────────────────────────────

def test_update_track_status_no_kwargs_is_no_op(db_conn):
    init_db(db_conn)
    track_id = insert_track(db_conn, Track(title="A", artist="X"))
    update_track_status(db_conn, track_id)
    assert get_track(db_conn, track_id).download_status == "pending"


# ── get_all_tracks filtering ──────────────────────────────────────────────────

def test_get_all_tracks_invalid_order_by_falls_back(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="A", artist="X"))
    tracks = get_all_tracks(db_conn, order_by="INVALID INJECTION")
    assert len(tracks) == 1


def test_get_all_tracks_filters_by_audio_format(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="A", artist="X", audio_format="m4a"))
    insert_track(db_conn, Track(title="B", artist="Y", audio_format="mp3"))
    result = get_all_tracks(db_conn, audio_format="m4a")
    assert len(result) == 1
    assert result[0].title == "A"


# ── get_tracks_by_artist / album ──────────────────────────────────────────────

def test_get_tracks_by_artist_case_insensitive(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    insert_track(db_conn, Track(title="High and Dry", artist="Radiohead"))
    insert_track(db_conn, Track(title="Numb", artist="Linkin Park"))
    result = get_tracks_by_artist(db_conn, "radiohead")
    assert len(result) == 2
    titles = {t.title for t in result}
    assert titles == {"Creep", "High and Dry"}


def test_get_tracks_by_album_case_insensitive(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="Creep", artist="Radiohead", album="Pablo Honey"))
    insert_track(db_conn, Track(title="High and Dry", artist="Radiohead", album="The Bends"))
    result = get_tracks_by_album(db_conn, "pablo honey", "radiohead")
    assert len(result) == 1
    assert result[0].title == "Creep"


# ── get_all_artists / albums ──────────────────────────────────────────────────

def test_get_all_artists_groups_by_artist(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    insert_track(db_conn, Track(title="OK Computer", artist="Radiohead"))
    insert_track(db_conn, Track(title="Numb", artist="Linkin Park"))
    result = get_all_artists(db_conn)
    assert len(result) == 2
    rh = next(r for r in result if r["artist"] == "Radiohead")
    assert rh["track_count"] == 2


def test_get_all_albums_excludes_null_album(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="Creep", artist="Radiohead", album="Pablo Honey"))
    insert_track(db_conn, Track(title="Anthem", artist="Radiohead", album="Pablo Honey"))
    insert_track(db_conn, Track(title="Single", artist="X", album=None))
    result = get_all_albums(db_conn)
    assert len(result) == 1
    assert result[0]["album"] == "Pablo Honey"
    assert result[0]["track_count"] == 2


# ── search_tracks_local ────────────────────────────────────────────────────────

def test_search_tracks_local_partial_title_match(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="Creep", artist="Radiohead"))
    insert_track(db_conn, Track(title="Creeping Death", artist="Metallica"))
    insert_track(db_conn, Track(title="Numb", artist="Linkin Park"))
    result = search_tracks_local(db_conn, "creep")
    assert len(result) == 2


def test_search_tracks_local_matches_artist(db_conn):
    init_db(db_conn)
    insert_track(db_conn, Track(title="Numb", artist="Linkin Park"))
    result = search_tracks_local(db_conn, "linkin")
    assert len(result) == 1
    assert result[0].title == "Numb"


def test_search_tracks_local_respects_limit(db_conn):
    init_db(db_conn)
    for i in range(10):
        insert_track(db_conn, Track(title=f"Song {i}", artist="X"))
    result = search_tracks_local(db_conn, "song", limit=3)
    assert len(result) == 3


# ── Playlist CRUD ─────────────────────────────────────────────────────────────

def test_insert_and_get_playlists(db_conn):
    init_db(db_conn)
    pid = insert_playlist(db_conn, Playlist(name="My Mix", type="manual"))
    playlists = get_all_playlists(db_conn)
    assert len(playlists) == 1
    assert playlists[0].id == pid
    assert playlists[0].name == "My Mix"


def test_delete_playlist_removes_it(db_conn):
    init_db(db_conn)
    pid = insert_playlist(db_conn, Playlist(name="Temp", type="manual"))
    delete_playlist(db_conn, pid)
    assert get_all_playlists(db_conn) == []


def test_update_playlist_name(db_conn):
    init_db(db_conn)
    pid = insert_playlist(db_conn, Playlist(name="Old", type="manual"))
    update_playlist_name(db_conn, pid, "New")
    assert get_all_playlists(db_conn)[0].name == "New"


# ── Auto playlist count + oldest deletion ─────────────────────────────────────

def test_get_auto_playlist_count(db_conn):
    init_db(db_conn)
    insert_playlist(db_conn, Playlist(name="Auto 1", type="auto"))
    insert_playlist(db_conn, Playlist(name="Manual", type="manual"))
    insert_playlist(db_conn, Playlist(name="Auto 2", type="auto"))
    assert get_auto_playlist_count(db_conn) == 2


def test_delete_oldest_auto_playlist(db_conn):
    init_db(db_conn)
    id1 = insert_playlist(db_conn, Playlist(name="Old Auto", type="auto"))
    id2 = insert_playlist(db_conn, Playlist(name="New Auto", type="auto"))
    db_conn.execute("UPDATE playlists SET updated_at='2020-01-01' WHERE id=?", (id1,))
    db_conn.commit()
    delete_oldest_auto_playlist(db_conn)
    remaining = get_all_playlists(db_conn)
    assert len(remaining) == 1
    assert remaining[0].id == id2


def test_delete_oldest_auto_playlist_no_op_when_empty(db_conn):
    init_db(db_conn)
    delete_oldest_auto_playlist(db_conn)  # should not raise


# ── Playlist track operations ─────────────────────────────────────────────────

def test_add_tracks_to_playlist_increments_position(db_conn):
    init_db(db_conn)
    pid = insert_playlist(db_conn, Playlist(name="Mix", type="manual"))
    tid1 = insert_track(db_conn, Track(title="First", artist="X"))
    tid2 = insert_track(db_conn, Track(title="Second", artist="Y"))
    add_track_to_playlist(db_conn, pid, tid1)
    add_track_to_playlist(db_conn, pid, tid2)
    tracks = get_playlist_tracks(db_conn, pid)
    assert len(tracks) == 2
    assert tracks[0].title == "First"
    assert tracks[1].title == "Second"


def test_add_track_to_playlist_is_idempotent(db_conn):
    init_db(db_conn)
    pid = insert_playlist(db_conn, Playlist(name="Mix", type="manual"))
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    add_track_to_playlist(db_conn, pid, tid)
    add_track_to_playlist(db_conn, pid, tid)  # duplicate ignored
    assert len(get_playlist_tracks(db_conn, pid)) == 1


def test_remove_track_from_playlist(db_conn):
    init_db(db_conn)
    pid = insert_playlist(db_conn, Playlist(name="Mix", type="manual"))
    tid = insert_track(db_conn, Track(title="A", artist="X"))
    add_track_to_playlist(db_conn, pid, tid)
    remove_track_from_playlist(db_conn, pid, tid)
    assert get_playlist_tracks(db_conn, pid) == []


def test_get_playlist_tracks_empty_for_missing_playlist(db_conn):
    init_db(db_conn)
    assert get_playlist_tracks(db_conn, 9999) == []
