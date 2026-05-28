import sqlite3
import threading
from pathlib import Path
from lrcup import LRCLib, AudioFile
from lrcup.audio import UnsupportedSuffix
from src.database.database import get_track, update_lyrics_status, get_tracks_without_lyrics
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("lrclib")


class LRCLibService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._running = threading.Event()

    def fetch_and_embed(self, track_id: int) -> str | None:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return None

        lrclib = LRCLib()
        result = None

        if track.duration is not None:
            try:
                result = lrclib.get(
                    track=track.title,
                    artist=track.artist,
                    album=track.album or "",
                    duration=track.duration,
                )
            except Exception:
                log.error(
                    f"LRCLib.get failed for track {track_id}", exc_info=True)
                update_lyrics_status(self._conn, track_id, "not_fetched")
                return "not_fetched"

        if result is None:
            try:
                results = lrclib.search(track=track.title, artist=track.artist)
                result = results[0] if results else None
            except Exception:
                log.error(
                    f"LRCLib.search failed for track {track_id}", exc_info=True)
                update_lyrics_status(self._conn, track_id, "not_fetched")
                return "not_fetched"

        if result is None:
            update_lyrics_status(self._conn, track_id, "not_found")
            return "not_found"

        if result.instrumental:
            update_lyrics_status(self._conn, track_id, "instrumental")
            return "instrumental"

        if result.syncedLyrics is not None:
            lyrics, state, status = result.syncedLyrics, "synced", "synchronized"
        elif result.plainLyrics is not None:
            lyrics, state, status = result.plainLyrics, "unsynced", "plain_text"
        else:
            update_lyrics_status(self._conn, track_id, "not_found")
            return "not_found"

        try:
            AudioFile(Path(track.file_path)).set_lyrics(
                state=state, lyrics=lyrics)
        except UnsupportedSuffix:
            log.error(
                f"Unsupported format for track {track_id}: {track.file_path}")
            update_lyrics_status(self._conn, track_id, "not_supported")
            return "not_supported"

        update_lyrics_status(self._conn, track_id, status)
        return status

    def fetch_and_embed_async(self, track_id: int) -> None:
        threading.Thread(target=self.fetch_and_embed,
                         args=(track_id,), daemon=True).start()

    def fetch_missing_lyrics(self) -> None:
        if not self._running.is_set():
            self._running.set()
            threading.Thread(target=self._run_batch, daemon=True).start()

    def _run_batch(self) -> None:
        tracks = get_tracks_without_lyrics(self._conn)
        counters = {
            "synchronized": 0, "plain_text": 0, "instrumental": 0,
            "not_found": 0, "not_supported": 0, "errors": 0,
        }
        for track in tracks:
            status = "not_fetched"
            try:
                status = self.fetch_and_embed(track.id)
                if status == "not_fetched":
                    counters["errors"] += 1
                elif status in counters:
                    counters[status] += 1
            except Exception:
                log.error(
                    f"Unexpected error processing track {track.id}", exc_info=True)
                counters["errors"] += 1
            event_bus.emit("lyrics_progress", {
                           "track_id": track.id, "status": status})
        self._running.clear()
        event_bus.emit("lyrics_fetch_complete", counters)

    def get_lyrics(self, track_id: int) -> dict | None:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return None
        try:
            text = AudioFile(Path(track.file_path)).get_lyrics()
            return {"lyrics": text, "lyrics_status": track.lyrics_status}
        except Exception:
            log.error(f"get_lyrics failed for track {track_id}", exc_info=True)
            return None
