import sqlite3
import threading

from src.database.database import get_tracks_to_enrich
from src.database.config_manager import get_setting
from src.models.enums import ArtworkStatus, LyricsStatus
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("enrichment")

# Per-kind config: (started_event, progress_event, complete_event, counter_keys)
_BATCH_EVENTS = {
    "lyrics": (
        "enrichment_lyrics_started",
        "lyrics_progress",
        "lyrics_fetch_complete",
        ("synchronized", "plain_text", "instrumental", "not_found", "not_supported", "errors"),
    ),
    "artwork": (
        "enrichment_artwork_started",
        "enrichment_artwork_progress",
        "enrichment_artwork_complete",
        ("embedded", "not_found", "errors"),
    ),
}


class EnrichmentScheduler:
    def __init__(self, conn: sqlite3.Connection, lrclib_service, cover_art_service) -> None:
        self._conn = conn
        self._lrclib = lrclib_service
        self._cover_art = cover_art_service
        self._lyrics_timer: threading.Timer | None = None
        self._artwork_timer: threading.Timer | None = None
        self._lyrics_running = threading.Event()
        self._artwork_running = threading.Event()

    # ── Public triggers ──────────────────────────────────────────────────────

    def run_lyrics(self) -> None:
        if self._lyrics_running.is_set():
            return
        self._lyrics_running.set()
        threading.Thread(target=self._run_lyrics_batch, daemon=True).start()

    def run_artwork(self) -> None:
        if self._artwork_running.is_set():
            return
        self._artwork_running.set()
        threading.Thread(target=self._run_artwork_batch, daemon=True).start()

    # ── Batch loops ──────────────────────────────────────────────────────────

    def _run_lyrics_batch(self) -> None:
        try:
            self._run_batch("lyrics", self._lrclib.fetch_and_embed)
        finally:
            self._lyrics_running.clear()
        if get_setting(self._conn, "enrich_repeat_lyrics") == "true":
            self._schedule_lyrics()

    def _run_artwork_batch(self) -> None:
        try:
            self._run_batch("artwork", self._cover_art.fetch_and_embed)
        finally:
            self._artwork_running.clear()
        if get_setting(self._conn, "enrich_repeat_artwork") == "true":
            self._schedule_artwork()

    def _run_batch(self, kind: str, fetch_fn) -> None:
        days = int(get_setting(self._conn, "enrich_retry_not_found_days") or "7")
        tracks = get_tracks_to_enrich(self._conn, kind=kind, retry_not_found_after_days=days)
        started, progress, complete, counter_keys = _BATCH_EVENTS[kind]
        counters = {k: 0 for k in counter_keys}
        event_bus.emit(started, {"total": len(tracks)})
        for track in tracks:
            status = None
            try:
                status = fetch_fn(track.id)
                counters[self._bucket(kind, status)] += 1
            except Exception:
                log.error(f"{kind} enrichment failed for track {track.id}", exc_info=True)
                counters["errors"] += 1
            payload = {"track_id": track.id}
            if kind == "lyrics":
                # Preserve original payload shape: lyrics emits status, artwork does not.
                payload["status"] = status
            event_bus.emit(progress, payload)
        event_bus.emit(complete, counters)

    @staticmethod
    def _bucket(kind: str, status) -> str:
        """Map a per-track fetch return value to its counter bucket.

        Preserves the original per-kind semantics:
        - lyrics: NOT_FETCHED / None / unknown -> ``errors``; everything else uses its own bucket.
        - artwork: EMBEDDED -> ``embedded``; everything else -> ``not_found``.
        """
        if kind == "lyrics":
            valid = _BATCH_EVENTS["lyrics"][3]
            if status in (None, LyricsStatus.NOT_FETCHED, LyricsStatus.NOT_FETCHED.value):
                return "errors"
            return status if status in valid else "errors"
        # artwork
        if status in (ArtworkStatus.EMBEDDED, ArtworkStatus.EMBEDDED.value):
            return "embedded"
        return "not_found"

    # ── Timer management ─────────────────────────────────────────────────────

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
        self._lyrics_timer = threading.Timer(self._interval_secs(), self.run_lyrics)
        self._lyrics_timer.daemon = True
        self._lyrics_timer.start()

    def _schedule_artwork(self) -> None:
        self._artwork_timer = threading.Timer(self._interval_secs(), self.run_artwork)
        self._artwork_timer.daemon = True
        self._artwork_timer.start()
