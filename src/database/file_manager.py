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
    for key in keys:
        if key in tags:
            return str(tags[key][0])
    return default


def _extract_metadata(path: Path) -> dict:
    title = path.stem
    artist = _UNKNOWN_ARTIST
    duration = None
    try:
        meta = mutagen.File(path)
        if meta:
            duration = int(meta.info.length) if hasattr(meta, "info") else None
            tags = meta.tags or {}
            title = _get_tag(tags, "TIT2", "title", default=title)
            artist = _get_tag(tags, "TPE1", "artist", default=artist)
    except Exception as e:
        log.debug(f"mutagen failed for {path}: {e}")
    return {"title": title, "artist": artist, "duration": duration, "audio_format": path.suffix.lstrip(".")}


def quick_scan(conn: sqlite3.Connection) -> None:
    tracks = get_all_tracks(conn)
    for track in tracks:
        if track.file_path and not Path(track.file_path).exists():
            update_track_status(conn, track.id, file_status=FileStatus.MISSING)
            log.info(f"Marked missing: {track.file_path}")


def full_scan(conn: sqlite3.Connection, folders: list[str]) -> int:
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
    t = threading.Thread(target=full_scan, args=(conn, folders), daemon=True)
    t.start()
    return t
