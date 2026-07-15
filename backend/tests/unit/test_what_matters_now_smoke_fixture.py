from copy import deepcopy

import pytest

import database.task_intelligence_control as task_control_db
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode


class _ControlSnapshot:
    def __init__(self, payload):
        self._payload = deepcopy(payload)
        self.exists = payload is not None

    def to_dict(self):
        return deepcopy(self._payload)


class _CreateOnlyControlReference:
    def __init__(self, payload=None):
        self.payload = deepcopy(payload)
        self.create_payloads = []

    def create(self, payload):
        self.create_payloads.append(deepcopy(payload))
        if self.payload is not None:
            raise task_control_db.AlreadyExists('control already exists')
        self.payload = deepcopy(payload)

    def get(self):
        return _ControlSnapshot(self.payload)


def test_fixture_identity_is_code_owned_and_requires_explicit_dev_runtime(monkeypatch):
    assert task_control_db.is_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')
    assert not task_control_db.is_development_smoke_fixture('another-user', stage='dev')
    assert not task_control_db.is_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='prod')
    assert not task_control_db.is_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='local')

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert task_control_db.is_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID)


def test_fixture_setup_create_only_writes_the_minimal_control_document(monkeypatch):
    expected = TaskWorkflowControl(workflow_mode=TaskWorkflowMode.read, account_generation=0)
    control_ref = _CreateOnlyControlReference()

    monkeypatch.setattr(task_control_db, '_control_ref', lambda _uid: control_ref)

    assert task_control_db.ensure_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')
    assert control_ref.payload == expected.persisted_payload()
    assert control_ref.create_payloads == [expected.persisted_payload()]


def test_fixture_setup_is_idempotent_when_expected_control_already_exists(monkeypatch):
    expected = TaskWorkflowControl(workflow_mode=TaskWorkflowMode.read, account_generation=0).persisted_payload()
    control_ref = _CreateOnlyControlReference(expected)

    monkeypatch.setattr(task_control_db, '_control_ref', lambda _uid: control_ref)

    assert not task_control_db.ensure_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')
    assert control_ref.payload == expected
    assert control_ref.create_payloads == [expected]


def test_fixture_setup_treats_a_legacy_control_without_the_ui_flag_as_the_default_off_state(monkeypatch):
    control_ref = _CreateOnlyControlReference({'workflow_mode': 'read', 'account_generation': 0})

    monkeypatch.setattr(task_control_db, '_control_ref', lambda _uid: control_ref)

    assert not task_control_db.ensure_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')
    assert control_ref.create_payloads == [
        TaskWorkflowControl(workflow_mode=TaskWorkflowMode.read, account_generation=0).persisted_payload()
    ]


def test_fixture_setup_preserves_differing_existing_control_and_fails_smoke(monkeypatch):
    differing_control = {'workflow_mode': 'write', 'account_generation': 3}
    control_ref = _CreateOnlyControlReference(differing_control)

    monkeypatch.setattr(task_control_db, '_control_ref', lambda _uid: control_ref)

    with pytest.raises(task_control_db.DevelopmentSmokeFixtureConflictError, match='differing state'):
        task_control_db.ensure_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')

    assert control_ref.payload == differing_control
    assert control_ref.create_payloads == [
        TaskWorkflowControl(workflow_mode=TaskWorkflowMode.read, account_generation=0).persisted_payload()
    ]


def test_fixture_setup_fails_closed_without_a_development_runtime(monkeypatch):
    monkeypatch.setattr(
        task_control_db,
        'get_task_workflow_control',
        lambda _uid: (_ for _ in ()).throw(AssertionError('Firestore must not be read outside dev')),
    )

    assert not task_control_db.ensure_development_smoke_fixture(
        task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='prod'
    )
    assert not task_control_db.ensure_development_smoke_fixture('another-user', stage='dev')
