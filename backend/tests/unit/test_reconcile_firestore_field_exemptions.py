import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import reconcile_firestore_field_exemptions as field_reconciler

MANIFEST_PATH = Path(__file__).resolve().parents[3] / 'firestore.indexes.json'


def _field_payload(*, disabled: bool) -> dict:
    if disabled:
        return {'indexConfig': {'indexes': [], 'usesAncestorConfig': False}}
    return {
        'indexConfig': {
            'indexes': [{'fields': [{'order': 'ASCENDING'}]}],
            'usesAncestorConfig': True,
        }
    }


class FakeRunner:
    def __init__(self, disabled=None, *, pending=(), slow=(), failures=(), lost=(), races=()):
        self.disabled = set(disabled or set())
        self.pending = set(pending)
        self.slow = set(slow)
        self.failures = set(failures)
        self.lost = set(lost)
        self.races = set(races)
        self.extra_operations = []
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.commands.append(command)
        if command[2:4] == ['operations', 'list']:
            assert not any(token == '--filter' or token.startswith('--filter=') for token in command)
            assert '--limit=unlimited' in command
            operations = [_operation(group, field) for group, field in self.pending]
            return SimpleNamespace(returncode=0, stdout=json.dumps(operations + self.extra_operations))
        collection_group = next(token.split('=', 1)[1] for token in command if token.startswith('--collection-group='))
        field_path = command[5]
        key = (collection_group, field_path)
        if command[4] == 'describe':
            return SimpleNamespace(returncode=0, stdout=json.dumps(_field_payload(disabled=key in self.disabled)))
        assert command[4] == 'update'
        assert '--disable-indexes' in command
        assert '--async' in command
        if key in self.races:
            self.pending.add(key)
            return SimpleNamespace(returncode=1, stdout='')
        if key in self.failures:
            return SimpleNamespace(returncode=1, stdout='')
        if key in self.slow:
            self.pending.add(key)
        elif key not in self.lost:
            self.disabled.add(key)
        return SimpleNamespace(returncode=0, stdout='')


def test_expected_exemptions_are_the_manifest_empty_index_overrides():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))

    # Read-back text and sync task payload maps are never queried. The small
    # screen-activity device fields remain indexed for future device filtering.
    assert field_reconciler.expected_field_exemptions(manifest) == (
        field_reconciler.FieldExemption('conversations', 'live_transcript_replay_receipt'),
        field_reconciler.FieldExemption('conversations', 'owner_recognition_diagnostics'),
        field_reconciler.FieldExemption('screen_activity', 'ocrText'),
        field_reconciler.FieldExemption('screen_activity', 'windowTitle'),
        field_reconciler.FieldExemption('sync_backfill_pending', 'payload'),
        field_reconciler.FieldExemption('sync_backfill_sequencer', 'active_payload'),
    )


@pytest.mark.parametrize(
    'override',
    [
        {'collectionGroup': 'events', 'fieldPath': 'expiresAt', 'ttl': True, 'indexes': []},
        {
            'collectionGroup': 'events',
            'fieldPath': 'title',
            'ttl': False,
            'indexes': [{'order': 'ASCENDING', 'queryScope': 'COLLECTION'}],
        },
    ],
)
def test_reconciler_rejects_overrides_that_are_not_index_exemptions(override):
    with pytest.raises(ValueError, match='ttl=false|collection-group'):
        field_reconciler.expected_field_exemptions({'fieldOverrides': [override]})


def test_reconciler_skips_additive_overrides_and_returns_only_exemptions():
    manifest = {
        'fieldOverrides': [
            {
                'collectionGroup': 'conversations',
                'fieldPath': 'status',
                'ttl': False,
                'indexes': [
                    {'queryScope': 'COLLECTION', 'order': 'ASCENDING'},
                    {'queryScope': 'COLLECTION_GROUP', 'order': 'ASCENDING'},
                ],
            },
            {'collectionGroup': 'conversations', 'fieldPath': 'raw', 'ttl': False, 'indexes': []},
        ]
    }

    assert field_reconciler.expected_field_exemptions(manifest) == (
        field_reconciler.FieldExemption('conversations', 'raw'),
    )


