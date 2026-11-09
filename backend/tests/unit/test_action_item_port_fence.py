"""Real port and standalone commit boundaries keep Redis tickets across exits."""

from datetime import datetime, timezone
import importlib
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import fakeredis
import pytest
from google.api_core.exceptions import Aborted
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import action_item_versions as versions, action_items, action_item_completion_backfill as backfill
from database import candidates, candidate_integration_outbox as outbox, chat_edits, staged_tasks, review_changes
from database import locked_content, legal_holds, review_store, action_item_refresh, user_data_deletion
from database import batch_pipeline_purge, goals, workstreams
from database.ports.action_items import ActionItemTransactionLimitError
from models.goal import GoalStatus, GoalRelationshipDisposition
from models.candidate import CandidateSubjectKind
from models.workstream import TaskGoalLinkImportRequest
from database.action_item_fence import ActionItemCommitFence, fenced_action_item_commit
from database.ports.action_items import ActionItemDraft
from database.space_store import FirestoreSpaceStore, FirestoreSpaceTx
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
        'account-wipe',
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
    if surface == 'account-wipe':
        monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', lambda uid: None)
        monkeypatch.setattr(user_data_deletion, 'get_data_plane_firestore_client', lambda: loose_client())
        monkeypatch.setattr(user_data_deletion, 'search_apps_db', lambda *a, **k: [])
        monkeypatch.setattr(user_data_deletion, 'delete_generic_cache', lambda *a: None)
        client.collections.return_value = [SimpleNamespace(id='action_items')]
        client.get.return_value = SimpleNamespace(exists=False)
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
        elif surface == 'account-wipe':
            user_data_deletion.purge_user_subtree.__wrapped__(UID, client, commit)
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


@pytest.mark.parametrize('writes_task', [False, True])
def test_outbox_claim_takes_ticket_only_for_task_commit(redis, monkeypatch, writes_task):
    before = versions.version(UID)
    payload = {'account_generation': 0, 'status': 'pending', 'attempt_count': 0, 'task_id': 'task'}
    if writes_task:
        payload['external_task_id'] = 'external'
    client = StrictFirestore(
        {
            ('users', UID, 'candidate_integration_outbox', 'candidate'): payload,
            ('users', UID, 'action_items', 'task'): {'description': 'Synthetic'},
        }
    )
    begins = []
    original = versions.begin

    def begin(uid):
        begins.append(uid)
        return original(uid)

    monkeypatch.setattr(versions, 'begin', begin)
    monkeypatch.setattr(outbox, 'bump_action_items_list_version', lambda uid: None)
    monkeypatch.setattr(outbox.dream_dirty, 'notify', lambda *a: None)

    def commit(tx):
        assert (versions.version(UID) is None) == writes_task

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit)
    token = outbox.claim_candidate_integration_dispatch(UID, 'candidate', account_generation=0, firestore_client=client)
    assert bool(token) != writes_task
    assert begins == ([UID] if writes_task else [])
    assert (versions.version(UID) != before) == writes_task


@pytest.mark.parametrize('operation', ['ids', 'conversation'])
@pytest.mark.parametrize('count,staged,reject', [(501, 0, True), (500, 1, True), (500, 0, False), (499, 1, False)])
def test_atomic_bulk_delete_checks_entire_transaction_before_staging(
    redis, monkeypatch, operation, count, staged, reject
):
    # Use the real SDK write buffer, with anonymous credentials and no RPCs.
    client = firestore.Client(project='demo-omi-isolated-tests', credentials=AnonymousCredentials())
    transaction = client.transaction()
    tx = FirestoreSpaceTx(UID, client, transaction)
    for i in range(staged):
        transaction.set(client.document(f'users/{UID}/folders/other-{i}'), {'name': 'Synthetic'})
    ids = [f'task-{i}' for i in range(count)]
    docs = [SimpleNamespace(id=i, reference=client.document(f'users/{UID}/action_items/{i}')) for i in ids]
    monkeypatch.setattr(tx.action_items, '_stream', lambda query: iter(docs))

    def apply():
        return (
            tx.action_items.delete_batch(ids)
            if operation == 'ids'
            else tx.action_items.delete_conversation_documents('conversation')
        )

    if reject:
        with pytest.raises(ActionItemTransactionLimitError):
            apply()
        assert len(transaction._write_pbs) == staged
        assert tx._fences == [] and tx._effects == []
    else:
        apply()
        assert len(transaction._write_pbs) == staged + count
    client.close()


@pytest.mark.parametrize('operation', ['ids', 'conversation'])
def test_standalone_bulk_delete_keeps_chunking(redis, monkeypatch, operation):
    client = firestore.Client(project='demo-omi-isolated-tests', credentials=AnonymousCredentials())
    repo = action_items.FirestoreActionItems(UID, firestore_client=client)
    ids = [f'task-{i}' for i in range(1001)]
    monkeypatch.setattr(
        repo,
        '_stream',
        lambda query: iter(
            [SimpleNamespace(id=i, reference=client.document(f'users/{UID}/action_items/{i}')) for i in ids]
        ),
    )
    monkeypatch.setattr(action_items, '_purge_proactivity_source', lambda *a: None)
    sizes = []

    def commit(batch):
        assert versions.version(UID) is None
        sizes.append(len(batch._write_pbs))

    monkeypatch.setattr(firestore.WriteBatch, 'commit', commit)
    if operation == 'ids':
        assert repo.delete_batch(ids) == ids
    else:
        assert repo.delete_conversation_documents('conversation') == len(ids)
    assert sizes == [499, 499, 3]
    client.close()


