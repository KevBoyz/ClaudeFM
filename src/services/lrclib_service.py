import sqlite3
import threading
from pathlib import Path
from lrcup import LRCLib, AudioFile
from lrcup.audio import UnsupportedSuffix
from src.database.database import (
    get_track, set_enrichment_status, get_tracks_to_enrich,
)
from src.models.enums import LyricsStatus
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("lrclib")


class LRCLibFetcher:
    """Thin wrapper around the lrcup LRCLib client, isolated for testability."""

    def __init__(self):
        self._client = LRCLib()

    def get(self, title: str, artist: str, album: str, duration: int):
        """Fetch lyrics by exact track metadata (preferred — duration-matched result)."""
        return self._client.get(track=title, artist=artist, album=album, duration=duration)

    def search(self, title: str, artist: str):
        """Fuzzy-search for lyrics and return the first result, or None if not found."""
        results = self._client.search(track=title, artist=artist)
        return results[0] if results else None


class LyricsEmbedder:
    """Read/write lyrics tags in audio files via lrcup's AudioFile abstraction."""

    def embed(self, file_path: str, state: str, lyrics: str) -> None:
        """Write lyrics to the file's tags (``state`` is ``'synced'`` or ``'unsynced'``)."""
        AudioFile(Path(file_path)).set_lyrics(state=state, lyrics=lyrics)

    def read(self, file_path: str) -> str | None:
        """Read embedded lyrics text from the file's tags, or None if absent.

        For MP3 files, SYLT is read directly via mutagen to work around a
        formatting bug in lrcup's dump_lyrics: it strips trailing zeros before
        left-padding, so 50 ms becomes ".50" instead of ".050", which the LRC
        parser then misreads as 500 ms.
        """
        path = Path(file_path)
        if path.suffix.lower() == ".mp3":
            return self._read_mp3_lyrics(path)
        return AudioFile(path).get_lyrics()

    @staticmethod
    def _read_mp3_lyrics(path: Path) -> str | None:
        from mutagen.mp3 import MP3
        from mutagen.id3 import SYLT, USLT

        f = MP3(path)
        for tag, value in f.items():
            if isinstance(value, SYLT):
                lines = []
                for text, time_ms in value.text:
                    minutes = time_ms // 60000
                    remaining = time_ms % 60000
                    seconds = remaining // 1000
                    ms = remaining % 1000
                    lines.append(
                        f"[{minutes:02d}:{seconds:02d}.{ms:03d}] {text}")
                return "\n".join(lines)
            if isinstance(value, USLT):
                return str(value)
        return None


class LRCLibService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._running = threading.Event()
        self._fetcher = LRCLibFetcher()
        self._embedder = LyricsEmbedder()

    def fetch_and_embed(self, track_id: int) -> str | None:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return None

        result = None

        if track.duration is not None:
            try:
                result = self._fetcher.get(
                    track.title, track.artist, track.album or "", track.duration
                )
            except Exception:
                log.error(
                    f"LRCLib.get failed for track {track_id}", exc_info=True)
                set_enrichment_status(
                    self._conn, track_id, "lyrics", LyricsStatus.NOT_FETCHED)
                return LyricsStatus.NOT_FETCHED

        if result is None:
            try:
                result = self._fetcher.search(track.title, track.artist)
            except Exception:
                log.error(
                    f"LRCLib.search failed for track {track_id}", exc_info=True)
                set_enrichment_status(
                    self._conn, track_id, "lyrics", LyricsStatus.NOT_FETCHED)
                return LyricsStatus.NOT_FETCHED

        if result is None:
            set_enrichment_status(self._conn, track_id,
                                  "lyrics", LyricsStatus.NOT_FOUND)
            return LyricsStatus.NOT_FOUND

        if result.instrumental:
            set_enrichment_status(self._conn, track_id,
                                  "lyrics", LyricsStatus.INSTRUMENTAL)
            return LyricsStatus.INSTRUMENTAL

        if result.syncedLyrics is not None:
            lyrics, state, status = result.syncedLyrics, "synced", LyricsStatus.SYNCHRONIZED
        elif result.plainLyrics is not None:
            lyrics, state, status = result.plainLyrics, "unsynced", LyricsStatus.PLAIN_TEXT
        else:
            set_enrichment_status(self._conn, track_id,
                                  "lyrics", LyricsStatus.NOT_FOUND)
            return LyricsStatus.NOT_FOUND

        try:
            self._embedder.embed(track.file_path, state, lyrics)
        except UnsupportedSuffix:
            log.error(
                f"Unsupported format for track {track_id}: {track.file_path}")
            set_enrichment_status(self._conn, track_id,
                                  "lyrics", LyricsStatus.NOT_SUPPORTED)
            return LyricsStatus.NOT_SUPPORTED
        except Exception as e:
            log.error(
                f"Failed to embed lyrics for track {track_id}: {e}", exc_info=True)
            set_enrichment_status(self._conn, track_id,
                                  "lyrics", LyricsStatus.NOT_FETCHED)
            return LyricsStatus.NOT_FETCHED

        set_enrichment_status(self._conn, track_id, "lyrics", status)
        return status

    def fetch_and_embed_async(self, track_id: int) -> None:
        """Run ``fetch_and_embed`` in a daemon thread (fire-and-forget, used post-download)."""
        threading.Thread(target=self.fetch_and_embed,
                         args=(track_id,), daemon=True).start()

    def fetch_missing_lyrics(self, retry_not_found_after_days: int = 7) -> None:
        """Start a batch lyrics fetch, if not already running."""
        if not self._running.is_set():
            self._running.set()
            threading.Thread(
                target=self._run_batch,
                args=(retry_not_found_after_days,),
                daemon=True,
            ).start()

    def _run_batch(self, retry_not_found_after_days: int = 7) -> None:
        tracks = get_tracks_to_enrich(
            self._conn, kind="lyrics", retry_not_found_after_days=retry_not_found_after_days
        )
        event_bus.emit("enrichment_lyrics_started", {"total": len(tracks)})
        counters = {
            "synchronized": 0, "plain_text": 0, "instrumental": 0,
            "not_found": 0, "not_supported": 0, "errors": 0,
        }
        for track in tracks:
            status = LyricsStatus.NOT_FETCHED
            try:
                status = self.fetch_and_embed(track.id)
                if status == LyricsStatus.NOT_FETCHED:
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
            text = self._embedder.read(track.file_path)
            return {"lyrics": text, "lyrics_status": track.lyrics_status}
        except Exception:
            log.error(f"get_lyrics failed for track {track_id}", exc_info=True)
            return None
