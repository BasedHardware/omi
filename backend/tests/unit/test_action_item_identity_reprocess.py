"""Reprocessing a conversation must not send its unchanged tasks to the user's task app again.

``_write_action_items`` replaces a conversation's tasks on every reprocess (smart-merge
survivor refresh, user reprocess, sync update, server recovery). It recreated them under
fresh ids, and the only duplicate guard is the ``exported`` marker looked up by id, so
every reprocess created the same tasks again in Todoist/Asana/... Apple Reminders keeps
that behavior on purpose (a second reminder per reprocess; see the module docstring).

These tests run the real replace writer, the real ``database.action_items`` functions on
an in-memory Firestore that evaluates the production filters and projection, and the
real ``utils.task_sync`` delivery with a fake task app. Nothing reaches a network.
"""

import asyncio
import logging
import os
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

import pytest
from google.api_core.exceptions import NotFound

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.action_items as action_items_db
import database.vector_db as vector_db
from config.action_item_identity import ACTION_ITEM_IDENTITY_PRESERVE_ENV, action_item_identity_preserve_enabled
from utils import task_sync
from utils.conversations import action_item_identity, process_conversation, smart_merge
from utils.conversations.action_item_identity import identity_key, plan_replacement
from utils.conversations.processing_trigger import PROCESSING_MODES, ProcessingTrigger

UID = 'uid-identity'
DUE = datetime(2026, 10, 9, 17, tzinfo=timezone.utc)
_REAL_CREATE_BATCH = action_items_db.create_action_items_batch


# --------------------------------------------------------------------------- in-memory Firestore


class _Snapshot:
    def __init__(self, ref: '_Ref', data: Optional[Dict[str, Any]], fields: Optional[List[str]] = None):
        self.reference = ref
        self.id = ref.id
        self.exists = data is not None
        if data is not None and fields is not None:
            data = {name: data[name] for name in fields if name in data}
        self._data = dict(data) if data is not None else None

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return dict(self._data) if self._data is not None else None


class _Ref:
    def __init__(self, store: 'TaskFirestore', path: str):
        self._store, self.path = store, path
        self.id = path.rsplit('/', 1)[-1]

    def collection(self, name: str) -> '_Query':
        return _Query(self._store, f'{self.path}/{name}')

    def get(self, transaction=None) -> _Snapshot:
        self._store.events.append(('get', self.path, transaction is not None))
        return _Snapshot(self, self._store.docs.get(self.path))

    def set(self, data: Dict[str, Any]) -> None:
        self._store.events.append(('set', self.path, dict(data)))
        self._store.docs[self.path] = dict(data)

    def update(self, patch: Dict[str, Any]) -> None:
        self._store.events.append(('update', self.path, dict(patch)))
        if self.path not in self._store.docs:
            raise NotFound(self.path)
        self._store.docs[self.path].update(patch)

    def delete(self) -> None:
        self._store.events.append(('delete', self.path))
        self._store.docs.pop(self.path, None)


class _Query:
    def __init__(self, store: 'TaskFirestore', path: str, filters=(), fields=None, limit=None):
        self._store, self._path, self._filters, self._fields, self._limit = store, path, tuple(filters), fields, limit

    def _with(self, **changes) -> '_Query':
        state = {'filters': self._filters, 'fields': self._fields, 'limit': self._limit, **changes}
        return _Query(self._store, self._path, **state)

    def document(self, document_id: Optional[str] = None) -> _Ref:
        if document_id == '':
            raise ValueError('a Firestore document id must not be empty')
        return _Ref(self._store, f'{self._path}/{document_id or self._store.mint()}')

    def where(self, *, filter) -> '_Query':
        assert filter.op_string == '==', filter.op_string
        return self._with(filters=self._filters + ((filter.field_path, filter.value),))

    def select(self, fields) -> '_Query':
        return self._with(fields=list(fields))

    def limit(self, count: int) -> '_Query':
        return self._with(limit=count)

    def order_by(self, *args, **kwargs) -> '_Query':
        return self

    def stream(self, *args, **kwargs):
        self._store.events.append(('query', self._path, self._filters, self._fields, self._limit))
        prefix = f'{self._path}/'
        rows = []
        for path in sorted(self._store.docs):
            data = self._store.docs[path]
            if path.startswith(prefix) and '/' not in path[len(prefix) :]:
                if all(data.get(name) == value for name, value in self._filters):
                    rows.append(_Snapshot(_Ref(self._store, path), data, self._fields))
        return rows[: self._limit] if self._limit is not None else rows


