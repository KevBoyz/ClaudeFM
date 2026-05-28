import sqlite3
from datetime import datetime
from pathlib import Path
from src.models.track import Track
from src.models.playlist import Playlist
from src.models.enums import LyricsStatus, PlaylistType

_ALLOWED_ORDER_BY = {
    "date_downloaded DESC", "date_downloaded ASC",
    "title ASC", "title DESC",
    "artist ASC", "artist DESC",
    "duration ASC", "duration DESC",
}

_DB_PATH = Path(__file__).parent.parent.parent / "claudefm.db"


def get_connection(path: Path = _DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tracks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            artist          TEXT NOT NULL,
            album           TEXT,
            duration        INTEGER,
            file_path       TEXT,
            audio_format    TEXT,
            youtube_url     TEXT,
            date_downloaded TEXT,
            download_status TEXT NOT NULL DEFAULT 'pending',
            download_error  TEXT,
            file_status     TEXT NOT NULL DEFAULT 'available',
            lyrics_status   TEXT NOT NULL DEFAULT 'not_fetched'
        );

        CREATE TABLE IF NOT EXISTS playlists (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            type       TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS playlist_tracks (
            playlist_id INTEGER NOT NULL,
            track_id    INTEGER NOT NULL,
            position    INTEGER NOT NULL,
            PRIMARY KEY (playlist_id, track_id),
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS cache (
            key        TEXT PRIMARY KEY,
            response   TEXT,
            cached_at  TEXT,
            expires_at TEXT
        );
    """)
    conn.commit()


def _row_to_track(row: sqlite3.Row) -> Track:
    date_dl = row["date_downloaded"]
    return Track(
        id=row["id"],
        title=row["title"],
        artist=row["artist"],
        album=row["album"],
        duration=row["duration"],
        file_path=row["file_path"],
        audio_format=row["audio_format"],
        youtube_url=row["youtube_url"],
        date_downloaded=datetime.fromisoformat(date_dl) if date_dl else None,
        download_status=row["download_status"],
        download_error=row["download_error"],
        file_status=row["file_status"],
        lyrics_status=row["lyrics_status"],
    )


def insert_track(conn: sqlite3.Connection, track: Track) -> int:
    existing = conn.execute(
        "SELECT id FROM tracks WHERE title=? AND artist=?",
        (track.title, track.artist),
    ).fetchone()
    if existing:
        return existing["id"]
    cur = conn.execute(
        """INSERT INTO tracks (title, artist, album, duration, file_path, audio_format,
           youtube_url, date_downloaded, download_status, download_error, file_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (track.title, track.artist, track.album, track.duration, track.file_path,
         track.audio_format, track.youtube_url,
         track.date_downloaded.isoformat() if track.date_downloaded else None,
         track.download_status, track.download_error, track.file_status),
    )
    conn.commit()
    return cur.lastrowid


def get_track(conn: sqlite3.Connection, track_id: int) -> Track | None:
    row = conn.execute("SELECT * FROM tracks WHERE id=?",
                       (track_id,)).fetchone()
    return _row_to_track(row) if row else None


def update_track_status(
    conn: sqlite3.Connection,
    track_id: int,
    *,
    download_status: str | None = None,
    download_error: str | None = None,
    file_status: str | None = None,
    file_path: str | None = None,
    youtube_url: str | None = None,
    duration: int | None = None,
) -> None:
    fields, values = [], []
    for col, val in [
        ("download_status", download_status),
        ("download_error", download_error),
        ("file_status", file_status),
        ("file_path", file_path),
        ("youtube_url", youtube_url),
        ("duration", duration),
    ]:
        if val is not None:
            fields.append(f"{col}=?")
            values.append(val)
    if not fields:
        return
    values.append(track_id)
    conn.execute(f"UPDATE tracks SET {', '.join(fields)} WHERE id=?", values)
    conn.commit()


def update_lyrics_status(conn: sqlite3.Connection, track_id: int, status: str) -> None:
    conn.execute("UPDATE tracks SET lyrics_status=? WHERE id=?",
                 (status, track_id))
    conn.commit()


def get_tracks_without_lyrics(conn: sqlite3.Connection) -> list[Track]:
    rows = conn.execute(
        "SELECT * FROM tracks WHERE lyrics_status=?", (LyricsStatus.NOT_FETCHED,)
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def get_all_tracks(
    conn: sqlite3.Connection,
    order_by: str = "date_downloaded DESC",
    audio_format: str | None = None,
) -> list[Track]:
    if order_by not in _ALLOWED_ORDER_BY:
        order_by = "date_downloaded DESC"
    if audio_format:
        rows = conn.execute(
            f"SELECT * FROM tracks WHERE audio_format=? ORDER BY {order_by}",
            (audio_format,),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM tracks ORDER BY {order_by}").fetchall()
    return [_row_to_track(r) for r in rows]


def get_tracks_by_artist(conn: sqlite3.Connection, artist: str) -> list[Track]:
    rows = conn.execute(
        "SELECT * FROM tracks WHERE LOWER(artist)=LOWER(?) ORDER BY album, title",
        (artist,)
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def get_tracks_by_album(conn: sqlite3.Connection, album: str, artist: str) -> list[Track]:
    rows = conn.execute(
        "SELECT * FROM tracks WHERE LOWER(album)=LOWER(?) AND LOWER(artist)=LOWER(?) ORDER BY title",
        (album, artist)
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def get_all_artists(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT artist, COUNT(*) as track_count FROM tracks GROUP BY LOWER(artist) ORDER BY LOWER(artist) ASC"
    ).fetchall()
    return [{"artist": r["artist"], "track_count": r["track_count"]} for r in rows]


def get_all_albums(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT album, artist, COUNT(*) as track_count
           FROM tracks WHERE album IS NOT NULL
           GROUP BY LOWER(album), LOWER(artist)
           ORDER BY LOWER(album) ASC"""
    ).fetchall()
    return [{"album": r["album"], "artist": r["artist"], "track_count": r["track_count"]} for r in rows]


def search_tracks_local(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[Track]:
    q = f"%{query.lower()}%"
    rows = conn.execute(
        "SELECT * FROM tracks WHERE LOWER(title) LIKE ? OR LOWER(artist) LIKE ? LIMIT ?",
        (q, q, limit)
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def insert_playlist(conn: sqlite3.Connection, playlist: Playlist) -> int:
    now = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO playlists (name, type, created_at, updated_at) VALUES (?,?,?,?)",
        (playlist.name, playlist.type, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_all_playlists(conn: sqlite3.Connection) -> list[Playlist]:
    rows = conn.execute(
        "SELECT * FROM playlists ORDER BY updated_at DESC").fetchall()
    return [Playlist(id=r["id"], name=r["name"], type=r["type"]) for r in rows]


def get_auto_playlist_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM playlists WHERE type=?", (PlaylistType.AUTO,)
    ).fetchone()[0]


def delete_oldest_auto_playlist(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT id FROM playlists WHERE type=? ORDER BY updated_at ASC LIMIT 1",
        (PlaylistType.AUTO,),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM playlists WHERE id=?", (row["id"],))
        conn.commit()


def get_playlist_tracks(conn: sqlite3.Connection, playlist_id: int) -> list[Track]:
    rows = conn.execute(
        """SELECT t.* FROM tracks t
           JOIN playlist_tracks pt ON pt.track_id = t.id
           WHERE pt.playlist_id=?
           ORDER BY pt.position""",
        (playlist_id,)
    ).fetchall()
    return [_row_to_track(r) for r in rows]


def delete_playlist(conn: sqlite3.Connection, playlist_id: int) -> None:
    conn.execute("DELETE FROM playlists WHERE id=?", (playlist_id,))
    conn.commit()


def update_playlist_name(conn: sqlite3.Connection, playlist_id: int, name: str) -> None:
    conn.execute(
        "UPDATE playlists SET name=?, updated_at=datetime('now') WHERE id=?", (name, playlist_id))
    conn.commit()


def add_track_to_playlist(conn: sqlite3.Connection, playlist_id: int, track_id: int) -> None:
    row = conn.execute(
        "SELECT MAX(position) FROM playlist_tracks WHERE playlist_id=?", (playlist_id,)
    ).fetchone()
    position = (row[0] or -1) + 1
    conn.execute(
        "INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, position) VALUES (?,?,?)",
        (playlist_id, track_id, position),
    )
    conn.commit()


def remove_track_from_playlist(conn: sqlite3.Connection, playlist_id: int, track_id: int) -> None:
    conn.execute(
        "DELETE FROM playlist_tracks WHERE playlist_id=? AND track_id=?",
        (playlist_id, track_id),
    )
    conn.commit()
