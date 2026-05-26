from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class Playlist(BaseModel):
    id: int | None = None
    name: str
    type: Literal["auto", "manual"]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlaylistTrack(BaseModel):
    playlist_id: int
    track_id: int
    position: int
