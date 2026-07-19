from datetime import datetime, timezone
from types import SimpleNamespace

from utils.people_leaderboard import build_people_leaderboard


def _seg(person_id, start=0.0, end=1.0, is_user=False):
    return SimpleNamespace(person_id=person_id, start=start, end=end, is_user=is_user)


def _conv(segments, created_at=None):
    return SimpleNamespace(transcript_segments=segments, created_at=created_at, started_at=created_at)


def _at(day):
    return datetime(2026, 1, day, tzinfo=timezone.utc)


def test_ranks_by_conversation_count():
    convos = [
        _conv([_seg('alice')], _at(1)),
        _conv([_seg('alice'), _seg('bob')], _at(2)),
        _conv([_seg('alice')], _at(3)),
    ]
    board = build_people_leaderboard(convos, {'alice': 'Alice', 'bob': 'Bob'}, limit=10)
    assert [e.person_id for e in board] == ['alice', 'bob']
    assert board[0].conversation_count == 3
    assert board[1].conversation_count == 1
    assert board[0].name == 'Alice'


def test_counts_each_person_once_per_conversation():
    # Alice speaks in several segments of ONE conversation: count 1, seconds summed.
    convos = [_conv([_seg('alice', 0, 2), _seg('alice', 5, 6)], _at(1))]
    board = build_people_leaderboard(convos, {'alice': 'Alice'}, limit=10)
    assert board[0].conversation_count == 1
    assert board[0].speaking_seconds == 3.0


def test_tie_broken_by_speaking_time():
    convos = [
        _conv([_seg('quiet', 0, 1)], _at(1)),
        _conv([_seg('chatty', 0, 30)], _at(1)),
    ]
    board = build_people_leaderboard(convos, {}, limit=10)
    assert [e.person_id for e in board] == ['chatty', 'quiet']


def test_excludes_user_and_unattributed_segments():
    convos = [_conv([_seg('me', is_user=True), _seg(None), _seg('alice')], _at(1))]
    board = build_people_leaderboard(convos, {'alice': 'Alice'}, limit=10)
    assert [e.person_id for e in board] == ['alice']


def test_unknown_name_falls_back_and_is_not_dropped():
    convos = [_conv([_seg('ghost')], _at(1))]
    board = build_people_leaderboard(convos, {}, limit=10)
    assert len(board) == 1
    assert board[0].name == 'Unknown'


def test_last_talked_at_is_most_recent():
    convos = [_conv([_seg('alice')], _at(1)), _conv([_seg('alice')], _at(5))]
    board = build_people_leaderboard(convos, {'alice': 'Alice'}, limit=10)
    assert board[0].last_talked_at == _at(5)


def test_limit_caps_results():
    convos = [_conv([_seg(f'p{i}')], _at(1)) for i in range(5)]
    board = build_people_leaderboard(convos, {}, limit=2)
    assert len(board) == 2


def test_tie_broken_by_name_when_metrics_equal():
    # Equal conversation count and speaking time, different names: ordered by name.
    convos = [_conv([_seg('bob', 0, 5), _seg('amy', 0, 5)], _at(1))]
    board = build_people_leaderboard(convos, {'amy': 'Amy', 'bob': 'Bob'}, limit=10)
    assert [e.person_id for e in board] == ['amy', 'bob']


def test_order_is_deterministic_for_duplicate_names_and_equal_metrics():
    # Two different people share a display name with identical metrics: person_id
    # is the final tie-breaker, so the order is stable regardless of traversal order.
    convos = [_conv([_seg('p_b', 0, 1), _seg('p_a', 0, 1)], _at(1))]
    board = build_people_leaderboard(convos, {'p_a': 'Sam', 'p_b': 'Sam'}, limit=10)
    assert [e.person_id for e in board] == ['p_a', 'p_b']


def test_empty_input_returns_empty():
    assert build_people_leaderboard([], {}, limit=10) == []
