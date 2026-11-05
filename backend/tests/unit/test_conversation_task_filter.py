"""Production filter/presence behavior with bounded, owner-scoped I/O seams."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from database import conversation_task_links as links
from models.conversation_tasks import ConversationTaskPresenceRequest, TaskConversationPageRequest
from utils.conversations.task_filter import TaskFilterUnavailable, task_conversation_page
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted


@pytest.fixture(autouse=True)
def secret_and_uncached(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-task-filter-test-key')
    monkeypatch.setattr(links, 'get_action_items_list_version', lambda uid: None)


def budget():
    return ListReadBudget(deadline_monotonic=time.monotonic() + 20, max_documents=10000)


def row(index, **extra):
    return {
        'id': str(index),
        'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
        'status': 'completed',
        'discarded': False,
        **extra,
    }


def source(rows, linked):
    async def browse(after, scope):
        start = int(after) + 1 if after is not None else 0
        end = min(start + 50, len(rows))
        return [(str(i), rows[i]) for i in range(start, end)], end < len(rows)

    async def presence(ids):
        return {cid: cid in linked for cid in ids}

    async def search(page):
        start = (page - 1) * 50
        return {'items': rows[start : start + 50], 'total_pages': (len(rows) + 49) // 50}

    return dict(browse_page=browse, presence=presence, search_page=search)


@pytest.mark.asyncio
@pytest.mark.parametrize('query', ['', 'invoice'])
async def test_filter_paginates_entire_server_set_without_losing_unconsumed_hits(query):
    rows = [row(i) for i in range(153)]
    expected = ['54', '55', '56', '104', '152']
    filters = TaskConversationPageRequest(query=query, limit=2)
    collected = []
    cursors = set()
    while True:
        page = await task_conversation_page('owner', filters, budget=budget(), **source(rows, set(expected)))
        collected.extend(item['id'] for item in page['items'])
        if page['next_cursor'] is None:
            break
        assert page['next_cursor'] not in cursors
        cursors.add(page['next_cursor'])
        filters = filters.model_copy(update={'cursor': page['next_cursor']})
    assert collected == expected


@pytest.mark.asyncio
async def test_locks_deletion_and_filter_intersection_are_enforced_after_hydration():
    rows = [
        row(0, is_locked=True),
        row(1, deleted=True),
        row(2, folder_id='other', starred=True),
        row(3, folder_id='wanted', starred=False),
        row(4, folder_id='wanted', starred=True),
        row(5, folder_id='wanted', starred=True, discarded=True),
    ]
    page = await task_conversation_page(
        'owner',
        TaskConversationPageRequest(folder_id='wanted', starred=True),
        budget=budget(),
        **source(rows, {str(i) for i in range(6)}),
    )
    assert [item['id'] for item in page['items']] == ['4']
    assert page['next_cursor'] is None


@pytest.mark.asyncio
async def test_empty_intermediate_page_retains_progress_instead_of_claiming_no_matches():
    rows = [row(i) for i in range(101)]
    callbacks = source(rows, {'100'})
    normal = callbacks['browse_page']

    async def bounded(after, scope):
        if after is not None:
            raise ListReadBudgetExhausted('documents')
        return await normal(after, scope)

    page = await task_conversation_page(
        'owner', TaskConversationPageRequest(), budget=budget(), **{**callbacks, 'browse_page': bounded}
    )
    assert page['items'] == [] and page['partial'] is True and page['next_cursor']
    resumed = await task_conversation_page(
        'owner', TaskConversationPageRequest(cursor=page['next_cursor']), budget=budget(), **callbacks
    )
    assert [item['id'] for item in resumed['items']] == ['100']


@pytest.mark.asyncio
@pytest.mark.parametrize('query', ['', 'query'])
async def test_no_raw_progress_is_retryable_failure_not_empty_success(query):
    async def unavailable(*args):
        raise ListReadBudgetExhausted('documents')

    with pytest.raises(TaskFilterUnavailable):
        await task_conversation_page(
            'owner',
            TaskConversationPageRequest(query=query),
            budget=budget(),
            browse_page=unavailable,
            search_page=unavailable,
            presence=unavailable,
        )


@pytest.mark.asyncio
async def test_cursor_is_signed_owner_and_filter_bound():
    callbacks = source([row(i) for i in range(5)], {'0', '1', '2'})
    first = await task_conversation_page('owner', TaskConversationPageRequest(limit=1), budget=budget(), **callbacks)
    cursor = first['next_cursor']
    for uid, request in [
        ('other', TaskConversationPageRequest(limit=1, cursor=cursor)),
        ('owner', TaskConversationPageRequest(limit=1, folder_id='changed', cursor=cursor)),
        ('owner', TaskConversationPageRequest(limit=1, cursor=cursor[:-3] + 'AAA')),
    ]:
        with pytest.raises(ValueError):
            await task_conversation_page(uid, request, budget=budget(), **callbacks)


@pytest.mark.asyncio
async def test_expired_cursor_requires_refresh(monkeypatch):
    callbacks = source([row(i) for i in range(3)], {'0', '1', '2'})
    request = TaskConversationPageRequest(limit=1)
    page = await task_conversation_page('owner', request, budget=budget(), **callbacks)
    now = time.time()
    monkeypatch.setattr(time, 'time', lambda: now + 3601)
    with pytest.raises(ValueError):
        await task_conversation_page(
            'owner', request.model_copy(update={'cursor': page['next_cursor']}), budget=budget(), **callbacks
        )


class Snapshot:
    def __init__(self, cid, data, exists=True):
        self.id, self.data, self.exists = cid, data, exists

    def to_dict(self):
        return self.data.copy()


class Query:
    def __init__(self, client, path=(), filters=(), fields=None, count=None, after=None):
        self.client, self.path, self.filters, self.fields, self.count, self.after = (
            client,
            path,
            filters,
            fields,
            count,
            after,
        )

    def collection(self, name):
        return Query(self.client, (*self.path, name))

    def document(self, name):
        return Query(self.client, (*self.path, name))

    def where(self, *, filter):
        assert filter.op_string == 'in'
        return Query(self.client, self.path, (*self.filters, filter), self.fields, self.count, self.after)

    def select(self, fields):
        return Query(self.client, self.path, self.filters, fields, self.count, self.after)

    def order_by(self, name):
        assert name == '__name__'
        return self

    def limit(self, count):
        assert 0 < count <= 100
        return Query(self.client, self.path, self.filters, self.fields, count, self.after)

    def start_after(self, snapshot):
        return Query(self.client, self.path, self.filters, self.fields, self.count, snapshot.id)

    def stream(self, **kwargs):
        assert self.count and kwargs['timeout'] > 0
        assert self.path[0] == 'users' and self.path[-1] == 'action_items'
        assert set(self.fields) == {'conversation_id', 'deleted'}
        self.client.reads.append((self.path, self.filters))
        rows = self.client.tasks.get(self.path[1], {})
        matches = [
            (cid, data)
            for cid, data in sorted(rows.items())
            if (self.after is None or cid > self.after) and all(data.get(f.field_path) in f.value for f in self.filters)
        ]
        return iter(
            [Snapshot(cid, {k: v for k, v in data.items() if k in self.fields}) for cid, data in matches[: self.count]]
        )


class Client:
    def __init__(self, tasks, parents):
        self.tasks, self.parents, self.reads = tasks, parents, []

    def collection(self, name):
        return Query(self, (name,))

    def get_all(self, refs, **kwargs):
        assert set(kwargs['field_paths']) == {'is_locked', 'deleted'}
        for ref in reversed(refs):
            owner, cid = ref.path[1], ref.path[-1]
            data = self.parents.get(owner, {}).get(cid)
            yield Snapshot(cid, data or {}, data is not None)


def test_presence_uses_current_canonical_links_including_completed_and_manual_tasks():
    tasks = {
        'owner': {
            'a': {'conversation_id': 'live', 'completed': True},
            'b': {'conversation_id': 'manual', 'source': 'manual'},
            'c': {'conversation_id': 'deleted', 'deleted': True},
            'd': {'conversation_id': 'locked'},
            'e': {'conversation_id': 'gone'},
        },
        'other': {'foreign': {'conversation_id': 'no-link'}},
    }
    parents = {'owner': {cid: {} for cid in ['live', 'manual', 'deleted', 'locked', 'gone', 'no-link']}}
    parents['owner']['locked'] = {'is_locked': True}
    parents['owner']['gone'] = {'deleted': True}
    client = Client(tasks, parents)
    ids = ['live', 'manual', 'deleted', 'locked', 'gone', 'no-link', 'unknown']
    result = links.visible_task_presence('owner', ids, budget=budget(), firestore_client=client)
    assert result == {cid: cid in ('live', 'manual') for cid in ids}
    client.tasks['owner'].pop('a')
    assert links.visible_task_presence('owner', ['live'], budget=budget(), firestore_client=client) == {'live': False}


def test_presence_walks_past_deleted_rows_instead_of_treating_a_prefix_as_complete():
    tasks = {f'{i:04}': {'conversation_id': 'c', 'deleted': True} for i in range(205)}
    tasks['9999'] = {'conversation_id': 'c'}
    client = Client({'owner': tasks}, {'owner': {'c': {}}})
    assert links.visible_task_presence('owner', ['c'], budget=budget(), firestore_client=client) == {'c': True}
    assert len(client.reads) == 3


def test_invalid_presence_ids_and_reversed_dates_are_rejected():
    with pytest.raises(ValueError):
        ConversationTaskPresenceRequest(conversation_ids=['../foreign'])
    with pytest.raises(ValueError):
        TaskConversationPageRequest(
            start_date=datetime.now(timezone.utc), end_date=datetime.now(timezone.utc) - timedelta(days=1)
        )
