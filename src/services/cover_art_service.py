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
    pass  # filled in next task


class CoverArtService:
    pass  # filled in later task
