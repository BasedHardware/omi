"""Batch projection creates sync conversations under the same v3 admission as sync intake.

Synthetic owner and rows only. Before this contract, projection called ``assign_sync_conversation``
without ``mark_new``: every row it created for a v3-admitted owner was a legacy conversation (full
notes, memories, a second Home card) beside that owner's v3 recordings.
"""

import ast
from pathlib import Path
from unittest.mock import Mock

import pytest

from utils.batch_pipeline import projection
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.capture import batch_coverage
from utils.conversations.v3 import triggers
from utils.episodes import transcript_receipts

BACKEND = Path(__file__).resolve().parents[2]


def _run_projection(monkeypatch, *, admitted, assigned_row=None, wake_error=None):
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('segment',))
    item = WorkItem('segment', binding.owner_id, 0, 'gs://synthetic/audio', 1, Priority.DEEP)
    payload = {
        'words': [{'word': 'Fixture.', 'timestamp': [0, 1]}],
        'audio_seconds': 1,
        'speech_seconds': 1,
        'diarization': {'turns': []},
    }
    projector = projection.Projector(Mock(), Mock(return_value=payload))
    projector.store = Mock()
    projector.store.session.return_value.persist.return_value = {'state': 'persisted', 'conversation_id': 'row'}
    incoming = {
        'id': 'row',
        'source': 'omi',
        'data_protection_level': 'standard',
        'structured': {'title': 'synthetic'},
        'transcript_segments': [{'text': 'Synthetic speech.', 'speaker_id_scope': 'sync:fixture'}],
        'started_at': Mock(timestamp=lambda: 0),
        'finished_at': Mock(timestamp=lambda: 1),
    }
    monkeypatch.setattr(projection, 'build_incoming', lambda *a, **kw: incoming)
    monkeypatch.setattr(projection.conversations_db, 'get_closest_conversation_to_timestamps', lambda *a: None)
    monkeypatch.setattr(triggers, 'conversations_v3_enabled', lambda uid: admitted)
    seen = {}

    def assign(uid, row, **kwargs):
        seen['incoming'] = dict(row)
        stored = assigned_row if assigned_row is not None else dict(row)
        kwargs['after_assign'](Mock(), (stored, True, []))
        return stored, True, []

    monkeypatch.setattr(projection.conversations_db, 'assign_sync_conversation', assign)
    monkeypatch.setattr(batch_coverage, 'record_projection', Mock())
    monkeypatch.setattr(transcript_receipts, 'enqueue', Mock())
    woken = []

    def changed(uid, cid, **kwargs):
        if wake_error is not None:
            raise wake_error
        woken.append((uid, cid))

    monkeypatch.setattr(triggers, 'changed', changed)
    finished = []
    projector.finish_part = lambda *a, **kw: finished.append(True)
    projector.assign_parts(item, {'result': {'result_uri': 'fixture'}}, binding)
    return seen['incoming'], woken, finished


def test_admitted_owner_projection_creates_a_v3_recording_and_wakes_reconcile(monkeypatch):
    incoming, woken, finished = _run_projection(monkeypatch, admitted=True)
    assert incoming['recording'] is True
    assert incoming['terminal_no_derived_effects'] is True
    assert incoming['v3_pending'] is True
    assert incoming['structured'] == {}
    assert woken == [('synthetic-owner', 'row')]
    assert finished == [True]


def test_unadmitted_owner_projection_stays_legacy(monkeypatch):
    incoming, woken, _ = _run_projection(monkeypatch, admitted=False)
    assert 'recording' not in incoming and 'terminal_no_derived_effects' not in incoming
    assert incoming['structured'] == {'title': 'synthetic'}
    assert woken == []


def test_projection_append_to_existing_recording_wakes_reconcile(monkeypatch):
    # A later unit for a non-admitted (lapsed) owner can still land in a stored recording.
    _, woken, _ = _run_projection(monkeypatch, admitted=False, assigned_row={'id': 'stored', 'recording': True})
    assert woken == [('synthetic-owner', 'stored')]


def test_wake_failure_after_commit_does_not_replay_the_unit(monkeypatch, caplog):
    _, _, finished = _run_projection(monkeypatch, admitted=True, wake_error=RuntimeError('synthetic'))
    assert finished == [True]
    assert 'action=v3_wake outcome=error exception_type=RuntimeError' in caplog.text


# Every function that may create a conversation from new speech must apply v3 admission first.
# bridge.py re-assigns rows that already exist; assign_record_silence carries no speech.
_NO_NEW_SPEECH = {
    ('utils/sync/bridge.py', '_finish_pending_live_bridge'),
    ('utils/batch_pipeline/projection.py', 'assign_record_silence'),
}


def _names(node, name):
    """True when ``node`` (a call's func, including ``a or b`` forms) names ``name``."""
    return any(getattr(part, 'attr', None) == name or getattr(part, 'id', None) == name for part in ast.walk(node))


def _functions_calling(tree, name):
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
            if any(_names(call.func, name) for call in calls):
                yield fn, calls


@pytest.mark.parametrize(
    'path',
    sorted(
        str(path.relative_to(BACKEND))
        for root in ('utils', 'database', 'routers')
        for path in (BACKEND / root).rglob('*.py')
        if 'assign_sync_conversation' in path.read_text() and path.name != 'conversations.py'
    ),
)
def test_every_new_speech_sync_assignment_caller_applies_v3_admission(path):
    tree = ast.parse((BACKEND / path).read_text())
    for fn, calls in _functions_calling(tree, 'assign_sync_conversation'):
        if (path, fn.name) in _NO_NEW_SPEECH:
            continue
        # Every def whose own body calls the assignment (nested defs included) must call mark_new itself.
        assert any(_names(call.func, 'mark_new') for call in calls), f'{path}:{fn.name} assigns without mark_new'


def test_caller_contract_sees_the_projection_call_form():
    tree = ast.parse((BACKEND / 'utils/batch_pipeline/projection.py').read_text())
    assert 'assign_parts' in {fn.name for fn, _ in _functions_calling(tree, 'assign_sync_conversation')}


def test_append_wake_retries_a_transient_mark_pending_failure(monkeypatch):
    from utils.conversations.v3 import triggers

    calls = []

    def flaky(uid, cid, **_):
        calls.append(cid)
        if len(calls) == 1:
            raise RuntimeError('synthetic')

    monkeypatch.setattr(triggers, 'changed', flaky)
    monkeypatch.setattr(triggers.time, 'sleep', lambda _: None)
    triggers.committed_sync_assignment('u', {'id': 'c', 'recording': True})
    assert calls == ['c', 'c']


def test_append_wake_counts_the_degraded_branch_after_every_attempt_fails(monkeypatch):
    from utils.conversations.v3 import triggers

    fallbacks = []

    def broken(uid, cid, **_):
        raise RuntimeError('synthetic')

    monkeypatch.setattr(triggers, 'changed', broken)
    monkeypatch.setattr(triggers.time, 'sleep', lambda _: None)
    monkeypatch.setattr(triggers, 'record_fallback', lambda **kw: fallbacks.append(kw))
    triggers.committed_sync_assignment('u', {'id': 'c', 'recording': True})
    assert fallbacks and fallbacks[0]['outcome'] == 'degraded'