class _Batch:
    """Batch and transaction: writes apply on commit (transactions apply immediately; no contention here)."""

    def __init__(self, immediate: bool, events: list):
        self._immediate, self._ops = immediate, []
        self._events = events

    def _apply(self, op: Callable[[], None]) -> None:
        op() if self._immediate else self._ops.append(op)

    def set(self, ref: _Ref, data: Dict[str, Any]) -> None:
        self._apply(lambda: ref.set(data))

    def update(self, ref: _Ref, patch: Dict[str, Any]) -> None:
        self._apply(lambda: ref.update(patch))

    def delete(self, ref: _Ref) -> None:
        self._apply(ref.delete)

    def commit(self) -> None:
        self._events.append(('commit', len(self._ops)))
        for op in self._ops:
            op()
        self._ops.clear()


class TaskFirestore:
    def __init__(self):
        self.docs: Dict[str, Dict[str, Any]] = {}
        self.minted = 0
        self.events: List[tuple] = []

    def mint(self) -> str:
        self.minted += 1
        return f'auto-{self.minted:04d}'

    def collection(self, name: str) -> _Query:
        return _Query(self, name)

    def batch(self) -> _Batch:
        self.events.append(('batch',))
        return _Batch(immediate=False, events=self.events)

    def transaction(self) -> _Batch:
        self.events.append(('transaction',))
        return _Batch(immediate=True, events=self.events)

    def tasks(self, conversation_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        prefix = f'users/{UID}/action_items/'
        return {
            path[len(prefix) :]: data
            for path, data in self.docs.items()
            if path.startswith(prefix) and (conversation_id is None or data.get('conversation_id') == conversation_id)
        }


# --------------------------------------------------------------------------- world


def _item(description, due_at=None):
    return SimpleNamespace(
        description=description, completed=False, created_at=None, updated_at=None, due_at=due_at, completed_at=None
    )


def _conversation(conversation_id, items):
    return SimpleNamespace(
        id=conversation_id, is_locked=False, source='omi', structured=SimpleNamespace(action_items=list(items))
    )


def _no_real_firestore(*args, **kwargs):
    raise AssertionError('hermetic test reached a real Firestore client')


class _NoNetworkClient:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class World:
    """Real writer + real task-store functions + real delivery, with every network seam faked."""

    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.store = TaskFirestore()
        self.default_app = 'todoist'
        self.deferred = False
        self.queue: List[Callable[[], None]] = []
        self.external: List[str] = []  # titles created in the user's cloud task app
        self.apple_pushes: List[List[str]] = []  # ids per Apple Reminders silent push
        self.vector_error: Optional[BaseException] = None
        self.events: List[tuple] = []  # ordered seam calls, for first-processing parity
        self.reminders: List[tuple] = []
        self.creates: List[Dict[str, Any]] = []

        monkeypatch.setattr(action_items_db, 'db', self.store)
        monkeypatch.setattr(action_items_db, 'get_firestore_client', _no_real_firestore)
        monkeypatch.setattr(action_items_db.firestore, 'transactional', lambda fn: fn)
        monkeypatch.setattr(action_items_db, 'bump_action_items_list_version', lambda uid: None)

        def create(uid, data, **kwargs):
            self.creates.append(kwargs)
            ids = _REAL_CREATE_BATCH(uid, data, **kwargs)
            self.events.append(('create', [dict(row) for row in data], sorted(kwargs)))
            return ids

        monkeypatch.setattr(action_items_db, 'create_action_items_batch', create)

        pc = process_conversation
        monkeypatch.setattr(pc.conversation_capture, 'canonical_conversation_fields', lambda *a, **k: {})
        monkeypatch.setattr(pc, 'emit_product_event', lambda **k: self.events.append(('event', k['event'])))
        monkeypatch.setattr(pc, 'delete_action_item_vectors_batch', lambda uid, ids: self.events.append(('unvec', ids)))
        monkeypatch.setattr(pc, 'upsert_action_item_vectors_batch', self._upsert_vectors)
        monkeypatch.setattr(pc, 'submit_with_context', self._submit)
        monkeypatch.setattr(pc, 'send_action_item_data_message', lambda **k: self.reminders.append(('schedule', k)))
        monkeypatch.setattr(pc, 'sync_action_item_reminder', lambda **k: self.reminders.append(('reconcile', k)))

        async def inline(executor, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        async def create_task_internal(**kwargs):
            self.external.append(kwargs['title'])
            return {'success': True, 'external_task_id': f'ext-{len(self.external)}'}

        async def apple_push(user_id, action_items):
            self.apple_pushes.append([item['id'] for item in action_items])
            return True

        monkeypatch.setattr(task_sync, 'httpx', SimpleNamespace(AsyncClient=_NoNetworkClient))
        monkeypatch.setattr(task_sync, 'run_blocking', inline)
        monkeypatch.setattr(task_sync, 'create_task_internal', create_task_internal)
        monkeypatch.setattr(task_sync, 'send_apple_reminders_sync_push_async', apple_push)
        monkeypatch.setattr(task_sync.users_db, 'get_default_task_integration', lambda uid: self.default_app)
        monkeypatch.setattr(task_sync.users_db, 'get_task_integration', lambda uid, app: {'connected': True})

    def _upsert_vectors(self, uid, items):
        self.events.append(('vectors', [dict(item) for item in items]))
        if self.vector_error is not None:
            raise self.vector_error
        return len(items)

    def _submit(self, executor, fn, *args, **kwargs):
        self.events.append(('deliver_queued',))
        job = lambda: fn(*args, **kwargs)  # noqa: E731
        self.queue.append(job) if self.deferred else job()

    def drain(self) -> None:
        while self.queue:
            self.queue.pop(0)()

    def process(self, conversation_id, items) -> None:
        process_conversation._save_action_items(UID, _conversation(conversation_id, items))

    def ids(self, conversation_id='conv-1') -> Dict[str, str]:
        return {data['description']: task_id for task_id, data in self.store.tasks(conversation_id).items()}

    def client_marks_apple_exported(self) -> None:
        """The iOS app's markExportedBatch callback, through the real backend writer."""
        updates = [
            {
                'id': task_id,
                'data': {'exported': True, 'export_platform': 'apple_reminders', 'apple_reminder_id': f'ek-{task_id}'},
            }
            for task_id, data in self.store.tasks().items()
            if data.get('sync_requested') and not data.get('exported')
        ]
        action_items_db.batch_sync_update_action_items(UID, updates)


@pytest.fixture(scope='module', autouse=True)
def _warm():
    # The CPU guard measures the call phase; pay one-time event-loop and unicode-table costs here.
    asyncio.run(asyncio.sleep(0))
    identity_key('Ｗａｒｍ ｕｐ’s')


@pytest.fixture
def world(monkeypatch):
    monkeypatch.delenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, raising=False)
    return World(monkeypatch)


BUDGET, VENUE, NOTES = 'Send the budget to Maria', 'Book the venue for Friday', 'Share the meeting notes'


# --------------------------------------------------------------------------- reprocess delivers once


def test_reprocessing_twice_creates_each_task_once_in_the_task_app(world):
    world.process('conv-1', [_item(BUDGET, DUE), _item(VENUE)])
    first_ids = world.ids()
    world.process('conv-1', [_item(BUDGET, DUE), _item(VENUE)])
    world.process('conv-1', [_item(BUDGET, DUE), _item(VENUE)])

    assert sorted(world.external) == sorted([BUDGET, VENUE])
    assert world.ids() == first_ids
    assert all(data.get('exported') is True for data in world.store.tasks('conv-1').values())


@pytest.mark.parametrize('rounds', [3, 8])
def test_n_reprocesses_with_llm_casing_and_punctuation_noise_still_deliver_once(world, rounds):
    variants = [BUDGET, BUDGET.upper() + '.', f'  {BUDGET.lower()}!  ', BUDGET.replace(' ', '  ') + '…']
    world.process('conv-1', [_item(BUDGET), _item(NOTES)])
    first_ids = sorted(world.ids().values())
    for round_number in range(rounds):
        world.process('conv-1', [_item(variants[round_number % len(variants)]), _item(NOTES)])

    assert sorted(world.external) == sorted([BUDGET, NOTES])
    assert sorted(world.ids().values()) == first_ids


def test_already_exported_tasks_are_left_out_of_delivery_on_reprocess(world, monkeypatch):
    """The per-id guard would skip them too, but only after one read and one provider lookup each."""
    world.process('conv-1', [_item(BUDGET), _item(VENUE)])
    delivered: List[List[str]] = []
    real = process_conversation.auto_sync_action_items_batch

    async def recording(uid, items):
        delivered.append([item['description'] for item in items])
        return await real(uid, items)

    monkeypatch.setattr(process_conversation, 'auto_sync_action_items_batch', recording)
    world.process('conv-1', [_item(BUDGET), _item(VENUE), _item(NOTES)])

    assert delivered == [[NOTES]]
    assert world.external == [BUDGET, VENUE, NOTES]


def test_reworded_and_new_tasks_are_sent_and_dropped_tasks_are_deleted(world):
    world.process('conv-1', [_item(BUDGET), _item(VENUE), _item(NOTES)])
    reworded_budget = 'Send the revised budget to Maria'
    world.process('conv-1', [_item(reworded_budget), _item(VENUE), _item('Order the projector')])

    # A materially different wording is a different task: it is delivered. VENUE is not.
    assert world.external == [BUDGET, VENUE, NOTES, reworded_budget, 'Order the projector']
    # Tasks the new extraction dropped are deleted from Omi, as before; their task-app copy is untouched.
    assert sorted(world.ids()) == sorted([reworded_budget, VENUE, 'Order the projector'])


def test_a_reprocess_that_extracts_nothing_leaves_the_existing_tasks_alone(world):
    world.process('conv-1', [_item(BUDGET)])
    before = dict(world.store.tasks())
    world.process('conv-1', [])

    assert world.store.tasks() == before
    assert world.external == [BUDGET]


def test_a_task_in_another_conversation_never_lends_its_identity(world):
    world.process('conv-1', [_item(BUDGET)])
    world.process('conv-2', [_item(BUDGET)])
    world.process('conv-2', [_item(BUDGET)])

    # The same words in a different conversation are a separate task; each is delivered once.
    assert world.external == [BUDGET, BUDGET]
    assert world.ids('conv-1')[BUDGET] != world.ids('conv-2')[BUDGET]


# --------------------------------------------------------------------------- failure injection


def test_vector_failure_after_delivery_was_queued_then_retry_delivers_once(world):
    """Sol's proof scenario: delivery is queued, task-vector persistence fails, the job retries."""
    world.deferred = True
    world.vector_error = RuntimeError('external write fence unavailable')
    with pytest.raises(RuntimeError):
        world.process('conv-1', [_item(BUDGET), _item(VENUE)])
    assert len(world.queue) == 1  # first processing keeps today's order: queued before the vectors

    world.vector_error = None
    world.process('conv-1', [_item(BUDGET), _item(VENUE)])  # the retry, before the first delivery ran
    world.drain()

    assert sorted(world.external) == sorted([BUDGET, VENUE])


def test_reprocess_failure_before_the_vectors_queues_no_delivery_for_its_retry_to_repeat(world):
    """A new task's id is not exported yet, so a queued delivery plus the retry's would send it twice."""
    world.process('conv-1', [_item(BUDGET)])
    assert world.external == [BUDGET]

    world.deferred = True
    world.vector_error = RuntimeError('external write fence unavailable')
    with pytest.raises(RuntimeError):
        world.process('conv-1', [_item(BUDGET), _item(VENUE)])
    assert world.queue == []  # prior rows exist: delivery waits for persistence

    world.vector_error = None
    world.process('conv-1', [_item(BUDGET), _item(VENUE)])
    world.drain()

    assert world.external == [BUDGET, VENUE]


def test_real_vector_write_fence_failure_prevents_reprocess_delivery(world, monkeypatch):
    world.process('conv-1', [_item(BUDGET)])
    world.deferred = True
    monkeypatch.setattr(
        process_conversation, 'upsert_action_item_vectors_batch', vector_db.upsert_action_item_vectors_batch
    )
    monkeypatch.setattr(vector_db, 'index', SimpleNamespace(upsert=lambda **kwargs: None))
    monkeypatch.setattr(vector_db, 'embeddings', SimpleNamespace(embed_documents=lambda texts: [[0.0] for _ in texts]))

    def failed_fence(*args, **kwargs):
        raise RuntimeError('synthetic external-write fence failure')

    monkeypatch.setattr(vector_db, 'external_write_fence', failed_fence)
    with pytest.raises(RuntimeError, match='synthetic external-write fence'):
        world.process('conv-1', [_item(BUDGET), _item(VENUE)])
    assert world.queue == []
    monkeypatch.setattr(vector_db, 'external_write_fence', lambda *a, **k: nullcontext())
    world.process('conv-1', [_item(BUDGET), _item(VENUE)])
    world.drain()
    assert world.external == [BUDGET, VENUE]


# --------------------------------------------------------------------------- smart merge refresh


def test_smart_merge_survivor_refresh_does_not_resend_exported_tasks(world, monkeypatch):
    world.process('survivor', [_item(BUDGET, DUE), _item(VENUE)])
    exported_ids = world.ids('survivor')
    assert sorted(world.external) == sorted([BUDGET, VENUE])

    row = {'id': 'survivor', 'smart_merge': {'role': 'survivor', 'revision': 2}}
    merged = _conversation('survivor', [_item(BUDGET, DUE), _item(VENUE), _item(NOTES)])
    merged.language = 'en'
    triggers = []

    def process_like_production(uid, language, conversation, *, trigger, persistence_observer, smart_merge_refresh):
        # process_conversation runs _save_action_items synchronously for every reprocess trigger.
        assert PROCESSING_MODES[trigger].reprocess
        triggers.append(trigger)
        process_conversation._save_action_items(uid, conversation)
        persistence_observer(True)
        return conversation

    monkeypatch.setattr(smart_merge.smart_merge_db, 'get_firestore_client', _no_real_firestore)
    monkeypatch.setattr(smart_merge.smart_merge_db, 'claim_survivor_refresh', lambda *a, **k: 2)
    monkeypatch.setattr(smart_merge.smart_merge_db, 'checkpoint_survivor_processing', lambda *a, **k: True)
    monkeypatch.setattr(smart_merge.smart_merge_db, 'release_survivor_refresh', lambda *a, **k: None)
    monkeypatch.setattr(smart_merge.smart_merge_db, 'complete_survivor_refresh', lambda *a, **k: True)
    monkeypatch.setattr(smart_merge.conversations_db, 'get_conversation', lambda *a, **k: dict(row))
    monkeypatch.setattr(smart_merge, 'deserialize_conversation', lambda raw: merged)
    monkeypatch.setattr(smart_merge, 'process_conversation', process_like_production)
    monkeypatch.setattr(smart_merge, 'save_structured_vector', lambda uid, conversation: None)

    smart_merge.refresh_survivor(UID, 'survivor', owner='job-1')

    assert triggers == [ProcessingTrigger.SMART_MERGE]
    assert sorted(world.external) == sorted([BUDGET, VENUE, NOTES])  # only the new task went out
    assert {k: v for k, v in world.ids('survivor').items() if k != NOTES} == exported_ids


# --------------------------------------------------------------------------- kill switch


@pytest.mark.parametrize('raw', ['false', 'off', '0', ' OFF ', 'of', 'flase', 'disable'])
def test_flag_off_recreates_every_task_under_fresh_ids_exactly_as_before(world, monkeypatch, raw):
    monkeypatch.setenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, raw)
    world.process('conv-1', [_item(BUDGET, DUE)])
    first_id = world.ids()[BUDGET]
    world.process('conv-1', [_item(BUDGET, DUE)])

    assert world.ids()[BUDGET] != first_id
    assert world.external == [BUDGET, BUDGET]  # today's duplicate, reproduced under the kill switch
    assert world.creates == [{}, {}]  # never passes document_ids
    # The replaced row's reminder is cancelled and the new id scheduled, as before.
    assert [kind for kind, _ in world.reminders] == ['schedule', 'reconcile', 'schedule']


