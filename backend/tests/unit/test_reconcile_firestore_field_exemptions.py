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
    def __init__(self, disabled: set[tuple[str, str]] | None = None):
        self.disabled = set(disabled or set())
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.commands.append(command)
        collection_group = next(token.split('=', 1)[1] for token in command if token.startswith('--collection-group='))
        field_path = command[5]
        key = (collection_group, field_path)
        if command[4] == 'describe':
            return SimpleNamespace(returncode=0, stdout=json.dumps(_field_payload(disabled=key in self.disabled)))
        assert command[4] == 'update'
        assert '--disable-indexes' in command
        self.disabled.add(key)
        return SimpleNamespace(returncode=0, stdout='')


def test_expected_exemptions_are_the_manifest_empty_index_overrides():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))

    # Only the two read-back text fields are exempted. deviceName/clientDeviceId are
    # deliberately left indexed so device-scoped filtering stays available; see
    # FIELD_INDEXING_EXEMPTIONS in database/firestore_index_registry.py.
    assert field_reconciler.expected_field_exemptions(manifest) == (
        field_reconciler.FieldExemption('screen_activity', 'ocrText'),
        field_reconciler.FieldExemption('screen_activity', 'windowTitle'),
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
    with pytest.raises(ValueError, match='only supports ttl=false with indexes='):
        field_reconciler.expected_field_exemptions({'fieldOverrides': [override]})


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
    assert {command[5] for command in updates} == {'windowTitle'}
    assert all('--disable-indexes' in command for command in updates)
    assert all('--clear-exemption' not in command for command in updates)
    assert runner.disabled == {
        ('screen_activity', 'ocrText'),
        ('screen_activity', 'windowTitle'),
    }
