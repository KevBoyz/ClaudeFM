# tests/test_cover_art_service.py
import pytest
import base64
from unittest.mock import MagicMock, call, patch
from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, APIC
from src.services.cover_art_service import CoverArtEmbedder


def test_embed_m4a_writes_covr_tag(mocker):
    mock_mp4_cls = mocker.patch('src.services.cover_art_service.MP4')
    mock_cover_cls = mocker.patch('src.services.cover_art_service.MP4Cover')
    mock_audio = MagicMock()
    mock_audio.tags = {}
    mock_mp4_cls.return_value = mock_audio

    CoverArtEmbedder().embed('/music/song.m4a', b'img_bytes')

    mock_mp4_cls.assert_called_once_with('/music/song.m4a')
    mock_cover_cls.assert_called_once_with(b'img_bytes', imageformat=mock_cover_cls.FORMAT_JPEG)
    assert mock_audio.tags['covr'] == [mock_cover_cls.return_value]
    mock_audio.save.assert_called_once()


def test_embed_m4a_adds_tags_when_none(mocker):
    mock_mp4_cls = mocker.patch('src.services.cover_art_service.MP4')
    mocker.patch('src.services.cover_art_service.MP4Cover')
    mock_audio = MagicMock()
    mock_audio.tags = None

    def _set_tags():
        mock_audio.tags = {}
    mock_audio.add_tags.side_effect = _set_tags

    mock_mp4_cls.return_value = mock_audio

    CoverArtEmbedder().embed('/music/song.m4a', b'img')

    mock_audio.add_tags.assert_called_once()


def test_embed_mp3_adds_apic_frame(mocker):
    mock_id3_cls = mocker.patch('src.services.cover_art_service.ID3')
    mock_apic_cls = mocker.patch('src.services.cover_art_service.APIC')
    mock_audio = MagicMock()
    mock_id3_cls.return_value = mock_audio

    CoverArtEmbedder().embed('/music/song.mp3', b'img_bytes')

    mock_apic_cls.assert_called_once_with(mime='image/jpeg', type=3, desc='Cover', data=b'img_bytes')
    mock_audio.add.assert_called_once_with(mock_apic_cls.return_value)
    mock_audio.save.assert_called_once_with('/music/song.mp3')


def test_embed_mp3_creates_new_id3_when_no_header(mocker):
    from mutagen.id3 import ID3NoHeaderError
    mock_id3_cls = mocker.patch('src.services.cover_art_service.ID3')
    mocker.patch('src.services.cover_art_service.APIC')
    fresh_audio = MagicMock()
    # First call (with file_path) raises; second call (empty constructor) returns fresh_audio
    mock_id3_cls.side_effect = [ID3NoHeaderError, fresh_audio]

    CoverArtEmbedder().embed('/music/song.mp3', b'img')

    assert mock_id3_cls.call_count == 2
    fresh_audio.add.assert_called_once()
    fresh_audio.save.assert_called_once_with('/music/song.mp3')


def test_embed_unsupported_format_raises():
    with pytest.raises(ValueError, match="Unsupported format"):
        CoverArtEmbedder().embed('/music/song.flac', b'img')


from src.services.cover_art_service import CoverArtFetcher


def test_fetcher_returns_bytes(mocker):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'fake_image'
    mocker.patch(
        'src.services.cover_art_service.urllib.request.urlopen',
        return_value=mock_resp,
    )
    result = CoverArtFetcher().fetch_bytes('http://example.com/cover.jpg')
    assert result == b'fake_image'
    mock_resp.close.assert_called_once()


def test_fetcher_sends_user_agent(mocker):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b''
    captured = {}

    def fake_urlopen(req, timeout):
        captured['req'] = req
        return mock_resp

    mocker.patch('src.services.cover_art_service.urllib.request.urlopen', side_effect=fake_urlopen)
    CoverArtFetcher().fetch_bytes('http://example.com/img.jpg')
    assert captured['req'].headers.get('User-agent') == 'ClaudeFM/1.0'


def test_fetcher_propagates_exceptions(mocker):
    mocker.patch(
        'src.services.cover_art_service.urllib.request.urlopen',
        side_effect=OSError("timeout"),
    )
    with pytest.raises(OSError):
        CoverArtFetcher().fetch_bytes('http://bad.url/img.jpg')


