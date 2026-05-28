import re
import shutil
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imageio_ffmpeg
import yt_dlp

from src.database.database import get_track, update_track_status
from src.database.config_manager import get_setting
from src.models.enums import DownloadStatus, FileStatus
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("youtube")


def _read_duration(file_path: str) -> int | None:
    try:
        import mutagen
        meta = mutagen.File(file_path)
        if meta and hasattr(meta, "info"):
            return int(meta.info.length)
    except Exception:
        pass
    return None


_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*]')
_RESERVED = {"CON", "PRN", "AUX", "NUL",
             "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
             "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
_MAX_LEN = 200


def sanitize_filename(name: str) -> str:
    name = _WINDOWS_INVALID.sub("_", name)
    name = name.rstrip(". ")
    if name.upper() in _RESERVED:
        name = name + "_"
    return name[:_MAX_LEN]


class YtDlpDownloader:
    def download(
        self,
        query: str,
        download_dir: str,
        audio_format: str,
        base_name: str,
        on_progress: Callable[[int], None],
    ) -> str:
        filename_tmpl = base_name + ".%(ext)s"
        out_template = str(Path(download_dir) / filename_tmpl)

        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                downloaded = d.get("downloaded_bytes", 0)
                on_progress(int(downloaded / total * 100))

        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_exe = None

        js_runtime = next(
            (r for r in ("node", "deno", "phantomjs") if shutil.which(r)),
            None,
        )

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": audio_format}],
            "default_search": "ytsearch",
            "noplaylist": True,
            "playlist_items": "1",
            "progress_hooks": [progress_hook],
            "quiet": True,
        }
        if js_runtime:
            ydl_opts["js_runtimes"] = {js_runtime: {}}
        if ffmpeg_exe:
            ydl_opts["ffmpeg_location"] = ffmpeg_exe

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            # ytsearch returns a playlist-like dict; unwrap first entry
            if "entries" in info:
                info = next((e for e in info["entries"] if e), None)
                if not info:
                    raise ValueError("No search results found")
            filename = ydl.prepare_filename(info)
            final = Path(filename).with_suffix(f".{audio_format}")
            if not final.exists():
                raise FileNotFoundError(f"Download completed but file not found: {final}")
            return str(final)


class YouTubeService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._executor = ThreadPoolExecutor(
            max_workers=int(get_setting(conn, "download_concurrency"))
        )
        self._active: set[int] = set()
        self._active_lock = threading.Lock()
        self._downloader = YtDlpDownloader()

    def queue_download(self, track_id: int, on_complete: Callable[[int], None] | None = None) -> None:
        with self._active_lock:
            if track_id in self._active:
                log.debug(f"queue_download: track {track_id} already active, skipping")
                return
            self._active.add(track_id)
        self._executor.submit(self._run_download, track_id, on_complete)

    def _run_download(self, track_id: int, on_complete: Callable[[int], None] | None) -> None:
        try:
            self.download(track_id, on_complete)
        finally:
            with self._active_lock:
                self._active.discard(track_id)

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait)

    def download(self, track_id: int, on_complete: Callable[[int], None] | None = None) -> None:
        track = get_track(self._conn, track_id)
        if not track:
            return
        if track.download_status == DownloadStatus.COMPLETED and track.file_status == FileStatus.AVAILABLE:
            if on_complete:
                on_complete(track_id)
            return
        update_track_status(self._conn, track_id, download_status=DownloadStatus.DOWNLOADING)
        event_bus.emit("download_progress", {"track_id": track_id, "percent": 0})
        try:
            download_dir = get_setting(self._conn, "download_folder")
            audio_format = get_setting(self._conn, "audio_format")
            query = f"{track.artist} - {track.title}"
            base_name = sanitize_filename(f"{track.artist} - {track.title}")
            out_path = self._run_ytdlp(query, download_dir, audio_format, track_id, base_name)
            duration = _read_duration(out_path)
            update_track_status(
                self._conn, track_id,
                download_status=DownloadStatus.COMPLETED,
                file_status=FileStatus.AVAILABLE,
                file_path=out_path,
                youtube_url=f"ytsearch:{query}",
                duration=duration,
            )
            event_bus.emit("download_complete", {"track_id": track_id})
            if on_complete:
                on_complete(track_id)
        except Exception as e:
            log.error(f"Download failed for track {track_id}: {e}", exc_info=True)
            update_track_status(
                self._conn, track_id,
                download_status=DownloadStatus.FAILED,
                download_error=str(e),
            )
            event_bus.emit("download_error", {"track_id": track_id, "message": str(e)})

    def _run_ytdlp(self, query: str, download_dir: str, audio_format: str, track_id: int, base_name: str) -> str:
        return self._downloader.download(
            query, download_dir, audio_format, base_name,
            on_progress=lambda pct: event_bus.emit("download_progress", {"track_id": track_id, "percent": pct}),
        )