@pytest.mark.parametrize('raw, enabled', [(None, True), ('', True), ('  ', True), ('true', True), ('ON', True)])
def test_flag_parse_defaults_on(monkeypatch, raw, enabled):
    if raw is None:
        monkeypatch.delenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, raising=False)
    else:
        monkeypatch.setenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, raw)
    assert action_item_identity_preserve_enabled() is enabled


def _scrub(value):
    """Wall-clock stamps differ between two runs; everything else must not."""
    if isinstance(value, datetime):
        return value if value == DUE else 'now'
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_scrub(item) for item in value)
    return value


def _first_processing_trace(monkeypatch, flag: Optional[str]):
    world = World(monkeypatch)
    if flag is None:
        monkeypatch.delenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, raising=False)
    else:
        monkeypatch.setenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, flag)
    world.process('conv-1', [_item(BUDGET, DUE), _item(VENUE), _item(BUDGET)])
    return _scrub((world.events, world.reminders, world.external, world.creates, world.store.docs, world.store.events))


def test_first_processing_is_identical_with_the_flag_on_and_off(monkeypatch):
    on = _first_processing_trace(monkeypatch, None)
    off = _first_processing_trace(monkeypatch, 'false')

    assert on == off
    events = on[0]
    assert [event[0] for event in events].index('deliver_queued') < [event[0] for event in events].index('vectors')


