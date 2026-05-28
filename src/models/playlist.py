from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field
from src.models.enums import PlaylistType


class Playlist(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1)
    type: PlaylistType
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlaylistTrack(BaseModel):
    playlist_id: int
    track_id: int
    position: int = Field(ge=0)
