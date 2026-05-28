from enum import Enum


class DownloadStatus(str, Enum):
    """Lifecycle state of a track's yt-dlp download job."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class FileStatus(str, Enum):
    """Whether the audio file exists on disk and is usable."""

    AVAILABLE = "available"
    MISSING = "missing"
    CORRUPTED = "corrupted"


class LyricsStatus(str, Enum):
    """Result of a LRCLIB lyrics fetch attempt for a track."""

    NOT_FETCHED = "not_fetched"
    NOT_FOUND = "not_found"
    PLAIN_TEXT = "plain_text"
    SYNCHRONIZED = "synchronized"
    INSTRUMENTAL = "instrumental"
    NOT_SUPPORTED = "not_supported"


class PlaylistType(str, Enum):
    """Whether a playlist was created by the user or auto-generated (e.g. from Last.fm)."""

    AUTO = "auto"
    MANUAL = "manual"


class SearchType(str, Enum):
    """Target entity type for a Last.fm search query."""

    ARTIST = "artist"
    TRACK = "track"
    ALBUM = "album"