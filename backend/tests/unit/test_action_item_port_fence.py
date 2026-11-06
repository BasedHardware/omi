"""Real port and standalone commit boundaries keep Redis tickets across exits."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import fakeredis
import pytest
from google.api_core.exceptions import Aborted

from database import action_item_versions as versions, action_items, action_item_completion_backfill as backfill
from database import candidates, candidate_integration_outbox as outbox, chat_edits, staged_tasks, review_changes
from database import locked_content, legal_holds, review_store, action_item_refresh
from database.action_item_fence import ActionItemCommitFence, fenced_action_item_commit
from database.ports.action_items import ActionItemDraft
from database.space_store import FirestoreSpaceStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction

UID = 'port-test-fence'
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


@pytest.fixture
def redis(monkeypatch):
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(versions, '_redis', lambda: redis)
    monkeypatch.setattr(action_items, 'bump_action_items_list_version', lambda uid: None)
    return redis


def test_uow_tickets_are_busy_at_commit_and_effects_follow_commit(redis, monkeypatch):
    client = StrictFirestore({})
    store = FirestoreSpaceStore(UID, firestore_client=client)
    before = versions.version(UID)
    events = []

    def commit(tx):
        assert versions.version(UID) is None
        events.append('commit')

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit)
    monkeypatch.setattr(action_items, 'bump_action_items_list_version', lambda uid: events.append('bump'))
    store.run(lambda tx: tx.action_items.create(ActionItemDraft(data={'description': 'Synthetic'}), document_id='task'))
    assert events == ['commit', 'bump']
    assert versions.version(UID) not in (before, None)


def test_read_only_uow_takes_no_ticket(redis, monkeypatch):
    store = FirestoreSpaceStore(UID, firestore_client=StrictFirestore({}))
    before = versions.version(UID)
    monkeypatch.setattr(versions, 'begin', lambda uid: pytest.fail('read-only ticket'))
    assert store.run(lambda tx: tx.action_items.read_control()) == {}
    assert versions.version(UID) == before


def test_ticket_spans_all_sdk_retry_attempts(redis, monkeypatch):
    client = StrictFirestore({})
    original = client.transaction

    def transaction(*args, **kwargs):
        tx = original(*args, **kwargs)
        tx._max_attempts = 2
        return tx

    monkeypatch.setattr(client, 'transaction', transaction)
    commits = []

    def commit(tx):
        assert versions.version(UID) is None
        commits.append(versions._redis().hlen(versions._key(UID) + ':writers'))
        if len(commits) == 1:
            raise Aborted('synthetic retry')

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit)
    FirestoreSpaceStore(UID, firestore_client=client).run(
        lambda tx: tx.action_items.stage_write('set', 'task', {'description': 'Synthetic'})
    )
    assert commits == [1, 2]  # First ticket remains live until the full retry exits.
    assert versions.version(UID) is not None


def test_failed_commit_finishes_and_invalidates(redis, monkeypatch):
    before = versions.version(UID)

    def fail(tx):
        assert versions.version(UID) is None
        raise RuntimeError('ambiguous commit')

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', fail)
    with pytest.raises(RuntimeError, match='ambiguous commit'):
        FirestoreSpaceStore(UID, firestore_client=StrictFirestore({})).run(
            lambda tx: tx.action_items.create(ActionItemDraft(data={'description': 'Synthetic'}), document_id='task')
        )
    assert versions.version(UID) not in (before, None)


def test_uncertain_redis_begin_poisons_even_on_store_failure(redis, monkeypatch):
    original = redis.eval

    def uncertain(script, *args):
        result = original(script, *args)
        if script == versions._BEGIN:
            raise TimeoutError('reply lost after Redis applied begin')
        return result

    monkeypatch.setattr(redis, 'eval', uncertain)
    with pytest.raises(RuntimeError):
        with fenced_action_item_commit(UID):
            raise RuntimeError('store failure')
    assert versions.version(UID) is None
    assert redis.hget(versions._key(UID) + ':writers', 'poison') == b'1'


def test_duplicate_registration_after_body_is_rejected(redis):
    seen = []

    def body(tx):
        seen.append(tx)
        tx.action_items.create(ActionItemDraft(data={'description': 'Synthetic'}), document_id='task')

    FirestoreSpaceStore(UID, firestore_client=StrictFirestore({})).run(body)
    with pytest.raises(RuntimeError, match='already returned'):
        seen[0].register_commit_fence(ActionItemCommitFence(UID))


class AtCommit(RuntimeError):
    pass


def loose_client():
    """Reads are immaterial here; each test stops at the real commit boundary.

    Ordering/rollback and written rows are covered by emulator conformance.
    """
    client = MagicMock()
    for name in ('collection', 'document', 'where', 'order_by', 'limit', 'select', 'start_after'):
        getattr(client, name).return_value = client
    snapshot = SimpleNamespace(
        id='task',
        exists=True,
        to_dict=lambda: {'source': 'conversation_migration', 'completed': None},
        update_time=NOW,
        reference=client,
    )
    client.stream.return_value = [snapshot]
    client.get.return_value = snapshot
    client.batch.return_value = client
    return client


@pytest.mark.parametrize(
    'surface',
    [
        'candidate',
        'outbox',
        'chat-update',
        'chat-restore',
        'staged-recovery',
        'completion-backfill',
        'unlock',
        'review-apply',
        'review-undo',
    ],
)
def test_each_standalone_writer_fences_its_actual_commit(redis, monkeypatch, surface):
    before = versions.version(UID)
    commits = []

    def commit(*args, **kwargs):
        assert versions.version(UID) is None, surface
        commits.append(surface)
        raise AtCommit(surface)

    client = loose_client()
    client.commit.side_effect = commit
    client.update.side_effect = commit
    monkeypatch.setattr(candidates, 'db', client)
    monkeypatch.setattr(candidates, 'run_with_transaction_contention_retry', commit)
    monkeypatch.setattr(chat_edits, 'run_with_transaction_contention_retry', commit)
    # Direct @transactional surfaces still execute their owning runner. Stop at
    # its commit boundary to isolate fence placement from domain fixture data.
    if surface == 'outbox':
        monkeypatch.setattr(outbox.firestore, 'transactional', lambda body: commit)
    if surface == 'unlock':
        monkeypatch.setattr(action_items, 'db', client)
        monkeypatch.setattr(locked_content, 'unlock_query_rows', commit)
        monkeypatch.setattr(
            legal_holds, 'external_write_fence', lambda uid: fenced_action_item_commit('unrelated-authority')
        )
    if surface.startswith('review'):
        monkeypatch.setattr(review_store, 'require_enabled', lambda uid: None)
        monkeypatch.setattr(review_store, 'user', lambda uid: client)
        monkeypatch.setattr(review_store, 'client', lambda: client)
        monkeypatch.setattr(review_changes.memory_ledger, 'append_commit_with_builder', commit)
        monkeypatch.setattr(review_changes, 'sync_conversations', lambda *a, **k: None)
        if surface == 'review-undo':
            data = {'created_at': NOW, 'change': {'undone': False}, 'edits': [{'collection': 'action_items'}]}
            monkeypatch.setattr(review_store, 'decode_doc', lambda *a: data)
    with pytest.raises(AtCommit):
        if surface == 'candidate':
            candidates.resolve_task_candidate(UID, 'candidate', account_generation=0)
        elif surface == 'outbox':
            outbox.claim_candidate_integration_dispatch(UID, 'candidate', account_generation=0, firestore_client=client)
        elif surface == 'chat-update':
            chat_edits.apply_update(UID, 'task', 'task', {}, {'description': 'Synthetic'}, firestore_client=client)
        elif surface == 'chat-restore':
            chat_edits.restore(UID, 'task', 'task', {}, {}, firestore_client=client)
        elif surface == 'staged-recovery':
            staged_tasks.restore_legacy_conversation_items(UID, firestore_client=client)
        elif surface == 'completion-backfill':
            backfill.backfill_completion_page(UID, apply=True, firestore_client=client)
        elif surface == 'unlock':
            action_items.unlock_all_action_items(UID)
        elif surface == 'review-apply':
            change = SimpleNamespace(undone=False, kind='edit', change_id='change')
            edit = SimpleNamespace(
                collection='action_items', document_id='task', patch={'status': 'completed', 'completed': True}
            )
            review_changes.record_agent_change(UID, change, [edit], edit_key='edit')
        else:
            review_changes.set_undone(UID, 'change', True, now=NOW)
    assert commits == [surface]
    assert versions.version(UID) not in (before, None)


def test_non_task_chat_commit_does_not_take_task_ticket(redis, monkeypatch):
    before = versions.version(UID)

    def commit(*args, **kwargs):
        assert versions.version(UID) == before
        return None

    monkeypatch.setattr(chat_edits, 'run_with_transaction_contention_retry', commit)
    chat_edits.restore(UID, 'person', 'person', {}, {}, firestore_client=loose_client())
    assert versions.version(UID) == before


def test_mutation_replay_does_not_repeat_post_commit_effect(redis, monkeypatch):
    client = StrictFirestore({})
    calls = []
    monkeypatch.setattr(action_items, 'bump_action_items_list_version', lambda uid: calls.append(uid))
    repo = action_items.FirestoreActionItems(UID, firestore_client=client)
    draft = ActionItemDraft(data={'description': 'Synthetic'})
    first = repo.create(draft, document_id='task', mutation_id='once')
    assert repo.create(draft, document_id='task', mutation_id='once') == first
    assert calls == [UID]


@pytest.mark.parametrize('operation', ['reconcile', 'claim_delivery'])
def test_refresh_writer_tickets_cover_real_commit(redis, monkeypatch, operation):
    before = versions.version(UID)
    client = StrictFirestore(
        {
            ('users', UID, 'conversations', 'conversation'): {'id': 'conversation', 'sync_content_revision': 1},
            ('users', UID, 'action_items', 'existing'): {
                'description': 'Existing',
                'completed': False,
                'status': 'active',
                'conversation_id': 'conversation',
                'account_generation': 0,
                'refresh_delivery': 'pending',
            },
        }
    )
    calls = []

    def fail(tx):
        assert versions.version(UID) is None
        calls.append(operation)
        raise AtCommit(operation)

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', fail)
    with pytest.raises(AtCommit):
        if operation == 'reconcile':
            action_item_refresh.reconcile(
                UID,
                'conversation',
                [{'description': 'Existing'}, {'description': 'New'}],
                expected_revision=1,
                firestore_client=client,
            )
        else:
            action_item_refresh.claim_delivery(UID, 'conversation', ['existing'], firestore_client=client)
    assert calls == [operation]
    assert versions.version(UID) not in (before, None)


@pytest.mark.parametrize('retry', [False, True])
def test_failing_cleanup_does_not_leak_any_attempt_ticket(redis, monkeypatch, retry):
    client = StrictFirestore({})
    original = client.transaction
    commits = []
    finished = []

    def transaction(*args, **kwargs):
        tx = original(*args, **kwargs)
        tx._max_attempts = 2
        return tx

    def commit(tx):
        assert versions.version(UID) is None
        commits.append(tx)
        if retry and len(commits) == 1:
            raise Aborted('synthetic retry')

    class Fence:
        def before_commit(self):
            pass

        def after_commit(self, committed):
            finished.append(committed)
            if len(finished) == 1:
                raise RuntimeError('cleanup failed')

    def body(tx):
        tx.register_commit_fence(Fence())
        tx.action_items.stage_write('set', 'task', {'description': 'Synthetic'})

    monkeypatch.setattr(client, 'transaction', transaction)
    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit)
    with pytest.raises(RuntimeError, match='cleanup failed'):
        FirestoreSpaceStore(UID, firestore_client=client).run(body)
    assert finished == ([False, True] if retry else [True])
    assert versions.version(UID) is not None
    assert redis.hlen(versions._key(UID) + ':writers') == 0