@pytest.mark.parametrize(
    'repo_type', [action_items.FirestoreActionItems, goals.FirestoreGoals, workstreams.FirestoreWorkstreams]
)
def test_raw_transaction_cannot_silently_drop_post_commit_effect(repo_type):
    repo = repo_type(UID, firestore_client=loose_client(), transaction=object())
    with pytest.raises(RuntimeError, match='commit context'):
        repo._post_commit(lambda: pytest.fail('effect executed before commit'))


@pytest.mark.parametrize('repo_type', [goals.FirestoreGoals, workstreams.FirestoreWorkstreams])
def test_raw_transaction_rejects_task_write_before_running_body(repo_type):
    repo = repo_type(UID, firestore_client=loose_client(), transaction=object())
    with pytest.raises(RuntimeError, match='commit context'):
        repo._apply_transaction(lambda tx: pytest.fail('task writes were staged'), None, task_writes=True)


@pytest.mark.parametrize('repo_type', [goals.FirestoreGoals, workstreams.FirestoreWorkstreams])
def test_workflow_task_writer_forwards_uow_commit_context(redis, monkeypatch, repo_type):
    client = StrictFirestore({('users', UID, 'action_items', 'task'): {'description': 'Synthetic'}})

    def body(tx):
        repo = tx.goals if repo_type is goals.FirestoreGoals else tx.workstreams
        repo._task_write(tx.transaction, 'update', client.document(f'users/{UID}/action_items/task'), {'goal_id': None})

    def commit(tx):
        assert versions.version(UID) is None

    before = versions.version(UID)
    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit)
    FirestoreSpaceStore(UID, firestore_client=client).run(body)
    assert versions.version(UID) not in (before, None)


@pytest.mark.parametrize('surface', ['goal-detach', 'resolve-candidate', 'resolve-intent', 'import-links'])
def test_workflow_standalone_task_writes_are_fenced(redis, monkeypatch, surface):
    before = versions.version(UID)
    calls = []

    def transactional(fn):
        def run(tx):
            if fn.__name__ == 'reserve':
                return None
            assert versions.version(UID) is None, surface
            calls.append(surface)
            raise AtCommit(surface)

        return run

    monkeypatch.setattr(goals.firestore, 'transactional', transactional)
    client = loose_client()
    with pytest.raises(AtCommit):
        if surface == 'goal-detach':
            goals.FirestoreGoals(UID, firestore_client=client).transition_lifecycle_document(
                'goal',
                status=GoalStatus.paused,
                relationship_disposition=GoalRelationshipDisposition.detach,
                idempotency_key='detach',
                account_generation=0,
            )
        elif surface == 'resolve-candidate':
            candidate = SimpleNamespace(
                subject_kind=CandidateSubjectKind.workstream, workstream_proposal=object(), candidate_id='candidate'
            )
            workstreams.FirestoreWorkstreams(UID, firestore_client=client).resolve_candidate_document(candidate, 0)
        elif surface == 'resolve-intent':
            request = SimpleNamespace(model_dump=lambda **k: {})
            workstreams.FirestoreWorkstreams(UID, firestore_client=client).resolve_intent_document(
                request, idempotency_key='intent', account_generation=0
            )
        else:
            request = TaskGoalLinkImportRequest(links=[{'task_id': 'task', 'goal_id': 'goal'}])
            workstreams.FirestoreWorkstreams(UID, firestore_client=client).import_links_documents(
                request, idempotency_key='import', account_generation=0
            )
    assert calls == [surface]
    assert versions.version(UID) not in (before, None)


@pytest.mark.parametrize('surface', ['legacy-migration', 'soft-cap-unlock'])
def test_operator_task_writers_fence_commits(redis, monkeypatch, surface):
    before = versions.version(UID)
    client = loose_client()

    def commit():
        assert versions.version(UID) is None
        if surface == 'legacy-migration':
            assert versions.version('second-synthetic-owner') is None
        raise AtCommit(surface)

    client.commit.side_effect = commit
    with pytest.raises(AtCommit):
        if surface == 'legacy-migration':
            migration = importlib.import_module('migrations.004_migrate_action_items_to_collection')
            migration._commit_action_item_batch(client, [UID, 'second-synthetic-owner'])
        else:
            operator = importlib.import_module('scripts.unlock_soft_cap_locked')
            operator.unlock_collection(client, UID, 'action_items')
    assert versions.version(UID) not in (before, None)


def test_non_task_operator_unlock_takes_no_task_ticket(redis, monkeypatch):
    operator = importlib.import_module('scripts.unlock_soft_cap_locked')
    monkeypatch.setattr(versions, 'begin', lambda uid: pytest.fail('non-task ticket'))
    operator.unlock_collection(loose_client(), UID, 'memories')


def test_operator_direct_script_help_needs_no_pythonpath(tmp_path):
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'unlock_soft_cap_locked.py'
    result = subprocess.run(
        [sys.executable, str(script), '--help'], cwd=tmp_path, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert '--uids-file' in result.stdout