def _process_and_reprocess_trace(monkeypatch, flag: Optional[str]):
    world = World(monkeypatch)
    if flag is None:
        monkeypatch.delenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, raising=False)
    else:
        monkeypatch.setenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, flag)
    world.process('conv-1', [_item(BUDGET, DUE), _item(VENUE)])
    world.process('conv-1', [_item(BUDGET, DUE), _item(VENUE), _item(NOTES)])
    trace = (world.events, world.reminders, world.external, world.creates, world.store.docs, world.store.events)
    return world, _scrub(trace)


def test_a_planner_error_falls_back_to_the_kill_switch_plan_and_still_writes_the_tasks(monkeypatch, caplog):
    _, off = _process_and_reprocess_trace(monkeypatch, 'false')

    def broken(description):
        raise RuntimeError('synthetic planner defect')

    monkeypatch.setattr(action_item_identity, 'identity_key', broken)
    with caplog.at_level(logging.INFO, logger=action_item_identity.__name__):
        world, failed = _process_and_reprocess_trace(monkeypatch, None)

    # First processing and the reprocess both match the flag-off writer call for call.
    assert failed == off
    assert sorted(data['description'] for data in world.store.tasks('conv-1').values()) == sorted(
        [BUDGET, VENUE, NOTES]
    )
    assert world.external == [BUDGET, VENUE, BUDGET, VENUE, NOTES]  # today's behavior, not a lost write
    errors = [r.getMessage() for r in caplog.records if 'planner_error' in r.getMessage()]
    assert errors == ['event=action_item_identity outcome=planner_error cause=RuntimeError'] * 2
    assert not any(text in caplog.text for text in (BUDGET, VENUE, NOTES, 'synthetic planner defect'))


