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
