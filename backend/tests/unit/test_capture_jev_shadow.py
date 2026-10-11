"""EXP-003 admission and telemetry contracts; no provider or Firestore calls."""

import json
from datetime import datetime, timezone

import fakeredis

from config.jev_decisions import capture_jev_shadow_enabled
from utils.conversations import capture_jev_shadow as shadow
from utils.conversations import capture_shadow_outcomes as outcomes


def test_hard_expiry_even_if_flag_and_later_override(monkeypatch):
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_EXPIRY', '2026-11-01T00:00:00Z')
    assert capture_jev_shadow_enabled(datetime(2026, 10, 17, tzinfo=timezone.utc)) == (True, 'enabled')
    assert capture_jev_shadow_enabled(datetime(2026, 10, 18, tzinfo=timezone.utc)) == (False, 'expired')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_EXPIRY', 'broken')
    assert capture_jev_shadow_enabled(datetime(2026, 10, 1, tzinfo=timezone.utc)) == (False, 'expired')


def test_naive_or_date_only_deadline_fails_closed_without_raising(monkeypatch):
    """A deadline with no UTC offset is malformed: the contract is fail-closed, not TypeError."""
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    for value in ('2026-10-05T00:00:00', '2026-10-05'):
        monkeypatch.setenv('CAPTURE_JEV_SHADOW_EXPIRY', value)
        assert capture_jev_shadow_enabled(datetime(2026, 10, 1, tzinfo=timezone.utc)) == (False, 'expired')


def test_expired_shadow_never_submits(monkeypatch):
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_EXPIRY', '2026-09-01T00:00:00Z')
    submitted = []
    monkeypatch.setattr(shadow, 'submit_with_context', lambda *args: submitted.append(args))
    shadow.submit_same_scene('david', 'a', 'b')
    shadow.submit_resummary('david', 'a', 'b')
    assert not submitted


def test_outcome_log_obeys_flag_and_expiry(monkeypatch):
    emitted = []
    monkeypatch.setattr(outcomes.logger, 'info', lambda *args: emitted.append(args))
    monkeypatch.delenv('CAPTURE_JEV_SHADOW_ENABLED', raising=False)
    outcomes.record_capture_outcome('uid', 'separate', ['a', 'b'], separated_id='a')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_EXPIRY', '2026-09-01T00:00:00Z')
    outcomes.record_capture_outcome('uid', 'separate', ['a', 'b'], separated_id='a')
    assert not emitted


def test_cohort_default_allowlist_only(monkeypatch):
    monkeypatch.delenv('CAPTURE_JEV_SHADOW_PERCENT', raising=False)
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_UID_ALLOWLIST', 'david')
    assert shadow._in_cohort('david')
    assert not shadow._in_cohort('other')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_PERCENT', '100')
    assert shadow._in_cohort('other')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_PERCENT', 'broken')
    assert not shadow._in_cohort('other')


def test_atomic_global_and_user_caps(monkeypatch):
    monkeypatch.setattr(shadow.redis_db, 'r', fakeredis.FakeRedis())
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_GLOBAL_DAILY_CAP', '2')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_USER_DAILY_CAP', '1')
    assert shadow._cap('a', 'same_scene', '1', '2') == 'admitted'
    assert shadow._cap('a', 'same_scene', '2', '1') == 'duplicate'
    assert shadow._cap('a', 'same_scene', '1', '3') == 'cap'
    assert shadow._cap('b', 'same_scene', '1', '2') == 'admitted'
    assert shadow._cap('c', 'same_scene', '1', '2') == 'cap'


