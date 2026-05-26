import sqlite3
import threading
from pathlib import Path
from src.database.database import (
    get_all_tracks, insert_track, update_track_status
)
from src.models.track import Track
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("file_manager")

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".ogg", ".wav", ".opus"}


def _extract_metadata(path: Path) -> dict:
    title = path.stem
    artist = "Unknown Artist"
    duration = None
    try:
        import mutagen
        meta = mutagen.File(path)
        if meta:
            duration = int(meta.info.length) if hasattr(meta, "info") else None
            tags = meta.tags or {}
            title = str(tags.get("TIT2", [title])[0]) if "TIT2" in tags else str(tags.get("title", [title])[0]) if "title" in tags else title
            artist = str(tags.get("TPE1", [artist])[0]) if "TPE1" in tags else str(tags.get("artist", [artist])[0]) if "artist" in tags else artist
    except Exception as e:
        log.debug(f"mutagen failed for {path}: {e}")
    return {"title": title, "artist": artist, "duration": duration, "audio_format": path.suffix.lstrip(".")}


def quick_scan(conn: sqlite3.Connection) -> None:
    tracks = get_all_tracks(conn)
    for track in tracks:
        if track.file_path and not Path(track.file_path).exists():
            update_track_status(conn, track.id, file_status="missing")
            log.info(f"Marked missing: {track.file_path}")


def full_scan(conn: sqlite3.Connection, folders: list[str]) -> tuple[int, int]:
    existing_paths = {t.file_path for t in get_all_tracks(conn) if t.file_path}
    added, missing = 0, 0

    for folder_str in folders:
        folder = Path(folder_str)
        if not folder.exists():
            log.warning(f"Folder not found: {folder}")
            continue
        for path in folder.rglob("*"):
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            path_str = str(path)
            if path_str in existing_paths:
                continue
            meta = _extract_metadata(path)
            track = Track(
                title=meta["title"],
                artist=meta["artist"],
                duration=meta["duration"],
                file_path=path_str,
                audio_format=meta["audio_format"],
                download_status="completed",
                file_status="available",
            )
            insert_track(conn, track)
            added += 1

    log.info(f"Full scan complete: {added} added, {missing} missing")
    event_bus.emit("library_scan_complete", {"added": added, "missing": missing})
    return added, missing


def start_background_scan(conn: sqlite3.Connection, folders: list[str]) -> threading.Thread:
    t = threading.Thread(target=full_scan, args=(conn, folders), daemon=True)
    t.start()
    return t
