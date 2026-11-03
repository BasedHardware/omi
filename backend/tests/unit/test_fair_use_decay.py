"""The fair-use ladder has persisted, bounded exits and cannot overwrite a newer row."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.fair_use as store
import routers.fair_use_admin as admin
import utils.fair_use as engine
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.observability import fair_use as metrics

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
PERIOD = timedelta(days=7)
PATH = ('users', 'decay-user', 'fair_use_state', 'current')


@pytest.fixture
def state_store(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(store, 'get_fair_use_state', lambda uid: dict(client.rows[PATH]))
    monkeypatch.setattr(store, 'update_fair_use_state', lambda uid, updates: client.rows[PATH].update(updates))
    monkeypatch.setattr(engine, 'redis_client', MagicMock())
    monkeypatch.setattr(engine, 'FAIR_USE_THROTTLE_DECAY_ENABLED', True)
    return client.rows


def read(rows, now=NOW):
    return engine.normalize_expired_restriction_state('decay-user', dict(rows[PATH]), now=now)


@pytest.mark.parametrize('deadline', [NOW - timedelta(seconds=1), None, 'broken', 123, '2026-11-03T00:00:00Z'])
def test_expired_or_unknown_throttle_recovers_on_first_read(state_store, deadline):
    state_store[PATH] = {'stage': 'throttle', 'throttle_until': deadline}
    result = read(state_store)
    assert result['stage'] == state_store[PATH]['stage'] == 'warning'
    assert result['throttle_until'] is None
    assert result['warning_until'] == NOW + PERIOD
    assert result['stage_entered_at'] == NOW
    engine.redis_client.delete.assert_called_once_with('fair_use:stage:decay-user')
    assert read(state_store, NOW + PERIOD)['stage'] == 'warning'
    assert read(state_store, NOW + PERIOD + timedelta(seconds=1))['stage'] == 'none'


def test_missing_throttle_deadline_recovers(state_store):
    state_store[PATH] = {'stage': 'throttle'}
    assert read(state_store)['stage'] == 'warning'


def test_malformed_throttle_emits_recovery_fallback(state_store, monkeypatch):
    fallback = MagicMock()
    monkeypatch.setattr(engine, 'record_fallback', fallback)
    state_store[PATH] = {'stage': 'throttle', 'throttle_until': 'broken'}
    assert read(state_store)['stage'] == 'warning'
    fallback.assert_called_once_with(
        component='other',
        from_mode='throttle',
        to_mode='warning',
        reason='malformed_doc',
        outcome='recovered',
        log=engine.logger,
    )


@pytest.mark.parametrize('deadline', [NOW + timedelta(seconds=1), NOW, '2026-11-05T00:00:00', '2026-11-05T00:00:00Z'])
def test_active_throttle_does_not_decay(state_store, deadline):
    state_store[PATH] = {'stage': 'throttle', 'throttle_until': deadline}
    assert read(state_store)['stage'] == 'throttle'
    assert state_store[PATH] == {'stage': 'throttle', 'throttle_until': deadline}
    engine.redis_client.delete.assert_not_called()


def test_full_downward_ladder_with_clock(state_store):
    state_store[PATH] = {'stage': 'restrict', 'restrict_until': NOW - timedelta(seconds=1)}
    throttle = read(state_store)
    assert throttle['stage'] == 'throttle'
    assert throttle['throttle_until'] == NOW + PERIOD
    assert read(state_store, NOW + PERIOD)['stage'] == 'throttle'
    exit_time = NOW + PERIOD + timedelta(seconds=1)
    assert read(state_store, exit_time)['stage'] == 'warning'
    assert read(state_store, exit_time + PERIOD)['stage'] == 'warning'
    assert read(state_store, exit_time + PERIOD + timedelta(seconds=1))['stage'] == 'none'


@pytest.mark.parametrize('stage', ['throttle', 'warning'])
def test_switch_off_preserves_expired_stages(state_store, monkeypatch, stage):
    monkeypatch.setattr(engine, 'FAIR_USE_THROTTLE_DECAY_ENABLED', False)
    original = {'stage': stage, f'{stage}_until': NOW - PERIOD}
    state_store[PATH] = dict(original)
    assert read(state_store) == original
    assert state_store[PATH] == original


def test_switch_off_preserves_original_restrict_exit(state_store, monkeypatch):
    monkeypatch.setattr(engine, 'FAIR_USE_THROTTLE_DECAY_ENABLED', False)
    state_store[PATH] = {'stage': 'restrict', 'restrict_until': NOW - PERIOD}
    assert read(state_store) == {'stage': 'throttle', 'restrict_until': None}
    assert 'throttle_until' not in state_store[PATH]


@pytest.mark.parametrize(
    'replacement',
    [
        {'stage': 'restrict', 'restrict_until': NOW + PERIOD},
        {'stage': 'throttle', 'throttle_until': NOW + PERIOD},
        {'stage': 'warning', 'warning_until': NOW + PERIOD},
    ],
)
def test_stale_reader_cannot_clobber_escalation_or_renewal(state_store, replacement):
    stale = {'stage': 'throttle', 'throttle_until': NOW - PERIOD}
    state_store[PATH] = dict(replacement)
    before = metrics.STAGE_DECAY_TOTAL.labels(from_stage='throttle', to_stage='warning')._value.get()
    result = engine.normalize_expired_restriction_state('decay-user', stale, now=NOW)
    assert result == state_store[PATH] == replacement
    assert metrics.STAGE_DECAY_TOTAL.labels(from_stage='throttle', to_stage='warning')._value.get() == before


def test_legacy_warning_gets_bounded_quiet_period(state_store):
    state_store[PATH] = {'stage': 'warning'}
    assert read(state_store)['warning_until'] == NOW + PERIOD
    assert read(state_store, NOW + PERIOD + timedelta(seconds=1))['stage'] == 'none'


def test_legacy_warning_with_old_violation_clears(state_store):
    state_store[PATH] = {'stage': 'warning', 'last_violation_at': NOW - PERIOD - timedelta(seconds=1)}
    assert read(state_store)['stage'] == 'none'


def test_dwell_and_decay_metrics_on_read(state_store):
    state_store[PATH] = {'stage': 'throttle', 'stage_entered_at': NOW - PERIOD, 'throttle_until': NOW - PERIOD}
    counter = metrics.STAGE_DECAY_TOTAL.labels(from_stage='throttle', to_stage='warning')
    before = counter._value.get()
    read(state_store)
    assert metrics.STAGE_DWELL_SECONDS.labels(stage='throttle')._value.get() == PERIOD.total_seconds()
    assert counter._value.get() == before + 1
    read(state_store)
    assert counter._value.get() == before + 1
    assert metrics.STAGE_DWELL_SECONDS.labels(stage='warning')._value.get() == 0


@pytest.mark.parametrize(
    'stage, expected, message',
    [
        ('throttle', 'warning', 'higher than typical'),
        ('warning', 'none', 'within normal limits'),
    ],
)
def test_status_endpoint_returns_persisted_decayed_stage(state_store, monkeypatch, stage, expected, message):
    state_store[PATH] = {'stage': stage, f'{stage}_until': datetime.now(timezone.utc) - PERIOD}
    monkeypatch.setattr(admin, 'get_rolling_speech_ms', lambda uid: {})
    monkeypatch.setattr(
        admin,
        'get_dg_budget_status',
        lambda uid: {'daily_limit_ms': 0, 'used_ms': 0, 'remaining_ms': 0, 'exhausted': False},
    )
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin.get_current_user_uid] = lambda: 'decay-user'
    with TestClient(app) as http:
        response = http.get('/v1/fair-use/status')
        assert response.status_code == 200
        assert response.json()['stage'] == expected
        assert message in response.json()['message']
    assert state_store[PATH]['stage'] == expected


def test_cache_miss_returns_decayed_stage(state_store):
    state_store[PATH] = {'stage': 'throttle'}
    engine.redis_client.get.return_value = None
    assert engine.get_enforcement_stage('decay-user') == 'warning'
    engine.redis_client.setex.assert_called_once_with('fair_use:stage:decay-user', 60, 'warning')


@pytest.mark.parametrize('initial_stage', ['none', 'warning'])
def test_warning_entry_or_qualifying_violation_stamps_quiet_deadline(state_store, monkeypatch, initial_stage):
    state_store[PATH] = {'stage': initial_stage}
    monkeypatch.setattr(store, 'get_violation_counts', lambda uid: {'violation_count_7d': 1, 'violation_count_30d': 1})
    monkeypatch.setattr(store, 'create_fair_use_event', lambda uid, data: 'event')
    monkeypatch.setattr(store, 'get_fair_use_events', lambda uid, limit: [])
    monkeypatch.setattr(engine, 'get_rolling_speech_ms', lambda uid: {})
    before = datetime.now(timezone.utc)
    engine.escalate_enforcement('decay-user', [], {'misuse_score': 0.9})
    row = state_store[PATH]
    assert row['stage'] == 'warning'
    assert before + PERIOD <= row['warning_until'] <= datetime.now(timezone.utc) + PERIOD


@pytest.mark.parametrize('decay_first', [True, False], ids=['decay-then-escalation', 'escalation-then-decay'])
def test_qualifying_violation_survives_both_warning_decay_commit_orders(state_store, monkeypatch, decay_first):
    now = datetime.now(timezone.utc)
    expired_warning = {'stage': 'warning', 'warning_until': now - PERIOD}
    state_store[PATH] = dict(expired_warning)
    events = []

    def violation_counts(uid):
        # Escalation has already read the warning when it asks for counts. Let
        # the real decay transaction commit before escalation's write.
        if decay_first:
            decayed = engine.normalize_expired_restriction_state(uid, expired_warning, now=now)
            assert decayed['stage'] == 'none'
        return {'violation_count_7d': 1, 'violation_count_30d': 1}

    monkeypatch.setattr(store, 'get_violation_counts', violation_counts)
    monkeypatch.setattr(store, 'create_fair_use_event', lambda uid, data: events.append(data) or 'event')
    monkeypatch.setattr(store, 'get_fair_use_events', lambda uid, limit: [])
    monkeypatch.setattr(engine, 'get_rolling_speech_ms', lambda uid: {})

    result = engine.escalate_enforcement('decay-user', [], {'misuse_score': 0.9, 'usage_type': 'audiobook'})
    if not decay_first:
        # The status reader captured its row before renewal, but commits after it.
        observed = engine.normalize_expired_restriction_state('decay-user', expired_warning, now=now)
        assert observed['stage'] == 'warning'

    assert state_store[PATH]['stage'] == result['new_stage'] == 'warning'
    assert state_store[PATH]['last_violation_at'] >= now
    assert state_store[PATH]['warning_until'] >= now + PERIOD
    expected_previous_stage = 'none' if decay_first else 'warning'
    expected_action = 'warning' if decay_first else 'none'
    assert result['previous_stage'] == events[0]['previous_stage'] == expected_previous_stage
    assert result['action'] == events[0]['enforcement_action'] == expected_action


@pytest.mark.parametrize('stage', ['warning', 'throttle'])
@pytest.mark.parametrize('enabled', [True, False])
def test_admin_entry_writes_deadline_unless_switch_off(state_store, monkeypatch, stage, enabled):
    monkeypatch.setattr(admin, 'FAIR_USE_THROTTLE_DECAY_ENABLED', enabled)
    state_store[PATH] = {}
    assert admin.set_user_stage('decay-user', stage=stage, admin_id='admin')['stage'] == stage
    row = state_store[PATH]
    if enabled:
        assert row[f'{stage}_until'] == row['stage_entered_at'] + PERIOD
    else:
        assert row == {'stage': stage}