from src.services.cover_art_service import CoverArtService
from src.database.database import init_db, insert_track, get_track, update_track_status
from src.models.track import Track
from datetime import datetime
import time


def test_service_fetches_and_embeds_cover(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="Karma Police", artist="Radiohead", album="OK Computer",
        download_status="completed", file_status="available", file_path="/tmp/song.m4a",
    ))
    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = 'https://cdn.com/cover.jpg'
    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.return_value = b'img'
    svc._embedder = MagicMock()

    result = svc.fetch_and_embed(tid)

    assert result == "embedded"
    mock_lastfm.get_cover_image_url.assert_called_once_with("Radiohead", "OK Computer")
    svc._fetcher.fetch_bytes.assert_called_once_with('https://cdn.com/cover.jpg')
    svc._embedder.embed.assert_called_once_with("/tmp/song.m4a", b'img')


def test_service_resolves_album_via_lastfm_when_missing(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="Creep", artist="Radiohead",
        download_status="completed", file_status="available", file_path="/tmp/s.m4a",
    ))
    mock_lastfm = MagicMock()
    mock_lastfm.get_track_album.return_value = "Pablo Honey"
    mock_lastfm.get_cover_image_url.return_value = 'https://cdn.com/album.jpg'
    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.return_value = b'img'
    svc._embedder = MagicMock()

    svc.fetch_and_embed(tid)

    mock_lastfm.get_track_album.assert_called_once_with("Radiohead", "Creep")
    mock_lastfm.get_cover_image_url.assert_called_once_with("Radiohead", "Pablo Honey")


def test_service_falls_back_to_none_album_when_lookup_fails(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="T", artist="A", download_status="completed",
        file_status="available", file_path="/tmp/s.m4a",
    ))
    mock_lastfm = MagicMock()
    mock_lastfm.get_track_album.return_value = None
    mock_lastfm.get_cover_image_url.return_value = None
    svc = CoverArtService(db_conn, mock_lastfm)
    svc._embedder = MagicMock()

    assert svc.fetch_and_embed(tid) == "not_found"
    mock_lastfm.get_cover_image_url.assert_called_once_with("A", None)
    svc._embedder.embed.assert_not_called()


def test_service_returns_false_when_no_file_path(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="T", artist="A"))
    mock_lastfm = MagicMock()
    svc = CoverArtService(db_conn, mock_lastfm)

    assert svc.fetch_and_embed(tid) == "not_found"
    mock_lastfm.get_cover_image_url.assert_not_called()


def test_service_returns_not_fetched_on_download_error(db_conn):
    # Transient network error → NOT_FETCHED so next batch retries without 7-day cooldown.
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="T", artist="A", download_status="completed",
        file_status="available", file_path="/tmp/s.m4a",
    ))
    mock_lastfm = MagicMock()
    mock_lastfm.get_track_album.return_value = None
    mock_lastfm.get_cover_image_url.return_value = 'https://cdn.com/img.jpg'
    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.side_effect = OSError("network error")
    svc._embedder = MagicMock()

    assert svc.fetch_and_embed(tid) == "not_fetched"
    svc._embedder.embed.assert_not_called()


def test_service_returns_not_fetched_on_embed_error(db_conn):
    # Transient embed error → NOT_FETCHED so next batch retries without 7-day cooldown.
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="T", artist="A", download_status="completed",
        file_status="available", file_path="/tmp/s.m4a",
    ))
    mock_lastfm = MagicMock()
    mock_lastfm.get_track_album.return_value = None
    mock_lastfm.get_cover_image_url.return_value = 'https://cdn.com/img.jpg'
    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.return_value = b'img'
    svc._embedder = MagicMock()
    svc._embedder.embed.side_effect = Exception("mutagen error")

    assert svc.fetch_and_embed(tid) == "not_fetched"


def test_service_fetch_and_embed_async_runs_in_thread(db_conn, mocker):
    init_db(db_conn)
    mock_lastfm = MagicMock()
    svc = CoverArtService(db_conn, mock_lastfm)
    mock_embed = mocker.patch.object(svc, 'fetch_and_embed')
    svc.fetch_and_embed_async(99)
    time.sleep(0.05)
    mock_embed.assert_called_once_with(99)


