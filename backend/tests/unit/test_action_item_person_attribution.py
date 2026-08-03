"""Per-person task attribution: schema, person-scoped reads, and legacy safety.

A task could name a *kind* of owner (user / other / unknown) but never *which person*, so
the person profile's Commitments tab could only ever show extracted prose. These tests pin
the contract that closes that gap:

* ``assignee_person_id`` / ``assigner_person_id`` survive create -> storage -> response and
  update, and ``extra='forbid'`` still rejects genuinely unknown fields.
* The person filter returns only that person's tasks, from either side of the commitment.
* **Legacy principal:** every task written before these fields existed carries neither. It
  must keep deserializing, keep appearing in the unfiltered list, and must not acquire a
  person by accident. The person filter is additive, never a gate on the general list.
* Extraction attributes a person only when ownership is already settled and the name is
  unambiguous — the over-attribution guard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import database.action_items as action_items_db
import routers.action_items as action_items_router
from database.firestore_index_registry import firebase_index_manifest
from models.action_item import (
    ActionItemResponse,
    CanonicalTaskCreate,
    CanonicalTaskUpdate,
    TaskCreatePayload,
)
from utils.task_intelligence import conversation_capture

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------- schema round trip


def test_person_ids_round_trip_through_create_storage_and_response():
    created = CanonicalTaskCreate.model_validate(
        {
            'description': 'Send the budget',
            'owner': 'other',
            'assignee_person_id': 'person-sarah',
            'assigner_person_id': 'person-me',
        }
    )
    stored = {'id': 'task-1', **created.storage_payload()}

    assert stored['assignee_person_id'] == 'person-sarah'
    assert stored['assigner_person_id'] == 'person-me'

    response = ActionItemResponse.model_validate(stored).model_dump(mode='json')
    assert response['assignee_person_id'] == 'person-sarah'
    assert response['assigner_person_id'] == 'person-me'


def test_update_carries_person_ids_and_can_clear_them():
    assigned = CanonicalTaskUpdate.model_validate({'assignee_person_id': 'person-sarah'}).storage_payload()
    cleared = CanonicalTaskUpdate.model_validate({'assignee_person_id': None}).storage_payload()

    assert assigned['assignee_person_id'] == 'person-sarah'
    # Explicitly set to null: unassigning must reach storage, not be dropped as "unset".
    assert 'assignee_person_id' in cleared and cleared['assignee_person_id'] is None


def test_task_create_payload_carries_person_ids_into_the_candidate_lifecycle():
    payload = TaskCreatePayload(description='Send the budget', assignee_person_id='person-sarah')
    assert payload.model_dump(exclude_none=True)['assignee_person_id'] == 'person-sarah'


@pytest.mark.parametrize(
    'field',
    ['assignee_person', 'assigned_to', 'person_id', 'assignee_person_id_typo'],
)
def test_forbidden_extra_fields_are_still_rejected(field):
    with pytest.raises(ValidationError):
        CanonicalTaskCreate.model_validate({'description': 'Send the budget', field: 'person-sarah'})


# ------------------------------------------------------------------ legacy principal


def test_legacy_task_without_person_still_deserializes_and_reads_back_unattributed():
    """The legacy principal: a task written before per-person attribution existed."""
    legacy_stored = {
        'id': 'task-legacy',
        'description': 'Pay the electricity bill',
        'completed': False,
    }

    prepared = action_items_db._prepare_action_item_for_read(dict(legacy_stored))
    # The read path must not invent a person for a task that never had one.
    assert 'assignee_person_id' not in prepared
    assert 'assigner_person_id' not in prepared

    response = ActionItemResponse.model_validate(prepared).model_dump(mode='json')
    assert response['assignee_person_id'] is None
    assert response['assigner_person_id'] is None
    assert response['description'] == 'Pay the electricity bill'


def test_legacy_task_is_untouched_by_an_update_that_does_not_mention_people():
    patch = CanonicalTaskUpdate.model_validate({'description': 'Pay the electricity bill today'}).storage_payload()
    assert 'assignee_person_id' not in patch
    assert 'assigner_person_id' not in patch


# ------------------------------------------------------------- person-scoped reads


class _FakeDoc:
    def __init__(self, data: Dict[str, Any]):
        self.id = data['id']
        self._data = {key: value for key, value in data.items() if key != 'id'}

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    """Firestore query stand-in that applies equality filters and records each built chain.

    Chains are immutable, exactly like Firestore's: two queries derived from the same
    collection reference must not contaminate each other's filters.
    """

    def __init__(self, docs: List[_FakeDoc], recorder: List[list], chain: Optional[list] = None):
        self._docs = docs
        self._recorder = recorder
        self._chain = list(chain or [])

    def where(self, *args, **kwargs):
        filt = kwargs.get('filter') or (args[0] if args else None)
        entry = ('where', filt.field_path, filt.op_string, filt.value)
        return _FakeQuery(self._docs, self._recorder, self._chain + [entry])

    def order_by(self, field, direction=None):
        return _FakeQuery(self._docs, self._recorder, self._chain + [('order_by', field, direction)])

    def limit(self, _n):
        return self

    def offset(self, _n):
        return self

    def stream(self):
        self._recorder.append(list(self._chain))
        docs = self._docs
        for _kind, field, op, value in [entry for entry in self._chain if entry[0] == 'where']:
            assert op == '==', 'person-scoped reads must stay equality-only'
            docs = [doc for doc in docs if doc._data.get(field) == value]
        for doc in docs:
            yield _FakeDoc({'id': doc.id, **doc._data})


class _FakeDB:
    def __init__(self, docs: List[_FakeDoc], recorder: List[list]):
        self._docs = docs
        self._recorder = recorder

    def collection(self, name: str):
        assert name == 'users'
        return SimpleNamespace(
            document=lambda _uid: SimpleNamespace(collection=lambda _name: _FakeQuery(self._docs, self._recorder))
        )


def _task(task_id: str, **fields: Any) -> _FakeDoc:
    return _FakeDoc(
        {
            'id': task_id,
            'description': task_id,
            'completed': False,
            'created_at': NOW,
            **fields,
        }
    )


@pytest.fixture
def person_read(monkeypatch):
    recorder: List[list] = []

    def _install(docs: List[_FakeDoc]):
        monkeypatch.setattr(action_items_db, 'db', _FakeDB(docs, recorder))
        monkeypatch.setattr(action_items_db, 'record_firestore_read', lambda *args: None)
        return recorder

    return _install


def test_person_filter_returns_only_that_persons_tasks_from_either_side(person_read):
    docs = [
        _task('assigned-to-sarah', assignee_person_id='person-sarah'),
        _task('sarah-asked-me', assigner_person_id='person-sarah'),
        _task('both-sides', assignee_person_id='person-sarah', assigner_person_id='person-sarah'),
        _task('someone-else', assignee_person_id='person-alex'),
        _task('legacy-no-person'),
    ]
    person_read(docs)

    results = action_items_db.get_action_items_for_person('uid', 'person-sarah')

    assert sorted(item['id'] for item in results) == ['assigned-to-sarah', 'both-sides', 'sarah-asked-me']


def test_person_filter_never_returns_a_legacy_task_that_carries_no_person(person_read):
    person_read([_task('legacy-no-person'), _task('assigned', assignee_person_id='person-sarah')])

    assert [item['id'] for item in action_items_db.get_action_items_for_person('uid', 'person-sarah')] == ['assigned']


def test_person_scoped_read_is_equality_only_so_undated_tasks_survive(person_read):
    """An ordered due_at read drops rows with no due_at — most person-attributed tasks."""
    recorder = person_read([_task('undated', assignee_person_id='person-sarah')])

    results = action_items_db.get_action_items_for_person('uid', 'person-sarah', completed=False)

    assert [item['id'] for item in results] == ['undated']
    assert recorder, 'the person-scoped read must issue at least one query'
    for chain in recorder:
        assert not [
            entry for entry in chain if entry[0] == 'order_by'
        ], 'ordering a person-scoped read would hide every task without a due date'


def test_person_scoped_composites_are_declared_in_the_firestore_index_manifest(person_read):
    declared = {
        tuple((field['fieldPath'], field['order']) for field in index['fields'])
        for index in firebase_index_manifest()['indexes']
        if index['collectionGroup'] == 'action_items' and index['queryScope'] == 'COLLECTION'
    }
    recorder = person_read([_task('assigned', assignee_person_id='person-sarah')])

    action_items_db.get_action_items_for_person('uid', 'person-sarah', completed=False)

    for chain in recorder:
        equalities = tuple((entry[1], 'ASCENDING') for entry in chain if entry[0] == 'where')
        if len(equalities) < 2:
            # One equality filter: Firestore's automatic single-field index serves it.
            continue
        assert (
            equalities + (('__name__', 'ASCENDING'),) in declared
        ), f'undeclared Firestore composite for the person-scoped read: {equalities}'


# ----------------------------------------------------------------------- the route


def _client(monkeypatch, *, person_items=None, general_items=None):
    calls: Dict[str, Any] = {}

    def _for_person(**kwargs):
        calls['person'] = kwargs
        return list(person_items or [])

    def _general(**kwargs):
        calls['general'] = kwargs
        return list(general_items or [])

    monkeypatch.setattr(action_items_router.action_items_db, 'get_action_items_for_person', _for_person)
    monkeypatch.setattr(action_items_router.action_items_db, 'get_action_items', _general)
    app = FastAPI()
    app.include_router(action_items_router.router)
    app.dependency_overrides[action_items_router.auth.get_current_user_uid] = lambda: 'uid'
    return TestClient(app), calls


def test_route_sends_person_id_to_the_person_scoped_read(monkeypatch):
    item = {'id': 'task-1', 'description': 'Send the budget', 'completed': False, 'assignee_person_id': 'person-sarah'}
    client, calls = _client(monkeypatch, person_items=[item])

    response = client.get('/v1/action-items', params={'person_id': 'person-sarah', 'completed': False})

    assert response.status_code == 200
    assert calls['person']['person_id'] == 'person-sarah'
    assert calls['person']['completed'] is False
    assert 'general' not in calls
    assert response.json()['action_items'][0]['assignee_person_id'] == 'person-sarah'


def test_route_without_person_id_still_lists_legacy_tasks_through_the_general_read(monkeypatch):
    legacy = {'id': 'task-legacy', 'description': 'Pay the electricity bill', 'completed': False}
    client, calls = _client(monkeypatch, general_items=[legacy])

    response = client.get('/v1/action-items')

    assert response.status_code == 200
    assert 'person' not in calls
    body = response.json()['action_items']
    assert [item['id'] for item in body] == ['task-legacy']
    assert body[0]['assignee_person_id'] is None


@pytest.mark.parametrize(
    'params',
    [
        {'person_id': 'person-sarah', 'due_start_date': '2026-01-01T00:00:00Z'},
        {'person_id': 'person-sarah', 'start_date': '2026-01-01T00:00:00Z'},
        {'person_id': 'person-sarah', 'conversation_id': 'conversation-1'},
    ],
)
def test_route_rejects_person_filter_combinations_it_has_no_index_for(monkeypatch, params):
    client, calls = _client(monkeypatch)

    response = client.get('/v1/action-items', params=params)

    assert response.status_code == 400
    assert calls == {}


# ------------------------------------------------------------ extraction attribution


def _extracted(**fields: Any) -> SimpleNamespace:
    base = {
        'description': 'Send the budget',
        'completed': False,
        'due_at': None,
        'capture_owner': None,
        'ownership_confidence': None,
        'counterparty_name': None,
    }
    base.update(fields)
    return SimpleNamespace(**base)


@pytest.fixture
def people_store(monkeypatch):
    created: List[str] = []
    people: List[Dict[str, str]] = [{'id': 'person-sarah', 'name': 'Sarah'}]

    def _get_people(_uid):
        return [dict(person) for person in people]

    def _get_or_create(_uid, name):
        created.append(name)
        record = {'id': f'person-{name.lower().replace(" ", "-")}', 'name': name}
        people.append(record)
        return dict(record)

    monkeypatch.setattr(conversation_capture.users_db, 'get_people', _get_people)
    monkeypatch.setattr(conversation_capture.users_db, 'get_or_create_person_by_name', _get_or_create)
    return created


def test_named_other_owner_becomes_the_assignee(people_store):
    resolver = conversation_capture.PersonAttributionResolver('uid')

    attribution = resolver.attribution(
        _extracted(capture_owner='other', ownership_confidence=0.95, counterparty_name='Sarah')
    )

    assert attribution == {'assignee_person_id': 'person-sarah'}
    assert people_store == [], 'an existing person must be matched, never re-created'


def test_named_party_on_a_user_owned_task_becomes_the_assigner(people_store):
    resolver = conversation_capture.PersonAttributionResolver('uid')

    attribution = resolver.attribution(
        _extracted(capture_owner='user', ownership_confidence=0.9, counterparty_name='Sarah')
    )

    assert attribution == {'assigner_person_id': 'person-sarah'}


def test_existing_person_is_matched_case_insensitively_instead_of_duplicated(people_store):
    resolver = conversation_capture.PersonAttributionResolver('uid')

    attribution = resolver.attribution(
        _extracted(capture_owner='other', ownership_confidence=0.95, counterparty_name='sarah')
    )

    assert attribution == {'assignee_person_id': 'person-sarah'}
    assert people_store == []


def test_a_name_the_account_does_not_have_is_never_created_and_attributes_nothing(people_store):
    """Extraction may attribute to an existing person; it may never invent one.

    A name can pass every shape guard and still not be the counterparty -- it only has
    to be spoken. Creating a Person from that would put a contact the user never added
    into their real People list and pin a task on them. No eval covers counterparty_name,
    so the failure is unmeasured. Missing an attribution is recoverable; a fabricated
    person in the user's own data is not.
    """
    resolver = conversation_capture.PersonAttributionResolver('uid')
    first = resolver.attribution(
        _extracted(capture_owner='other', ownership_confidence=0.95, counterparty_name='Alex Kim')
    )
    second = resolver.attribution(
        _extracted(capture_owner='other', ownership_confidence=0.95, counterparty_name='Alex Kim')
    )

    assert first == second == {}
    assert people_store == [], 'extraction must not write a Person the user never created'


@pytest.mark.parametrize(
    ('owner', 'confidence', 'name'),
    [
        # Ownership was never settled: naming anyone here is a guess.
        ('unknown', 0.99, 'Sarah'),
        (None, 0.99, 'Sarah'),
        # Ownership confidence below the shared capture floor.
        ('other', 0.5, 'Sarah'),
        ('other', None, 'Sarah'),
        # Nothing to attribute.
        ('other', 0.99, None),
        ('other', 0.99, '   '),
        # Not a person.
        ('other', 0.99, 'Speaker 0'),
        ('other', 0.99, 'they'),
        ('other', 0.99, 'the team'),
        ('other', 0.99, 'everyone'),
        ('other', 0.99, 'S'),
        ('other', 0.99, 'Sarah from the design team who sits upstairs'),
    ],
)
def test_ambiguous_or_unsettled_attribution_names_nobody(people_store, owner, confidence, name):
    resolver = conversation_capture.PersonAttributionResolver('uid')

    attribution = resolver.attribution(
        _extracted(capture_owner=owner, ownership_confidence=confidence, counterparty_name=name)
    )

    assert attribution == {}
    assert people_store == [], 'a rejected attribution must never mint a person'


def test_a_people_store_failure_costs_the_attribution_not_the_task(monkeypatch):
    def _boom(_uid):
        raise RuntimeError('people store unavailable')

    monkeypatch.setattr(conversation_capture.users_db, 'get_people', _boom)
    resolver = conversation_capture.PersonAttributionResolver('uid')

    assert (
        resolver.attribution(_extracted(capture_owner='other', ownership_confidence=0.95, counterparty_name='Sarah'))
        == {}
    )


def test_canonical_fields_attach_the_person_to_the_legacy_writer_payload(people_store):
    resolver = conversation_capture.PersonAttributionResolver('uid')

    fields = conversation_capture.canonical_fields(
        _extracted(capture_owner='other', ownership_confidence=0.95, counterparty_name='Sarah'),
        'conversation-1',
        resolver,
    )

    assert fields['assignee_person_id'] == 'person-sarah'
    assert fields['owner'] == 'other'


def test_canonical_fields_for_an_unattributed_item_write_no_person(people_store):
    resolver = conversation_capture.PersonAttributionResolver('uid')

    fields = conversation_capture.canonical_fields(_extracted(), 'conversation-1', resolver)

    assert 'assignee_person_id' not in fields
    assert 'assigner_person_id' not in fields
