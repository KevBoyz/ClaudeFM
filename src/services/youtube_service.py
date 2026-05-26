import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from src.database.database import get_track, update_track_status
from src.database.config_manager import get_setting
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("youtube")

_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*]')
_RESERVED = {"CON", "PRN", "AUX", "NUL",
             "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
             "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"}
_MAX_LEN = 200


def sanitize_filename(name: str) -> str:
    name = _WINDOWS_INVALID.sub("_", name)
    name = name.rstrip(". ")
    if name.upper() in _RESERVED:
        name = name + "_"
    return name[:_MAX_LEN]


class YouTubeService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._executor = ThreadPoolExecutor(
            max_workers=int(get_setting(conn, "download_concurrency"))
        )

    def queue_download(self, track_id: int) -> None:
        self._executor.submit(self.download, track_id)

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait)

    def download(self, track_id: int) -> None:
        track = get_track(self._conn, track_id)
        if not track:
            return
        update_track_status(self._conn, track_id, download_status="downloading")
        event_bus.emit("download_progress", {"track_id": track_id, "percent": 0})
        try:
            download_dir = get_setting(self._conn, "download_folder")
            audio_format = get_setting(self._conn, "audio_format")
            query = f"{track.artist} - {track.title}"
            out_path = self._run_ytdlp(query, download_dir, audio_format, track_id)
            update_track_status(
                self._conn, track_id,
                download_status="completed",
                file_status="available",
                file_path=out_path,
                youtube_url=f"ytsearch:{query}",
            )
            event_bus.emit("download_complete", {"track_id": track_id})
        except Exception as e:
            log.error(f"Download failed for track {track_id}: {e}", exc_info=True)
            update_track_status(
                self._conn, track_id,
                download_status="failed",
                download_error=str(e),
            )
            event_bus.emit("download_error", {"track_id": track_id, "message": str(e)})

    def _run_ytdlp(self, query: str, download_dir: str, audio_format: str, track_id: int) -> str:
        import yt_dlp

        filename_tmpl = sanitize_filename("%(artist)s - %(title)s") + ".%(ext)s"
        out_template = str(Path(download_dir) / filename_tmpl)

        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                downloaded = d.get("downloaded_bytes", 0)
                percent = int(downloaded / total * 100)
                event_bus.emit("download_progress", {"track_id": track_id, "percent": percent})

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
            }],
            "default_search": "ytsearch",
            "noplaylist": True,
            "progress_hooks": [progress_hook],
            "quiet": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            filename = ydl.prepare_filename(info)
            final = Path(filename).with_suffix(f".{audio_format}")
            if not final.exists():
                raise FileNotFoundError(f"Download completed but file not found: {final}")
            return str(final)
