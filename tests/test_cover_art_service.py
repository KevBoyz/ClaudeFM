# tests/test_cover_art_service.py
import pytest
from unittest.mock import MagicMock, call, patch
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
    assert any(k.lower() == 'user-agent' for k in captured['req'].headers)


def test_fetcher_propagates_exceptions(mocker):
    mocker.patch(
        'src.services.cover_art_service.urllib.request.urlopen',
        side_effect=OSError("timeout"),
    )
    with pytest.raises(OSError):
        CoverArtFetcher().fetch_bytes('http://bad.url/img.jpg')
