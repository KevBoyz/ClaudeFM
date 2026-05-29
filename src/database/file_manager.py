import sqlite3
import threading
from pathlib import Path

import mutagen

from src.database.database import (
    get_all_tracks, insert_track, update_track_status
)
from src.models.track import Track
from src.models.enums import DownloadStatus, FileStatus
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("file_manager")

AUDIO_EXTENSIONS = {".mp3", ".m4a"}
_UNKNOWN_ARTIST = "Unknown Artist"


def _get_tag(tags: dict, *keys: str, default: str) -> str:
    """Return the first non-empty tag value found under any of the given keys, or ``default``."""
    for key in keys:
        if key in tags:
            return str(tags[key][0])
    return default


def _extract_metadata(path: Path) -> dict:
    """Read title, artist, album, duration, and format from an audio file's tags via mutagen.

    Falls back to the filename stem / "Unknown Artist" if tags are missing or
    mutagen raises. Returns a plain dict so callers don't import mutagen.
    """
    title = path.stem
    artist = _UNKNOWN_ARTIST
    album = None
    duration = None
    try:
        meta = mutagen.File(path)
        if meta:
            duration = int(meta.info.length) if hasattr(meta, "info") else None
            tags = meta.tags or {}
            title = _get_tag(tags, "TIT2", "title", default=title)
            artist = _get_tag(tags, "TPE1", "artist", default=artist)
            raw_album = _get_tag(tags, "TALB", "album", default="")
            album = raw_album or None
    except Exception as e:
        log.debug(f"mutagen failed for {path}: {e}")
    return {"title": title, "artist": artist, "album": album, "duration": duration, "audio_format": path.suffix.lstrip(".")}


def quick_scan(conn: sqlite3.Connection) -> None:
    """Mark tracks as MISSING if their recorded file_path no longer exists on disk.

    Runs synchronously at startup — O(n) stat checks only, no directory walk.
    """
    tracks = get_all_tracks(conn)
    for track in tracks:
        if track.file_path and not Path(track.file_path).exists():
            update_track_status(conn, track.id, file_status=FileStatus.MISSING)
            log.info(f"Marked missing: {track.file_path}")


def full_scan(conn: sqlite3.Connection, folders: list[str]) -> int:
    """Walk ``folders`` recursively and import any .mp3/.m4a files not yet in the DB.

    Also back-fills missing duration values for already-known tracks. Emits
    ``library_scan_complete`` on the event bus when done. Returns the number
    of newly added tracks.
    """
    existing = {t.file_path: t for t in get_all_tracks(conn) if t.file_path}
    added = 0

    for folder_str in folders:
        folder = Path(folder_str)
        if not folder.exists():
            log.warning(f"Folder not found: {folder}")
            continue
        for path in folder.rglob("*"):
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            path_str = str(path)
            if path_str in existing:
                if existing[path_str].duration is None:
                    meta = _extract_metadata(path)
                    if meta["duration"] is not None:
                        update_track_status(
                            conn, existing[path_str].id, duration=meta["duration"])
                continue
            meta = _extract_metadata(path)
            track = Track(
                title=meta["title"],
                artist=meta["artist"],
                album=meta["album"],
                duration=meta["duration"],
                file_path=path_str,
                audio_format=meta["audio_format"],
                download_status=DownloadStatus.COMPLETED,
                file_status=FileStatus.AVAILABLE,
            )
            insert_track(conn, track)
            added += 1

    log.info(f"Full scan complete: {added} added")
    event_bus.emit("library_scan_complete", {"added": added})
    return added


def start_background_scan(conn: sqlite3.Connection, folders: list[str]) -> threading.Thread:
    """Launch ``full_scan`` in a daemon thread and return it immediately."""
    t = threading.Thread(target=full_scan, args=(conn, folders), daemon=True)
    t.start()
    return t