def test_check_only_fails_when_declared_savings_are_not_serving(monkeypatch):
    monkeypatch.setattr(field_reconciler, 'verify_manifest_source', lambda _path: json.loads(MANIFEST_PATH.read_text()))
    runner = FakeRunner()

    with pytest.raises(RuntimeError, match='Declared Firestore field exemptions are not serving'):
        field_reconciler.reconcile(
            project='based-hardware',
            database='(default)',
            manifest_path=MANIFEST_PATH,
            check_only=True,
            runner=runner,
        )

    assert all(command[4] == 'describe' for command in runner.commands)


def test_apply_requires_the_destructive_confirmation(monkeypatch):
    monkeypatch.setattr(field_reconciler, 'verify_manifest_source', lambda _path: json.loads(MANIFEST_PATH.read_text()))

    with pytest.raises(ValueError, match=field_reconciler.APPLY_CONFIRMATION):
        field_reconciler.reconcile(
            project='based-hardware',
            database='(default)',
            manifest_path=MANIFEST_PATH,
            apply=True,
            confirmation='APPLY_FIRESTORE_INDEXES',
            runner=FakeRunner(),
        )


def test_apply_disables_only_missing_declared_fields_and_verifies_convergence(monkeypatch):
    monkeypatch.setattr(field_reconciler, 'verify_manifest_source', lambda _path: json.loads(MANIFEST_PATH.read_text()))
    already_disabled = {('screen_activity', 'ocrText')}
    runner = FakeRunner(disabled=already_disabled)

    field_reconciler.reconcile(
        project='based-hardware',
        database='(default)',
        manifest_path=MANIFEST_PATH,
        apply=True,
        confirmation=field_reconciler.APPLY_CONFIRMATION,
        runner=runner,
    )

    updates = [command for command in runner.commands if command[4] == 'update']
    assert {command[5] for command in updates} == {
        'live_transcript_replay_receipt',
        'owner_recognition_diagnostics',
        'windowTitle',
        'payload',
        'active_payload',
    }
    assert all('--disable-indexes' in command for command in updates)
    assert all('--clear-exemption' not in command for command in updates)
    assert runner.disabled == {
        ('conversations', 'live_transcript_replay_receipt'),
        ('conversations', 'owner_recognition_diagnostics'),
        ('screen_activity', 'ocrText'),
        ('screen_activity', 'windowTitle'),
        ('sync_backfill_pending', 'payload'),
        ('sync_backfill_sequencer', 'active_payload'),
    }


FIRST = ('conversations', 'live_transcript_replay_receipt')
SECOND = ('conversations', 'owner_recognition_diagnostics')


def _operation(group, field):
    return {
        'metadata': {
            '@type': 'type.googleapis.com/google.firestore.admin.v1.FieldOperationMetadata',
            'field': f'projects/based-hardware/databases/(default)/collectionGroups/{group}/fields/{field}',
        }
    }


def _apply(runner, *, sleeper=lambda _seconds: None):
    field_reconciler.apply_field_exemptions(
        project='based-hardware',
        database='(default)',
        exemptions=field_reconciler.expected_field_exemptions(json.loads(MANIFEST_PATH.read_text())),
        runner=runner,
        sleeper=sleeper,
    )


def test_slow_field_does_not_block_remaining_submissions(capsys):
    runner = FakeRunner(slow={FIRST})
    _apply(runner)
    assert FIRST in runner.pending
    assert len(runner.disabled) == 5
    assert 'conversations.live_transcript_replay_receipt: submitted' in capsys.readouterr().out


def test_pending_field_is_skipped_on_repeated_apply(capsys):
    runner = FakeRunner(pending={FIRST})
    _apply(runner)
    _apply(runner)
    updates = [c for c in runner.commands if c[4] == 'update']
    assert len(updates) == 5
    assert all(c[5] != FIRST[1] for c in updates)
    assert 'conversations.live_transcript_replay_receipt: in-flight' in capsys.readouterr().out