# --------------------------------------------------------------------------- Apple Reminders + reminders


def test_apple_reminders_reprocess_keeps_todays_fresh_id_and_second_push(world):
    """A kept link would let the next last-writer-wins sync overwrite the user's Reminders edit."""
    world.default_app = 'apple_reminders'
    world.process('conv-1', [_item(BUDGET, DUE)])
    world.client_marks_apple_exported()
    budget_id = world.ids()[BUDGET]

    world.process('conv-1', [_item(BUDGET, DUE), _item(VENUE)])

    new_budget_id = world.ids()[BUDGET]
    assert new_budget_id != budget_id and budget_id not in world.store.tasks()
    assert world.apple_pushes == [[budget_id], [new_budget_id, world.ids()[VENUE]]]
    fresh = world.store.tasks()[new_budget_id]
    assert not {'exported', 'export_platform', 'export_date', 'apple_reminder_id'} & set(fresh)
    # The orphaned reminder is cancelled and the fresh id scheduled, exactly as before.
    assert ('reconcile', budget_id) in [(kind, k['action_item_id']) for kind, k in world.reminders]
    assert ('schedule', new_budget_id) in [(kind, k['action_item_id']) for kind, k in world.reminders]


@pytest.mark.parametrize(
    'apple_marker',
    [
        {'exported': True, 'export_platform': 'apple_reminders', 'apple_reminder_id': 'ek-1'},
        {'exported': True, 'export_platform': 'apple_reminders'},  # markExported without an id
        {'apple_reminder_id': 'ek-1'},
    ],
)
def test_apple_linked_rows_never_lend_identity_while_cloud_exports_do(apple_marker):
    prior = [
        _row('apple-row', 'Call mom', due_at=DUE, **apple_marker),
        _row('asana-row', 'Pay rent', exported=True, export_platform='asana', export_date=DUE),
    ]
    items = [{'description': 'Call mom', 'due_at': DUE}, {'description': 'Pay rent'}]
    plan = plan_replacement('c', items, prior)

    assert plan.outcomes == ['new', 'skipped_already_exported']
    assert plan.document_ids == [None, 'asana-row']
    assert plan.items[0] == items[0]  # no marker fields carried onto the Apple item
    assert 'apple-row' not in plan.kept_reminders and 'asana-row' in plan.kept_reminders


