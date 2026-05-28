import json
from src.utils.logger import get_logger

log = get_logger("event_bus")


class EventBus:
    """Singleton bridge that pushes server-side events to the JS frontend.

    Calls ``window.evaluate_js("onEvent({...})")`` with a flat JSON object
    where ``type`` and all payload fields are at the same level. No module
    should call ``evaluate_js`` directly — route everything through here so
    the window lifecycle is isolated and the bus stays testable without a real
    window.
    """

    def __init__(self, window=None):
        self._window = window

    def set_window(self, window) -> None:
        """Attach the pywebview window created after startup."""
        self._window = window

    def emit(self, event_type: str, payload: dict) -> None:
        """Push an event to the frontend.

        Silently drops the event if no window has been set yet (e.g. during
        startup before pywebview is ready).
        """
        if self._window is None:
            return
        data = json.dumps({"type": event_type, **payload})
        js = f"onEvent({data})"
        try:
            self._window.evaluate_js(js)
        except Exception as e:
            log.error(
                f"EventBus.emit failed for '{event_type}': {e}", exc_info=True)


event_bus = EventBus()
