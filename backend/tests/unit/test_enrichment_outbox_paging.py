"""Unit tests pinning Firestore enrichment outbox cursor paging and pull refill invariants.

Pins the repair for https://github.com/BasedHardware/omi/issues/23558:
- 101 earlier live-leased rows cannot hide the next runnable row from one pull claim.
- 101 earlier privacy-fenced rows must retire without consuming the actionable claim budget.
- An explicit claim budget of 125 returns all 125 eligible due rows without silent cap at 100.

Failure-Class: FC-bounded-discovery-pinned-by-blocked-page
"""

from typing import Any
import pytest
from unittest.mock import Mock

from database.outbox import Claim, Outcome, OutboxKind
from database.outbox_firestore import FirestoreEnrichmentOutbox
from utils.enrichment import outbox as reprocess


class FakeSnapshot:
    def __init__(self, doc_id: str, data: dict[str, Any]):
        self.id = doc_id
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class FakeQuery:
    def __init__(self, docs: list[FakeSnapshot], page_size: int = 100, cursor: FakeSnapshot | None = None):
        self.docs = docs
        self.page_size = page_size
        self.cursor = cursor

    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n: int):
        return FakeQuery(self.docs, page_size=n, cursor=self.cursor)

    def start_after(self, snapshot: FakeSnapshot):
        return FakeQuery(self.docs, page_size=self.page_size, cursor=snapshot)

    def stream(self):
        start_idx = 0
        if self.cursor is not None:
            for idx, doc in enumerate(self.docs):
                if doc.id == self.cursor.id:
                    start_idx = idx + 1
                    break
        return iter(self.docs[start_idx : start_idx + self.page_size])


class FakeCollection:
    def __init__(self, docs: list[FakeSnapshot]):
        self.docs = docs

    def where(self, *args, **kwargs):
        return FakeQuery(self.docs)


class FakeFirestoreClient:
    def __init__(self, docs: list[FakeSnapshot]):
        self.collection_obj = FakeCollection(docs)

    def collection(self, name: str):
        return self.collection_obj


def test_due_rows_pages_past_101_leased_rows_to_find_runnable_work():
    now = 1000.0
    docs = []
    # 101 live-leased rows (lease_until > now)
    for i in range(101):
        docs.append(
            FakeSnapshot(
                f'leased-{i:03}',
                {
                    'due_at': now - 200 + i,
                    'lease_until': now + 120.0,
                    'dormant': False,
                    'task_token': f'token-leased-{i}',
                },
            )
        )
    # 1 runnable row
    docs.append(
        FakeSnapshot(
            'runnable-001',
            {
                'due_at': now - 50,
                'lease_until': 0.0,
                'dormant': False,
                'task_token': 'token-runnable-1',
            },
        )
    )

    client = FakeFirestoreClient(docs)
    results = reprocess.due_rows(now=now, limit=1, client=client)
    assert len(results) == 1
    assert results[0][0] == 'runnable-001'
    assert results[0][1]['task_token'] == 'token-runnable-1'


def test_due_rows_returns_125_eligible_rows_without_capping_at_100():
    now = 1000.0
    docs = []
    for i in range(125):
        docs.append(
            FakeSnapshot(
                f'due-{i:03}',
                {
                    'due_at': now - 200 + i,
                    'lease_until': 0.0,
                    'dormant': False,
                    'task_token': f'token-{i}',
                },
            )
        )
    client = FakeFirestoreClient(docs)
    results = reprocess.due_rows(now=now, limit=125, client=client)
    assert len(results) == 125
    doc_ids = [r[0] for r in results]
    assert doc_ids == [f'due-{i:03}' for i in range(125)]


def test_claim_refills_after_privacy_fenced_candidates_retire():
    now = 1000.0
    retired_rows = []
    store: dict[str, dict[str, Any]] = {}

    for i in range(101):
        row_id = f'deleted-{i:03}'
        store[row_id] = {
            'task_token': f'tok-{i}',
            'dormant': False,
            'lease_until': 0.0,
            'uid': 'user-1',
            'conversation_id': f'c-{i}',
        }

    runnable_id = 'runnable-001'
    store[runnable_id] = {
        'task_token': 'tok-runnable',
        'dormant': False,
        'lease_until': 0.0,
        'uid': 'user-1',
        'conversation_id': 'c-runnable',
    }

    class StubOutbox(FirestoreEnrichmentOutbox):
        def __init__(self):
            self._bound_client = None
            self._privacy_blocked = lambda uid, payload: payload['conversation_id'].startswith('c-deleted') or 'c-' in payload['conversation_id'] and payload['conversation_id'] != 'c-runnable'

        def claim_key(self, row_id: str, wake_token: str, lease_seconds: float, *, now: float):
            if row_id.startswith('deleted-'):
                retired_rows.append(row_id)
                store.pop(row_id, None)
                return Outcome.DISCARDED
            elif row_id == runnable_id:
                store[row_id]['lease_until'] = now + lease_seconds
                return Claim(
                    kind=OutboxKind.ENRICHMENT,
                    row_id=row_id,
                    lease_token='lease-1',
                    wake_token=wake_token,
                    attempt=1,
                    lease_until=now + lease_seconds,
                    owner_id='user-1',
                    payload={'conversation_id': 'c-runnable'},
                    policy_id=None,
                )
            return Outcome.STALE

    stub_outbox = StubOutbox()

    def fake_due_rows(*, now: float, limit: int, client: Any = None):
        res = []
        for k, v in list(store.items()):
            if v.get('lease_until', 0) <= now:
                res.append((k, v))
                if len(res) >= limit:
                    break
        return res

    import database.outbox_firestore as outbox_fs_mod
    original_outbox_func = outbox_fs_mod._outbox
    mock_outbox_module = Mock()
    mock_outbox_module.due_rows = fake_due_rows
    outbox_fs_mod._outbox = lambda: mock_outbox_module

    try:
        claims = stub_outbox.claim(1, 120.0, now=now)
        assert len(claims) == 1
        assert claims[0].row_id == runnable_id
        assert len(retired_rows) == 101
    finally:
        outbox_fs_mod._outbox = original_outbox_func
