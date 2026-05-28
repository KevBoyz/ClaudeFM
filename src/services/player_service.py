import array
import subprocess
import threading

import imageio_ffmpeg
import sounddevice as sd

from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("player")

_SAMPLE_RATE = 44100
_CHANNELS = 2
_CHUNK_FRAMES = 2048
_BYTES_PER_FRAME = 4  # s16le stereo: 2 ch × 2 bytes
_SILENCE = bytes(_CHUNK_FRAMES * _BYTES_PER_FRAME)


def apply_volume(data: bytes, vol: float) -> bytes:
    arr = array.array("h", data)
    for i in range(len(arr)):
        arr[i] = max(-32768, min(32767, int(arr[i] * vol)))
    return arr.tobytes()


class FFmpegDecoder:
    def __init__(self, file_path: str, seek_position: float = 0.0):
        self._file_path = file_path
        self._seek_position = seek_position
        self._proc: subprocess.Popen | None = None

    def __enter__(self) -> "FFmpegDecoder":
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ffmpeg_exe, "-nostdin"]
        if self._seek_position > 0:
            cmd += ["-ss", str(self._seek_position)]
        cmd += ["-i", self._file_path, "-f", "s16le", "-ar",
                str(_SAMPLE_RATE), "-ac", str(_CHANNELS), "-"]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        if self._proc is not None:
            try:
                self._proc.stdout.close()
            except Exception:
                pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                pass
            self._proc = None

    def read_chunk(self) -> bytes | None:
        data = self._proc.stdout.read(_CHUNK_FRAMES * _BYTES_PER_FRAME)
        return data if data else None


class AudioOutput:
    def __enter__(self) -> "AudioOutput":
        # Re-initialize PortAudio to pick up OS default device changes
        # (headphones/speakers connected after app start).
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            pass
        self._stream = sd.RawOutputStream(
            samplerate=_SAMPLE_RATE, channels=_CHANNELS, dtype="int16", blocksize=_CHUNK_FRAMES
        )
        self._stream.__enter__()
        return self

    def __exit__(self, *args) -> None:
        self._stream.__exit__(*args)

    def write(self, data: bytes) -> None:
        needed = _CHUNK_FRAMES * _BYTES_PER_FRAME
        if len(data) < needed:
            data += bytes(needed - len(data))
        self._stream.write(data)

    def write_silence(self) -> None:
        self._stream.write(_SILENCE)


class Queue:
    def __init__(self):
        self._track_ids: list[int] = []
        self._index: int = -1
        self.ended: bool = False

    def set_context(self, track_ids: list[int], start_index: int = 0) -> None:
        self._track_ids = track_ids
        self._index = start_index
        self.ended = False

    def current_id(self) -> int | None:
        if 0 <= self._index < len(self._track_ids):
            return self._track_ids[self._index]
        return None

    def next_id(self) -> int | None:
        next_idx = self._index + 1
        if next_idx < len(self._track_ids):
            self._index = next_idx
            return self._track_ids[self._index]
        self.ended = True
        return None

    def prev_id(self) -> int | None:
        prev_idx = self._index - 1
        if prev_idx >= 0:
            self._index = prev_idx
            return self._track_ids[self._index]
        return None

    def to_dict(self) -> dict:
        return {"track_ids": self._track_ids, "index": self._index}

    @classmethod
    def from_dict(cls, data: dict) -> "Queue":
        q = cls()
        q._track_ids = data.get("track_ids", [])
        q._index = data.get("index", -1)
        return q


class PlayerService:
    def __init__(self):
        self.queue = Queue()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._decoder: FFmpegDecoder | None = None
        self._position: float = 0.0
        self._paused: bool = False
        self._volume: float = 1.0
        self._current_file: str | None = None

    def play(self, file_path: str, seek_position: float = 0.0) -> None:
        self._stop_event.set()
        with self._lock:
            if self._decoder is not None:
                self._decoder.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._stop_event.clear()
        self._position = seek_position
        self._paused = False
        self._current_file = file_path
        self._thread = threading.Thread(
            target=self._playback_thread, args=(file_path, seek_position), daemon=True
        )
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def stop(self) -> None:
        self._stop_event.set()

    def seek(self, position: float) -> None:
        if self._current_file:
            self.play(self._current_file, seek_position=position)

    def set_volume(self, level: float) -> None:
        with self._lock:
            self._volume = max(0.0, min(1.0, level))

    def get_volume(self) -> float:
        with self._lock:
            return self._volume

    def get_position(self) -> float:
        with self._lock:
            return self._position

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def _playback_thread(self, file_path: str, seek_position: float = 0.0) -> None:
        try:
            with FFmpegDecoder(file_path, seek_position) as decoder:
                with self._lock:
                    self._decoder = decoder
                with AudioOutput() as output:
                    while not self._stop_event.is_set():
                        with self._lock:
                            paused = self._paused
                            vol = self._volume
                        if paused:
                            output.write_silence()
                            continue
                        chunk = decoder.read_chunk()
                        if not chunk:
                            break
                        output.write(apply_volume(chunk, vol) if vol != 1.0 else chunk)
                        with self._lock:
                            self._position += _CHUNK_FRAMES / _SAMPLE_RATE

            if not self._stop_event.is_set():
                event_bus.emit("playback_ended", {})

        except Exception as e:
            log.error(f"Playback error: {e}", exc_info=True)
            event_bus.emit("playback_failed", {"message": str(e)})
        finally:
            with self._lock:
                self._decoder = None
