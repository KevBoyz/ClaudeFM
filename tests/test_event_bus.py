# tests/test_event_bus.py
import json
import pytest
from unittest.mock import MagicMock, patch
from src.utils.event_bus import EventBus


def test_emit_calls_evaluate_js():
    window = MagicMock()
    bus = EventBus(window)
    bus.emit("download_progress", {"track_id": 1, "percent": 50})
    window.evaluate_js.assert_called_once()
    call_arg = window.evaluate_js.call_args[0][0]
    assert "onEvent" in call_arg
    assert "download_progress" in call_arg


def test_emit_payload_is_valid_json():
    window = MagicMock()
    bus = EventBus(window)
    bus.emit("test_event", {"key": "value", "num": 42})
    call_arg = window.evaluate_js.call_args[0][0]
    # Extract JSON from onEvent(JSON)
    json_str = call_arg[len("onEvent("):-1]
    parsed = json.loads(json_str)
    assert parsed["type"] == "test_event"
    assert parsed["key"] == "value"


def test_emit_does_nothing_when_window_is_none():
    bus = EventBus(None)
    bus.emit("test", {})  # should not raise


def test_set_window_enables_emit():
    window = MagicMock()
    bus = EventBus(None)
    bus.set_window(window)
    bus.emit("ready", {})
    window.evaluate_js.assert_called_once()
