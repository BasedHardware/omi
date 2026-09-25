"""Self-heal sweep: modes, dry-run, allowlist, bounds, cursor, and verification.

The sweep is a rotated window over ``status == 'in_progress'`` rows with every
recovery predicate evaluated Python-side. These tests drive
``run_selfheal_tick`` with injected fakes — no Firestore, no network.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from services import conversation_selfheal as sweep
from utils.conversations.lifecycle import FinalizationDispatchUnavailable
from utils.conversations.processing_trigger import ProcessingTrigger

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)
STALE = NOW - timedelta(hours=3)
FRESH = NOW - timedelta(hours=1)
ANCIENT = NOW - timedelta(hours=20)


def _row(uid: str, conversation_id: str, data: dict) -> dict:
    return {
        'uid': uid,
        'conversation_id': conversation_id,
        'path': f'users/{uid}/conversations/{conversation_id}',
        'data': data,
    }


def _eligible_data(**overrides) -> dict:
    return {
        'status': 'in_progress',
        'source': 'omi',
        'finished_at': STALE,
        'has_content': True,
        **overrides,
    }


def _stdout_events(capsys) -> list[dict]:
    events = []
    for line in capsys.readouterr().out.strip().splitlines():
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and 'event' in parsed:
            events.append(parsed)
    return events


def _harness(rows, **overrides):
    state: dict[str, Any] = {
        'scan_calls': [],
        'advances': [],
        'finalization_calls': [],
        'cursor': {'resume_after_path': None, 'generation': 7, 'pending_verifications': []},
        'jobs': {},
        'conversations': {},
        'wedge': {'candidates': 0, 'nudged': 0, 'undeliverable': 0, 'errors': 0},
    }

    def scan_fn(**kwargs):
        state['scan_calls'].append(kwargs)
        return {
            'rows': rows,
            'scanned': len(rows),
            'resume_after_path': rows[-1]['path'] if rows else None,
            'exhausted': True,
        }

    def cursor_getter(**_kwargs):
        return state['cursor']

    def cursor_advancer(generation, new_path, *, pending_verifications=None, **_kwargs):
        state['advances'].append({'generation': generation, 'path': new_path, 'pending': pending_verifications})
        return True

    def request_finalization_fn(uid, conversation_id, **kwargs):
        state['finalization_calls'].append({'uid': uid, 'conversation_id': conversation_id, **kwargs})
        return {
            'created': True,
            'job_id': f'job-{conversation_id}',
            'status': 'queued',
            'route': 'cloud_tasks',
            'requires_byok': False,
            'fanout_key': 'k',
            'dispatch_generation': 1,
        }

    def conversation_reader(uid, conversation_id):
        return state['conversations'].get(conversation_id)

    def job_reader(job_id, **_kwargs):
        return state['jobs'].get(job_id)

    def wedge_runner(**kwargs):
        state['wedge_kwargs'] = kwargs
        return dict(state['wedge'])

    kwargs = {
        'now': NOW,
        'scan_fn': scan_fn,
        'cursor_getter': cursor_getter,
        'cursor_advancer': cursor_advancer,
        'request_finalization_fn': request_finalization_fn,
        'conversation_reader': conversation_reader,
        'job_reader': job_reader,
        'wedge_runner': wedge_runner,
        'mode': 'detect',
        'dry_run': False,
        'uid_allowlist': None,
        **overrides,
    }
    return state, kwargs


def test_mode_off_emits_tick_and_does_no_work(capsys, monkeypatch):
    scanned = []
    monkeypatch.setenv('SELFHEAL_MODE', 'off')
    _, kwargs = _harness([_row('u1', 'c1', _eligible_data())])
    kwargs['mode'] = None
    kwargs['scan_fn'] = lambda **kw: scanned.append(kw)

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['mode'] == 'off'
    assert scanned == []
    tick = [e for e in _stdout_events(capsys) if e['event'] == 'selfheal_tick'][0]
    assert tick['mode'] == 'off'
    assert tick['scanned'] == 0


def test_invalid_mode_fails_closed(monkeypatch):
    monkeypatch.setenv('SELFHEAL_MODE', 'nuke-everything')
    assert sweep.selfheal_mode() == 'off'


def test_detect_scans_reports_and_admits_nothing(capsys):
    rows = [
        _row('u1', 'c1', _eligible_data()),
        _row('u2', 'c2', _eligible_data(finished_at=FRESH)),
        _row('u3', 'c3', _eligible_data(finished_at=ANCIENT)),
        _row('u4', 'c4', {'status': 'in_progress', 'source': 'omi', 'finished_at': STALE}),
    ]
    state, kwargs = _harness(rows)

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['scanned'] == 4
    assert counters['content_holding'] == 2
    assert counters['content_holding_over_12h'] == 1
    assert counters['oldest_age_seconds'] == pytest.approx((NOW - ANCIENT).total_seconds())
    assert counters['enqueued'] == 0
    assert state['finalization_calls'] == []
    events = _stdout_events(capsys)
    skipped = [e for e in events if e['event'] == 'selfheal_action' and e['outcome'] == 'skipped']
    assert {e['conversation_id'] for e in skipped} == {'c1', 'c3'}
    assert all(e['reason'] == 'mode_detect' for e in skipped)
    tick = [e for e in events if e['event'] == 'selfheal_tick'][0]
    assert tick['exhausted'] is True
    assert tick['mode'] == 'detect'


def test_heal_enqueues_and_records_pending_verification(capsys):
    rows = [_row('u1', 'c1', _eligible_data())]
    state, kwargs = _harness(rows, mode='heal')

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['enqueued'] == 1
    (call,) = state['finalization_calls']
    assert call['uid'] == 'u1' and call['conversation_id'] == 'c1'
    assert call['trigger'] is ProcessingTrigger.SERVER_RECOVERY
    assert call['require_cloud_tasks'] is True
    assert call['recovery_cutoff'] == NOW - sweep.STALE_AFTER
    (advance,) = state['advances']
    assert advance['generation'] == 7
    assert advance['pending'] == [{'uid': 'u1', 'conversation_id': 'c1', 'job_id': 'job-c1'}]
    enqueued = [e for e in _stdout_events(capsys) if e.get('outcome') == 'enqueued']
    assert len(enqueued) == 1 and enqueued[0]['uid'] == 'u1'


def test_heal_caps_admissions_at_ten_per_tick():
    rows = [_row('u1', f'c{i}', _eligible_data()) for i in range(12)]
    state, kwargs = _harness(rows, mode='heal')

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['enqueued'] == sweep.MAX_HEAL_ADMISSIONS_PER_TICK == 10
    assert len(state['finalization_calls']) == 10


def test_heal_respects_uid_allowlist(capsys):
    rows = [_row('u1', 'c1', _eligible_data()), _row('u2', 'c2', _eligible_data())]
    state, kwargs = _harness(rows, mode='heal', uid_allowlist=frozenset({'u1'}))

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['enqueued'] == 1
    assert [c['uid'] for c in state['finalization_calls']] == ['u1']
    allowlist_skips = [
        e for e in _stdout_events(capsys) if e.get('outcome') == 'skipped' and e['reason'] == 'allowlist'
    ]
    assert [e['uid'] for e in allowlist_skips] == ['u2']


def test_detect_ignores_uid_allowlist_for_stats():
    rows = [_row('u1', 'c1', _eligible_data())]
    state, kwargs = _harness(rows, mode='detect', uid_allowlist=frozenset({'nobody'}))

    counters = sweep.run_selfheal_tick(**kwargs)
    assert counters['content_holding'] == 1


def test_dry_run_suppresses_mutations_and_cursor_advance(capsys):
    rows = [_row('u1', 'c1', _eligible_data())]
    state, kwargs = _harness(rows, mode='heal', dry_run=True)

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['enqueued'] == 0
    assert state['finalization_calls'] == []
    assert state['advances'] == []
    previews = [e for e in _stdout_events(capsys) if e.get('outcome') == 'dry_run']
    assert len(previews) == 1 and previews[0]['conversation_id'] == 'c1'


def test_noop_route_from_admission_counts_as_refused(capsys):
    rows = [_row('u1', 'c1', _eligible_data())]
    state, kwargs = _harness(rows, mode='heal')

    def refused(uid, conversation_id, **kwargs):
        return {'created': False, 'job_id': None, 'status': 'refused_not_stale', 'route': 'noop'}

    kwargs['request_finalization_fn'] = refused
    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['enqueued'] == 0
    assert counters['refused'] == 1
    refused_events = [e for e in _stdout_events(capsys) if e.get('outcome') == 'refused']
    assert refused_events[0]['reason'] == 'refused_not_stale'


def test_dispatch_unavailable_is_a_refusal_not_an_enqueue():
    rows = [_row('u1', 'c1', _eligible_data())]
    state, kwargs = _harness(rows, mode='heal')

    def unavailable(uid, conversation_id, **kwargs):
        raise FinalizationDispatchUnavailable('no worker')

    kwargs['request_finalization_fn'] = unavailable
    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['enqueued'] == 0
    assert counters['refused'] == 1


def test_non_enqueue_routes_are_not_reported_as_enqueued():
    rows = [_row('u1', 'c1', _eligible_data())]
    state, kwargs = _harness(rows, mode='heal')

    def pusher_route(uid, conversation_id, **kwargs):
        return {'created': True, 'job_id': 'j', 'status': 'queued', 'route': 'pusher'}

    kwargs['request_finalization_fn'] = pusher_route
    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['enqueued'] == 0
    assert counters['skipped'] >= 1


def test_pending_verification_verifies_a_completed_job(capsys):
    job_id = 'job-1'
    transcript = 'blob'
    state, kwargs = _harness([], mode='detect')
    state['cursor']['pending_verifications'] = [{'uid': 'u1', 'conversation_id': 'c1', 'job_id': job_id}]
    state['jobs'][job_id] = {
        'status': 'completed',
        'selfheal_transcript_bytes': len(transcript.encode('utf-8')),
        'selfheal_audio_file_ids': ['a1'],
    }
    state['conversations']['c1'] = {
        'status': 'completed',
        'finalization_job_id': job_id,
        'transcript_segments': transcript,
        'audio_files': [{'id': 'a1'}, {'id': 'a2'}],
        'structured': {'overview': 'rich'},
    }

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['verified'] == 1
    verified = [e for e in _stdout_events(capsys) if e.get('outcome') == 'verified']
    assert verified[0]['conversation_id'] == 'c1'


def _pending_completed_job(state, job_id='job-1', transcript=b'blob', audio_ids=None):
    state['cursor']['pending_verifications'] = [{'uid': 'u1', 'conversation_id': 'c1', 'job_id': job_id}]
    state['jobs'][job_id] = {
        'status': 'completed',
        'selfheal_transcript_bytes': len(transcript),
        'selfheal_audio_file_ids': audio_ids or [],
    }


def _completed_conversation(job_id='job-1', **overrides):
    return {
        'status': 'completed',
        'finalization_job_id': job_id,
        'transcript_segments': 'blob',
        'structured': {'overview': 'rich'},
        **overrides,
    }


def test_pending_verification_tolerates_benign_growth(capsys):
    state, kwargs = _harness([], mode='detect')
    _pending_completed_job(state)
    state['conversations']['c1'] = _completed_conversation(transcript_segments='blob-and-more')

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['verified'] == 1


def test_pending_verification_compressed_raw_bytes_compare_equal(capsys):
    """The raw snapshot must not decompress: a stored blob compares byte-for-byte."""
    blob = b'\x1f\x8b compressed-encrypted-payload \x00\x01'
    state, kwargs = _harness([], mode='detect')
    _pending_completed_job(state, transcript=blob)
    state['conversations']['c1'] = _completed_conversation(transcript_segments=blob)

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['verified'] == 1


def test_pending_verification_stays_pending_until_conversation_completed(capsys):
    state, kwargs = _harness([], mode='detect')
    _pending_completed_job(state)
    state['conversations']['c1'] = _completed_conversation(status='processing')

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['verified'] == 0
    assert counters['refused'] == 0
    (advance,) = state['advances']
    assert advance['pending'] == [{'uid': 'u1', 'conversation_id': 'c1', 'job_id': 'job-1'}]


def test_pending_verification_refuses_deleted_and_unbound_rows(capsys):
    state, kwargs = _harness([], mode='detect')
    _pending_completed_job(state)
    state['conversations']['c1'] = _completed_conversation(deleted=True)

    counters = sweep.run_selfheal_tick(**kwargs)
    assert counters['verified'] == 0
    assert counters['refused'] == 1

    state, kwargs = _harness([], mode='detect')
    _pending_completed_job(state)
    state['conversations']['c1'] = _completed_conversation(finalization_job_id='other-job')

    counters = sweep.run_selfheal_tick(**kwargs)
    assert counters['verified'] == 0
    assert counters['refused'] == 1
    refused = [e for e in _stdout_events(capsys) if e.get('outcome') == 'refused']
    assert refused[-1]['reason'] == 'verify_job_binding'


def test_pending_verification_refuses_missing_audio_ids(capsys):
    state, kwargs = _harness([], mode='detect')
    _pending_completed_job(state, audio_ids=['a1', 'a2'])
    state['conversations']['c1'] = _completed_conversation(audio_files=[{'id': 'a1'}])

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['verified'] == 0
    assert counters['refused'] == 1


def test_pending_verification_refuses_on_content_mismatch(capsys):
    job_id = 'job-1'
    state, kwargs = _harness([], mode='detect')
    state['cursor']['pending_verifications'] = [{'uid': 'u1', 'conversation_id': 'c1', 'job_id': job_id}]
    state['jobs'][job_id] = {
        'status': 'completed',
        'selfheal_transcript_bytes': 999,
        'selfheal_audio_file_ids': ['a1'],
    }
    state['conversations']['c1'] = {
        'status': 'completed',
        'finalization_job_id': job_id,
        'transcript_segments': 'different',
        'structured': {'overview': 'x'},
    }

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['verified'] == 0
    assert counters['refused'] == 1
    refused = [e for e in _stdout_events(capsys) if e.get('outcome') == 'refused']
    assert refused[0]['reason'] == 'verify_content_mismatch'


def test_pending_verification_keeps_inflight_jobs():
    job_id = 'job-1'
    state, kwargs = _harness([], mode='detect')
    state['cursor']['pending_verifications'] = [{'uid': 'u1', 'conversation_id': 'c1', 'job_id': job_id}]
    state['jobs'][job_id] = {'status': 'queued'}

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['verified'] == 0
    (advance,) = state['advances']
    assert advance['pending'] == [{'uid': 'u1', 'conversation_id': 'c1', 'job_id': job_id}]


def test_dead_lettered_attempt_is_dropped_without_readmission(capsys, caplog):
    job_id = 'job-1'
    state, kwargs = _harness([], mode='detect')
    state['cursor']['pending_verifications'] = [{'uid': 'u1', 'conversation_id': 'c1', 'job_id': job_id}]
    state['jobs'][job_id] = {'status': 'dead_letter'}

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['verified'] == 0
    assert counters['refused'] == 1
    refused = [e for e in _stdout_events(capsys) if e['event'] == 'selfheal_action' and e['outcome'] == 'refused']
    assert [e['reason'] for e in refused] == ['dead_letter']
    assert any(
        record.levelname == 'CRITICAL' and 'selfheal verification failed' in record.getMessage()
        for record in caplog.records
    )
    assert state['finalization_calls'] == []
    (advance,) = state['advances']
    assert advance['pending'] == []


def test_noop_admission_with_unrecognized_status_logs_bounded_reason(capsys):
    rows = [_row('u1', 'c1', _eligible_data())]
    state, kwargs = _harness(rows, mode='heal')

    def noop(uid, conversation_id, **kwargs):
        return {'created': False, 'job_id': None, 'status': 'ValueError: exploded /tmp/audio.wav', 'route': 'noop'}

    kwargs['request_finalization_fn'] = noop
    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['refused'] == 1
    refused = [e for e in _stdout_events(capsys) if e['event'] == 'selfheal_action' and e['outcome'] == 'refused']
    assert [e['reason'] for e in refused] == ['unknown']


def test_cursor_advances_with_scan_resume_path():
    rows = [_row('u1', 'c1', _eligible_data())]
    state, kwargs = _harness(rows, mode='detect')
    state['cursor']['resume_after_path'] = 'users/u0/conversations/c0'

    sweep.run_selfheal_tick(**kwargs)

    assert state['scan_calls'][0]['resume_after_path'] == 'users/u0/conversations/c0'
    (advance,) = state['advances']
    assert advance['path'] == rows[-1]['path']


def test_scan_error_is_counted_not_raised(capsys):
    state, kwargs = _harness([], mode='detect')

    def boom(**_kw):
        raise RuntimeError('firestore down')

    kwargs['scan_fn'] = boom
    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['errors'] >= 1


def test_wedge_counts_merge_into_tick():
    state, kwargs = _harness([], mode='nudge')
    state['wedge'] = {'candidates': 1, 'nudged': 1, 'undeliverable': 1, 'errors': 0}

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['nudged'] == 1
    assert counters['undeliverable'] == 1


def test_full_pending_verifications_skip_new_admissions(capsys):
    """At the pending cap, eligible rows are skipped, never admitted or dropped."""
    rows = [_row('u1', 'c-new', _eligible_data())]
    state, kwargs = _harness(rows, mode='heal')
    full = [{'uid': f'u{i}', 'conversation_id': f'c{i}', 'job_id': f'j{i}'} for i in range(100)]
    state['cursor']['pending_verifications'] = full
    for entry in full:
        state['jobs'][entry['job_id']] = {'status': 'queued'}

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['enqueued'] == 0
    assert state['finalization_calls'] == []
    (advance,) = state['advances']
    assert advance['pending'] == full
    capacity = [e for e in _stdout_events(capsys) if e.get('reason') == 'verification_capacity']
    assert [e['conversation_id'] for e in capacity] == ['c-new']


def test_cas_loss_after_enqueue_is_a_critical_error(capsys, caplog):
    rows = [_row('u1', 'c1', _eligible_data())]
    state, kwargs = _harness(rows, mode='heal')
    kwargs['cursor_advancer'] = lambda *a, **kw: False

    with caplog.at_level('CRITICAL', logger='services.conversation_selfheal'):
        counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['enqueued'] == 1
    assert counters['errors'] >= 1
    assert any('job-c1' in record.getMessage() for record in caplog.records)


def test_young_rows_never_decode_transcript(monkeypatch):
    """Rows inside the 2h window skip the content probe entirely."""
    blob_row = _row(
        'u1', 'c1', {'status': 'in_progress', 'source': 'omi', 'finished_at': FRESH, 'transcript_segments': b'\x1f\x8b'}
    )
    state, kwargs = _harness([blob_row], mode='detect')
    calls = []
    monkeypatch.setattr(
        sweep.conversations_db,
        'raw_conversation_has_content',
        lambda uid, data: calls.append(data) or True,
    )

    counters = sweep.run_selfheal_tick(**kwargs)

    assert calls == []
    assert counters['content_holding'] == 0


def test_empty_old_stub_does_not_move_oldest_age():
    rows = [
        _row('u1', 'c-old-stub', {'status': 'in_progress', 'source': 'omi', 'finished_at': ANCIENT}),
        _row('u2', 'c-stale', _eligible_data()),
    ]
    state, kwargs = _harness(rows, mode='detect')

    counters = sweep.run_selfheal_tick(**kwargs)

    assert counters['content_holding'] == 1
    assert counters['content_holding_over_12h'] == 0
    assert counters['oldest_age_seconds'] == pytest.approx((NOW - STALE).total_seconds())


def test_action_logs_carry_no_transcript_or_structured_fields(capsys):
    secret = 'the user said launch the rockets'
    rows = [
        _row(
            'u1',
            'c1',
            _eligible_data(
                transcript_segments=[{'text': secret}],
                structured={'overview': 'secret overview'},
            ),
        )
    ]
    state, kwargs = _harness(rows, mode='detect')
    sweep.run_selfheal_tick(**kwargs)

    raw = capsys.readouterr().out
    assert secret not in raw
    assert 'secret overview' not in raw
