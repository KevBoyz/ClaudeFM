import sqlite3
import threading
from pathlib import Path
from lrcup import LRCLib, AudioFile
from lrcup.audio import UnsupportedSuffix
from src.database.database import get_track, update_lyrics_status, get_tracks_without_lyrics
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
        """Read embedded lyrics text from the file's tags, or None if absent."""
        return AudioFile(Path(file_path)).get_lyrics()


class LRCLibService:
    """Orchestrates lyrics fetching from LRCLIB and embedding into audio file tags.

    Fetch strategy per track: try ``LRCLibFetcher.get`` (duration-matched) first,
    fall back to ``LRCLibFetcher.search`` if the result is None, then embed
    synced lyrics preferring over plain text. ``UnsupportedSuffix`` maps to
    ``NOT_SUPPORTED`` status so unsupported formats don't re-trigger fetches.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._running = threading.Event()
        self._fetcher = LRCLibFetcher()
        self._embedder = LyricsEmbedder()

    def fetch_and_embed(self, track_id: int) -> str | None:
        """Fetch and embed lyrics for one track; return the resulting ``LyricsStatus`` value or None.

        Returns None only if the track doesn't exist or has no file_path.
        All other outcomes (not found, instrumental, error) return a status string.
        """
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
                log.error(f"LRCLib.get failed for track {track_id}", exc_info=True)
                update_lyrics_status(self._conn, track_id, LyricsStatus.NOT_FETCHED)
                return LyricsStatus.NOT_FETCHED

        if result is None:
            try:
                result = self._fetcher.search(track.title, track.artist)
            except Exception:
                log.error(f"LRCLib.search failed for track {track_id}", exc_info=True)
                update_lyrics_status(self._conn, track_id, LyricsStatus.NOT_FETCHED)
                return LyricsStatus.NOT_FETCHED

        if result is None:
            update_lyrics_status(self._conn, track_id, LyricsStatus.NOT_FOUND)
            return LyricsStatus.NOT_FOUND

        if result.instrumental:
            update_lyrics_status(self._conn, track_id, LyricsStatus.INSTRUMENTAL)
            return LyricsStatus.INSTRUMENTAL

        if result.syncedLyrics is not None:
            lyrics, state, status = result.syncedLyrics, "synced", LyricsStatus.SYNCHRONIZED
        elif result.plainLyrics is not None:
            lyrics, state, status = result.plainLyrics, "unsynced", LyricsStatus.PLAIN_TEXT
        else:
            update_lyrics_status(self._conn, track_id, LyricsStatus.NOT_FOUND)
            return LyricsStatus.NOT_FOUND

        try:
            self._embedder.embed(track.file_path, state, lyrics)
        except UnsupportedSuffix:
            log.error(f"Unsupported format for track {track_id}: {track.file_path}")
            update_lyrics_status(self._conn, track_id, LyricsStatus.NOT_SUPPORTED)
            return LyricsStatus.NOT_SUPPORTED

        update_lyrics_status(self._conn, track_id, status)
        return status

    def fetch_and_embed_async(self, track_id: int) -> None:
        """Run ``fetch_and_embed`` in a daemon thread (fire-and-forget, used post-download)."""
        threading.Thread(target=self.fetch_and_embed, args=(track_id,), daemon=True).start()

    def fetch_missing_lyrics(self) -> None:
        """Start a batch lyrics fetch for all ``not_fetched`` tracks, if not already running.

        Uses ``_running`` (a threading.Event) as a singleton guard — a second
        call while a batch is active is silently ignored.
        """
        if not self._running.is_set():
            self._running.set()
            threading.Thread(target=self._run_batch, daemon=True).start()

    def _run_batch(self) -> None:
        """Batch thread target: fetch lyrics for every not_fetched track and emit per-track progress events.

        Emits ``lyrics_progress`` after each track and ``lyrics_fetch_complete``
        with aggregate counters when done. Clears ``_running`` at the end.
        """
        tracks = get_tracks_without_lyrics(self._conn)
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
                log.error(f"Unexpected error processing track {track.id}", exc_info=True)
                counters["errors"] += 1
            event_bus.emit("lyrics_progress", {"track_id": track.id, "status": status})
        self._running.clear()
        event_bus.emit("lyrics_fetch_complete", counters)

    def get_lyrics(self, track_id: int) -> dict | None:
        """Read embedded lyrics from the audio file and return them with the track's lyrics_status.

        Returns None if the track doesn't exist, has no file_path, or the read
        raises an exception.
        """
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return None
        try:
            text = self._embedder.read(track.file_path)
            return {"lyrics": text, "lyrics_status": track.lyrics_status}
        except Exception:
            log.error(f"get_lyrics failed for track {track_id}", exc_info=True)
            return None
