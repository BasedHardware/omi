"""Real preservation writer/transactions with synthetic task rows and fake integrations only."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import socket
from google.api_core.exceptions import Aborted

from config.action_item_identity import action_item_refresh_preserve_enabled
from database import action_item_refresh as db
from database.action_item_refresh_policy import RECEIPT, key
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction
from utils.conversations import action_item_refresh as flow
from utils.conversations import process_conversation as pc, smart_merge
from utils.conversations.processing_trigger import ProcessingTrigger as Trigger

UID = 'synthetic-refresh'
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


def task_path(task_id):
    return ('users', UID, 'action_items', task_id)


def conv_path(cid):
    return ('users', UID, 'conversations', cid)


def item(description, **extra):
    return {
        'description': description,
        'conversation_id': 'survivor',
        'completed': False,
        'created_at': NOW,
        'updated_at': NOW,
        'due_at': None,
        'completed_at': None,
        **extra,
    }


class AtomicTransaction(StrictFirestoreTransaction):
    """Strict ordering plus staged writes/atomic commit and conservative conflict retry.

    The whole synthetic store is the read set (stronger than production). This is
    failure injection, not proof of Firestore's real contention/query planner.
    """

    def _begin(self, retry_id=None):
        super()._begin(retry_id)
        self.before = deepcopy(self._database.rows)
        self.ops = []
        self.has_written = False

    def _stage(self, kind, ref, data):
        self._assert_reference_belongs(ref)
        self.has_written = True
        self.ops.append((kind, ref.path, deepcopy(data)))
        if self._database.fail_after == len(self.ops):
            self._database.fail_after = None
            raise RuntimeError('injected before commit')

    def create(self, ref, data):
        self._stage('create', ref, data)

    def update(self, ref, data):
        self._stage('update', ref, data)

    def _commit(self):
        callback, self._database.before_commit = self._database.before_commit, None
        if callback:
            callback()
        if self._database.rows != self.before:
            raise Aborted('synthetic concurrent edit')
        next_rows = deepcopy(self.before)
        for kind, path, data in self.ops:
            if kind == 'create':
                assert path not in next_rows
                next_rows[path] = data
            else:
                assert path in next_rows
                next_rows[path].update(data)
        self._database.rows = next_rows


class Store(StrictFirestore):
    fail_after = None
    before_commit = None

    def transaction(self):
        txn = AtomicTransaction(self)
        txn._max_attempts = 3
        self.transactions.append(txn)
        return txn


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv('ACTION_ITEM_REFRESH_PRESERVE_ENABLED', 'true')
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setattr(
        pc.action_items_db,
        'get_action_items_by_conversation',
        lambda *a, **k: pytest.fail('unexpected legacy fallback'),
    )
    store = Store(
        {
            conv_path('survivor'): {'id': 'survivor', 'sync_content_revision': 1},
            task_path('original'): item('Send report', exported=True),
        }
    )
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(db, 'bump_action_items_list_version', lambda uid: None)
    monkeypatch.setattr(db, 'run_transactional', lambda client, fn: fn(client.transaction()))
    monkeypatch.setattr(pc.conversation_capture, 'canonical_conversation_fields', lambda *a: {})
    effects, queue, external = [], [], []
    monkeypatch.setattr(flow, 'submit_with_context', lambda executor, fn, *args: queue.append(lambda: fn(*args)))
    monkeypatch.setattr(flow, 'dispatch_action_item_reminder', lambda **kwargs: effects.append(('reminder', kwargs)))

    async def sync(uid, rows):
        for row in rows:
            current = store.rows[task_path(row['id'])]
            if not current.get('exported'):
                external.append(row['id'])
                current['exported'] = True

    monkeypatch.setattr(flow, 'auto_sync_action_items_batch', sync)
    monkeypatch.setattr(pc, 'upsert_action_item_vectors_batch', lambda uid, rows: effects.append(('vectors', rows)))

    def write(descriptions, trigger=Trigger.SMART_MERGE, cid='survivor'):
        items = [SimpleNamespace(**item(desc)) for desc in descriptions]
        conversation = SimpleNamespace(
            id=cid, is_locked=False, sync_content_revision=1, structured=SimpleNamespace(action_items=items)
        )
        pc._write_action_items(UID, conversation, trigger)

    def drain():
        while queue:
            queue.pop(0)()

    return SimpleNamespace(store=store, write=write, effects=effects, queue=queue, external=external, drain=drain)


@pytest.mark.parametrize('trigger', [Trigger.SMART_MERGE, Trigger.SYNC_UPDATE])
def test_repeated_refresh_preserves_all_state_and_adds_once(world, trigger):
    row = world.store.rows[task_path('original')]
    row.update(
        completed=True,
        completed_at=NOW,
        due_at=NOW,
        folder_id='folder',
        manual_assignment='person',
        external_task_id='external-1',
        apple_reminder_id='reminder-1',
        provenance=[{'kind': 'conversation', 'id': 'survivor'}],
    )
    original = deepcopy(row)
    for _ in range(5):
        world.write(['SEND REPORT.', 'Book room'], trigger)
        world.drain()
    assert world.store.rows[task_path('original')] == original
    assert len(world.external) == 1
    assert len([p for p in world.store.rows if p[-2] == 'action_items']) == 2


def test_edits_and_hard_deletion_after_enrollment_are_not_recreated(world):
    world.write(['Send report'])
    world.store.rows[task_path('original')].update(description='My edited title', due_at=NOW, completed=True)
    edited = deepcopy(world.store.rows[task_path('original')])
    world.write(['Send report'])
    assert world.store.rows[task_path('original')] == edited
    del world.store.rows[task_path('original')]
    world.write(['Send report'])
    assert not [p for p in world.store.rows if p[-2] == 'action_items']
    assert not world.queue


def test_soft_deleted_tasks_are_suppressors_and_omitted_tasks_stay(world):
    world.store.rows[task_path('original')]['deleted'] = True
    original = deepcopy(world.store.rows[task_path('original')])
    world.write(['Send report', 'New task'])
    world.write([])
    assert world.store.rows[task_path('original')] == original
    assert len([p for p in world.store.rows if p[-2] == 'action_items']) == 2


def test_same_description_in_another_conversation_never_matches(world):
    world.store.rows[task_path('foreign')] = item('Book room', conversation_id='other', exported=True)
    world.write(['Book room'])
    world.drain()
    assert len(world.external) == 1
    assert world.external[0] != 'foreign'


def test_duplicate_occurrences_pair_one_to_one(world):
    world.write(['Send report', 'Send report'])
    world.drain()
    world.write(['Send report', 'Send report'])
    world.drain()
    assert len(world.external) == 1


def test_user_edit_at_commit_retries_and_does_not_clobber(world):
    world.store.before_commit = lambda: world.store.rows[task_path('original')].update(completed=True, due_at=NOW)
    world.write(['Send report', 'Book room'])
    assert world.store.rows[task_path('original')]['completed'] is True
    assert world.store.rows[task_path('original')]['due_at'] == NOW
    world.drain()
    assert len(world.external) == 1


@pytest.mark.parametrize('step', [1, 2])
def test_failure_before_persist_never_queues_and_retry_loses_nothing(world, step):
    before = deepcopy(world.store.rows)
    world.store.fail_after = step
    with pytest.raises(RuntimeError):
        world.write(['Send report', 'Book room'])
    assert world.store.rows == before
    assert not world.queue
    world.write(['Send report', 'Book room'])
    world.drain()
    assert len(world.external) == 1


def test_vector_failure_then_empty_extraction_retries_pending_once(world, monkeypatch):
    monkeypatch.setattr(
        pc, 'upsert_action_item_vectors_batch', lambda *a: (_ for _ in ()).throw(RuntimeError('vector'))
    )
    with pytest.raises(RuntimeError):
        world.write(['Book room'])
    assert not world.queue
    monkeypatch.setattr(pc, 'upsert_action_item_vectors_batch', lambda *a: None)
    world.write([])
    world.drain()
    world.write(['Book room'])
    world.drain()
    assert len(world.external) == 1


def test_replay_while_delivery_queued_and_export_guard(world):
    world.write(['Book room'])
    world.write(['Book room'])
    assert len(world.queue) == 1
    new_id = next(p[-1] for p in world.store.rows if p[-2] == 'action_items' and p[-1] != 'original')
    world.store.rows[task_path(new_id)]['exported'] = True
    world.drain()
    assert not world.external


def seed_donor(world):
    world.store.rows[conv_path('donor')] = {
        'deleted': True,
        'smart_merge': {'role': 'donor', 'survivor_id': 'survivor'},
    }
    world.store.rows[task_path('donor-task')] = item(
        'Call vendor',
        conversation_id='donor',
        exported=True,
        completed=True,
        due_at=NOW,
        external_task_id='external-donor',
        provenance=[{'kind': 'conversation', 'id': 'donor', 'transcript_segment_ids': ['s2']}],
    )
    world.store.rows[task_path('donor-duplicate')] = item('Send report', conversation_id='donor', exported=True)


@pytest.mark.parametrize('step', [1, 2, 3])
def test_transfer_atomic_failure_retry_and_duplicate_alias(world, step):
    seed_donor(world)
    before = deepcopy(world.store.rows)
    world.store.fail_after = step
    with pytest.raises(RuntimeError):
        flow.transfer_donor(UID, 'donor', 'survivor')
    assert world.store.rows == before
    flow.transfer_donor(UID, 'donor', 'survivor')
    transferred = deepcopy(world.store.rows)
    flow.transfer_donor(UID, 'donor', 'survivor')
    assert world.store.rows == transferred
    row = world.store.rows[task_path('donor-task')]
    assert row == {**before[task_path('donor-task')], 'conversation_id': 'survivor'}
    assert world.store.rows[task_path('donor-duplicate')]['refresh_duplicate_of'] == 'original'
    world.write(['Send report', 'Call vendor'])
    world.drain()
    assert not world.external


def test_real_cleanup_transfers_before_retraction_and_retry(world, monkeypatch):
    seed_donor(world)
    donor = {'sync_content_revision': 1}
    monkeypatch.setattr(smart_merge.conversations_db, 'get_conversation', lambda *a, **k: {'id': 'survivor'})
    calls = []

    def cleanup(uid, donor_id):
        assert not [
            r for p, r in world.store.rows.items() if p[-2] == 'action_items' and r.get('conversation_id') == donor_id
        ]
        calls.append('cleanup')
        if len(calls) == 1:
            raise RuntimeError('before donor cleanup')

    monkeypatch.setattr(smart_merge, 'retract_sync_bridge_source', cleanup)
    monkeypatch.setattr(smart_merge, 'mark_sync_bridge_cleaned', lambda *a: True)
    with pytest.raises(RuntimeError):
        smart_merge._cleanup_donor(UID, 'donor', donor, 'survivor')
    smart_merge._cleanup_donor(UID, 'donor', donor, 'survivor')
    assert calls == ['cleanup', 'cleanup']
    assert world.store.rows[task_path('donor-task')]['completed']


@pytest.mark.parametrize('trigger', [Trigger.USER_REPROCESS, Trigger.SERVER_RECOVERY, Trigger.CAPTURE_END, None])
def test_other_triggers_never_touch_preservation_store(monkeypatch, trigger):
    monkeypatch.setattr(db, 'reconcile', lambda *a, **k: pytest.fail('new store reached'))
    assert flow.preserve(UID, SimpleNamespace(id='survivor'), [], trigger, lambda *a: None) is False


@pytest.mark.parametrize(
    'raw,enabled', [('', True), ('true', True), ('on', True), ('off', False), ('false', False), ('typo', False)]
)
def test_flag_parse_and_disabled_path(monkeypatch, raw, enabled):
    monkeypatch.setenv('ACTION_ITEM_REFRESH_PRESERVE_ENABLED', raw)
    assert action_item_refresh_preserve_enabled() is enabled
    if not enabled:
        monkeypatch.setattr(db, 'reconcile', lambda *a, **k: pytest.fail('disabled store reached'))
        assert not flow.preserve(UID, SimpleNamespace(id='survivor'), [], Trigger.SMART_MERGE, lambda *a: None)
        flow.transfer_donor(UID, 'donor', 'survivor')


def test_first_processing_no_prior_rows_returns_legacy(world):
    del world.store.rows[task_path('original')]
    before = deepcopy(world.store.rows)
    assert db.reconcile(UID, 'survivor', [item('New')], expected_revision=1) is None
    assert world.store.rows == before


def test_revision_and_generation_fences(world):
    with pytest.raises(ValueError, match='revision'):
        db.reconcile(UID, 'survivor', [item('New')], expected_revision=0)
    world.store.rows[('users', UID, 'task_intelligence_control', 'state')] = {'account_generation': 2}
    with pytest.raises(ValueError, match='generation'):
        world.write(['New'])
    assert not world.queue


def test_deleted_after_queue_is_not_delivered(world):
    world.write(['Book room'])
    for path in list(world.store.rows):
        if path[-2] == 'action_items' and path[-1] != 'original':
            del world.store.rows[path]
    world.drain()
    world.write(['Book room'])
    assert not world.external and not world.queue


@pytest.mark.parametrize('field', ['exported', 'completed', 'deleted', 'sync_requested', 'apple_reminder_id'])
def test_claim_does_not_deliver_user_handled_tasks(world, field):
    world.store.rows[task_path('original')].update(refresh_delivery='pending', exported=False)
    world.store.rows[task_path('original')][field] = True
    assert db.claim_delivery(UID, 'survivor', ['original']) == []


def test_donor_deleted_receipt_transfers_without_resurrection(world):
    seed_donor(world)
    world.store.rows[conv_path('donor')][RECEIPT] = {'generation': 0, 'keys': {key('User deleted'): ['gone']}}
    flow.transfer_donor(UID, 'donor', 'survivor')
    world.write(['User deleted'])
    assert not world.queue
    assert not any(row.get('description') == 'User deleted' for row in world.store.rows.values())


def test_overflow_is_atomic_and_does_not_fall_through_to_replace(world):
    before = deepcopy(world.store.rows)
    with pytest.raises(ValueError, match='budget'):
        world.write([f'Unique task {i}' for i in range(201)])
    assert world.store.rows == before and not world.queue


def test_hard_deleted_all_rows_cannot_cross_account_generation(world):
    world.write(['Send report'])
    del world.store.rows[task_path('original')]
    world.store.rows[('users', UID, 'task_intelligence_control', 'state')] = {'account_generation': 1}
    with pytest.raises(ValueError, match='generation'):
        world.write(['Send report'])
    assert not world.queue


def test_donor_cannot_resurrect_survivor_deleted_identity(world):
    world.write(['Send report'])
    del world.store.rows[task_path('original')]
    seed_donor(world)
    flow.transfer_donor(UID, 'donor', 'survivor')
    duplicate = world.store.rows[task_path('donor-duplicate')]
    assert duplicate['deleted'] and duplicate['refresh_duplicate_of'] == 'original'
    world.write(['Send report', 'Call vendor'])
    assert not world.queue


def test_empty_donor_transfer_keeps_first_processing_legacy(world):
    del world.store.rows[task_path('original')]
    world.store.rows[conv_path('donor')] = {'deleted': True, 'smart_merge': {'survivor_id': 'survivor'}}
    before = deepcopy(world.store.rows)
    flow.transfer_donor(UID, 'donor', 'survivor')
    assert world.store.rows == before
    assert db.reconcile(UID, 'survivor', [item('New')], expected_revision=1) is None
