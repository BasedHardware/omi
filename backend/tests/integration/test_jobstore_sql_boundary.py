"""Raw SQL cannot remove authority or reopen FS without implemented certificates.

All SQL runs against the private synthetic cluster owned by postgres_connect.
"""

from uuid import uuid4

import pytest
from database.jobstore.authority import acquire, transition
from database.jobstore.connection import Pool
from database.jobstore.postgres_store import jsonb
from database.privacy_fence import Fence, owner_key
from testing.store_fixtures import postgres_connect

pytestmark = pytest.mark.integration


@pytest.fixture
def authority():
    pool = Pool('', size=2, connect=postgres_connect())
    namespace = 'batch_pipeline_test_' + uuid4().hex
    owner = owner_key(namespace)
    fence = Fence(pool)
    before = fence.snapshot(owner)
    with pool.connection() as conn, conn.transaction():
        fence.admit(conn, owner, before, 'synthetic')
        conn.execute('INSERT INTO queue_authority(namespace) VALUES (%s)', (namespace,))
        transition(conn, namespace, 'FS_OPEN', 0, 'FS_CLOSING')
        transition(conn, namespace, 'FS_CLOSING', 1, 'BOTH_CLOSED')
        ticket = transition(conn, namespace, 'BOTH_CLOSED', 2, 'PG_OPEN')
        acquire(conn, ticket)
        conn.execute(
            "INSERT INTO docs(namespace,tbl,key,doc) VALUES (%s,'intakes','one',%s)",
            (namespace, jsonb({'owner_key': owner, 'value': 1})),
        )
    yield pool, namespace
    pool.close()


def test_raw_sql_cannot_reverse_open_even_with_forged_session_flags(authority):
    pool, ns = authority
    with pool.connection() as conn, conn.transaction():
        transition(conn, ns, 'PG_OPEN', 3, 'PG_CLOSING')
        transition(conn, ns, 'PG_CLOSING', 4, 'BOTH_CLOSED')
    with pool.connection() as conn:
        with pytest.raises(Exception, match='reverse certificate'):
            with conn.transaction():
                conn.execute("SET LOCAL omi.queue_reverse_verified='true'")
                conn.execute("UPDATE queue_authority SET state='FS_OPEN',epoch=epoch+1 WHERE namespace=%s", (ns,))
        assert conn.execute('SELECT state,epoch FROM queue_authority WHERE namespace=%s', (ns,)).fetchone() == (
            'BOTH_CLOSED',
            5,
        )


@pytest.mark.parametrize('attack', ['delete', 'truncate', 'rename'])
def test_authority_cannot_be_erased_to_reenable_legacy_writes(authority, attack):
    pool, ns = authority
    with pool.connection() as conn:
        with pytest.raises(Exception, match='cannot be removed|namespace is immutable'):
            with conn.transaction():
                if attack == 'delete':
                    conn.execute('DELETE FROM queue_authority WHERE namespace=%s', (ns,))
                elif attack == 'truncate':
                    conn.execute('TRUNCATE queue_authority CASCADE')
                else:
                    conn.execute('UPDATE queue_authority SET namespace=%s WHERE namespace=%s', (ns + 'x', ns))
        assert conn.execute(
            'SELECT state,epoch,committed_seq FROM queue_authority WHERE namespace=%s', (ns,)
        ).fetchone() == ('PG_OPEN', 3, 1)
        with pytest.raises(Exception, match='epoch refused'):
            with conn.transaction():
                conn.execute("UPDATE docs SET doc=doc || '{\"value\":2}'::jsonb WHERE namespace=%s", (ns,))
        assert conn.execute('SELECT doc FROM docs WHERE namespace=%s', (ns,)).fetchone()[0]['value'] == 1


@pytest.mark.parametrize('state,epoch', [('PG_OPEN', 3), ('BOTH_CLOSED', 2), ('FS_OPEN', 6)])
def test_authority_bootstrap_cannot_forge_transition_history(authority, state, epoch):
    pool, _ = authority
    with pool.connection() as conn, pytest.raises(Exception, match='bootstrap'):
        with conn.transaction():
            conn.execute(
                'INSERT INTO queue_authority(namespace,state,epoch) VALUES (%s,%s,%s)',
                ('batch_pipeline_test_' + uuid4().hex, state, epoch),
            )