def test_fetch_and_embed_writes_embedded_status(db_conn, tmp_path):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="Song", artist="Artist", album="Album",
        download_status="completed", file_status="available", file_path="/tmp/song.m4a",
    ))

    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = "https://example.com/cover.jpg"

    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.return_value = b"JPEG_DATA"
    svc._embedder = MagicMock()

    result = svc.fetch_and_embed(tid)

    track = get_track(db_conn, tid)
    assert result == "embedded"
    assert track.artwork_status == "embedded"
    assert track.artwork_fetched_at is not None


def test_fetch_and_embed_writes_not_found_when_no_url(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="Song", artist="Artist", album="Album",
        download_status="completed", file_status="available", file_path="/tmp/song.m4a",
    ))

    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = None

    svc = CoverArtService(db_conn, mock_lastfm)
    result = svc.fetch_and_embed(tid)

    track = get_track(db_conn, tid)
    assert result == "not_found"
    assert track.artwork_status == "not_found"
    assert track.artwork_fetched_at is not None


def test_fetch_and_embed_returns_not_fetched_on_download_error(db_conn):
    # Transient download error must not mark NOT_FOUND — track must remain retryable.
    init_db(db_conn)
    tid = insert_track(db_conn, Track(
        title="Song", artist="Artist", album="Album",
        download_status="completed", file_status="available", file_path="/tmp/song.m4a",
    ))

    mock_lastfm = MagicMock()
    mock_lastfm.get_cover_image_url.return_value = "https://example.com/cover.jpg"

    svc = CoverArtService(db_conn, mock_lastfm)
    svc._fetcher = MagicMock()
    svc._fetcher.fetch_bytes.side_effect = OSError("network error")

    result = svc.fetch_and_embed(tid)

    track = get_track(db_conn, tid)
    assert result == "not_fetched"
    assert track.artwork_status == "not_fetched"


def test_read_bytes_returns_bytes_from_m4a(tmp_path, mocker):
    fake_path = str(tmp_path / "test.m4a")
    image_bytes = b'\xff\xd8\xff\xe0JPEG_DATA'

    mock_mp4 = mocker.MagicMock()
    # MP4Cover is a bytes subclass; use a real bytes object so bytes() conversion works
    mock_mp4.tags = {'covr': [MP4Cover(image_bytes, imageformat=MP4Cover.FORMAT_JPEG)]}
    mocker.patch('src.services.cover_art_service.MP4', return_value=mock_mp4)

    embedder = CoverArtEmbedder()
    result = embedder.read_bytes(fake_path)
    assert result == image_bytes


def test_read_bytes_returns_none_when_no_covr_tag(tmp_path, mocker):
    fake_path = str(tmp_path / "test.m4a")
    mock_mp4 = mocker.MagicMock()
    mock_mp4.tags = {}
    mocker.patch('src.services.cover_art_service.MP4', return_value=mock_mp4)

    embedder = CoverArtEmbedder()
    result = embedder.read_bytes(fake_path)
    assert result is None


def test_read_bytes_returns_bytes_from_mp3(tmp_path, mocker):
    fake_path = str(tmp_path / "test.mp3")
    image_bytes = b'\xff\xd8\xff\xe0JPEG_DATA'

    mock_apic = mocker.MagicMock(spec=APIC)
    mock_apic.data = image_bytes
    mock_id3 = mocker.MagicMock()
    mock_id3.values.return_value = [mock_apic]
    mocker.patch('src.services.cover_art_service.ID3', return_value=mock_id3)

    embedder = CoverArtEmbedder()
    result = embedder.read_bytes(fake_path)
    assert result == image_bytes


def test_get_cover_bytes_returns_bytes_when_embedded(db_conn):
    init_db(db_conn)
    tid = insert_track(db_conn, Track(title="Song", artist="Artist", album="Album",
                                      file_path="/fake/song.m4a"))
    update_track_status(db_conn, tid, download_status="completed")

    mock_lastfm = MagicMock()
    svc = CoverArtService(db_conn, mock_lastfm)
    image_bytes = b'\xff\xd8\xff\xe0JPEG'
    svc._embedder = MagicMock()
    svc._embedder.read_bytes.return_value = image_bytes

    result = svc.get_cover_bytes(tid)
    assert result == image_bytes


def test_get_cover_bytes_returns_none_for_missing_track(db_conn):
    init_db(db_conn)
    mock_lastfm = MagicMock()
    svc = CoverArtService(db_conn, mock_lastfm)
    assert svc.get_cover_bytes(9999) is None
