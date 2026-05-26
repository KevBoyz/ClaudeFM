from __future__ import annotations
from pydantic import BaseModel
from src.models.track import Track


class Album(BaseModel):
    title: str
    artist: str
    mbid: str | None = None
    tracks: list[Track] = []
