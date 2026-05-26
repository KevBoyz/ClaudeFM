from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


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
    download_status: Literal["pending", "downloading", "completed", "failed"] = "pending"
    download_error: str | None = None
    file_status: Literal["available", "missing", "corrupted"] = "available"
    lyrics_status: str = "not_fetched"