def test_a_kept_task_reschedules_its_reminder_in_one_message_and_dropped_ones_cancel(world):
    world.process('conv-1', [_item(BUDGET, DUE), _item(VENUE, DUE)])
    ids = world.ids()
    world.reminders.clear()
    later = DUE + timedelta(days=1)

    world.process('conv-1', [_item(BUDGET, later), _item(NOTES, later)])

    reconciles = {k['action_item_id']: k for kind, k in world.reminders if kind == 'reconcile'}
    schedules = [k['action_item_id'] for kind, k in world.reminders if kind == 'schedule']
    # Kept id: no separate cancel that FCM could deliver after the new schedule; one update instead.
    assert reconciles[ids[BUDGET]]['completed'] is False and reconciles[ids[BUDGET]]['due_at'] == later
    # Dropped id: cancelled as before. New id: scheduled as before.
    assert reconciles[ids[VENUE]]['completed'] is True
    assert schedules == [world.ids()[NOTES]]


# --------------------------------------------------------------------------- the identity rule


@pytest.mark.parametrize(
    'left, right',
    [
        ('Send the budget', 'send the budget'),
        ('Send the budget.', 'Send the budget'),
        ('  Send   the\tbudget\n', 'Send the budget'),
        ("Don't forget Bob's file", 'Don’t forget Bob’s file'),
        ('Ｓｅｎｄ ｔｈｅ ｂｕｄｇｅｔ', 'Send the budget'),
        ('Send​ the budget', 'Send the budget'),
        ('Straße buchen', 'STRASSE buchen'),
        ('Call Bob, then email Ann', 'Call Bob then email Ann'),
    ],
)
def test_identity_key_ignores_case_whitespace_punctuation_and_unicode_form(left, right):
    assert identity_key(left) == identity_key(right) != ''


