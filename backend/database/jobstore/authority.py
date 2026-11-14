"""Dark D authority primitives; no serving-mode factory selects this module.

The namespace row is a deliberately serialized journal allocator: allocation and
mutation share the transaction, so a rolled-back allocation leaves no hole and a
visible committed_seq is a committed prefix. Sizing must measure this cost. A
bare sequence/bigserial maximum is never a certificate.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from database.jobstore import codec
from database.jobstore.postgres_store import jsonb


class AuthorityRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class Epoch:
    namespace: str
    value: int


def acquire(conn, ticket: Epoch):
    conn.execute("SET LOCAL lock_timeout='2s'")
    conn.execute("SET LOCAL statement_timeout='5s'")
    row = conn.execute(
        'SELECT state,epoch FROM queue_authority WHERE namespace=%s FOR UPDATE', (ticket.namespace,)
    ).fetchone()
    if row != ('PG_OPEN', ticket.value):
        raise AuthorityRefused('queue authority closed or stale epoch')
    conn.execute("SELECT set_config('omi.queue_epoch',%s,true)", (str(ticket.value),))


def journal(conn, ticket, family, identity, owner, body):
    """Every caller must mutate and journal under acquire(), before the same COMMIT."""
    acquire(conn, ticket)
    seq = conn.execute(
        'UPDATE queue_authority SET committed_seq=committed_seq+1 WHERE namespace=%s ' 'RETURNING committed_seq',
        (ticket.namespace,),
    ).fetchone()[0]
    conn.execute(
        'INSERT INTO queue_journal(namespace,seq,epoch,family,identity,operation,owner_key,body) '
        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
        (
            ticket.namespace,
            seq,
            ticket.value,
            family,
            jsonb(identity),
            'delete' if body is None else 'put',
            owner,
            jsonb(body) if body is not None else None,
        ),
    )
    return seq


def transition(conn, namespace, expected_state, expected_epoch, target):
    """Only fenced transitions; returning to FS requires a separate verified certificate.

    This source checkpoint intentionally refuses the reverse-open edge: no
    generic operator boolean or environment flip can stand in for parity proof.
    """
    if target == 'FS_OPEN':
        raise AuthorityRefused('reverse certificate integration required')
    row = conn.execute(
        'UPDATE queue_authority SET state=%s,epoch=epoch+1 WHERE namespace=%s '
        'AND state=%s AND epoch=%s RETURNING epoch',
        (target, namespace, expected_state, expected_epoch),
    ).fetchone()
    if row is None:
        raise AuthorityRefused('authority transition lost CAS')
    return Epoch(namespace, row[0])


def committed_prefix(conn, namespace):
    row = conn.execute(
        'SELECT committed_seq FROM queue_authority WHERE namespace=%s FOR SHARE', (namespace,)
    ).fetchone()
    if row is None:
        raise AuthorityRefused('unknown queue namespace')
    return row[0]


def fingerprint(value):
    return hashlib.sha256(codec.canonical(value).encode()).hexdigest()


def stop_copier(conn, namespace):
    """Bounded SQL stop; never waits for a sink RPC and preserves applied_seq."""
    conn.execute("SET LOCAL lock_timeout='2s'")
    conn.execute("SET LOCAL statement_timeout='5s'")
    return conn.execute(
        'UPDATE queue_authority SET copier_stopped=true WHERE namespace=%s ' 'RETURNING committed_seq,applied_seq',
        (namespace,),
    ).fetchone()


def replay_page(pool, namespace, apply, *, limit=100):
    """Conditional sink apply is idempotent; checkpoint advances only after all acks.

    `apply` must transactionally compare (epoch,seq) at the cold FS destination,
    persist delete/expiry tombstones, and refuse to claim/wake there. Error/lost
    ack leaves the page replayable. No runtime installs an apply adapter yet.
    """
    with pool.connection() as conn, conn.transaction():
        conn.execute("SET LOCAL lock_timeout='2s'")
        conn.execute("SET LOCAL statement_timeout='5s'")
        state = conn.execute(
            'SELECT copier_stopped,applied_seq,committed_seq,epoch FROM queue_authority '
            'WHERE namespace=%s FOR SHARE',
            (namespace,),
        ).fetchone()
        if state is None or state[0]:
            return 0
        rows = conn.execute(
            'SELECT seq,epoch,family,identity,operation,owner_key,body FROM queue_journal '
            'WHERE namespace=%s AND seq>%s AND seq<=%s ORDER BY seq LIMIT %s',
            (namespace, state[1], state[2], max(1, min(limit, 100))),
        ).fetchall()
    # No PG transaction, guard or pool slot survives across sink I/O. A stopped
    # page cannot advance the checkpoint. Each concrete sink adapter must also
    # check destination authority in its own committing FS transaction, so a
    # late page can never write into a restored FS-authoritative generation.
    expected = state[1] + 1
    deadline = time.monotonic() + 1.5
    for row in rows:
        if row[0] != expected:
            raise AuthorityRefused('journal gap; preserve checkpoint')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('copier page deadline; checkpoint unchanged')
        apply(row, timeout=remaining)
        expected += 1
    if rows:
        with pool.connection() as conn, conn.transaction():
            conn.execute("SET LOCAL lock_timeout='2s'")
            conn.execute("SET LOCAL statement_timeout='5s'")
            conn.execute(
                'UPDATE queue_authority SET applied_seq=%s WHERE namespace=%s AND applied_seq=%s '
                'AND NOT copier_stopped AND epoch=%s',
                (rows[-1][0], namespace, state[1], state[3]),
            )
    return len(rows)
