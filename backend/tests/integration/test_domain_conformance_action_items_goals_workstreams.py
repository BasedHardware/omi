"""Task workflow semantics through ports only, over independent sim and Firestore.

All owners/documents are synthetic. Required backends cannot silently skip.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from database.ports.action_items import ActionItemDraft, ActionItemEntity, TaskRelationshipConflictError
from database.ports.base import MutationConflict, RevisionConflict
from database.ports.folders import FolderCreate
from database.ports.goals import GoalCreate, GoalUpdate, GoalEntity, GoalConflictError
from database.ports.workstreams import (
    WorkstreamCreate,
    WorkstreamUpdate,
    WorkstreamEntity,
    WorkstreamGenerationMismatchError,
)
from testing.domain_fixtures import domain_backend

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def workflow(h, label):
    sid = h.space(label)
    goal = h.goals(sid).create(GoalCreate(data={'title': 'Synthetic goal', 'desired_outcome': 'Finish synthetic work'}))
    workstream = h.workstreams(sid).create(
        WorkstreamCreate(data={'title': 'Synthetic thread', 'objective': 'Advance work', 'goal_id': goal.id})
    )
    return sid, goal, workstream


def test_typed_crud_unknown_fields_and_codec(domain_backend):
    h = domain_backend
    sid, goal, ws = workflow(h, 'crud')
    assert isinstance(goal, GoalEntity) and isinstance(ws, WorkstreamEntity)
    repo = h.action_items(sid)
    tid = repo.create(
        ActionItemDraft(
            data={
                'description': 'Task',
                'goal_id': goal.id,
                'workstream_id': ws.workstream_id,
                'due_at': '2026-11-01T12:00:00',
                'unknown': {'number': 7},
            }
        )
    )
    row = repo.get(tid)
    assert isinstance(row, ActionItemEntity) and row.description == 'Task'
    assert row.due_at == NOW + timedelta(hours=12) and type(row.unknown['number']) is int
    assert repo.get_by_ids(['missing', tid])[0].id == tid
    assert repo.delete(tid) and not repo.delete(tid) and repo.get(tid) is None


def test_lenient_legacy_entities_do_not_rewrite_defaults(domain_backend):
    h = domain_backend
    sid = h.space('legacy')
    h.seed(sid, 'action_items', 'legacy', {'description': None, 'completed': None, 'unknown': 42})
    h.seed(sid, 'goals', 'old-goal', {'title': None, 'unknown': 42})
    h.seed(sid, 'workstreams', 'old-thread', {'title': 42, 'unknown': True})
    assert h.action_items(sid).get('legacy').description is None
    assert h.action_items(sid).get('legacy').completed is False
    assert h.goals(sid).get('old-goal').title is None
    assert h.workstreams(sid).get('old-thread').title == 42
    assert 'deleted' not in h.read(sid, 'action_items', 'legacy')


@pytest.mark.parametrize('failure', ['missing-goal', 'ended-goal', 'mismatch', 'generation'])
def test_cross_domain_uow_rejects_invalid_links(domain_backend, failure):
    h = domain_backend
    sid, goal, ws = workflow(h, 'invalid-' + failure)
    if failure == 'ended-goal':
        h.goals(sid).delete(goal.id)
    if failure == 'generation':
        h.seed(sid, 'task_intelligence_control', 'state', {'account_generation': 9})
    gid = 'missing' if failure == 'missing-goal' else goal.id
    if failure == 'mismatch':
        other = h.goals(sid).create(GoalCreate(data={'title': 'Other'}))
        gid = other.id

    def body(tx):
        tx.action_items.create(
            ActionItemDraft(data={'description': 'Must abort', 'goal_id': gid, 'workstream_id': ws.workstream_id}),
            document_id='aborted',
        )

    with pytest.raises(TaskRelationshipConflictError):
        h.store(sid).run(body)
    assert h.action_items(sid).get('aborted') is None


def test_cross_domain_uow_links_task_and_rolls_back_on_exception(domain_backend):
    h = domain_backend
    sid, goal, ws = workflow(h, 'atomic')
    store = h.store(sid)
    store.run(
        lambda tx: tx.action_items.create(
            ActionItemDraft(data={'description': 'Linked', 'goal_id': goal.id, 'workstream_id': ws.workstream_id}),
            document_id='linked',
        )
    )
    assert h.action_items(sid).get('linked').goal_id == goal.id

    def abort(tx):
        tx.action_items.update('linked', {'description': 'Abort'}, expected_revision=1)
        raise RuntimeError('abort all writes')

    with pytest.raises(RuntimeError, match='abort all'):
        store.run(abort)
    assert h.action_items(sid).get('linked').description == 'Linked'

    def abort_control(tx):
        tx.goals.write_control({'account_generation': 15})
        raise RuntimeError('control abort')

    with pytest.raises(RuntimeError):
        store.run(abort_control)
    assert h.action_items(sid).read_control().get('account_generation', 0) == 0


def test_ended_goal_links_may_be_preserved_by_update(domain_backend):
    h = domain_backend
    sid, goal, ws = workflow(h, 'ended-link')
    repo = h.action_items(sid)
    tid = repo.create(
        ActionItemDraft(data={'description': 'Task', 'goal_id': goal.id, 'workstream_id': ws.workstream_id})
    )
    h.goals(sid).delete(goal.id)
    assert repo.update(tid, {'goal_id': goal.id, 'description': 'Still linked'}, expected_revision=1)
    assert repo.get(tid).goal_id == goal.id


def test_cas_and_blind_revisions(domain_backend):
    h = domain_backend
    sid = h.space('cas')
    repo = h.action_items(sid)
    tid = repo.create(ActionItemDraft(data={'description': 'Before'}))
    assert repo.get(tid).revision == 1
    assert repo.update(tid, {'description': 'After'}, expected_revision=1)
    assert repo.get(tid).revision == 2
    with pytest.raises(RevisionConflict) as error:
        repo.update(tid, {'description': 'Stale'}, expected_revision=1)
    assert error.value.current_revision == 2
    repo.update(tid, {'description': 'Blind'})
    assert repo.get(tid).revision == 4
    h.seed(sid, 'action_items', 'legacy', {'description': 'legacy'})
    repo.update('legacy', {'description': 'blind'})
    assert h.read(sid, 'action_items', 'legacy')['revision'] == 2


def test_task_mutation_replay_and_digest_conflicts(domain_backend):
    h = domain_backend
    sid = h.space('mutations')
    repo = h.action_items(sid)
    draft = ActionItemDraft(data={'description': 'One task'})
    tid = repo.create(draft, mutation_id='create-once')
    assert repo.create(draft, mutation_id='create-once') == tid
    assert len(list(repo.iter_all())) == 1
    with pytest.raises(MutationConflict):
        repo.create(ActionItemDraft(data={'description': 'Different'}), mutation_id='create-once')
    assert repo.update(tid, {'description': 'Edited'}, expected_revision=1, mutation_id='edit-once')
    assert repo.update(tid, {'description': 'Edited'}, expected_revision=1, mutation_id='edit-once')
    assert repo.get(tid).revision == 2
    with pytest.raises(MutationConflict):
        repo.update(tid, {'description': 'Conflict'}, mutation_id='edit-once')


def test_idempotency_skips_deleted_prefix_and_finished_matches(domain_backend):
    h = domain_backend
    sid = h.space('idempotency')
    repo = h.action_items(sid)
    for i in range(8):
        h.seed(sid, 'action_items', f'a-{i}', {'description': 'retired', 'idempotency_key': 'same', 'deleted': True})
    tid = repo.create(ActionItemDraft(data={'description': 'Live'}), idempotency_key='same')
    assert repo.create(ActionItemDraft(data={'description': 'retry'}), idempotency_key='same') == tid
    repo.update(tid, {'completed': True})
    assert repo.create(ActionItemDraft(data={'description': 'retry'}), idempotency_key='same') == tid
    fresh = repo.create(
        ActionItemDraft(data={'description': 'New occurrence'}), idempotency_key='same', reuse_finished=False
    )
    assert fresh != tid


def test_batch_caps_and_idempotent_reserved_id(domain_backend):
    h = domain_backend
    sid = h.space('batch')
    repo = h.action_items(sid)
    draft = ActionItemDraft(data={'description': 'Task'})
    assert repo.create(draft, document_id='reserved') == 'reserved'
    assert repo.create(ActionItemDraft(data={'description': 'retry'}), document_id='reserved') == 'reserved'
    assert repo.get('reserved').description == 'Task'
    assert repo.create_batch([ActionItemDraft(data={'description': 'Batch set'})], document_ids=['reserved']) == [
        'reserved'
    ]
    assert repo.get('reserved').description == 'Batch set'
    assert repo.create_batch([draft, draft], document_ids=['one', 'two']) == ['one', 'two']
    assert repo.delete_batch(['one', 'two', 'missing']) == ['one', 'two', 'missing']
    with pytest.raises(ValueError):
        repo.create_batch([draft] * 401)
    with pytest.raises(ValueError):
        repo.create_batch([draft], document_ids=[])


def test_active_first_legacy_missing_null_deleted_and_date_filters(domain_backend):
    h = domain_backend
    sid = h.space('list')
    repo = h.action_items(sid)
    for key, data in [
        ('done', {'completed': True}),
        ('missing', {}),
        ('null', {'completed': None}),
        ('deleted', {'deleted': True}),
        ('due', {'due_at': NOW}),
    ]:
        h.seed(sid, 'action_items', key, {'description': key, 'created_at': NOW, **data})
    assert [r.id for r in repo.list().items] == ['due', 'missing', 'null', 'done']
    assert {r.id for r in repo.list(completed=False).items} == {'due', 'missing', 'null'}
    assert [r.id for r in repo.list(completed=True).items] == ['done']
    assert [r.id for r in repo.list(due_start_date=NOW, due_end_date=NOW).items] == ['due']
    assert repo.list(start_date=NOW + timedelta(seconds=1)).items == []


def test_keyset_byte_order_deleted_cursor_and_concurrent_insert(domain_backend):
    h = domain_backend
    sid = h.space('keyset')
    repo = h.action_items(sid)
    for key in ['ä', 'a', 'z', 'B']:
        h.seed(sid, 'action_items', key, {'description': key, 'created_at': NOW, 'completed': False})
    page = repo.list(limit=2)
    assert [r.id for r in page.items] == ['B', 'a']
    repo.delete('a')
    for key in ['A', 'b']:
        h.seed(sid, 'action_items', key, {'description': key, 'created_at': NOW, 'completed': False})
    page2 = repo.list(limit=2, cursor=page.next_cursor)
    assert [r.id for r in page2.items] == ['b', 'z']
    page3 = repo.list(limit=2, cursor=page2.next_cursor)
    assert [r.id for r in page3.items] == ['ä'] and page3.next_cursor is None


def test_completion_preserves_timestamp_export_clears_sync_and_retirement(domain_backend):
    h = domain_backend
    sid = h.space('completion')
    repo = h.action_items(sid)
    tid = repo.create(
        ActionItemDraft(
            data={
                'description': 'Task',
                'completed': True,
                'completed_at': NOW,
                'sync_requested': True,
                'conversation_id': 'conv',
            }
        )
    )
    repo.update(tid, {'completed': True, 'completed_at': NOW + timedelta(days=1), 'exported': True})
    assert repo.get(tid).completed_at == NOW and repo.get(tid).sync_requested is False
    assert repo.retire_for_conversation('conv', active_ids=[], replacements={tid: 'replacement'}) == 1
    assert repo.get(tid).status == 'superseded' and repo.list().items == []


def test_goal_focus_cap_lifecycle_and_receipts(domain_backend):
    h = domain_backend
    sid = h.space('focus')
    repo = h.goals(sid)
    goals = [repo.create(GoalCreate(data={'title': f'Goal {i}'})) for i in range(6)]
    for i, goal in enumerate(goals[:5]):
        repo.focus(goal.id, idempotency_key=f'focus-{i}', account_generation=0)
    with pytest.raises(GoalConflictError):
        repo.focus(goals[5].id, idempotency_key='full', account_generation=0)
    row = repo.focus(goals[5].id, replacement_goal_id=goals[0].id, idempotency_key='replace', account_generation=0)
    assert row.status == 'focused'
    repo.unfocus(row.id, idempotency_key='unfocus', account_generation=0)
    assert repo.get(row.id).status == 'background'
    repo.transition_lifecycle(
        row.id, status='achieved', relationship_disposition='retain', idempotency_key='end', account_generation=0
    )
    assert repo.get(row.id).status == 'achieved'
    once = repo.create_idempotent(GoalCreate(data={'title': 'once'}), idempotency_key='once', account_generation=0)
    assert (
        repo.create_idempotent(GoalCreate(data={'title': 'once'}), idempotency_key='once', account_generation=0).id
        == once.id
    )


def test_goal_revision_and_mutation_receipt(domain_backend):
    h = domain_backend
    sid = h.space('goal-cas')
    repo = h.goals(sid)
    row = repo.create(GoalCreate(data={'title': 'Before'}))
    updated = repo.update(row.id, GoalUpdate(data={'title': 'After'}), expected_revision=1, mutation_id='update')
    assert updated.revision == 2
    assert (
        repo.update(row.id, GoalUpdate(data={'title': 'After'}), expected_revision=1, mutation_id='update').revision
        == 2
    )
    with pytest.raises(RevisionConflict):
        repo.update(row.id, GoalUpdate(data={'title': 'Stale'}), expected_revision=1)


@pytest.mark.parametrize('time_zone', ['Pacific/Honolulu', None, 'Invalid/Zone', ''])
def test_goal_progress_and_local_history_bucket(domain_backend, time_zone):
    h = domain_backend
    sid = h.space('history')
    repo = h.goals(sid)
    h.seed(sid, 'users', 'profile', {'time_zone': time_zone})
    row = repo.create(GoalCreate(data={'title': 'Progress'}))
    event = {
        'kind': 'metric_update',
        'summary': 'Synthetic progress',
        'metric': {'type': 'numeric', 'current': 2, 'target': 10},
    }
    saved = repo.append_progress_event(row.id, event, idempotency_key='event', account_generation=0)
    assert (
        repo.append_progress_event(row.id, event, idempotency_key='event', account_generation=0).event_id
        == saved.event_id
    )
    assert len(repo.list_progress_events(row.id)) == 1
    expected = saved.created_at.astimezone(
        ZoneInfo('Pacific/Honolulu') if time_zone == 'Pacific/Honolulu' else timezone.utc
    ).strftime('%Y-%m-%d')
    assert repo.get_history(row.id)[0]['date'] == expected and repo.get_history(row.id)[0]['value'] == 2
    assert repo.update_progress(row.id, 3, idempotency_key='update', account_generation=0).id == row.id
    latest = repo.list_progress_events(row.id)[0]
    expected_update = latest.created_at.astimezone(
        ZoneInfo('Pacific/Honolulu') if time_zone == 'Pacific/Honolulu' else timezone.utc
    ).strftime('%Y-%m-%d')
    assert repo.get_history(row.id)[0]['date'] == expected_update
    assert repo.get_history(row.id)[0]['value'] == 3


def test_goal_sort_retains_missing_created_at(domain_backend):
    h = domain_backend
    sid = h.space('goal-sort')
    h.seed(sid, 'goals', 'legacy', {'title': 'legacy', 'is_active': True})
    row = h.goals(sid).create(GoalCreate(data={'title': 'new'}))
    assert [g.id for g in h.goals(sid).get_all()] == [row.id, 'legacy']


def test_workstream_events_artifacts_checkpoints_and_generation(domain_backend):
    h = domain_backend
    sid, goal, ws = workflow(h, 'journal')
    repo = h.workstreams(sid)
    wid = ws.workstream_id
    changed = repo.update(
        wid, WorkstreamUpdate(data={'title': 'Changed'}), idempotency_key='title', account_generation=0
    )
    assert changed.title == 'Changed'
    event = repo.append_event(
        wid, {'kind': 'system', 'summary': 'Synthetic event'}, idempotency_key='event', account_generation=0
    )
    assert (
        repo.append_event(
            wid, {'kind': 'system', 'summary': 'Synthetic event'}, idempotency_key='event', account_generation=0
        ).event_id
        == event.event_id
    )
    assert repo.list_events(wid)[0].sequence == 1
    artifact = repo.create_artifact_descriptor(
        wid,
        {
            'logical_key': 'report',
            'version': 1,
            'kind': 'document',
            'uri': 'synthetic://report',
            'content_hash': 'a' * 64,
        },
        idempotency_key='artifact',
        account_generation=0,
    )
    assert repo.list_artifact_descriptors(wid)[0].artifact_id == artifact.artifact_id
    transitioned = repo.transition_artifact_status(
        wid, artifact.artifact_id, {'status': 'awaiting_review'}, idempotency_key='review', account_generation=0
    )
    assert transitioned.status == 'awaiting_review'
    checkpoint = repo.upsert_continuation_checkpoint(
        wid,
        {'runtime_id': 'synthetic', 'last_event_sequence': 1, 'context_summary': 'Resume'},
        idempotency_key='checkpoint',
        account_generation=0,
    )
    assert repo.list_continuation_checkpoints(wid)[0].checkpoint_id == checkpoint.checkpoint_id
    with pytest.raises(WorkstreamGenerationMismatchError):
        repo.update(
            wid, WorkstreamUpdate(data={'title': 'Wrong generation'}), idempotency_key='wrong', account_generation=2
        )


def test_import_task_links_composes_in_one_uow(domain_backend):
    h = domain_backend
    sid = h.space('import')
    goal = h.goals(sid).create(GoalCreate(data={'title': 'Goal'}))
    tid = h.action_items(sid).create(ActionItemDraft(data={'description': 'Unlinked'}))
    request = {'links': [{'task_id': tid, 'goal_id': goal.id}]}
    result = h.store(sid).run(
        lambda tx: tx.workstreams.import_task_goal_links(request, idempotency_key='import', account_generation=0)
    )
    assert result['imported'] == 1 and h.action_items(sid).get(tid).goal_id == goal.id
    assert (
        h.store(sid).run(
            lambda tx: tx.workstreams.import_task_goal_links(request, idempotency_key='import', account_generation=0)
        )
        == result
    )


def test_purge_family_is_idempotent(domain_backend):
    h = domain_backend
    sid, goal, ws = workflow(h, 'purge')
    h.action_items(sid).create(ActionItemDraft(data={'description': 'Purge', 'goal_id': goal.id}))
    for repo in [h.action_items(sid), h.workstreams(sid), h.goals(sid)]:
        assert repo.purge(sid) > 0
        assert repo.purge(sid) == 0
    assert h.action_items(sid).list().items == [] and h.goals(sid).get_all(include_inactive=True) == []


def test_commit_hook_parity_and_read_only_run(domain_backend):
    h = domain_backend
    sid = h.space('fences')
    events = []

    class Fence:
        def before_commit(self):
            events.append('begin')

        def after_commit(self, committed):
            events.append(('finish', committed))

    def body(tx):
        tx.register_commit_fence(Fence())
        return tx.action_items.create(ActionItemDraft(data={'description': 'Fenced'}))

    tid = h.store(sid).run(body)
    assert events == ['begin', ('finish', True)] and h.action_items(sid).get(tid) is not None
    assert h.store(sid).run(lambda tx: tx.action_items.read_control()).get('account_generation', 0) == 0

    def abort(tx):
        tx.register_commit_fence(Fence())
        raise ValueError('body failed')

    events.clear()
    with pytest.raises(ValueError):
        h.store(sid).run(abort)
    assert events == [('finish', False)]


def test_noop_skip_and_escape_flag(domain_backend, monkeypatch):
    h = domain_backend
    sid = h.space('noop')
    repo = h.action_items(sid)
    tid = repo.create(ActionItemDraft(data={'description': 'Same'}))
    before = h.read(sid, 'action_items', tid)
    assert repo.update(tid, {'description': 'Same'})
    assert h.read(sid, 'action_items', tid) == before
    monkeypatch.setenv('OMI_DEV_ACTION_ITEMS_SKIP_NOOP_WRITES_ENABLED', 'false')
    assert repo.update(tid, {'description': 'Same'})
    assert repo.get(tid).revision == 2


def test_sync_keyset_lookahead_and_soft_tombstones(domain_backend):
    h = domain_backend
    sid = h.space('sync')
    repo = h.action_items(sid)
    for entity_id in ['ä', 'a', 'z', 'B']:
        h.seed(
            sid, 'action_items', entity_id, {'description': entity_id, 'updated_at': NOW, 'deleted': entity_id == 'z'}
        )
    h.seed(sid, 'action_items', 'old', {'description': 'No timestamp'})
    page = repo.sync_page(limit=2)
    assert [row.id for row in page.items] == ['B', 'a']
    repo.delete('a')
    page2 = repo.sync_page(limit=2, cursor=page.next_cursor)
    assert [row.id for row in page2.items] == ['z', 'ä']
    assert page2.items[0].deleted is True and page2.next_cursor is None


def test_purge_removes_domain_mutation_receipts(domain_backend):
    h = domain_backend
    sid = h.space('purge-receipts')
    repo = h.action_items(sid)
    repo.create(
        ActionItemDraft(data={'description': 'Before purge'}), document_id='before', mutation_id='reusable-after-purge'
    )
    assert repo.purge(sid) > 0
    assert repo.purge(sid) == 0
    assert (
        repo.create(
            ActionItemDraft(data={'description': 'After purge'}),
            document_id='after',
            mutation_id='reusable-after-purge',
        )
        == 'after'
    )


def test_workstream_mutation_identity_includes_reserved_id(domain_backend):
    h = domain_backend
    sid = h.space('thread-mutation')
    repo = h.workstreams(sid)
    draft = WorkstreamCreate(data={'title': 'Thread', 'objective': 'Work', 'workstream_id': 'one'})
    assert repo.create(draft, mutation_id='once').workstream_id == 'one'
    assert repo.create(draft, mutation_id='once').workstream_id == 'one'
    with pytest.raises(MutationConflict):
        repo.create(
            WorkstreamCreate(data={'title': 'Thread', 'objective': 'Work', 'workstream_id': 'two'}), mutation_id='once'
        )


def test_goal_purge_preserves_other_domain_receipts(domain_backend):
    h = domain_backend
    sid = h.space('purge-isolation')
    folder = h.folders(sid).create(FolderCreate(name='Retained'), mutation_id='folder-once')
    h.goals(sid).create(GoalCreate(data={'title': 'Purge me'}), mutation_id='goal-once')
    h.goals(sid).purge(sid)
    assert h.folders(sid).create(FolderCreate(name='Retained'), mutation_id='folder-once').id == folder.id


@pytest.mark.parametrize('domain', ['goals', 'workstreams'])
def test_goal_and_workstream_creates_roll_back_with_uow(domain_backend, domain):
    h = domain_backend
    sid = h.space('rollback-' + domain)

    def abort(tx):
        if domain == 'goals':
            tx.goals.create(GoalCreate(data={'id': 'aborted', 'title': 'Abort'}))
        else:
            tx.workstreams.create(
                WorkstreamCreate(data={'workstream_id': 'aborted', 'title': 'Abort', 'objective': 'Abort'})
            )
        raise RuntimeError('abort domain write')

    with pytest.raises(RuntimeError, match='abort domain write'):
        h.store(sid).run(abort)
    assert h.read(sid, domain, 'aborted') is None


def test_atomic_import_retains_the_existing_request_limit(domain_backend):
    h = domain_backend
    sid = h.space('import-limit')
    request = {'links': [{'task_id': f'missing-task-{i}', 'goal_id': 'missing-goal'} for i in range(201)]}
    report = h.store(sid).run(
        lambda tx: tx.workstreams.import_task_goal_links(
            request, idempotency_key='bounded-import', account_generation=0
        )
    )
    assert report['failed'] == 201 and report['imported'] == report['unchanged'] == 0


@pytest.mark.parametrize('abort_body', [False, True])
def test_fence_cleanup_failure_finishes_all_and_resets_uow(domain_backend, abort_body):
    h = domain_backend
    sid = h.space('cleanup-error')
    events = []

    class Fence:
        def __init__(self, fail):
            self.fail = fail

        def before_commit(self):
            pass

        def after_commit(self, committed):
            events.append(committed)
            if self.fail:
                raise RuntimeError('cleanup failed')

    def body(tx):
        tx.register_commit_fence(Fence(True))
        tx.register_commit_fence(Fence(False))
        if abort_body:
            raise ValueError('abort body')
        return tx.action_items.create(ActionItemDraft(data={'description': 'Synthetic'}), document_id='task')

    with pytest.raises(RuntimeError, match='cleanup failed'):
        h.store(sid).run(body)
    assert events == [not abort_body, not abort_body]
    assert (h.action_items(sid).get('task') is not None) is (not abort_body)
    assert h.store(sid).run(lambda tx: tx.action_items.read_control()) == {}


def test_legacy_workflow_ids_and_retirement_use_document_keys(domain_backend):
    h = domain_backend
    sid = h.space('legacy-workflow-ids')
    for tid in ('active', 'retire', 'replace'):
        h.seed(
            sid,
            'action_items',
            tid,
            {
                'description': tid,
                'conversation_id': 'conversation',
                'updated_at': NOW,
            },
        )
        assert 'id' not in h.read(sid, 'action_items', tid)
    tasks = h.action_items(sid)
    assert tasks.get('active').id == 'active'
    assert [r.id for r in tasks.get_by_ids(['retire', 'active'])] == ['retire', 'active']
    assert {r.id for r in tasks.iter_all()} == {'active', 'retire', 'replace'}
    assert {r.id for r in tasks.list().items} == {'active', 'retire', 'replace'}
    assert {r.id for r in tasks.sync_page().items} == {'active', 'retire', 'replace'}
    assert (
        tasks.retire_for_conversation(
            'conversation',
            active_ids=['active'],
            replacements={'replace': 'active'},
        )
        == 2
    )
    assert not tasks.get('active').deleted
    assert tasks.get('retire').status == 'cancelled'
    assert tasks.get('replace').status == 'superseded'
    assert tasks.get('replace').superseded_by == 'active'
    assert [r.id for r in tasks.list().items] == ['active']
    assert {r.id for r in tasks.sync_page().items} == {'active', 'retire', 'replace'}
    assert 'id' not in h.read(sid, 'action_items', 'retire')

    h.seed(sid, 'goals', 'goal-key', {'title': 'Legacy goal', 'is_active': True})
    goals = h.goals(sid)
    assert goals.get('goal-key').id == 'goal-key'
    assert goals.get_user_goal().id == 'goal-key'
    assert goals.get_user_goals()[0].id == 'goal-key'
    assert goals.get_all()[0].id == 'goal-key'
    assert goals.update('goal-key', GoalUpdate(data={'title': 'Changed'})).id == 'goal-key'
    assert goals.focus('goal-key', idempotency_key='focus', account_generation=0).id == 'goal-key'
    assert goals.unfocus('goal-key', idempotency_key='unfocus', account_generation=0).id == 'goal-key'
    assert 'id' not in h.read(sid, 'goals', 'goal-key')

    h.seed(
        sid,
        'workstreams',
        'ws-key',
        {
            'title': 'Legacy workstream',
            'workstream_id': 'ws-key',
            'objective': 'Finish synthetic work',
            'created_at': NOW,
            'status': 'open',
            'goal_id': 'goal-key',
            'updated_at': NOW,
        },
    )
    streams = h.workstreams(sid)
    assert streams.get('ws-key').id == 'ws-key'
    assert streams.list_open()[0].workstream_id == 'ws-key'
    assert streams.list_for_goal('goal-key')[0].workstream_id == 'ws-key'
    assert (
        streams.update(
            'ws-key',
            WorkstreamUpdate(data={'title': 'Changed'}),
            idempotency_key='update',
            account_generation=0,
        ).workstream_id
        == 'ws-key'
    )
    assert 'id' not in h.read(sid, 'workstreams', 'ws-key')


def test_legacy_goal_focus_replacement_uses_document_keys(domain_backend):
    h = domain_backend
    sid = h.space('legacy-focus')
    for gid, status in [('focused-key', 'focused'), ('replacement-key', 'background')]:
        h.seed(
            sid,
            'goals',
            gid,
            {
                'title': gid,
                'desired_outcome': 'Finish',
                'is_active': True,
                'status': status,
                'focus_rank': 0 if status == 'focused' else None,
            },
        )
    repo = h.goals(sid)
    assert (
        repo.focus(
            'replacement-key',
            idempotency_key='replace',
            account_generation=0,
            replacement_goal_id='focused-key',
            focus_cap=1,
        ).id
        == 'replacement-key'
    )
    assert repo.get('focused-key').status == 'background'
    assert repo.get('replacement-key').status == 'focused'


def test_retirement_ignores_redundant_payload_id(domain_backend):
    h = domain_backend
    sid = h.space('retire-payload-id')
    h.seed(
        sid,
        'action_items',
        'keep-key',
        {
            'id': 'wrong-keep',
            'description': 'Keep',
            'conversation_id': 'c',
        },
    )
    h.seed(
        sid,
        'action_items',
        'retire-key',
        {
            'id': 'keep-key',
            'description': 'Retire',
            'conversation_id': 'c',
        },
    )
    repo = h.action_items(sid)
    assert repo.retire_for_conversation('c', active_ids=['keep-key'], replacements={'retire-key': 'keep-key'}) == 1
    assert not repo.get('keep-key').deleted
    assert repo.get('retire-key').superseded_by == 'keep-key'