@pytest.mark.parametrize(
    'left, right',
    [
        ('Send the budget', 'Send the revised budget'),
        ('Send $5 to Bob', 'Send 5 to Bob'),
        ('Call Bob', 'Call Rob'),
        ('Email Ann', 'Email Ann today'),
        ('Do not approve the invoice', 'Do approve the invoice'),
        ('联系张三', '联系李四'),
        ('اتصل بعلي', 'اتصل بعمر'),
    ],
)
def test_identity_key_keeps_material_wording_differences(left, right):
    assert identity_key(left) != identity_key(right)


@pytest.mark.parametrize(
    'left, right',
    [
        ('Set offset -5', 'Set offset 5'),
        ('Transfer 1.5 units', 'Transfer 1/5 units'),
        ('Send 1,500 units', 'Send 1.500 units'),
        ('Use account A-B', 'Use account A B'),
        ('Email a.b@example.test', 'Email a/b@example.test'),
        ('Use code AbC', 'Use code abc'),
        ('Enter Ab12', 'Enter ab12'),
        ('Calculate x²', 'Calculate x2'),
        ('👩\u200d💻', '👩💻'),
        ('می\u200cروم', 'میروم'),
    ],
)
def test_material_symbols_never_borrow_an_exported_identity(world, left, right):
    world.process('conv-1', [_item(left)])
    first_id = world.ids()[left]
    world.process('conv-1', [_item(right)])
    assert world.ids()[right] != first_id
    assert world.external == [left, right]


@pytest.mark.parametrize('description', [None, '', '   ', '...', '!?', 42])
def test_empty_or_non_text_descriptions_never_share_an_identity(description):
    prior = [{'id': 'old', 'conversation_id': 'c', 'description': description, 'exported': True}]
    plan = plan_replacement('c', [{'description': description}], prior)
    assert identity_key(description) == ''
    assert plan.document_ids is None and plan.outcomes == ['new']


def _row(task_id, description, conversation_id='c', **extra):
    return {'id': task_id, 'conversation_id': conversation_id, 'description': description, **extra}


def test_duplicate_tasks_in_one_conversation_pair_one_to_one_and_never_collide():
    prior = [_row('a1', 'Call mom'), _row('a2', 'Call mom', exported=True)]

    both = plan_replacement('c', [{'description': 'Call mom'}, {'description': 'call mom.'}], prior)
    assert sorted(both.document_ids) == ['a1', 'a2']
    assert sorted(both.outcomes) == ['reused_identity', 'skipped_already_exported']

    # One survivor of two prior duplicates takes the exported row, so nothing is re-sent.
    one = plan_replacement('c', [{'description': 'Call mom'}], prior)
    assert one.document_ids == ['a2'] and one.outcomes == ['skipped_already_exported']

    # Two new duplicates against one prior row: one keeps it, the other is a new task.
    grown = plan_replacement('c', [{'description': 'Call mom'}, {'description': 'Call mom'}], prior[1:])
    assert grown.document_ids == ['a2', None] and grown.outcomes == ['skipped_already_exported', 'new']


def test_duplicates_with_different_due_dates_keep_their_own_rows():
    monday, friday = DUE, DUE + timedelta(days=4)
    prior = [_row('mon', 'Call mom', due_at=monday), _row('fri', 'Call mom', due_at=friday.isoformat())]
    plan = plan_replacement(
        'c', [{'description': 'Call mom', 'due_at': friday}, {'description': 'Call mom', 'due_at': monday}], prior
    )
    assert plan.document_ids == ['fri', 'mon']


def test_a_changed_due_date_is_still_the_same_task():
    prior = [_row('t', 'Call mom', due_at=DUE, exported=True, export_platform='todoist')]
    plan = plan_replacement('c', [{'description': 'Call mom', 'due_at': DUE + timedelta(days=1)}], prior)
    assert plan.document_ids == ['t'] and plan.outcomes == ['skipped_already_exported']
    assert plan.items[0]['due_at'] == DUE + timedelta(days=1)


def test_rows_from_another_conversation_are_never_matched():
    prior = [_row('other', 'Call mom', conversation_id='elsewhere', exported=True)]
    plan = plan_replacement('c', [{'description': 'Call mom'}], prior)
    assert plan.document_ids is None and plan.outcomes == ['new']


