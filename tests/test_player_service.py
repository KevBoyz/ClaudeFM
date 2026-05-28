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


def test_player_service_construction():
    svc = PlayerService()
    assert svc is not None
    assert svc.get_position() == 0.0
    assert svc.get_volume() == 1.0


# ── Queue serialization ───────────────────────────────────────────────────────

def test_queue_current_id_when_empty():
    q = Queue()
    assert q.current_id() is None


def test_queue_prev_id_at_start_returns_none():
    q = Queue()
    q.set_context([1, 2, 3], start_index=0)
    assert q.prev_id() is None


def test_queue_to_dict():
    q = Queue()
    q.set_context([1, 2, 3], start_index=1)
    d = q.to_dict()
    assert d == {"track_ids": [1, 2, 3], "index": 1}


def test_queue_from_dict_roundtrip():
    q = Queue()
    q.set_context([10, 20, 30], start_index=2)
    q2 = Queue.from_dict(q.to_dict())
    assert q2.current_id() == q.current_id()
    assert q2.to_dict() == q.to_dict()


def test_queue_from_dict_empty():
    q = Queue.from_dict({})
    assert q.current_id() is None
    assert q.ended is False


def test_queue_set_context_resets_ended():
    q = Queue()
    q.set_context([1], start_index=0)
    q.next_id()
    assert q.ended is True
    q.set_context([1, 2], start_index=0)
    assert q.ended is False


# ── PlayerService state ───────────────────────────────────────────────────────

def test_player_service_is_paused_initially_false():
    svc = PlayerService()
    assert svc.is_paused is False


def test_player_service_pause():
    svc = PlayerService()
    svc.pause()
    assert svc.is_paused is True


def test_player_service_pause_then_resume():
    svc = PlayerService()
    svc.pause()
    svc.resume()
    assert svc.is_paused is False


def test_player_service_set_volume_clamps_high():
    svc = PlayerService()
    svc.set_volume(2.0)
    assert svc.get_volume() == 1.0


def test_player_service_set_volume_clamps_low():
    svc = PlayerService()
    svc.set_volume(-0.5)
    assert svc.get_volume() == 0.0


def test_player_service_set_volume_midrange():
    svc = PlayerService()
    svc.set_volume(0.7)
    assert abs(svc.get_volume() - 0.7) < 1e-9


def test_player_service_get_position_initially_zero():
    svc = PlayerService()
    assert svc.get_position() == 0.0


def test_player_service_seek_without_current_file_is_noop():
    svc = PlayerService()
    svc.seek(30.0)  # _current_file is None — should not raise or change position
    assert svc.get_position() == 0.0
