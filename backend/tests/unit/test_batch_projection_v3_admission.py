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


# Callers that may create a conversation from new speech must apply v3 admission first.
# bridge.py re-assigns rows that already exist; assign_record_silence carries no speech.
_NO_NEW_SPEECH_CALLERS = {'utils/sync/bridge.py'}


def _calls(tree, name):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (getattr(node.func, 'attr', None) == name or getattr(node.func, 'id', None) == name)
    ]


@pytest.mark.parametrize(
    'path',
    sorted(
        str(path.relative_to(BACKEND))
        for root in ('utils', 'database', 'routers')
        for path in (BACKEND / root).rglob('*.py')
        if 'assign_sync_conversation' in path.read_text()
    ),
)
def test_every_new_speech_sync_assignment_caller_applies_v3_admission(path):
    if path in _NO_NEW_SPEECH_CALLERS or path == 'database/conversations.py':
        return
    tree = ast.parse((BACKEND / path).read_text())
    if not _calls(tree, 'assign_sync_conversation'):
        return
    assert _calls(tree, 'mark_new'), f'{path} assigns sync speech without v3 mark_new'
