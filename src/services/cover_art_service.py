import sqlite3
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, APIC, ID3NoHeaderError

from src.database.database import get_track, update_artwork_status, update_track_album
from src.models.enums import ArtworkStatus
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

    def read_bytes(self, file_path: str) -> bytes | None:
        ext = Path(file_path).suffix.lower()
        try:
            if ext == '.m4a':
                audio = MP4(file_path)
                if audio.tags and 'covr' in audio.tags:
                    return bytes(audio.tags['covr'][0])
            elif ext == '.mp3':
                try:
                    audio = ID3(file_path)
                except ID3NoHeaderError:
                    return None
                for tag in audio.values():
                    if isinstance(tag, APIC):
                        return tag.data
        except Exception as e:
            log.debug(f"read_bytes failed for {file_path}: {e}")
        return None


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

    def fetch_and_embed(self, track_id: int) -> str:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return ArtworkStatus.NOT_FOUND

        album = track.album
        if not album:
            album = self._lastfm.get_track_album(track.artist, track.title)
            if album:
                log.debug(f"Resolved album for track {track_id} via Last.fm: {album!r}")
                update_track_album(self._conn, track_id, album)

        url = self._lastfm.get_cover_image_url(track.artist, album)
        if not url:
            log.debug(f"No cover art URL for track {track_id} ({track.artist!r}/{album!r})")
            update_artwork_status(self._conn, track_id, ArtworkStatus.NOT_FOUND, datetime.now())
            return ArtworkStatus.NOT_FOUND

        try:
            image_data = self._fetcher.fetch_bytes(url)
        except Exception as e:
            log.warning(f"Failed to download cover art for track {track_id}: {e}")
            update_artwork_status(self._conn, track_id, ArtworkStatus.NOT_FOUND, datetime.now())
            return ArtworkStatus.NOT_FOUND

        try:
            self._embedder.embed(track.file_path, image_data)
        except Exception as e:
            log.warning(f"Failed to embed cover art for track {track_id}: {e}")
            update_artwork_status(self._conn, track_id, ArtworkStatus.NOT_FOUND, datetime.now())
            return ArtworkStatus.NOT_FOUND

        update_artwork_status(self._conn, track_id, ArtworkStatus.EMBEDDED, datetime.now())
        return ArtworkStatus.EMBEDDED

    def fetch_and_embed_async(self, track_id: int) -> None:
        threading.Thread(target=self.fetch_and_embed, args=(track_id,), daemon=True).start()

    def get_cover_bytes(self, track_id: int) -> bytes | None:
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            return None
        return self._embedder.read_bytes(track.file_path)
