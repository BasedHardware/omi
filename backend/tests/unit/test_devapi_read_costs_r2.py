"""Count physical reads through real compatibility helpers; preserve legacy rows."""

from copy import deepcopy, copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import FailedPrecondition

from database import action_item_completion_backfill as backfill
from database import action_items
from models.memories import MemoryDB
from tests.unit.test_bounded_firestore_list_reads import _FakeDB, _FakeDoc, _FakeQuery, _item
from tests.unit.test_external_list_nested_budget import Store, budget
from utils.memory.developer_memory_list import read_developer_memories
from utils.memory.memory_service import MemoryService
from utils.memory import read_resilience


class BackfillQuery:
    def __init__(self, database):
        self.database, self.n, self.after = database, 100000, None

    def select(self, fields):
        return self

    def order_by(self, field):
        assert field == '__name__'
        return self

    def document(self, key):
        return SimpleNamespace(id=key)

    def start_after(self, cursor):
        query = copy(self)
        query.after = cursor['__name__'].id
        return query

    def limit(self, n):
        query = copy(self)
        query.n = n
        return query

    def stream(self):
        docs = sorted(self.database.docs, key=lambda doc: doc.id)
        return iter([doc for doc in docs if self.after is None or doc.id > self.after][: self.n])


class BackfillDB(_FakeDB):
    def __init__(self, rows):
        self.rows = deepcopy(rows)
        self.conflict = None
        self.docs = []
        for key, value in self.rows.items():
            doc = _FakeDoc({'id': key, **value})
            doc.update_time = 7

            def update(patch, *, option, row=value, key=key):
                assert option == 7
                if key == self.conflict:
                    raise FailedPrecondition('changed concurrently')
                row.update(patch)
                next(doc for doc in self.docs if doc.id == key).data.update(patch)

            doc.reference = SimpleNamespace(update=update)
            self.docs.append(doc)
        super().__init__(self.docs)

    def collection(self, name):
        assert name == 'users'
        return SimpleNamespace(document=lambda uid: SimpleNamespace(collection=lambda name: BackfillQuery(self)))

    def write_option(self, *, last_update_time):
        return last_update_time


def test_backfill_preserves_default_legacy_rows_and_removes_800_doc_scan(monkeypatch):
    rows = {f'done-{i:04}': _item(f'done-{i:04}', completed=True) for i in range(900)}
    rows['legacy-missing'] = _item('legacy-missing')
    rows['legacy-missing'].pop('completed')
    rows['legacy-null'] = {**_item('legacy-null'), 'completed': None}
    # Put the legacy rows inside the released 800-document harvest window.
    rows = {'legacy-missing': rows.pop('legacy-missing'), 'legacy-null': rows.pop('legacy-null'), **rows}
    database = BackfillDB(rows)
    monkeypatch.setattr(action_items, 'db', _FakeDB(database.docs))
    observed = []
    monkeypatch.setattr(action_items, 'record_firestore_read', lambda *args: observed.append(args[-1]))
    monkeypatch.setattr(backfill, 'bump_action_items_list_version', Mock())
    before = action_items.get_action_items('owner', limit=100)
    old_reads = observed[-1]
    # Feed the full fixture as one operator page; production pages are <=400.
    # Three invocations are independent bounded pages, with their query fixture
    # selecting just the page a Firestore __name__ cursor would return.
    for start in range(0, len(database.docs), 400):
        page_db = BackfillDB({doc.id: database.rows[doc.id] for doc in database.docs[start : start + 400]})
        outcome = backfill.backfill_completion_page('owner', apply=True, firestore_client=page_db)
        for doc in page_db.docs:
            target = next(item for item in database.docs if item.id == doc.id)
            target.data.update(doc.data)
        assert outcome['conflicts'] == 0
    after = action_items.get_action_items('owner', limit=100)
    assert after == before
    assert {'legacy-missing', 'legacy-null'} <= {row['id'] for row in after}
    assert old_reads == 932  # 800 legacy candidates + 130 completed + two count reads.
    assert observed[-1] == 134  # two active + 130 completed + the same two cheap counts.
    print(f'action default page cold reads: {old_reads} -> {observed[-1]} after bounded backfill')


