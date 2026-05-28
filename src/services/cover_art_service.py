import sqlite3
import threading
import urllib.request
from pathlib import Path

from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, APIC, ID3NoHeaderError

from src.database.database import get_track
from src.utils.logger import get_logger

log = get_logger("cover_art")


class CoverArtEmbedder:
    """Write cover art image bytes into audio file tags (M4A or MP3)."""

    def embed(self, file_path: str, image_data: bytes) -> None:
        ext = Path(file_path).suffix.lower()
        if ext == '.m4a':
            audio = MP4(file_path)
            if audio.tags is None:
                audio.add_tags()
            audio.tags['covr'] = [MP4Cover(image_data, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
        elif ext == '.mp3':
            try:
                audio = ID3(file_path)
            except ID3NoHeaderError:
                audio = ID3()
            audio.add(APIC(mime='image/jpeg', type=3, desc='Cover', data=image_data))
            audio.save(file_path)
        else:
            raise ValueError(f"Unsupported format: {ext}")


class CoverArtFetcher:
    """Download raw image bytes from a URL."""

    def fetch_bytes(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "ClaudeFM/1.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        try:
            return resp.read()
        finally:
            resp.close()


class CoverArtService:
    """Fetch a cover image URL from Last.fm, download the bytes, and embed into the audio file."""

    def __init__(self, conn: sqlite3.Connection, lastfm_service) -> None:
        self._conn = conn
        self._lastfm = lastfm_service
        self._fetcher = CoverArtFetcher()
        self._embedder = CoverArtEmbedder()

    def fetch_and_embed(self, track_id: int) -> bool:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return False

        url = self._lastfm.get_cover_image_url(track.artist, track.album)
        if not url:
            log.debug(f"No cover art URL for track {track_id} ({track.artist!r}/{track.album!r})")
            return False

        try:
            image_data = self._fetcher.fetch_bytes(url)
        except Exception as e:
            log.warning(f"Failed to download cover art for track {track_id}: {e}")
            return False

        try:
            self._embedder.embed(track.file_path, image_data)
        except Exception as e:
            log.warning(f"Failed to embed cover art for track {track_id}: {e}")
            return False

        return True

    def fetch_and_embed_async(self, track_id: int) -> None:
        threading.Thread(target=self.fetch_and_embed, args=(track_id,), daemon=True).start()
