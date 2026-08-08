from unittest.mock import patch

import pytest

import database.task_intelligence_control as task_control_db
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode
from tests.store_fakes import FakeDocumentStore

_CONTROL_PATH = f'users/{task_control_db.WHAT_MATTERS_NOW_SMOKE_UID}/task_intelligence_control/state'


def _install_store(monkeypatch, seed=None):
    store = FakeDocumentStore()
    if seed is not None:
        store.set(_CONTROL_PATH, seed)
    monkeypatch.setattr(task_control_db, '_store', lambda: store)
    return store


def test_fixture_identity_is_code_owned_and_requires_explicit_dev_runtime(monkeypatch):
    assert task_control_db.is_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')
    assert not task_control_db.is_development_smoke_fixture('another-user', stage='dev')
    assert not task_control_db.is_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='prod')
    assert not task_control_db.is_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='local')

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert task_control_db.is_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID)


def test_fixture_setup_create_only_writes_the_minimal_control_document(monkeypatch):
    expected = TaskWorkflowControl(workflow_mode=TaskWorkflowMode.read, account_generation=0)
    store = _install_store(monkeypatch)

    assert task_control_db.ensure_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')
    assert store.get(_CONTROL_PATH).to_dict() == expected.persisted_payload()


def test_fixture_setup_is_idempotent_when_expected_control_already_exists(monkeypatch):
    expected = TaskWorkflowControl(workflow_mode=TaskWorkflowMode.read, account_generation=0).persisted_payload()
    store = _install_store(monkeypatch, seed=expected)

    assert not task_control_db.ensure_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')
    assert store.get(_CONTROL_PATH).to_dict() == expected


def test_fixture_setup_treats_a_legacy_control_without_the_ui_flag_as_the_default_off_state(monkeypatch):
    seeded = {'workflow_mode': 'read', 'account_generation': 0}
    store = _install_store(monkeypatch, seed=seeded)

    assert not task_control_db.ensure_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')
    assert store.get(_CONTROL_PATH).to_dict() == TaskWorkflowControl(
        workflow_mode=TaskWorkflowMode.read, account_generation=0
    ).persisted_payload()


def test_fixture_setup_preserves_differing_existing_control_and_fails_smoke(monkeypatch):
    differing_control = {'workflow_mode': 'write', 'account_generation': 3}
    store = _install_store(monkeypatch, seed=differing_control)

    with pytest.raises(task_control_db.DevelopmentSmokeFixtureConflictError, match='differing state'):
        task_control_db.ensure_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')

    # The pre-existing (differing) document is preserved untouched, never overwritten.
    assert store.get(_CONTROL_PATH).to_dict() == differing_control


def test_fixture_setup_treats_malformed_existing_control_as_differing_without_overwrite(monkeypatch):
    malformed_control = {'workflow_mode': 'read', 'account_generation': 0, 'unexpected_legacy_field': True}
    store = _install_store(monkeypatch, seed=malformed_control)

    with patch('database.read_boundary.record_fallback') as fallback:
        with pytest.raises(task_control_db.DevelopmentSmokeFixtureConflictError, match='differing state'):
            task_control_db.ensure_development_smoke_fixture(task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='dev')

    fallback.assert_called_once()
    assert store.get(_CONTROL_PATH).to_dict() == malformed_control


def test_fixture_setup_fails_closed_without_a_development_runtime(monkeypatch):
    monkeypatch.setattr(
        task_control_db,
        'get_task_workflow_control',
        lambda _uid: (_ for _ in ()).throw(AssertionError('the store must not be read outside dev')),
    )

    assert not task_control_db.ensure_development_smoke_fixture(
        task_control_db.WHAT_MATTERS_NOW_SMOKE_UID, stage='prod'
    )
    assert not task_control_db.ensure_development_smoke_fixture('another-user', stage='dev')
