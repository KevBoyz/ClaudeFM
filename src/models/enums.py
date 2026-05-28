from enum import Enum


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class FileStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    CORRUPTED = "corrupted"


class LyricsStatus(str, Enum):
    NOT_FETCHED = "not_fetched"
    NOT_FOUND = "not_found"
    PLAIN_TEXT = "plain_text"
    SYNCHRONIZED = "synchronized"
    INSTRUMENTAL = "instrumental"
    NOT_SUPPORTED = "not_supported"


class PlaylistType(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class SearchType(str, Enum):
    ARTIST = "artist"
    TRACK = "track"
    ALBUM = "album"