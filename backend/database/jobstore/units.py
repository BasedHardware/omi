"""Dark D4/W4 provider units. No production selector imports this store.

This is a typed query/workload surface, not a certificate for the document
mirror. Capture admission, provider calls and FS projection remain separate
integration gates. No method can flip an authoritative namespace back to FS.
"""

from __future__ import annotations

from uuid import uuid4

from database.jobstore.authority import Epoch, acquire, fingerprint, AuthorityRefused
from database.jobstore.postgres_store import jsonb
from database.privacy_fence.protocol import _one


class Units:
    def __init__(self, pool, fence, ticket: Epoch):
        self.pool, self.fence, self.ticket = pool, fence, ticket
        self.namespace = ticket.namespace

    def _unit(self, conn, identity):
        return _one(
            conn, 'SELECT * FROM units WHERE namespace=%s AND unit_id=%s FOR UPDATE', (self.namespace, identity)
        )

    def admit(
        self,
        conn,
        identity,
        owner,
        recording,
        admission,
        *,
        capture_at,
        units_total,
        custody_deadline,
        fresh,
        owner_turn,
        now,
    ):
        """Caller joins a proven FS admission intent; retries must use identical data.

        Fresh class and approximate owner rotation are REQUIRED inputs from the
        cohort admission policy, not re-derived by the database. Migration census
        must establish the same units_total before this API serves old recordings.
        """
        acquire(conn, self.ticket)
        self.fence.check_work_write(conn, owner, admission)
        immutable = dict(
            owner=owner,
            recording=recording,
            capture_at=capture_at,
            units_total=units_total,
            custody_deadline=custody_deadline,
            fresh=fresh,
            owner_turn=owner_turn,
        )
        digest = fingerprint(immutable)
        existing = _one(
            conn,
            'SELECT * FROM queue_custody WHERE namespace=%s AND identity=%s FOR UPDATE',
            (self.namespace, identity),
        )
        if existing:
            if existing['fingerprint'] != digest or str(existing['admission_id']) != admission['admission_id']:
                raise AuthorityRefused('admission identity collision')
            return False
        conn.execute(
            'INSERT INTO recordings(namespace,recording_id,owner_key,units_total,first_capture_at) '
            'VALUES (%s,%s,%s,%s,%s) ON CONFLICT (namespace,recording_id) DO NOTHING',
            (self.namespace, recording, owner, units_total, capture_at),
        )
        binding = _one(
            conn,
            'SELECT * FROM recordings WHERE namespace=%s AND recording_id=%s FOR UPDATE',
            (self.namespace, recording),
        )
        if (
            binding['owner_key'] != owner
            or binding['units_total'] != units_total
            or binding['projection_state'] == 'revoked'
        ):
            raise AuthorityRefused('recording census/binding mismatch')
        conn.execute(
            'INSERT INTO units(namespace,unit_id,owner_key,recording_id,capture_at,stage,state,class,owner_turn,'
            'custody_deadline,privacy_generation,admission,created_at) '
            "VALUES (%s,%s,%s,%s,%s,'provider_stt','pending',%s,%s,%s,%s,%s,%s)",
            (
                self.namespace,
                identity,
                owner,
                recording,
                capture_at,
                0 if fresh else 1,
                owner_turn,
                custody_deadline,
                admission['privacy_generation'],
                jsonb(admission),
                now,
            ),
        )
        conn.execute(
            'INSERT INTO queue_custody(namespace,identity,owner_key,epoch,admission_id,phase,fingerprint) '
            "VALUES (%s,%s,%s,%s,%s,'admitted',%s)",
            (self.namespace, identity, owner, self.ticket.value, admission['admission_id'], digest),
        )
        return True

    def claim(self, count, *, now, lease_seconds, backlog_share):
        if not 0 <= backlog_share <= count <= 100 or lease_seconds <= 0:
            raise ValueError('bounded count/share and positive lease required')
        claimed = []
        with self.pool.connection() as conn, conn.transaction():
            acquire(conn, self.ticket)
            for cls, limit in ((0, count - backlog_share), (1, backlog_share)):
                rows = conn.execute(
                    "SELECT unit_id FROM units WHERE namespace=%s AND stage='provider_stt' AND class=%s "
                    "AND state='pending' AND hold_reason IS NULL AND (due_at IS NULL OR due_at<=%s) "
                    'AND lease_until<=%s ORDER BY owner_turn,capture_at,unit_id LIMIT %s FOR UPDATE SKIP LOCKED',
                    (self.namespace, cls, now, now, limit),
                ).fetchall()
                for (identity,) in rows:
                    job = self._unit(conn, identity)
                    self.fence.check_work_write(conn, job['owner_key'], job['admission'])
                    if job['attempt_token']:
                        # Unknown paid outcome is custody, never authority to send
                        # again. A receipt/reconciliation path must resolve it.
                        conn.execute(
                            "UPDATE units SET hold_reason='vendor' WHERE namespace=%s AND unit_id=%s",
                            (self.namespace, identity),
                        )
                    else:
                        conn.execute(
                            'UPDATE units SET lease_token=%s,lease_until=%s,attempt_token=%s,attempts=attempts+1 '
                            'WHERE namespace=%s AND unit_id=%s',
                            (uuid4().hex, now + lease_seconds, uuid4().hex, self.namespace, identity),
                        )
                        claimed.append(self._unit(conn, identity))
        return claimed

    def heartbeat(self, identity, lease_token, *, now, lease_seconds):
        if lease_seconds <= 0:
            raise ValueError('positive lease required')
        with self.pool.connection() as conn, conn.transaction():
            acquire(conn, self.ticket)
            job = self._unit(conn, identity)
            if not job or job['lease_token'] != lease_token or job['lease_until'] <= now or job['state'] != 'pending':
                return False
            self.fence.check_work_write(conn, job['owner_key'], job['admission'])
            conn.execute(
                'UPDATE units SET lease_until=%s WHERE namespace=%s AND unit_id=%s',
                (now + lease_seconds, self.namespace, identity),
            )
            return True

    def settle(self, identity, attempt, state, result, *, now, partial_wait):
        """One terminal CAS, accounting and one armed recording projection row.

        A missing recording raises and rolls back the unit transition. Privacy
        revocation after result_ready is handled by purge, never double-counted.
        partial_wait is required: the policy's unresolved choice is not silently
        hardcoded here. No provider retry is authorized by lease expiry.
        """
        if state not in {'result_ready', 'quarantined', 'privacy_blocked'} or partial_wait <= 0:
            raise ValueError('terminal state and explicit positive partial wait required')
        with self.pool.connection() as conn, conn.transaction():
            acquire(conn, self.ticket)
            job = self._unit(conn, identity)
            if not job or job['state'] != 'pending' or job['attempt_token'] != attempt:
                return False
            # Status-only refusal is a separate API/integration gate. Do not let
            # a caller smuggle a result through a privacy_blocked status write.
            self.fence.check_work_write(conn, job['owner_key'], job['admission'])
            if state != 'result_ready' and result is not None:
                raise ValueError('refused units cannot carry a result')
            conn.execute("SELECT set_config('omi.queue_owner_key',%s,true)", (job['owner_key'],))
            conn.execute(
                'UPDATE units SET state=%s,result=%s,attempt_token=NULL,lease_token=NULL,lease_until=0 '
                'WHERE namespace=%s AND unit_id=%s',
                (state, jsonb(result) if result is not None else None, self.namespace, identity),
            )
            recording = _one(
                conn,
                'UPDATE recordings SET units_final=units_final+1,projection_state=CASE '
                "WHEN %s='privacy_blocked' THEN 'revoked' ELSE projection_state END "
                'WHERE namespace=%s AND recording_id=%s RETURNING *',
                (state, self.namespace, job['recording_id']),
            )
            if recording is None:
                raise AuthorityRefused('missing recording; terminal CAS rolled back')
            due = (
                now
                if recording['units_final'] == recording['units_total'] or recording['projection_state'] == 'revoked'
                else now + partial_wait
            )
            if recording['projection_task_id'] is None:
                task = conn.execute(
                    'INSERT INTO outbox(namespace,kind,dedupe_key,owner_id,payload,available_at,created_at) '
                    "VALUES (%s,'project_conversation',%s,%s,%s,%s,%s) RETURNING id",
                    (
                        self.namespace,
                        job['recording_id'],
                        job['owner_key'],
                        jsonb({'recording_id': job['recording_id']}),
                        due,
                        now,
                    ),
                ).fetchone()[0]
                conn.execute(
                    'UPDATE recordings SET projection_task_id=%s,partial_deadline=%s WHERE namespace=%s AND recording_id=%s',
                    (task, due, self.namespace, job['recording_id']),
                )
            elif due == now:
                conn.execute(
                    'UPDATE outbox SET available_at=%s,wake_pending=true WHERE id=%s',
                    (now, recording['projection_task_id']),
                )
            conn.execute(
                "UPDATE queue_custody SET phase='completed',completion=%s WHERE namespace=%s AND identity=%s",
                (jsonb({'state': state, 'attempt': attempt, 'result': result}), self.namespace, identity),
            )
            return True
