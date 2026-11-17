"""Bounded G2 maintenance passes; construction/import starts no worker.

The service's existing job runner must explicitly call these passes. Wakes are
hints: SQL tasks and expired registry rows remain discoverable across restarts.
No pool slot or privacy lock spans a sink call. Errors leave custody durable.
"""

from __future__ import annotations

from uuid import uuid4

from database.privacy_fence.protocol import lock, row_dict


class Lifecycle:
    def __init__(self, fence, *, fence_gcs=None):
        self.fence = fence
        self.pool = fence.pool
        self.fence_gcs = fence_gcs

    def claim(self, *, owner=None):
        """One task, in a short transaction. A new lease fences a stale runner."""
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SET LOCAL lock_timeout='2s'")
            conn.execute("SET LOCAL statement_timeout='5s'")
            return row_dict(
                conn,
                'UPDATE privacy_close_drain SET lease_token=%s,'
                "lease_until=now()+interval '30 seconds',attempts=attempts+1 "
                'WHERE (owner_key,seq)=(SELECT owner_key,seq FROM privacy_close_drain '
                'WHERE available_at<=now() AND (lease_until IS NULL OR lease_until<=now()) '
                'AND (%s::text IS NULL OR owner_key=%s) '
                'ORDER BY available_at,owner_key,seq LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *',
                (uuid4(), owner, owner),
            )

    def finish(self, task, *, remaining):
        """Ack/retry only the exact lease. Unknown COMMIT is safe to replay."""
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SET LOCAL lock_timeout='2s'")
            conn.execute("SET LOCAL statement_timeout='5s'")
            args = (task['owner_key'], task['seq'], task['lease_token'])
            if remaining == 0:
                return bool(
                    conn.execute(
                        'DELETE FROM privacy_close_drain WHERE owner_key=%s AND seq=%s '
                        'AND lease_token=%s RETURNING seq',
                        args,
                    ).fetchone()
                )
            # Polling stops waiting for a lease; it never grants dispatch or
            # discards a GCS capability without terminal/absence proof.
            return bool(
                conn.execute(
                    "UPDATE privacy_close_drain SET available_at=now()+interval '5 seconds',"
                    'lease_token=NULL,lease_until=NULL WHERE owner_key=%s AND seq=%s '
                    'AND lease_token=%s RETURNING seq',
                    args,
                ).fetchone()
            )

    def close_pass(self, *, limit=20, owner=None):
        if not 1 <= limit <= 100:
            raise ValueError('bounded task limit required')
        completed = 0
        for _ in range(limit):
            task = self.claim(owner=owner)
            if task is None:
                break
            remaining = self.fence.drain_pass(
                task['owner_key'],
                conversation=task['conversation_key'],
                fence_gcs=self.fence_gcs,
                before_seq=task['seq'],
            )
            completed += int(self.finish(task, remaining=remaining) and remaining == 0)
        return completed

    def janitor_pass(self, *, limit=20):
        """Expired effects on open owners are discoverable without a close task."""
        if not 1 <= limit <= 100:
            raise ValueError('bounded owner limit required')
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SET LOCAL statement_timeout='5s'")
            owners = conn.execute(
                'SELECT owner_key FROM privacy_effect_inflight WHERE lease_until<=now() AND maintenance_after<=now() '
                'GROUP BY owner_key ORDER BY min(lease_until),owner_key LIMIT %s',
                (limit,),
            ).fetchall()
            # Retain unresolved capabilities, but move their next discovery
            # behind other expired owners. Commit before any sink operation;
            # a runner crash merely delays this retry by five seconds.
            for (owner,) in sorted(owners):
                lock(conn, owner)
                conn.execute(
                    "UPDATE privacy_effect_inflight SET maintenance_after=now()+interval '5 seconds' "
                    'WHERE owner_key=%s AND lease_until<=now()',
                    (owner,),
                )
        for (owner,) in owners:
            self.fence.drain_pass(owner, janitor=True, fence_gcs=self.fence_gcs)
        return len(owners)
