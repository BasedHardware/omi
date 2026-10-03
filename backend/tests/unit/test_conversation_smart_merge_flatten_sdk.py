"""Flatten absorb under a real Firestore SDK transaction with mocked RPCs.

The mocked transport applies commits to the world's strict store and can inject
a real competing transaction (the production absorb or the production sync
assignment) plus ``Aborted`` before the first commit, so the SDK's own retry
path re-runs the callback against the changed rows — the fixture models RPC
ordering, never server-side contention resolution. No credentials or network.
All text is synthetic.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import Aborted
from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.types import BatchGetDocumentsResponse, CommitResponse, Document

from config import conversation_smart_merge as config
from database import conversations as conversations_db
from database import smart_merge as smart_merge_db
from tests.unit.test_conversation_smart_merge import UID, World
from tests.unit.fixtures.offline_firestore_sdk import OfflineFirestoreClient
from utils.sync.assignment import assign_in_transaction


@pytest.fixture
def sdk_world(monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'off')
    monkeypatch.delenv(config.SMART_MERGE_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.delenv(config.SMART_MERGE_AUDIT_ENV, raising=False)
    monkeypatch.delenv(config.SMART_MERGE_FLATTEN_ENV, raising=False)
    world = World(monkeypatch)
    client = OfflineFirestoreClient(project='synthetic-flatten-sdk-test')
    api = MagicMock()
    client._firestore_api_internal = api
    monkeypatch.setattr(smart_merge_db, 'get_firestore_client', lambda: client)
    committed, rollbacks = [], []
    state = SimpleNamespace(compete=None, aborted=False, abort_on=None)

    def _absorb_writes(writes):
        return any(
            write.update.name.endswith('/conversations/n') and 'deleted' in write.update.fields for write in writes
        )

    def begin(**kwargs):
        return SimpleNamespace(transaction=f'txn-{api.begin_transaction.call_count}'.encode())

    def batch_get(*, request, **kwargs):
        out = []
        for name in request['documents']:
            path = tuple(name.split('/documents/', 1)[1].split('/'))
            row = world.store.rows.get(path)
            out.append(
                BatchGetDocumentsResponse(missing=name)
                if row is None
                else BatchGetDocumentsResponse(found=Document(name=name, fields=_helpers.encode_dict(row)))
            )
        return iter(out)

    def commit(*, request, **kwargs):
        abort_on = state.abort_on or _absorb_writes
        if state.compete is not None and abort_on(request['writes']) and not state.aborted:
            state.aborted = True
            state.compete()
            raise Aborted('synthetic conflict before commit')
        committed.append(request)
        for write in request['writes']:
            path = tuple(write.update.name.split('/documents/', 1)[1].split('/'))
            data = _helpers.decode_dict(write.update.fields, client)
            if write.update_mask.field_paths:
                world.store.rows.setdefault(path, {}).update(data)
            else:
                world.store.rows[path] = data
        return CommitResponse(commit_time=datetime.now(timezone.utc))

    api.begin_transaction.side_effect = begin
    api.batch_get_documents.side_effect = batch_get
    api.commit.side_effect = commit
    api.rollback.side_effect = lambda *, request, **kw: rollbacks.append(request['transaction'])
    return SimpleNamespace(world=world, client=client, api=api, state=state, committed=committed, rollbacks=rollbacks)


def _setup_pair(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    for gid in ('g1', 'g2'):
        world.add(gid, 5, 5)
        world.raw(gid).update(
            {
                'deleted': True,
                'discarded': True,
                'sync_merged_into': 'n',
                'sync_content_revision': 3,
            }
        )
    world.raw('n')['sync_merged_from'] = ['g1', 'g2']
    world.raw('n')['sync_content_revision'] = 7
    world.raw('p')['sync_content_revision'] = 2


def _chunk(cid, start_min, minutes=2):
    from tests.unit.test_conversation_smart_merge_flatten import _sync_chunk

    return _sync_chunk(cid, start_min, minutes=minutes)


def _sdk_assign(test, incoming, *, target_id=None):
    """The production sync intake inside a real SDK transaction (mocked RPCs)."""
    client, world = test.client, test.world
    transaction = client.transaction()

    @firestore.transactional
    def attempt(txn):
        return assign_in_transaction(
            txn,
            client.collection('users').document(UID),
            incoming,
            candidate_id=None,
            target_id=target_id,
            decode=lambda raw: world.get(UID, raw['id']),
            encode=lambda row: conversations_db.encode_conversation_for_write(UID, row, 'enhanced'),
            invalidate=lambda payload: None,
        )

    return attempt(transaction)


def _path(cid):
    return ('users', UID, 'conversations', cid)


def _committed_writes(test):
    return [write for request in test.committed for write in request['writes']]


def _visible(world):
    return sorted(
        key[-1] for key, row in world.store.rows.items() if key[:3] == _path('x')[:3] and not row.get('deleted')
    )


def test_sync_commit_aborted_by_real_absorb_retries_into_survivor(sdk_world):
    """A sync commit racing a real smart absorb retries onto the survivor.

    The first sync attempt reads n as its live target; the real absorb then
    commits the n->p flatten (n and g1/g2 repointed) before the sync commit is
    Aborted. The SDK retry re-reads, follows the one-hop redirect, and appends
    to p — no write from the first attempt is ever committed.
    """
    test = sdk_world
    world = test.world
    _setup_pair(world)
    test.state.abort_on = lambda writes: any(
        write.update.name.endswith('/conversations/n') and 'deleted' not in write.update.fields for write in writes
    )
    test.state.compete = lambda: world.finish('n')
    start_ids = {seg['id'] for cid in ('p', 'n') for seg in world.transcript(cid)}

    result, created, _ = _sdk_assign(test, _chunk('wal-race', 26), target_id='n')

    assert test.state.aborted
    assert test.api.begin_transaction.call_count >= 2
    assert result['id'] == 'p' and not created
    assert _visible(world) == ['p']
    for cid in ('n', 'g1', 'g2'):
        assert world.raw(cid)['sync_merged_into'] == 'p'
    assert world.raw('n')['smart_merge']['role'] == 'donor'
    audits = [key for key in world.store.rows if key[:3] == ('users', UID, 'smart_merge_audit')]
    assert [key[-1] for key in audits] == ['n']
    ids = [segment['id'] for segment in world.transcript('p')]
    expected = start_ids | {'wal-race-seg'}
    assert set(ids) == expected
    assert len(ids) == len(expected)


def test_absorb_commit_aborted_by_real_sync_rejects_then_converges(sdk_world):
    """A real sync append landing mid-absorb fences the stale plan, then replay converges.

    The competing assignment is the production ``assign_in_transaction``: it
    appends a WAL chunk to n and bumps ``sync_content_revision`` before the
    absorb commit is Aborted. The retried attempt re-reads n at the new
    revision, rejects with ``flatten_content_changed``, and commits nothing; a
    fresh finish re-plans against the post-append state and merges once, so the
    survivor carries every segment id — including the racing chunk — exactly once.
    """
    test = sdk_world
    world = test.world
    _setup_pair(world)
    test.state.compete = lambda: _sdk_assign(test, _chunk('wal-race-2', 20), target_id='n')
    start_ids = {seg['id'] for cid in ('p', 'n') for seg in world.transcript(cid)}

    assert world.finish('n') is False
    assert test.state.aborted
    donor_writes = [w for w in _committed_writes(test) if w.update.name.endswith('/conversations/n')]
    assert not any('deleted' in w.update.fields for w in donor_writes)
    assert not world.raw('n').get('smart_merge')
    assert not world.raw('n').get('deleted')

    assert world.finish('n') is True
    assert _visible(world) == ['p']
    for cid in ('n', 'g1', 'g2'):
        assert world.raw(cid)['sync_merged_into'] == 'p'
    absorb_writes = [
        w
        for w in _committed_writes(test)
        if w.update.name.endswith('/conversations/n') and 'deleted' in w.update.fields
    ]
    assert len(absorb_writes) == 1
    audits = [key for key in world.store.rows if key[:3] == ('users', UID, 'smart_merge_audit')]
    assert [key[-1] for key in audits] == ['n']
    ids = [segment['id'] for segment in world.transcript('p')]
    expected = start_ids | {'wal-race-2-seg'}
    assert set(ids) == expected
    assert len(ids) == len(expected)