def test_real_submit_error_fails_but_other_fields_are_attempted():
    runner = FakeRunner(failures={FIRST})
    with pytest.raises(RuntimeError, match='Firestore field exemption failed for conversations.live_transcript'):
        _apply(runner)
    assert len(runner.disabled) == 5


def test_submission_race_is_accepted_only_with_confirmed_pending_operation(capsys):
    runner = FakeRunner(races={FIRST})
    _apply(runner)
    assert 'conversations.live_transcript_replay_receipt: in-flight' in capsys.readouterr().out


def test_mixed_final_state_reports_disabled_submitted_and_in_flight(capsys):
    runner = FakeRunner(disabled={('screen_activity', 'ocrText')}, pending={FIRST}, slow={SECOND})
    _apply(runner)
    output = capsys.readouterr().out.splitlines()
    assert len(output) == 6
    assert 'screen_activity.ocrText: disabled' in output
    assert 'conversations.live_transcript_replay_receipt: in-flight' in output
    assert 'conversations.owner_recognition_diagnostics: submitted' in output


def test_successful_submission_without_disabled_field_or_pending_op_fails():
    waits = []
    with pytest.raises(RuntimeError, match='neither disabled nor in flight'):
        _apply(FakeRunner(lost={FIRST}), sleeper=waits.append)
    assert waits == [2, 2]


@pytest.mark.parametrize('kind', ['done', 'other-type', 'other-field', 'other-database', 'other-project'])
def test_unrelated_or_completed_operations_do_not_skip_submission(kind):
    runner = FakeRunner()
    operation = _operation(*FIRST)
    if kind == 'done':
        operation['done'] = True
    elif kind == 'other-type':
        operation['metadata']['@type'] = 'type.googleapis.com/google.firestore.admin.v1.IndexOperationMetadata'
    elif kind == 'other-field':
        operation['metadata']['field'] += '_other'
    elif kind == 'other-database':
        operation['metadata']['field'] = operation['metadata']['field'].replace('(default)', 'other')
    else:
        operation['metadata']['field'] = operation['metadata']['field'].replace('based-hardware', 'other-project')
    runner.extra_operations.append(operation)
    _apply(runner)
    assert FIRST in runner.disabled


def test_check_only_still_fails_with_pending_operations(monkeypatch):
    monkeypatch.setattr(field_reconciler, 'verify_manifest_source', lambda _path: json.loads(MANIFEST_PATH.read_text()))
    runner = FakeRunner(pending={FIRST})
    with pytest.raises(RuntimeError, match='not serving'):
        field_reconciler.reconcile(
            project='based-hardware',
            database='(default)',
            manifest_path=MANIFEST_PATH,
            check_only=True,
            runner=runner,
        )
    assert all(command[4] == 'describe' for command in runner.commands)


def test_running_operation_with_omitted_done_is_found_without_gcloud_filter():
    runner = FakeRunner(pending={FIRST})
    assert 'done' not in _operation(*FIRST)
    assert field_reconciler.in_flight_fields(
        project='based-hardware',
        database='(default)',
        runner=runner,
    ) == {'projects/based-hardware/databases/(default)/collectionGroups/conversations/fields/' + FIRST[1]}
    command = runner.commands[0]
    assert '--limit=unlimited' in command
    assert not any(token == '--filter' or token.startswith('--filter=') for token in command)


@pytest.mark.parametrize('visible_after', [1, 2])
@pytest.mark.parametrize('final_state', ['pending', 'disabled'])
def test_post_submit_verification_rechecks_eventual_state(visible_after, final_state, capsys):
    runner = FakeRunner(lost={FIRST})
    waits = []

    def advance(seconds):
        waits.append(seconds)
        if len(waits) == visible_after:
            if final_state == 'pending':
                runner.pending.add(FIRST)
            else:
                runner.disabled.add(FIRST)

    _apply(runner, sleeper=advance)
    assert waits == [2] * visible_after
    expected_status = 'submitted' if final_state == 'pending' else 'disabled'
    assert f'conversations.live_transcript_replay_receipt: {expected_status}' in capsys.readouterr().out
    assert len([command for command in runner.commands if command[4] == 'update']) == 6