def test_fail_closed_error_and_timeout(monkeypatch):
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_UID_ALLOWLIST', 'david')
    monkeypatch.setattr(shadow, 'submit_with_context', lambda _executor, fn, *args: fn(*args))
    monkeypatch.setattr(
        shadow.conversations_db,
        'get_conversation_for_capture_check',
        lambda *args: ({'transcript_segments': [{'text': 'many words ' * 20}]}, 'fingerprint'),
    )
    monkeypatch.setattr(shadow, '_cap', lambda *args: 'admitted')
    emitted = []
    monkeypatch.setattr(shadow, '_record', lambda record: emitted.append(record))
    monkeypatch.setattr(shadow, 'ask_jev', lambda *args, **kwargs: None)
    shadow.submit_same_scene('david', 'a', 'b')
    assert emitted[-1]['p'] is None and emitted[-1]['would_decide'] is None
    before = shadow.CAPTURE_JEV_SHADOW_SKIPS.labels('same_scene', 'timeout')._value.get()

    def vendor_timeout(*args, **kwargs):
        kwargs['outcome_observer']('timeout')
        return None

    monkeypatch.setattr(shadow, 'ask_jev', vendor_timeout)
    shadow.submit_same_scene('david', 'a', 'b')
    assert shadow.CAPTURE_JEV_SHADOW_SKIPS.labels('same_scene', 'timeout')._value.get() == before + 1
    assert emitted[-1]['outcome'] == 'timeout' and emitted[-1]['p'] is None
    monkeypatch.setattr(shadow, 'ask_jev', lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()))
    prior_records = len(emitted)
    shadow.submit_same_scene('david', 'a', 'b')
    assert len(emitted) == prior_records
    monkeypatch.setattr(shadow, 'DECISION_DEADLINE_SECONDS', -1)
    prior_records = len(emitted)
    shadow.submit_same_scene('david', 'a', 'b')
    assert len(emitted) == prior_records


def test_success_telemetry_and_identifier_only_record(monkeypatch):
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_UID_ALLOWLIST', 'david')
    monkeypatch.setattr(shadow, 'submit_with_context', lambda _executor, fn, *args: fn(*args))
    rows = {
        'a': {
            'source': 'omi',
            'client_device_id': 'one',
            'capture_group': None,
            'structured': {'overview': 'PRIVATE SUMMARY'},
            'transcript_segments': [{'text': 'PRIVATE TRANSCRIPT ' * 20}],
        },
        'b': {
            'source': 'omi',
            'client_device_id': 'two',
            'capture_group': None,
            'structured': {},
            'transcript_segments': [{'text': 'PRIVATE TRANSCRIPT ' * 20}],
        },
    }
    monkeypatch.setattr(
        shadow.conversations_db, 'get_conversation_for_capture_check', lambda uid, cid: (rows[cid], 'fingerprint')
    )
    monkeypatch.setattr(shadow, '_cap', lambda *args: 'admitted')

    class Answer:
        served_model = 'typesafe/jev-1.13'

        def noul(self, name):
            return 0.7

    monkeypatch.setattr(shadow, 'ask_jev', lambda *args, **kwargs: Answer())
    emitted = []
    monkeypatch.setattr(shadow, '_record', lambda record: emitted.append(record))
    before = shadow.CAPTURE_JEV_SHADOW_AGREEMENT.labels('same_source_different_device', 'jev_only')._value.get()
    shadow.submit_same_scene('david', 'a', 'b')
    assert emitted[0]['would_decide'] is True
    assert emitted[0]['rule_fold'] is False
    assert 'PRIVATE' not in json.dumps(emitted)
    after = shadow.CAPTURE_JEV_SHADOW_AGREEMENT.labels('same_source_different_device', 'jev_only')._value.get()
    assert after == before + 1


def test_resummary_uses_pinned_threshold_and_never_revises(monkeypatch):
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_UID_ALLOWLIST', 'david')
    monkeypatch.setattr(shadow, 'submit_with_context', lambda _executor, fn, *args: fn(*args))
    rows = {
        'a': {
            'source': 'omi',
            'capture_group': {'id': 'g'},
            'structured': {'overview': 'existing summary'},
            'transcript_segments': [{'text': 'first transcript ' * 15}],
        },
        'b': {
            'source': 'desktop',
            'capture_group': {'id': 'g'},
            'structured': {},
            'transcript_segments': [{'text': 'joining transcript ' * 15}],
        },
    }
    monkeypatch.setattr(
        shadow.conversations_db, 'get_conversation_for_capture_check', lambda uid, cid: (rows[cid], 'fingerprint')
    )
    monkeypatch.setattr(shadow, '_cap', lambda *args: 'admitted')

    class Answer:
        served_model = 'typesafe/jev-1.13'

        def noul(self, name):
            return 0.724

    monkeypatch.setattr(shadow, 'ask_jev', lambda *args, **kwargs: Answer())
    emitted = []
    monkeypatch.setattr(shadow, '_record', lambda record: emitted.append(record))
    shadow.submit_resummary('david', 'a', 'b')
    assert emitted[0]['would_decide'] is False
    assert emitted[0]['group_id'] == 'g'
    assert rows['a']['structured']['overview'] == 'existing summary'
