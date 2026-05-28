from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field
from src.models.enums import DownloadStatus, FileStatus, LyricsStatus


class Track(BaseModel):
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
