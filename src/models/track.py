from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field
from src.models.enums import DownloadStatus, FileStatus, LyricsStatus, ArtworkStatus


class Track(BaseModel):
    """Pydantic model mirroring the ``tracks`` DB table.

    ``date_downloaded`` is parsed from an ISO string by ``_row_to_track``.
    ``download_status`` and ``file_status`` default to safe values so a newly
    created Track (before any DB round-trip) is usable without extra setup.
    """

    id: int | None = None
    title: str = Field(min_length=1)
    artist: str = Field(min_length=1)
    album: str | None = None
    duration: int | None = None
    file_path: str | None = None
    audio_format: str | None = None
    youtube_url: str | None = None
    date_downloaded: datetime | None = None
    download_status: DownloadStatus = DownloadStatus.PENDING
    download_error: str | None = None
    file_status: FileStatus = FileStatus.AVAILABLE
    lyrics_status: LyricsStatus = LyricsStatus.NOT_FETCHED
    artwork_status: ArtworkStatus = ArtworkStatus.NOT_FETCHED
    lyrics_fetched_at: datetime | None = None
    artwork_fetched_at: datetime | None = None
