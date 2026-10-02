"""Capture-wedge detector: two bounded Cloud Logging reads, claims, nudges.

The detector reads a zero-session filter over the trailing 10 minutes, then a
positive-session filter restricted to the candidate uids. These tests pin both
verbatim filters, the fail-closed truncation/error/oversized paths, the streak
exclusions, the once-per-day cohort claim, and the cooldown-gated nudge.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from services import capture_wedge as wedge

NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
WINDOW_START = NOW - timedelta(minutes=10)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _entry(uid: str, *, bytes_received=0, chunks_total=0, duration=0.0, source='omi', **extra):
    payload = {
        'event': 'vad_gate_metrics',
        'uid': uid,
        'session_id': 's',
        'bytes_received': bytes_received,
        'chunks_total': chunks_total,
        'session_duration_sec': duration,
        'transcription_source': source,
        **extra,
    }
    return {'timestamp': _iso(NOW), 'jsonPayload': payload}


def test_zero_session_filter_is_the_verbatim_query():
    expected = (
        'resource.type="k8s_container" AND jsonPayload.event="vad_gate_metrics" '
        'AND jsonPayload.bytes_received=0 AND jsonPayload.chunks_total=0 '
        'AND jsonPayload.session_duration_sec=0 '
        f'AND timestamp>="{_iso(WINDOW_START)}" AND timestamp<="{_iso(NOW)}"'
    )
    assert wedge.zero_session_log_filter(WINDOW_START, NOW) == expected


def test_positive_session_filter_is_the_verbatim_query():
    uid_clause = ' OR '.join(f'jsonPayload.uid={json.dumps(uid)}' for uid in sorted(['b-uid', 'a-uid']))
    expected = (
        'resource.type="k8s_container" AND jsonPayload.event="vad_gate_metrics" '
        f'AND jsonPayload.bytes_received>0 AND ({uid_clause}) '
        f'AND timestamp>="{_iso(WINDOW_START)}" AND timestamp<="{_iso(NOW)}"'
    )
    assert wedge.positive_session_log_filter(['b-uid', 'a-uid'], WINDOW_START, NOW) == expected


def test_positive_session_filter_json_quotes_uids():
    clause = wedge.positive_session_log_filter(['evil" OR true'], WINDOW_START, NOW)
    assert 'evil\\" OR true' in clause
    assert 'jsonPayload.uid="evil\\" OR true"' in clause


def _fake_session(pages: list[dict], status_code=200, raise_on=None):
    class _Response:
        def __init__(self, page):
            self.page = page
            self.status_code = status_code

        def json(self):
            return self.page

    class _Session:
        def __init__(self):
            self.requests = []

        def post(self, url, *, json=None, timeout=None):
            self.requests.append({'url': url, 'body': json})
            if raise_on is not None:
                raise raise_on
            return _Response(pages.pop(0) if pages else {})

    return _Session()


def test_entries_reader_pages_and_sends_verbatim_request():
    session = _fake_session(
        [
            {'entries': [{'timestamp': 't1'}], 'nextPageToken': 'p2'},
            {'entries': [{'timestamp': 't2'}]},
        ]
    )

    result = wedge.read_vad_gate_metrics_entries(project_id='proj-1', filter_string='FILTER', session=session)

    assert result['errors'] == 0
    assert result['truncated'] is False
    assert [e['timestamp'] for e in result['entries']] == ['t1', 't2']
    first, second = session.requests
    assert first['url'] == 'https://logging.googleapis.com/v2/entries:list'
    assert first['body']['resourceNames'] == ['projects/proj-1']
    assert first['body']['filter'] == 'FILTER'
    assert first['body']['orderBy'] == 'timestamp desc'
    assert first['body']['pageSize'] == 1000
    assert first['body']['pageToken'] == ''
    assert second['body']['pageToken'] == 'p2'


def test_entries_reader_marks_truncated_when_cap_reached_with_more_pages():
    session = _fake_session([{'entries': [{'i': i} for i in range(10)], 'nextPageToken': 'more'}])

    result = wedge.read_vad_gate_metrics_entries(
        project_id='proj-1', filter_string='FILTER', session=session, max_entries=5
    )

    assert result['truncated'] is True
    assert len(result['entries']) == 5


def test_entries_reader_counts_errors_and_stops_on_failure():
    session = _fake_session([], status_code=500)
    result = wedge.read_vad_gate_metrics_entries(project_id='proj-1', filter_string='F', session=session)
    assert result['errors'] == 1
    assert result['entries'] == []

    session = _fake_session([], raise_on=RuntimeError('network'))
    result = wedge.read_vad_gate_metrics_entries(project_id='proj-1', filter_string='F', session=session)
    assert result['errors'] == 1


def test_zero_streak_requires_six_zero_tuples():
    entries = [_entry('u1') for _ in range(6)]
    assert wedge.zero_streak_candidates(entries) == {'u1': 6}

    entries = [_entry('u1') for _ in range(5)]
    assert wedge.zero_streak_candidates(entries) == {}


def test_onboarding_and_multi_channel_payloads_reject_candidate():
    entries = [_entry('u1') for _ in range(6)]
    entries.append(_entry('u1', onboarding_session_id='ob-1'))
    assert wedge.zero_streak_candidates(entries) == {}

    entries = [_entry('u1', multi_channel=True) for _ in range(6)]
    assert wedge.zero_streak_candidates(entries) == {}


def test_non_omi_source_zero_tuples_do_not_count():
    entries = [_entry('u1', source='phone_call') for _ in range(6)]
    assert wedge.zero_streak_candidates(entries) == {}


def test_non_json_payload_entries_are_ignored():
    entries = [{'timestamp': _iso(NOW), 'textPayload': 'vad_gate_metrics'} for _ in range(10)]
    assert wedge.zero_streak_candidates(entries) == {}


def test_positive_bytes_uids_collects_delivering_uids():
    entries = [
        _entry('u1', bytes_received=10, chunks_total=1, duration=1.0),
        _entry('u2'),
        {'textPayload': 'vad_gate_metrics'},
    ]
    assert wedge.positive_bytes_uids(entries) == {'u1'}


def _wedge_entries(uid='u1', count=6):
    return [_entry(uid) for _ in range(count)]


def _reader_dispatch(zero_entries=None, positive_entries=None, zero_fail=None, positive_fail=None):
    calls = []

    def reader(*, project_id, filter_string, **_kw):
        calls.append(filter_string)
        if 'bytes_received>0' in filter_string:
            return positive_fail or {'entries': positive_entries or [], 'truncated': False, 'errors': 0}
        return zero_fail or {'entries': zero_entries or [], 'truncated': False, 'errors': 0}

    reader.calls = calls
    return reader


def _claims(monkeypatch, *, first_seen=True, nudge=True, first_seen_error=None):
    state = {'first_seen': [], 'nudge': [], 'pushes': []}

    def claim_first_seen(uid, day, **kw):
        if first_seen_error is not None:
            raise first_seen_error
        state['first_seen'].append((uid, day))
        return first_seen

    monkeypatch.setattr(wedge.capture_wedge_state, 'claim_wedge_first_seen', claim_first_seen)
    monkeypatch.setattr(
        wedge.capture_wedge_state,
        'claim_wedge_nudge_cooldown',
        lambda uid, **kw: state['nudge'].append(uid) or nudge,
    )
    return state


def test_detect_mode_emits_candidate_and_first_seen_only(capsys, monkeypatch):
    state = _claims(monkeypatch)
    reader = _reader_dispatch(zero_entries=_wedge_entries())
    result = wedge.run_capture_wedge_check(mode='detect', now=NOW, project_id='proj-1', entries_reader=reader)

    assert result['candidates'] == 1
    assert len(reader.calls) == 2
    assert 'bytes_received=0' in reader.calls[0]
    assert 'bytes_received>0' in reader.calls[1]
    assert 'jsonPayload.uid="u1"' in reader.calls[1]
    assert state['first_seen'] == [('u1', NOW.strftime('%Y-%m-%d'))]
    assert state['nudge'] == []
    out = capsys.readouterr().out
    assert 'selfheal_wedge_candidate' in out
    assert 'selfheal_wedge_first_seen' in out


def test_positive_evidence_suppresses_candidate(monkeypatch):
    state = _claims(monkeypatch)
    reader = _reader_dispatch(
        zero_entries=_wedge_entries(),
        positive_entries=[_entry('u1', bytes_received=5, chunks_total=1, duration=1.0)],
    )
    result = wedge.run_capture_wedge_check(
        mode='nudge', now=NOW, project_id='proj-1', entries_reader=reader, send_push=lambda *a: 1
    )

    assert result['candidates'] == 0
    assert result['nudged'] == 0
    assert state['first_seen'] == [] and state['nudge'] == []


def test_no_candidates_skips_positive_read(monkeypatch):
    reader = _reader_dispatch(zero_entries=[])
    result = wedge.run_capture_wedge_check(mode='detect', now=NOW, project_id='proj-1', entries_reader=reader)

    assert result['candidates'] == 0
    assert len(reader.calls) == 1


def test_oversized_candidate_set_fails_closed(monkeypatch):
    state = _claims(monkeypatch)
    entries = []
    for i in range(51):
        entries.extend(_wedge_entries(uid=f'u{i}'))
    reader = _reader_dispatch(zero_entries=entries)

    result = wedge.run_capture_wedge_check(
        mode='nudge', now=NOW, project_id='proj-1', entries_reader=reader, send_push=lambda *a: 1
    )

    assert result['errors'] >= 1
    assert result['candidates'] == 0
    assert len(reader.calls) == 1
    assert state['first_seen'] == [] and state['nudge'] == []


def test_losing_first_seen_claim_suppresses_event(capsys, monkeypatch):
    _claims(monkeypatch, first_seen=False)
    wedge.run_capture_wedge_check(
        mode='detect',
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(zero_entries=_wedge_entries()),
    )
    out = capsys.readouterr().out
    assert 'selfheal_wedge_candidate' in out
    assert 'selfheal_wedge_first_seen' not in out


def test_first_seen_claim_failure_blocks_the_nudge(monkeypatch):
    state = _claims(monkeypatch, first_seen_error=RuntimeError('firestore down'))
    pushes = []
    result = wedge.run_capture_wedge_check(
        mode='nudge',
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(zero_entries=_wedge_entries()),
        send_push=lambda *a: pushes.append(a) or 1,
    )

    assert result['errors'] >= 1
    assert result['nudged'] == 0
    assert state['nudge'] == []
    assert pushes == []


def test_zero_read_failure_fails_closed_no_claims_no_push(capsys, monkeypatch):
    state = _claims(monkeypatch)
    result = wedge.run_capture_wedge_check(
        mode='nudge',
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(zero_fail={'entries': [], 'truncated': False, 'errors': 1}),
    )

    assert result['errors'] >= 1
    assert result['candidates'] == 0
    assert state['first_seen'] == [] and state['nudge'] == []


def test_truncation_of_either_read_fails_closed(monkeypatch):
    state = _claims(monkeypatch)
    result = wedge.run_capture_wedge_check(
        mode='nudge',
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(zero_fail={'entries': _wedge_entries(), 'truncated': True, 'errors': 0}),
    )
    assert result['errors'] >= 1
    assert state['first_seen'] == [] and state['nudge'] == []

    result = wedge.run_capture_wedge_check(
        mode='nudge',
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(
            zero_entries=_wedge_entries(),
            positive_fail={'entries': [], 'truncated': True, 'errors': 0},
        ),
        send_push=lambda *a: 1,
    )
    assert result['errors'] >= 1
    assert result['candidates'] == 0
    assert state['first_seen'] == [] and state['nudge'] == []


def test_nudge_sends_after_claiming_cooldown(capsys, monkeypatch):
    state = _claims(monkeypatch)
    pushes = []

    def send(uid, title, body, data):
        pushes.append((uid, title, body, dict(data)))
        return 1

    result = wedge.run_capture_wedge_check(
        mode='nudge',
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(zero_entries=_wedge_entries()),
        send_push=send,
    )

    assert result['nudged'] == 1
    assert state['nudge'] == ['u1']
    (push,) = pushes
    assert push[0] == 'u1'
    assert push[1] == "Omi isn't receiving audio"
    assert push[2] == (
        'Your pendant connection looks stuck. Open Omi and reconnect the device. ' 'Nothing was deleted.'
    )
    assert push[3] == {'push_type': 'capture_recovery', 'action': 'repair_device'}
    out = capsys.readouterr().out
    assert 'selfheal_nudge' in out and '"outcome": "sent"' in out


def test_zero_successful_sends_count_undeliverable(capsys, monkeypatch):
    _claims(monkeypatch)
    result = wedge.run_capture_wedge_check(
        mode='heal',
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(zero_entries=_wedge_entries()),
        send_push=lambda *a: 0,
    )

    assert result['nudged'] == 0
    assert result['undeliverable'] == 1
    assert '"outcome": "undeliverable"' in capsys.readouterr().out


def test_claimed_cooldown_skips_send(capsys, monkeypatch):
    state = _claims(monkeypatch, nudge=False)
    pushes = []
    result = wedge.run_capture_wedge_check(
        mode='nudge',
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(zero_entries=_wedge_entries()),
        send_push=lambda *a: pushes.append(a) or 1,
    )

    assert result['nudged'] == 0
    assert pushes == []
    assert '"outcome": "cooldown"' in capsys.readouterr().out


def test_dry_run_never_claims_or_pushes(capsys, monkeypatch):
    state = _claims(monkeypatch)
    pushes = []
    result = wedge.run_capture_wedge_check(
        mode='nudge',
        dry_run=True,
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(zero_entries=_wedge_entries()),
        send_push=lambda *a: pushes.append(a) or 1,
    )

    assert result['nudged'] == 0
    assert state['first_seen'] == []
    assert state['nudge'] == []
    assert pushes == []
    assert '"outcome": "dry_run"' in capsys.readouterr().out


def test_allowlist_restricts_nudge_but_not_detection(capsys, monkeypatch):
    state = _claims(monkeypatch)
    pushes = []
    result = wedge.run_capture_wedge_check(
        mode='nudge',
        uid_allowlist=frozenset({'other'}),
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(zero_entries=_wedge_entries()),
        send_push=lambda *a: pushes.append(a) or 1,
    )

    assert result['candidates'] == 1
    assert result['nudged'] == 0
    assert pushes == []
    assert state['nudge'] == []


def test_off_mode_does_nothing(monkeypatch):
    state = _claims(monkeypatch)
    result = wedge.run_capture_wedge_check(mode='off', now=NOW)
    assert result == {'candidates': 0, 'nudged': 0, 'undeliverable': 0, 'errors': 0}
    assert state['first_seen'] == []


def test_missing_project_id_fails_closed(monkeypatch):
    monkeypatch.delenv('SELFHEAL_LOGGING_PROJECT', raising=False)
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    monkeypatch.delenv('OMI_CUSTOMER_DATA_PROJECT', raising=False)
    result = wedge.run_capture_wedge_check(mode='detect', now=NOW)
    assert result['errors'] == 1


def test_nudge_telemetry_never_carries_token_or_pii(capsys, monkeypatch):
    _claims(monkeypatch)

    def send(uid, title, body, data):
        return 1

    wedge.run_capture_wedge_check(
        mode='nudge',
        now=NOW,
        project_id='proj-1',
        entries_reader=_reader_dispatch(zero_entries=_wedge_entries()),
        send_push=send,
    )
    out = capsys.readouterr().out
    nudge_lines = [line for line in out.strip().splitlines() if 'selfheal_nudge' in line]
    (line,) = nudge_lines
    assert json.loads(line) == {'event': 'selfheal_nudge', 'uid': 'u1', 'outcome': 'sent'}


def test_default_push_routes_through_typed_dispatch(monkeypatch):
    from utils.notification_dispatch import (
        NotificationDispatchOutcome,
        NotificationDispatchStatus,
        NotificationKind,
    )

    intents = []

    def fake_dispatch(intent):
        intents.append(intent)
        return NotificationDispatchOutcome(NotificationDispatchStatus.DISPATCHED, delivered=2)

    monkeypatch.setattr(wedge, 'dispatch_notification', fake_dispatch)
    assert wedge._default_push('u1', 'Title', 'Body', {'push_type': 'capture_recovery'}) == 1
    (intent,) = intents
    assert intent.user_id == 'u1'
    assert intent.kind == NotificationKind.CAPTURE_RECOVERY
    assert intent.data == {'push_type': 'capture_recovery'}


def test_default_push_counts_failed_or_zero_delivery_as_undeliverable(monkeypatch):
    from utils.notification_dispatch import NotificationDispatchOutcome, NotificationDispatchStatus

    monkeypatch.setattr(
        wedge,
        'dispatch_notification',
        lambda intent: NotificationDispatchOutcome(NotificationDispatchStatus.DISPATCHED, delivered=0),
    )
    assert wedge._default_push('u1', 'Title', 'Body', {}) == 0

    monkeypatch.setattr(
        wedge,
        'dispatch_notification',
        lambda intent: NotificationDispatchOutcome(NotificationDispatchStatus.FAILED, reason='delivery_failed'),
    )
    assert wedge._default_push('u1', 'Title', 'Body', {}) == 0
