from datetime import datetime, timezone

from utils.people_stats import aggregate_people_stats, collect_people_stats


def _conv(when, *segments, **extra):
    return {"started_at": when, "transcript_segments": list(segments), **extra}


def test_counts_conversations_once_per_person_and_sums_talk_time():
    t1 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 5, tzinfo=timezone.utc)
    stats = aggregate_people_stats(
        [
            _conv(t2, {"person_id": "p1", "start": 0, "end": 10}, {"person_id": "p1", "start": 20, "end": 25}),
            _conv(t1, {"person_id": "p1", "start": 0, "end": 5}, {"person_id": "p2", "start": 5, "end": 6}),
        ]
    )
    assert stats["p1"] == {"conversation_count": 2, "last_heard_at": t2, "talk_seconds": 20.0}
    assert stats["p2"]["conversation_count"] == 1


def test_ignores_locked_and_malformed_rows():
    stats = aggregate_people_stats(
        [
            _conv(None, {"person_id": "p1", "start": 0, "end": 1}, is_locked=True),
            {"transcript_segments": "oops"},
            _conv(None, None, {"person_id": None}, {"person_id": "p3", "start": 4, "end": 2}),
        ]
    )
    assert set(stats) == {"p3"} and stats["p3"]["talk_seconds"] == 0.0


def test_collect_stops_at_cap_and_short_page():
    rows = [_conv(None, {"person_id": "p1", "start": 0, "end": 1}) for _ in range(30)]
    calls = []

    def fetch(limit, offset):
        calls.append((limit, offset))
        return rows[offset : offset + limit]

    assert collect_people_stats(fetch, scan_cap=25, batch=10)["p1"]["conversation_count"] == 25
    assert calls == [(10, 0), (10, 10), (5, 20)]
    assert collect_people_stats(fetch, scan_cap=100, batch=10)["p1"]["conversation_count"] == 30
