"""Directory foundation conformance against a real throwaway Postgres database."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import threading

import pytest

from database.directory import store as directory_module
from database.jobstore.connection import dial
from database.jobstore.migrate import current_version, migrate
from testing.cells_fixtures import directory_dsn, make_directory

NOW = 2_000_000_000.0


@pytest.fixture(scope='module')
def harness():
    harness = make_directory()
    yield harness
    harness.close()


@pytest.fixture
def uid(harness, request):
    return harness.uid(request.node.name)


def test_concurrent_personal_creation(harness, uid):
    store = harness.store
    barrier = threading.Barrier(2)

    def create():
        barrier.wait(timeout=5)
        return store.get_or_create_personal_space(
            uid, cell='cell1', now=NOW, signup_platform='mobile', signup_os='ios', signup_platform_at=NOW - 10
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))
    assert results[0] == results[1]
    space = results[0]
    assert (space.space_id, space.cell, space.region, space.epoch) == (uid, 'cell1', None, 1)
    assert (space.signup_platform, space.signup_os, space.signup_platform_at) == ('mobile', 'ios', NOW - 10)
    assert store.get_or_create_personal_space(uid, cell='cell1', now=NOW + 1, signup_os='android') == space
    members = store.memberships_for_space(uid)
    assert len(members) == 1
    assert (members[0].uid, members[0].role, members[0].state) == (uid, 'owner', 'active')
    with store.pool.connection() as conn:
        assert conn.execute('SELECT count(*) FROM spaces WHERE space_id=%s', (uid,)).fetchone()[0] == 1


def test_routing_and_epoch(harness, uid):
    store = harness.store
    assert store.get_space(uid) is None
    with pytest.raises(LookupError):
        store.set_routing(uid, cell='cell2', now=NOW)
    store.get_or_create_personal_space(uid, cell='cell1', now=NOW)
    updated = store.set_routing(uid, cell='cell2', region='us-central1', bump_epoch=True, now=NOW + 1)
    assert (updated.cell, updated.region, updated.epoch, updated.updated_at) == ('cell2', 'us-central1', 2, NOW + 1)
    assert store.get_space(uid) == updated
    assert store.set_routing(uid, now=NOW + 2).epoch == 2


def test_membership_revoke_and_revive(harness, uid):
    store = harness.store
    member = harness.uid('membership-member')
    store.get_or_create_personal_space(uid, cell='cell1', now=NOW)
    store.add_member(uid, member, now=NOW)
    assert len(store.memberships_for_uid(member)) == 1
    assert store.revoke_member(uid, member, now=NOW + 1)
    assert not store.revoke_member(uid, member, now=NOW + 2)
    assert store.memberships_for_uid(member) == []
    revoked = store.memberships_for_uid(member, active_only=False)[0]
    assert (revoked.state, revoked.revoked_at) == ('revoked', NOW + 1)
    with store.pool.connection() as conn:
        with pytest.raises(Exception) as error:
            conn.execute("UPDATE memberships SET revoked_at=NULL WHERE space_id=%s AND uid=%s", (uid, member))
        assert error.value.sqlstate == '23514'
    store.add_member(uid, member, role='owner', now=NOW + 3)
    revived = store.memberships_for_uid(member)[0]
    assert (revived.state, revived.revoked_at, revived.role, revived.created_at) == ('active', None, 'owner', NOW)


def test_token_recycling_and_reverse_delete(harness, uid):
    store = harness.store
    other = harness.uid('token-other')
    token = uid + ':token'
    # Tokens are independent of spaces (no FK).
    store.upsert_token(uid, 'phone', token, now=NOW, time_zone='Asia/Ho_Chi_Minh')
    store.upsert_token(uid, 'phone', token, now=NOW + 1)
    row = store.tokens_for_uid(uid)[0]
    assert (row.token, row.created_at, row.updated_at) == (token, NOW, NOW + 1)
    store.upsert_token(other, 'tablet', token, now=NOW + 2)
    assert store.tokens_for_uid(uid) == []
    assert store.tokens_for_uid(other)[0].token == token
    assert store.remove_token(token)
    assert not store.remove_token(token)
    assert store.tokens_for_uid(other) == []


def test_concurrent_token_recycle(harness, uid):
    store = harness.store
    other = harness.uid('concurrent-token-other')
    barrier = threading.Barrier(2)

    def register(owner):
        barrier.wait(timeout=5)
        store.upsert_token(owner, 'phone', uid + ':token', now=NOW)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(register, (uid, other)))
    assert len(store.tokens_for_uid(uid)) + len(store.tokens_for_uid(other)) == 1


def test_public_conversations(harness, uid):
    store = harness.store
    conversation = uid + ':conversation'
    assert store.public_conversation_owner(conversation) is None
    store.get_or_create_personal_space(uid, cell='cell1', now=NOW)
    store.register_public_conversation(conversation, uid, visibility='public', now=NOW)
    assert store.public_conversation_owner(conversation) == uid
    store.register_public_conversation(conversation, uid, visibility='shared', now=NOW + 1)
    store.unregister_public_conversation(conversation)
    assert store.public_conversation_owner(conversation) is None
    store.unregister_public_conversation(conversation)
    with pytest.raises(Exception) as error:
        store.register_public_conversation(conversation, uid, visibility='private', now=NOW)
    assert error.value.sqlstate == '23514'


def test_owner_purge_all_tables_and_other_spaces(harness, uid):
    store = harness.store
    other = harness.uid('purge-neighbor')
    for owner in (uid, other):
        store.get_or_create_personal_space(owner, cell='cell1', now=NOW)
        store.upsert_token(owner, 'phone', owner + ':token', now=NOW)
        store.register_public_conversation(owner + ':conversation', owner, visibility='shared', now=NOW)
    store.add_member(other, uid, now=NOW)
    assert store.purge_owner(uid, now=NOW) == 5
    assert store.get_space(uid) is None
    assert store.memberships_for_uid(uid, active_only=False) == []
    assert store.memberships_for_space(uid, active_only=False) == []
    assert store.tokens_for_uid(uid) == []
    assert store.public_conversation_owner(uid + ':conversation') is None
    assert store.get_space(other) is not None
    assert store.public_conversation_owner(other + ':conversation') == other
    with store.pool.connection() as conn:
        for table, key in [
            ('spaces', 'space_id'),
            ('memberships', 'uid'),
            ('fcm_tokens', 'uid'),
            ('public_conversations', 'owner_space_id'),
        ]:
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE {key}=%s', (uid,)).fetchone()[0] == 0
    assert store.purge_owner(uid, now=NOW) == 0


def test_purge_rolls_back_on_error(harness, uid, monkeypatch):
    store = harness.store
    store.get_or_create_personal_space(uid, cell='cell1', now=NOW)
    store.upsert_token(uid, 'phone', uid + ':token', now=NOW)
    store.register_public_conversation(uid + ':conversation', uid, visibility='public', now=NOW)
    original = store.pool.connection

    class Proxy:
        def __init__(self, conn):
            self.conn = conn

        def transaction(self):
            return self.conn.transaction()

        def execute(self, sql, args=None):
            if sql.startswith('DELETE FROM fcm_tokens'):
                raise RuntimeError('injected deletion failure')
            return self.conn.execute(sql, args)

    @contextmanager
    def connection():
        with original() as conn:
            yield Proxy(conn)

    with monkeypatch.context() as patch:
        patch.setattr(store.pool, 'connection', connection)
        with pytest.raises(RuntimeError, match='injected'):
            store.purge_owner(uid, now=NOW)
    assert store.get_space(uid) is not None
    assert len(store.memberships_for_uid(uid)) == 1
    assert len(store.tokens_for_uid(uid)) == 1
    assert store.public_conversation_owner(uid + ':conversation') == uid


def test_migrations_are_separate_and_idempotent(harness):
    with dial(directory_dsn()) as conn:
        path = Path(directory_module.__file__).parent / 'migrations'
        assert migrate(conn, directory=path) == []
        assert migrate(conn, directory=path) == []
        assert current_version(conn) == 3
        assert conn.execute("SELECT to_regclass('cell_docs')").fetchone()[0] is None


def test_wipe_fence_survives_purge_and_blocks_all_route_creation(harness, uid):
    store = harness.store
    space = store.get_or_create_personal_space(uid, cell='cell1', now=NOW)
    fence = store.tombstone_owner(uid, now=NOW + 1)
    assert (fence.wipe_epoch, fence.cell) == (space.epoch + 1, 'cell1')
    store.purge_owner(uid, now=NOW + 2)
    assert store.tombstone_owner(uid, now=NOW + 3) == fence
    with pytest.raises(directory_module.OwnerTombstoned):
        store.get_or_create_personal_space(uid, cell='firestore', now=NOW + 4)
    with pytest.raises(directory_module.OwnerTombstoned):
        store.set_routing(uid, cell='cell1', now=NOW + 4)


def test_tombstoned_owner_cannot_recreate_directory_indexes(harness, uid):
    store = harness.store
    other = harness.uid('live-index-neighbor')
    store.get_or_create_personal_space(other, cell='firestore', now=NOW)
    store.tombstone_owner(uid, now=NOW)
    for create in (
        lambda: store.upsert_token(uid, 'phone', uid + ':token', now=NOW),
        lambda: store.add_member(other, uid, now=NOW),
        lambda: store.add_member(uid, other, now=NOW),
        lambda: store.register_public_conversation(uid + ':conversation', uid, visibility='public', now=NOW),
    ):
        with pytest.raises(directory_module.OwnerTombstoned):
            create()
    assert store.tokens_for_uid(uid) == []
    assert store.memberships_for_uid(uid) == []
    assert store.public_conversation_owner(uid + ':conversation') is None


def test_active_owner_lookup(harness, uid):
    store = harness.store
    assert not store.is_active_owner(uid, uid)
    store.get_or_create_personal_space(uid, cell='cell1', now=NOW)
    assert store.is_active_owner(uid, uid)
    assert not store.is_active_owner(uid, 'unknown-member')
    store.add_member(uid, 'another-member', now=NOW)
    assert not store.is_active_owner(uid, 'another-member')
    store.add_member(uid, 'another-member', now=NOW, role='owner')
    # Directory roles support future shared spaces; HTTP pilot admission also requires sid == uid.
    assert store.is_active_owner(uid, 'another-member')
    store.revoke_member(uid, 'another-member', now=NOW + 1)
    assert not store.is_active_owner(uid, 'another-member')
    store.add_member(uid, uid, now=NOW + 1, role='member')
    assert not store.is_active_owner(uid, uid)
    store.add_member(uid, uid, now=NOW + 2, role='owner')
    assert store.is_active_owner(uid, uid)
    store.purge_owner(uid, now=NOW)
    assert not store.is_active_owner(uid, uid)
