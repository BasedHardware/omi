"""Physical read and parity guards for Developer mixed canonical/legacy lists."""

import logging
from datetime import datetime, timedelta, timezone

import pytest
from google.api_core.exceptions import ServiceUnavailable

from database import memories
from models.memories import MemoryDB
from models.product_memory import MemoryItem
from tests.unit.test_external_list_nested_budget import Store, budget
from utils.memory import read_resilience
from utils.memory.developer_memory_list import read_developer_memories
from utils.memory.memory_service import MemoryService


@pytest.fixture(autouse=True)
def fresh_admission(monkeypatch):
    ticks = iter(range(10000))
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance(clock=lambda: next(ticks)))


def legacy_rows(count=360):
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    return {
        f'users/owner/memories/h-{i:04}': {
            'id': f'h-{i:04}',
            'content': f'Legacy durable fact {i}',
            'category': 'work' if i % 19 == 0 else 'interesting',
            # Ties plus updated/created disagreement exercise both streams.
            'created_at': now - timedelta(seconds=i // 2),
            **({'updated_at': now - timedelta(seconds=i // 3)} if i % 3 else {}),
            **({'user_review': False} if i % 23 == 1 else {}),
            **({'invalid_at': now} if i % 29 == 2 else {}),
            'data_protection_level': 'standard',
            'reviewed': False,
        }
        for i in range(count)
    }


def canonical_row(memory_id, now):
    return MemoryItem(
        memory_id=memory_id,
        ledger_commit_id='test',
        ledger_sequence=1,
        uid='owner',
        version=1,
        tier='long_term',
        status='active',
        processing_state='processed',
        source_state='active',
        content='Canonical durable fact',
        sensitivity_labels=[],
        visibility='private',
        user_asserted=True,
        captured_at=now,
        updated_at=now,
    ).model_dump(mode='python')


def read(service, monkeypatch, *, enabled, limit=26, offset=0, allowed=None, documents=25000):
    if enabled:
        monkeypatch.delenv('OMI_DEV_MEMORY_REUSE_READ_WINDOWS_ENABLED', raising=False)
    else:
        monkeypatch.setenv('OMI_DEV_MEMORY_REUSE_READ_WINDOWS_ENABLED', 'false')
    allowance = budget(documents)
    page = read_developer_memories(
        service,
        'owner',
        limit=limit,
        offset=offset,
        allowed=allowed,
        budget=allowance,
        response_model=MemoryDB,
        logger=logging.getLogger(__name__),
    )
    return [row.model_dump(mode='json') for row in page], allowance


@pytest.mark.parametrize('allowed,offset', [(None, 0), (None, 180), ({'system'}, 0), ({'system'}, 6)])
def test_mixed_pages_keep_rows_and_order_and_reduce_repeated_reads(monkeypatch, allowed, offset):
    rows = legacy_rows()
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    rows['users/owner/memory_items/canonical'] = canonical_row('canonical', now)
    for i in range(25):
        memory_id = f'h-{i:04}'
        rows[f'users/owner/memory_items/{memory_id}'] = canonical_row(memory_id, now - timedelta(seconds=i))
    for i in range(25, 45):
        rows[f'users/owner/memory_historical_overrides/h-{i:04}'] = {'status': 'tombstoned'}
    baseline_store = Store(rows)
    expected, old_budget = read(
        MemoryService(db_client=baseline_store),
        monkeypatch,
        enabled=False,
        offset=offset,
        allowed=allowed,
        limit=8 if allowed else 26,
    )
    store = Store(rows)
    actual, new_budget = read(
        MemoryService(db_client=store),
        monkeypatch,
        enabled=True,
        offset=offset,
        allowed=allowed,
        limit=8 if allowed else 26,
    )
    assert actual == expected and actual
    assert any(row['id'].startswith('h-') for row in actual)
    assert not new_budget.truncated and not old_budget.truncated
    assert store.physical == new_budget.docs_scanned <= baseline_store.physical == old_budget.docs_scanned
    if allowed:
        assert store.physical < baseline_store.physical * 0.7
    print(f'category={allowed} offset={offset}: old={baseline_store.physical} new={store.physical}')


def test_suppressed_history_expansion_seeks_once_and_keeps_legacy_tail(monkeypatch):
    rows = legacy_rows(600)
    for i in range(550):
        rows[f'users/owner/memory_historical_overrides/h-{i:04}'] = {'status': 'tombstoned'}
    old = Store(rows)
    old_service = MemoryService(db_client=old)
    monkeypatch.setattr(old_service._canonical, 'read', lambda *a, **k: [])
    expected, _ = read(old_service, monkeypatch, enabled=False)
    store = Store(rows)
    service = MemoryService(db_client=store)
    monkeypatch.setattr(service._canonical, 'read', lambda *a, **k: [])
    actual, allowance = read(service, monkeypatch, enabled=True)
    assert actual == expected and len(actual) == 26
    # Firestore omits missing updated_at, includes all created_at rows. Each
    # stream is consumed at most once even through repeated adapter expansions.
    query_docs = sum(window[3] for window in store.windows)
    assert query_docs == 600 + 400
    assert store.physical == allowance.docs_scanned < old.physical
    print(f'suppressed legacy: old={old.physical} new={store.physical}, index={query_docs}')


def test_read_state_does_not_survive_requests_or_share_status_results(monkeypatch):
    store = Store(legacy_rows(60))
    service = MemoryService(db_client=store)
    monkeypatch.setattr(service._canonical, 'read', lambda *a, **k: [])
    first, _ = read(service, monkeypatch, enabled=True, limit=1)
    victim = first[0]['id']
    store.rows[f'users/owner/memory_historical_overrides/{victim}'] = {'status': 'tombstoned'}
    second, _ = read(service, monkeypatch, enabled=True, limit=1)
    assert second and second[0]['id'] != victim
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    store.rows['users/owner/memories/new'] = {
        'id': 'new',
        'content': 'New legacy fact',
        'category': 'work',
        'created_at': now,
        'data_protection_level': 'standard',
    }
    third, _ = read(service, monkeypatch, enabled=True, limit=1)
    assert third[0]['id'] == 'new'


def test_index_state_replays_exact_smaller_prefix_and_rejects_other_scope():
    store = Store(legacy_rows(60))
    state = memories.MemoryListIndexState('owner')
    memories.list_memory_updated_or_created_index('owner', 30, firestore_client=store, index_state=state)
    before = store.physical
    actual = memories.list_memory_updated_or_created_index('owner', 4, firestore_client=store, index_state=state)
    assert store.physical == before
    expected = memories.list_memory_updated_or_created_index('owner', 4, firestore_client=Store(store.rows))
    assert actual == expected
    with pytest.raises(ValueError, match='cannot cross'):
        memories.list_memory_updated_or_created_index('other', 4, firestore_client=store, index_state=state)
    with pytest.raises(ValueError, match='cannot cross'):
        memories.list_memory_updated_or_created_index('owner', 4, firestore_client=Store(store.rows), index_state=state)


def test_budget_exhaustion_preserves_truncation_without_4xx(monkeypatch):
    store = Store(legacy_rows())
    service = MemoryService(db_client=store)
    monkeypatch.setattr(service._canonical, 'read', lambda *a, **k: [])
    page, allowance = read(service, monkeypatch, enabled=True, allowed={'system'}, documents=400)
    assert allowance.truncated and store.physical == allowance.docs_scanned
    assert all(row['category'] == 'system' for row in page)


def test_provider_retry_drops_retained_prefix_and_sees_new_history(monkeypatch):
    class RetryStore(Store):
        failed = False

        def get_all(self, refs, **kwargs):
            if not self.failed:
                self.failed = True
                # The first attempt has already read metadata. A fresh attempt
                # must not trust those cursors or miss an intervening new row.
                assert self.windows
                self.rows['users/owner/memories/arrived'] = {
                    'id': 'arrived',
                    'content': 'New fact during provider recovery',
                    'category': 'interesting',
                    'created_at': datetime(2026, 10, 21, tzinfo=timezone.utc),
                    'data_protection_level': 'standard',
                }
                raise ServiceUnavailable('synthetic transient status read')
            return super().get_all(refs, **kwargs)

    store = RetryStore(legacy_rows(60))
    service = MemoryService(db_client=store)
    monkeypatch.setattr(service._canonical, 'read', lambda *a, **k: [])
    page, allowance = read(service, monkeypatch, enabled=True, limit=1)
    assert store.failed and page[0]['id'] == 'arrived'
    assert allowance.docs_scanned == store.physical and not allowance.truncated
