import threading
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("player")


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
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._position: float = 0.0
        self._paused: bool = False
        self._lock = threading.Lock()

    def play(self, file_path: str) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._stop_event.clear()
        self._position = 0.0
        self._paused = False
        self._thread = threading.Thread(
            target=self._playback_thread, args=(file_path,), daemon=True
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

    def get_position(self) -> float:
        with self._lock:
            return self._position

    def _playback_thread(self, file_path: str) -> None:
        try:
            import miniaudio
            import time
            stream = miniaudio.stream_file(file_path)
            with miniaudio.PlaybackDevice() as device:
                device.start(stream)
                while not self._stop_event.is_set():
                    with self._lock:
                        paused = self._paused
                    if paused:
                        time.sleep(0.1)
                        continue
                    with self._lock:
                        self._position += 0.1
                    time.sleep(0.1)
            event_bus.emit("playback_ended", {})
        except Exception as e:
            log.error(f"Playback error: {e}", exc_info=True)
            event_bus.emit("playback_ended", {})
