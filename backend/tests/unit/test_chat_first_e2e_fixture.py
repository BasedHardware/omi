"""Hermetic contracts for the local-only Chat-first E2E fixture harness."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.chat_first_e2e_fixture import (
    CHAT_FIRST_E2E_ENABLED_PRINCIPAL,
    CHAT_FIRST_E2E_OUT_OF_COHORT_PRINCIPAL,
    fixture_uid_for_principal,
    is_chat_first_e2e_enabled_fixture,
    is_chat_first_e2e_fixture_uid,
    is_chat_first_e2e_harness_runtime,
)
import database.chat_first_intents as intents_db
from models.chat_first import ChatFirstSubject, ProactiveDeferral
from models.chat_first_e2e import ChatFirstE2EFixtureCase
from models.task_intelligence import TaskWorkflowMode
from utils.memory.memory_system import MemorySystem
import utils.task_intelligence.chat_first_e2e_fixture as fixture
import utils.task_intelligence.rollout as rollout
import routers.chat_first_e2e as fixture_router

ENABLED_UID = 'auth-emulator-enabled-fixture'
OUT_OF_COHORT_UID = 'auth-emulator-out-of-cohort-fixture'


class _Snapshot:
    def __init__(self, database, path):
        self._database = database
        self._path = path
        self.exists = path in database.rows
        self.reference = _Document(database, path)

    def to_dict(self):
        return deepcopy(self._database.rows.get(self._path))


class _Document:
    def __init__(self, database, path):
        self._database = database
        self._path = path

    @property
    def id(self):
        return self._path[-1]

    @property
    def path(self):
        return '/'.join(self._path)

    def collection(self, name):
        return _Collection(self._database, (*self._path, name))

    def get(self, transaction=None):
        if transaction is not None:
            raise AssertionError('fixture state must be read before opening its write-only transaction')
        return _Snapshot(self._database, self._path)


class _Collection:
    def __init__(self, database, path):
        self._database = database
        self._path = path

    def document(self, identifier):
        return _Document(self._database, (*self._path, identifier))

    def stream(self):
        child_length = len(self._path) + 1
        return [
            _Snapshot(self._database, path)
            for path in sorted(self._database.rows)
            if path[: len(self._path)] == self._path and len(path) == child_length
        ]


class _WriteBatch:
    def __init__(self, database):
        self._database = database
        self._operations = []

    def set(self, ref, payload):
        self._operations.append(('set', ref._path, deepcopy(payload)))

    def update(self, ref, payload):
        self._operations.append(('update', ref._path, deepcopy(payload)))

    def delete(self, ref):
        self._operations.append(('delete', ref._path, None))

    def commit(self):
        for operation, path, payload in self._operations:
            if operation == 'delete':
                self._database.rows.pop(path, None)
            elif operation == 'update':
                self._database.rows[path] = {**self._database.rows[path], **payload}
            else:
                self._database.rows[path] = payload


class _Firestore:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        return _Collection(self, (name,))

    def batch(self):
        return _WriteBatch(self)


@pytest.fixture
def firestore(monkeypatch, tmp_path):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    manifest_dir = tmp_path / 'manifests'
    manifest_dir.mkdir()
    (manifest_dir / 'canonical-auth-uids.json').write_text(
        json.dumps(
            {
                'users': {
                    CHAT_FIRST_E2E_ENABLED_PRINCIPAL: ENABLED_UID,
                    CHAT_FIRST_E2E_OUT_OF_COHORT_PRINCIPAL: OUT_OF_COHORT_UID,
                }
            }
        ),
        encoding='utf-8',
    )
    monkeypatch.setenv('OMI_HARNESS_STATE_ROOT', str(tmp_path))
    fake = _Firestore()
    monkeypatch.setattr(fixture, 'get_firestore_client', lambda: fake)
    return fake


def test_harness_runtime_and_fixture_identities_are_local_offline_only(monkeypatch, tmp_path):
    manifest_dir = tmp_path / 'manifests'
    manifest_dir.mkdir()
    (manifest_dir / 'canonical-auth-uids.json').write_text(
        json.dumps(
            {
                'users': {
                    CHAT_FIRST_E2E_ENABLED_PRINCIPAL: ENABLED_UID,
                    CHAT_FIRST_E2E_OUT_OF_COHORT_PRINCIPAL: OUT_OF_COHORT_UID,
                }
            }
        ),
        encoding='utf-8',
    )
    monkeypatch.setenv('OMI_HARNESS_STATE_ROOT', str(tmp_path))
    for stage in ('local', 'offline'):
        assert is_chat_first_e2e_harness_runtime(stage=stage)
        assert fixture_uid_for_principal(CHAT_FIRST_E2E_ENABLED_PRINCIPAL) == ENABLED_UID
        assert is_chat_first_e2e_enabled_fixture(ENABLED_UID, stage=stage)
        assert is_chat_first_e2e_fixture_uid(OUT_OF_COHORT_UID, stage=stage)
    for stage in ('dev', 'prod', ''):
        assert not is_chat_first_e2e_harness_runtime(stage=stage)
        assert not is_chat_first_e2e_enabled_fixture(ENABLED_UID, stage=stage)
        assert not is_chat_first_e2e_fixture_uid(OUT_OF_COHORT_UID, stage=stage)
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    assert not is_chat_first_e2e_harness_runtime()


def test_fixture_identity_is_fail_closed_without_live_auth_uid_manifest(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.delenv('OMI_HARNESS_STATE_ROOT', raising=False)

    assert fixture_uid_for_principal(CHAT_FIRST_E2E_ENABLED_PRINCIPAL) is None
    assert not is_chat_first_e2e_enabled_fixture(ENABLED_UID)
    assert not is_chat_first_e2e_fixture_uid(OUT_OF_COHORT_UID)


def test_fixture_router_is_defensively_hidden_when_directly_included_outside_local(monkeypatch):
    app = FastAPI()
    app.include_router(fixture_router.router)
    app.dependency_overrides[fixture_router.auth.get_current_user_uid] = lambda: ENABLED_UID
    monkeypatch.setattr(fixture_router, 'is_chat_first_e2e_harness_runtime', lambda: False)
    monkeypatch.setattr(
        fixture_router.chat_first_e2e_fixture,
        'prepare_fixture',
        lambda *args, **kwargs: pytest.fail('non-local harness route must not prepare state'),
    )

    response = TestClient(app).post('/v1/dev-harness/chat-first/prepare', json={'fixture_case': 'enabled'})

    assert response.status_code == 404
    assert response.json() == {'detail': 'Not found'}


def test_prepare_resets_fixed_canonical_fixture_rows_atomically(firestore):
    first = fixture.prepare_fixture(
        ENABLED_UID,
        fixture_case=ChatFirstE2EFixtureCase.enabled,
    )
    daily_opener = next(
        value
        for path, value in firestore.rows.items()
        if path[-2] == intents_db.INTENTS_COLLECTION and path[-1].startswith('cfi_')
    )
    second = fixture.prepare_fixture(
        ENABLED_UID,
        fixture_case=ChatFirstE2EFixtureCase.ui_flag_off,
    )

    assert first.expected_shell == 'chat_first'
    assert first.proactive_intent_count == 1
    assert second.fixture_revision == 2
    assert second.expected_shell == 'legacy'
    assert second.proactive_intent_count == 0
    assert second.ready_intent_count == 0
    control = firestore.rows[('users', ENABLED_UID, 'task_intelligence_control', 'state')]
    assert control['workflow_mode'] == TaskWorkflowMode.read.value
    assert control['chat_first_ui_enabled'] is False
    focused_goal = firestore.rows[('users', ENABLED_UID, 'goals', 'chat-first-e2e-goal-v1')]
    non_focused_goal = firestore.rows[('users', ENABLED_UID, 'goals', 'chat-first-e2e-secondary-goal-v1')]
    assert focused_goal['status'] == 'focused'
    assert focused_goal['focus_rank'] == 0
    assert non_focused_goal['status'] == 'background'
    assert non_focused_goal['focus_rank'] is None
    assert non_focused_goal['is_active'] is True
    task = firestore.rows[('users', ENABLED_UID, 'action_items', 'chat-first-e2e-task-v1')]
    assert task['source'] == 'transcription:omi'
    assert task['conversation_id'] == 'chat-first-e2e-capture-v1'
    assert ('users', ENABLED_UID, 'conversations', 'chat-first-e2e-capture-v1') in firestore.rows
    assert daily_opener['source'] == 'daily_opener'
    assert daily_opener['blocks'] == [
        {'type': 'goalLink', 'goal_id': 'chat-first-e2e-goal-v1', 'summary': 'E2E fixture goal'},
        {'type': 'taskCard', 'task_id': 'chat-first-e2e-task-v1'},
    ]


def test_cold_start_case_uses_existing_intent_contract(firestore):
    snapshot = fixture.prepare_fixture(
        ENABLED_UID,
        fixture_case=ChatFirstE2EFixtureCase.cold_start,
    )

    assert snapshot.expected_shell == 'chat_first'
    assert snapshot.ready_intent_count == 1
    stored = next(
        value
        for path, value in firestore.rows.items()
        if path[-2] == intents_db.INTENTS_COLLECTION and path[-1].startswith('cfi_')
    )
    assert stored['source'] == 'cold_start_sparse'
    assert stored['delivery_state'] == 'pending_kernel_receipt'


def test_question_case_starts_after_completed_rich_cold_start(firestore):
    snapshot = fixture.prepare_fixture(
        ENABLED_UID,
        fixture_case=ChatFirstE2EFixtureCase.question,
    )

    assert snapshot.expected_shell == 'chat_first'
    assert snapshot.proactive_intent_count == 2
    assert snapshot.ready_intent_count == 1
    assert snapshot.materialized_intent_count == 1
    intents = [
        value
        for path, value in firestore.rows.items()
        if path[-2] == intents_db.INTENTS_COLLECTION and path[-1].startswith('cfi_')
    ]
    completed_cold_start = next(intent for intent in intents if intent['source'] == 'cold_start_rich')
    question = next(intent for intent in intents if intent['source'] == 'deferral_reraise')
    assert completed_cold_start['delivery_state'] == 'delivered'
    assert completed_cold_start['materialization_receipt_id']
    assert question['delivery_state'] == 'ready'


def test_unreachable_control_case_only_affects_the_prepared_local_fixture(firestore):
    fixture.prepare_fixture(
        ENABLED_UID,
        fixture_case=ChatFirstE2EFixtureCase.unreachable_control,
    )

    assert fixture.is_control_unreachable(ENABLED_UID)
    assert not fixture.is_control_unreachable(OUT_OF_COHORT_UID)
    fixture.prepare_fixture(ENABLED_UID, fixture_case=ChatFirstE2EFixtureCase.enabled)
    assert not fixture.is_control_unreachable(ENABLED_UID)


def test_advance_clock_makes_fixture_deferrals_due_without_changing_chat_clock(firestore):
    fixture.prepare_fixture(ENABLED_UID, fixture_case=ChatFirstE2EFixtureCase.enabled)
    now = datetime.now(timezone.utc)
    deferred = ProactiveDeferral(
        deferral_id='fixture-pending-deferral',
        continuity_key='fixture-pending-deferral',
        account_generation=1,
        subject=ChatFirstSubject(kind='goal', id='chat-first-e2e-goal-v1'),
        question=fixture._question(),
        created_at=now,
        due_at=now + timedelta(hours=24),
    )
    path = (
        'users',
        ENABLED_UID,
        intents_db.DEFERRALS_COLLECTION,
        deferred.deferral_id,
    )
    firestore.rows[path] = deferred.model_dump(mode='python')

    snapshot = fixture.advance_fixture_clock(ENABLED_UID, seconds=86400)

    assert snapshot.advanced_seconds == 86400
    assert snapshot.pending_deferral_count == 1
    assert firestore.rows[path]['due_at'] < datetime.now(timezone.utc)


def test_fixture_identity_and_cohort_are_fail_closed(firestore, monkeypatch):
    with pytest.raises(fixture.ChatFirstE2EFixtureIdentityError):
        fixture.prepare_fixture('regular-user', fixture_case=ChatFirstE2EFixtureCase.enabled)
    with pytest.raises(fixture.ChatFirstE2EFixtureIdentityError):
        fixture.prepare_fixture(
            OUT_OF_COHORT_UID,
            fixture_case=ChatFirstE2EFixtureCase.enabled,
        )

    monkeypatch.setattr(rollout, 'resolve_memory_system', lambda *args, **kwargs: MemorySystem.LEGACY)
    enabled = rollout.resolve_task_intelligence_for_user(
        uid=ENABLED_UID,
        workflow_mode=TaskWorkflowMode.read,
        account_generation=1,
    )
    out_of_cohort = rollout.resolve_task_intelligence_for_user(
        uid=OUT_OF_COHORT_UID,
        workflow_mode=TaskWorkflowMode.read,
        account_generation=1,
    )
    assert enabled.intelligence_product_enabled is True
    assert out_of_cohort.intelligence_product_enabled is False