def test_backfill_dry_run_and_concurrent_edit_preserved(monkeypatch):
    db = BackfillDB({'missing': {}, 'null-completed-status': {'completed': None, 'status': 'completed'}})
    bump = Mock()
    monkeypatch.setattr(backfill, 'bump_action_items_list_version', bump)
    result = backfill.backfill_completion_page('owner', firestore_client=db)
    assert (result['legacy'], result['updated']) == (2, 0)
    assert 'completed' not in db.rows['missing']
    db.conflict = 'missing'
    result = backfill.backfill_completion_page('owner', apply=True, firestore_client=db)
    assert (result['updated'], result['conflicts']) == (1, 1)
    assert 'completed' not in db.rows['missing']
    assert db.rows['null-completed-status']['completed'] is True
    bump.assert_called_once_with('owner')


@pytest.mark.parametrize('late_legacy', [None, 'missing', 'null'])
def test_late_legacy_restore_is_never_hidden_by_migration_claim(monkeypatch, late_legacy):
    docs = [_FakeDoc(_item('done', completed=True))]
    if late_legacy:
        row = _item('restored')
        row.pop('completed')
        if late_legacy == 'null':
            row['completed'] = None
        docs.insert(0, _FakeDoc(row))
    monkeypatch.setattr(action_items, 'db', _FakeDB(docs))
    page = action_items.get_action_items('owner', limit=100)
    assert ('restored' in {row['id'] for row in page}) is bool(late_legacy)


def test_dense_category_avoids_500_row_dual_window_and_status_checks(monkeypatch):
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    rows = {
        f'users/owner/memories/h-{i:04}': {
            'id': f'h-{i:04}',
            'content': f'Legacy durable fact {i}',
            'category': 'system',
            'created_at': now - timedelta(seconds=i),
            'data_protection_level': 'standard',
            'reviewed': False,
            **({'updated_at': now - timedelta(seconds=i)} if i % 2 else {}),
        }
        for i in range(500)
    }
    ticks = iter(range(10000))
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance(clock=lambda: next(ticks)))

    def run(value):
        monkeypatch.setenv('OMI_DEV_MEMORY_ADAPTIVE_CATEGORY_SCAN_ENABLED', value)
        store = Store(rows)
        result = read_developer_memories(
            MemoryService(db_client=store),
            'owner',
            limit=26,
            offset=0,
            allowed={'system'},
            budget=budget(10000),
            response_model=MemoryDB,
            logger=Mock(),
        )
        return result, store.physical

    old, old_reads = run('false')
    new, new_reads = run('true')
    assert [row.id for row in new] == [row.id for row in old] == [f'h-{i:04}' for i in range(26)]
    assert old_reads == 2250 and new_reads == 130
    print(f'dense category real memory reads: {old_reads} -> {new_reads}')


def test_sparse_category_multiple_windows_spend_one_operation_admission(monkeypatch):
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    rows = {
        f'users/owner/memories/h-{i:04}': {
            'id': f'h-{i:04}',
            'content': f'Fact {i}',
            'category': 'interesting' if i < 80 else 'system',
            'created_at': now - timedelta(seconds=i),
            'data_protection_level': 'standard',
        }
        for i in range(200)
    }
    ticks = iter(range(10000))
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance(clock=lambda: next(ticks)))
    allowance = budget(20000)
    result = read_developer_memories(
        MemoryService(db_client=Store(rows)),
        'owner',
        limit=26,
        offset=5,
        allowed={'system'},
        budget=allowance,
        response_model=MemoryDB,
        logger=Mock(),
    )
    assert [row.id for row in result] == [f'h-{i:04}' for i in range(85, 111)]
    assert allowance._memory_read_attempts.used == 1
    assert not allowance.truncated
