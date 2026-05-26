from __future__ import annotations
from pydantic import BaseModel
from src.models.track import Track


class Artist(BaseModel):
    name: str
    mbid: str | None = None
    listeners: int | None = None
    top_tracks: list[Track] = []
