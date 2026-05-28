from __future__ import annotations
from pydantic import BaseModel, Field
from src.models.track import Track


class Album(BaseModel):
    """Last.fm album result. Not persisted to the DB — used only for API responses."""

    title: str = Field(min_length=1)
    artist: str = Field(min_length=1)
    mbid: str | None = None
    tracks: list[Track] = Field(default_factory=list)
