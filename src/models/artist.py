from __future__ import annotations
from pydantic import BaseModel, Field
from src.models.track import Track


class Artist(BaseModel):
    name: str = Field(min_length=1)
    mbid: str | None = None
    listeners: int | None = None
    top_tracks: list[Track] = Field(default_factory=list)
