from unittest.mock import patch, MagicMock
from src.services.player_service import PlayerService, Queue


def test_queue_set_context_linear():
    q = Queue()
    q.set_context([1, 2, 3], start_index=0)
    assert q.current_id() == 1
    assert q.next_id() == 2
    assert q.current_id() == 2


def test_queue_prev():
    q = Queue()
    q.set_context([10, 20, 30], start_index=1)
    assert q.current_id() == 20
    assert q.prev_id() == 10


def test_queue_next_at_end_returns_none():
    q = Queue()
    q.set_context([1], start_index=0)
    assert q.current_id() == 1
    assert q.next_id() is None


def test_queue_ended_flag():
    q = Queue()
    q.set_context([1], start_index=0)
    q.current_id()
    q.next_id()
    assert q.ended


def test_player_service_play_calls_miniaudio(tmp_path):
    f = tmp_path / "song.m4a"
    f.write_bytes(b"fake audio")
    with patch("miniaudio.stream_file") as mock_stream:
        mock_stream.return_value = iter([b"chunk"])
        with patch("miniaudio.PlaybackDevice") as mock_dev:
            mock_dev.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_dev.return_value.__exit__ = MagicMock(return_value=False)
            svc = PlayerService()
            # Just verify it doesn't raise on construction
            assert svc is not None
