import json
from src.utils.logger import get_logger

log = get_logger("event_bus")


class EventBus:
    def __init__(self, window=None):
        self._window = window

    def set_window(self, window) -> None:
        self._window = window

    def emit(self, event_type: str, payload: dict) -> None:
        if self._window is None:
            return
        data = json.dumps({"type": event_type, **payload})
        js = f"onEvent({data})"
        try:
            self._window.evaluate_js(js)
        except Exception as e:
            log.error(f"EventBus.emit failed for '{event_type}': {e}", exc_info=True)


event_bus = EventBus()
