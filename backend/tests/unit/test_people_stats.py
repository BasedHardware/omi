from datetime import datetime, timezone
import pytest

from utils.people_stats import aggregate_people_stats, collect_people_stats


def test_aggregate_people_stats_basic():
    conv1 = {
        'id': 'c1',
        'started_at': datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
        'transcript_segments': [
            {'person_id': 'p1', 'start': 0.0, 'end': 10.0},
            {'person_id': 'p2', 'start': 10.0, 'end': 25.0},
        ],
    }
    conv2 = {
        'id': 'c2',
        'started_at': datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        'transcript_segments': [
            {'person_id': 'p1', 'start': 5.0, 'end': 15.0},
        ],
    }
    stats = aggregate_people_stats([conv1, conv2])
    assert stats['p1']['conversation_count'] == 2
    assert stats['p1']['talk_seconds'] == 20.0
    assert stats['p1']['last_heard_at'] == datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
    assert stats['p2']['conversation_count'] == 1
    assert stats['p2']['talk_seconds'] == 15.0


def test_aggregate_people_stats_skips_discarded_tombstone():
    conv_valid = {
        'id': 'c1',
        'started_at': datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
        'transcript_segments': [
            {'person_id': 'p1', 'start': 0.0, 'end': 10.0},
        ],
    }
    conv_tombstone = {
        'id': 'c_tombstone',
        'discarded': True,
        'started_at': datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        'transcript_segments': [
            {'person_id': 'p1', 'start': 0.0, 'end': 50.0},
        ],
    }
    stats = aggregate_people_stats([conv_valid, conv_tombstone])
    assert stats['p1']['conversation_count'] == 1
    assert stats['p1']['talk_seconds'] == 10.0


def test_collect_people_stats_with_tombstone_row_in_scan():
    """Verify collect_people_stats continues scanning past tombstone rows."""
    conv_page1 = [
        {
            'id': 'c1',
            'started_at': datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
            'transcript_segments': [{'person_id': 'p1', 'start': 0.0, 'end': 10.0}],
        },
        {
            'id': 'c2_tombstone',
            'discarded': True,
            'transcript_segments': [{'person_id': 'p1', 'start': 0.0, 'end': 10.0}],
        },
    ]
    conv_page2 = [
        {
            'id': 'c3',
            'started_at': datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc),
            'transcript_segments': [{'person_id': 'p2', 'start': 0.0, 'end': 20.0}],
        },
    ]

    pages = {
        (2, 0): conv_page1,
        (2, 2): conv_page2,
        (2, 3): [],
    }

    def fake_reader(limit, offset):
        return pages.get((limit, offset), [])

    stats = collect_people_stats(fake_reader, scan_cap=10, batch=2)
    assert 'p1' in stats
    assert stats['p1']['conversation_count'] == 1
    assert 'p2' in stats
    assert stats['p2']['conversation_count'] == 1
    assert stats['p2']['talk_seconds'] == 20.0
