import sqlite3
import threading

from src.database.database import get_tracks_to_enrich_artwork
from src.database.config_manager import get_setting
from src.models.enums import ArtworkStatus
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("enrichment")


class EnrichmentScheduler:
    def __init__(self, conn: sqlite3.Connection, lrclib_service, cover_art_service) -> None:
        self._conn = conn
        self._lrclib = lrclib_service
        self._cover_art = cover_art_service
        self._lyrics_timer: threading.Timer | None = None
        self._artwork_timer: threading.Timer | None = None
        self._artwork_running = threading.Event()

    def run_lyrics(self) -> None:
        days = int(get_setting(self._conn, "enrich_retry_not_found_days") or "7")
        self._lrclib.fetch_missing_lyrics(retry_not_found_after_days=days)

    def run_artwork(self) -> None:
        if not self._artwork_running.is_set():
            self._artwork_running.set()
            threading.Thread(target=self._run_artwork_batch, daemon=True).start()

    def _run_artwork_batch(self) -> None:
        days = int(get_setting(self._conn, "enrich_retry_not_found_days") or "7")
        tracks = get_tracks_to_enrich_artwork(self._conn, retry_not_found_after_days=days)
        event_bus.emit("enrichment_artwork_started", {"total": len(tracks)})
        counters = {"embedded": 0, "not_found": 0, "errors": 0}
        for track in tracks:
            try:
                status = self._cover_art.fetch_and_embed(track.id)
                if status == ArtworkStatus.EMBEDDED:
                    counters["embedded"] += 1
                else:
                    counters["not_found"] += 1
            except Exception:
                log.error(f"Artwork enrichment failed for track {track.id}", exc_info=True)
                counters["errors"] += 1
            event_bus.emit("enrichment_artwork_progress", {"track_id": track.id})
        self._artwork_running.clear()
        event_bus.emit("enrichment_artwork_complete", counters)
        self._reschedule_artwork()

    def apply_settings(self) -> None:
        if self._lyrics_timer:
            self._lyrics_timer.cancel()
            self._lyrics_timer = None
        if self._artwork_timer:
            self._artwork_timer.cancel()
            self._artwork_timer = None
        if get_setting(self._conn, "enrich_repeat_lyrics") == "true":
            self._schedule_lyrics()
        if get_setting(self._conn, "enrich_repeat_artwork") == "true":
            self._schedule_artwork()

    def shutdown(self) -> None:
        if self._lyrics_timer:
            self._lyrics_timer.cancel()
        if self._artwork_timer:
            self._artwork_timer.cancel()

    def _interval_secs(self) -> float:
        return float(get_setting(self._conn, "enrich_interval_days") or "1") * 86400

    def _schedule_lyrics(self) -> None:
        self._lyrics_timer = threading.Timer(self._interval_secs(), self._on_lyrics_timer)
        self._lyrics_timer.daemon = True
        self._lyrics_timer.start()

    def _on_lyrics_timer(self) -> None:
        self.run_lyrics()
        if get_setting(self._conn, "enrich_repeat_lyrics") == "true":
            self._schedule_lyrics()

    def _schedule_artwork(self) -> None:
        self._artwork_timer = threading.Timer(self._interval_secs(), self.run_artwork)
        self._artwork_timer.daemon = True
        self._artwork_timer.start()

    def _reschedule_artwork(self) -> None:
        if get_setting(self._conn, "enrich_repeat_artwork") == "true":
            self._schedule_artwork()
