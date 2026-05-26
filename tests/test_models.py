import pytest
from datetime import datetime
from src.models.track import Track
from src.models.playlist import Playlist, PlaylistTrack
from src.models.artist import Artist
from src.models.album import Album


def test_track_defaults():
    t = Track(title="Song", artist="Artist")
    assert t.download_status == "pending"
    assert t.file_status == "available"
    assert t.id is None


def test_track_rejects_invalid_download_status():
    with pytest.raises(Exception):
        Track(title="Song", artist="Artist", download_status="invalid")


def test_track_rejects_invalid_file_status():
    with pytest.raises(Exception):
        Track(title="Song", artist="Artist", file_status="unknown")


def test_playlist_type_validation():
    p = Playlist(name="My List", type="manual")
    assert p.type == "manual"
    with pytest.raises(Exception):
        Playlist(name="Bad", type="other")


def test_playlist_track_requires_position():
    pt = PlaylistTrack(playlist_id=1, track_id=2, position=0)
    assert pt.position == 0


def test_artist_top_tracks_default_empty():
    a = Artist(name="Radiohead")
    assert a.top_tracks == []


def test_album_tracks_default_empty():
    al = Album(title="OK Computer", artist="Radiohead")
    assert al.tracks == []


def test_track_model_dump_serializable():
    t = Track(title="Creep", artist="Radiohead", duration=239)
    d = t.model_dump()
    assert d["title"] == "Creep"
    assert d["duration"] == 239
