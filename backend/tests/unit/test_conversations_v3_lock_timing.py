from datetime import datetime, timedelta, timezone

import pytest

from config.conversations_v3 import boundary_seconds
from utils.conversations.v3 import outline

AT = datetime(2026, 11, 19, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    'gap,lock,expected',
    [
        ('120', '3600', (120, 3600)),
        ('1800', '120', (1800, 120)),
        ('119', '3601', (300, 300)),
        ('1801', '119', (300, 300)),
        ('invalid', '1.5', (300, 300)),
        ('300', '300', (300, 300)),
    ],
)
def test_boundary_settings(monkeypatch, gap, lock, expected):
    monkeypatch.setenv('CONVERSATIONS_V3_SILENCE_GAP_SECONDS', gap)
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', lock)
    assert boundary_seconds(cohesion=True) == expected
    assert boundary_seconds(cohesion=False) == (300, 300)


def test_gap_and_lock_deadlines_are_independent():
    member = {
        'id': 'recording',
        'started_at': AT,
        'transcript_segments': [
            {'start': 0, 'end': 10, 'text': 'synthetic'},
            {'start': 500, 'end': 510, 'text': 'fresh synthetic'},
        ],
    }
    now = AT + timedelta(seconds=900)
    defaults = outline.stretches([member], now)
    assert len(defaults) == 2 and all(g['finished'] for g in defaults)
    groups = outline.stretches([member], now, silence_gap=timedelta(seconds=900), lock_delay=timedelta(seconds=3600))
    assert len(groups) == 1 and not groups[0]['finished']
    (ready,) = outline.stretches(
        [member], now + timedelta(seconds=600), silence_gap=timedelta(seconds=900), lock_delay=timedelta(seconds=3600)
    )
    assert ready['outline_ready'] and not ready['finished']
