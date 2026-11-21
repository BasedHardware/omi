"""Generated entry/read schedules must let the fair-use ladder reach its base."""

from datetime import timedelta
import random
from unittest.mock import MagicMock

import pytest

import database.fair_use as store
import utils.fair_use as engine
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

STAGES = ('none', 'warning', 'throttle', 'restrict')
UID = 'synthetic-lifecycle-ladder'
PATH = ('users', UID, 'fair_use_state', 'current')


@pytest.mark.parametrize('seed', range(8))
@pytest.mark.parametrize('escalations', [1, 2, 3], ids=['warning', 'throttle', 'restrict'])
def test_escalated_ladder_reaches_base_after_bounded_quiet_reads(monkeypatch, seed, escalations):
    # #24531 repaired latch F1. This is a green regression, not a stale xfail.
    client = StrictFirestore()
    client.rows[PATH] = {'stage': 'none'}
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(store, 'get_fair_use_state', lambda uid: dict(client.rows[PATH]))
    monkeypatch.setattr(store, 'update_fair_use_state', lambda uid, patch: client.rows[PATH].update(patch))
    monkeypatch.setattr(store, 'create_fair_use_event', lambda uid, event: 'synthetic-event')
    monkeypatch.setattr(store, 'get_fair_use_events', lambda uid, limit: [])
    monkeypatch.setattr(engine, 'redis_client', MagicMock())
    monkeypatch.setattr(engine, 'get_rolling_speech_ms', lambda uid: {})
    monkeypatch.setattr(engine, 'FAIR_USE_THROTTLE_DECAY_ENABLED', True)
    violations = [0]
    monkeypatch.setattr(
        store,
        'get_violation_counts',
        lambda uid: {'violation_count_7d': violations[0], 'violation_count_30d': violations[0]},
    )

    for count in range(1, escalations + 1):
        violations[0] = count
        result = engine.escalate_enforcement(UID, [], {'misuse_score': 1.0, 'usage_type': 'synthetic'})
        assert result['new_stage'] == client.rows[PATH]['stage'] == STAGES[count]
        assert client.rows[PATH][f'{STAGES[count]}_until'] > client.rows[PATH]['stage_entered_at']

    rng = random.Random(seed)
    observed = []
    for _ in range(escalations):
        row = dict(client.rows[PATH])
        stage = row['stage']
        deadline = row[f'{stage}_until']
        # Several generated reads inside the quiet period must preserve it.
        entered = row['stage_entered_at']
        for fraction in sorted(rng.random() for _ in range(3)):
            active_at = entered + (deadline - entered) * fraction
            assert engine.normalize_expired_restriction_state(UID, dict(row), now=active_at) == row
        assert engine.normalize_expired_restriction_state(UID, dict(row), now=deadline) == row

        expired_at = deadline + timedelta(microseconds=rng.randint(1, 10_000_000))
        after = engine.normalize_expired_restriction_state(UID, dict(row), now=expired_at)
        assert after == client.rows[PATH]
        assert STAGES.index(after['stage']) == STAGES.index(stage) - 1
        observed.append(after['stage'])

    assert observed[-1] == client.rows[PATH]['stage'] == 'none'
    baseline = dict(client.rows[PATH])
    assert engine.normalize_expired_restriction_state(UID, baseline, now=expired_at + timedelta(days=365)) == baseline