def test_only_the_export_marker_is_carried_forward():
    prior = [
        _row(
            't',
            'Call mom',
            exported=True,
            export_platform='asana',
            export_date=DUE,
            apple_reminder_id=None,
            completed=True,
            goal_id='g1',
            sort_order=7,
            created_at=DUE,
        )
    ]
    plan = plan_replacement('c', [{'description': 'Call mom', 'completed': False}], prior)
    assert plan.items == [
        {
            'description': 'Call mom',
            'completed': False,
            'exported': True,
            'export_platform': 'asana',
            'export_date': DUE,
        }
    ]


def test_create_action_items_batch_reserves_given_ids_and_mints_the_rest(world):
    ids = action_items_db.create_action_items_batch(
        UID,
        [{'description': 'a', 'completed': False}, {'description': 'b', 'completed': False}],
        document_ids=['kept-id', None],
    )
    assert ids[0] == 'kept-id' and ids[1].startswith('auto-')
    assert world.store.tasks()['kept-id']['description'] == 'a'


def test_flag_is_evaluated_for_each_replacement(world, monkeypatch):
    world.process('conv-1', [_item(BUDGET)])
    original = world.ids()[BUDGET]
    monkeypatch.setenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, 'false')
    world.process('conv-1', [_item(BUDGET)])
    replacement = world.ids()[BUDGET]
    assert replacement != original
    monkeypatch.setenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, 'true')
    world.process('conv-1', [_item(BUDGET)])
    assert world.ids()[BUDGET] == replacement
    assert world.external == [BUDGET, BUDGET]


def test_duplicate_pairing_reserves_due_matches_before_exported_fallback():
    prior = [
        _row('exported', 'Call mom', exported=True, due_at=DUE),
        _row('other', 'Call mom', due_at=DUE + timedelta(days=1)),
    ]
    plan = plan_replacement(
        'c',
        [{'description': 'Call mom', 'due_at': DUE + timedelta(days=2)}, {'description': 'Call mom', 'due_at': DUE}],
        prior,
    )
    assert plan.document_ids == ['other', 'exported']


def test_duplicate_pairing_prefers_oldest_after_due_and_export_state():
    plan = plan_replacement(
        'c',
        [{'description': 'Call mom'}],
        [_row('a-new', 'Call mom', created_at=DUE), _row('z-old', 'Call mom', created_at=DUE - timedelta(days=1))],
    )
    assert plan.document_ids == ['z-old']


def test_due_pairing_does_not_round_distinct_instants_into_one():
    early, late = DUE + timedelta(microseconds=100), DUE + timedelta(microseconds=200)
    plan = plan_replacement(
        'c',
        [{'description': 'Call mom', 'due_at': late}, {'description': 'Call mom', 'due_at': early}],
        [_row('a-early', 'Call mom', due_at=early), _row('z-late', 'Call mom', due_at=late)],
    )
    assert plan.document_ids == ['z-late', 'a-early']


def test_long_descriptions_are_not_truncated_for_identity():
    prefix = 'Synthetic detail ' * 600
    assert identity_key(prefix + 'alpha') != identity_key(prefix + 'beta')


def test_identical_emoji_only_tasks_keep_distinct_ids():
    plan = plan_replacement('c', [{'description': '💻'}, {'description': '💻'}], [_row('a', '💻'), _row('b', '💻')])
    assert plan.document_ids == ['a', 'b']


# --------------------------------------------------------------------------- telemetry


def test_telemetry_is_bounded_and_carries_no_ids_or_text(monkeypatch, caplog):
    counted: Dict[str, float] = {}

    class _Counter:
        def labels(self, *, outcome):
            return SimpleNamespace(inc=lambda amount=1: counted.__setitem__(outcome, counted.get(outcome, 0) + amount))

    monkeypatch.setattr(action_item_identity, 'OMI_ACTION_ITEM_IDENTITY_TOTAL', _Counter())
    monkeypatch.delenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, raising=False)
    prior = [_row('secret-id-1', 'Call mom', exported=True), _row('secret-id-2', 'Pay rent')]
    with caplog.at_level(logging.INFO, logger=action_item_identity.__name__):
        plan_replacement(
            'c', [{'description': 'Call mom'}, {'description': 'Pay rent'}, {'description': 'Buy milk'}], prior
        )
        monkeypatch.setenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, 'off')
        plan_replacement('c', [{'description': 'Call mom'}], prior)

    assert counted == {'skipped_already_exported': 1, 'reused_identity': 1, 'new': 1, 'disabled': 1}
    assert set(counted) <= set(action_item_identity.OUTCOMES)
    text = caplog.text
    assert 'event=action_item_identity' in text
    assert not any(secret in text for secret in ('secret-id', 'Call mom', 'Pay rent', 'Buy milk'))
