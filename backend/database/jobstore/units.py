"""Dark D4/W4 provider units. No production selector imports this store.

This typed surface can explicitly bind ordinary-upload admission and terminal
sealing through ProviderHandoff. Paid provider effects and customer projection
remain separate integration gates; it is not a cutover certificate. No method can flip an authoritative namespace back to FS.
"""

from __future__ import annotations

from uuid import uuid4

from database.jobstore.authority import Epoch, acquire, fingerprint, AuthorityRefused
from database.jobstore.postgres_store import jsonb
from database.privacy_fence.protocol import row_dict, lock
from database.privacy_fence import AdmissionChanged, FenceRefused, owner_key


class Units:
    def __init__(self, pool, fence, ticket: Epoch, *, handoff=None):
        self.pool, self.fence, self.ticket = pool, fence, ticket
        self.namespace = ticket.namespace
        if handoff is not None and (handoff.pool is not pool or handoff.fence is not fence or handoff.ticket != ticket):
            raise AuthorityRefused('unit handoff must share pool, privacy fence and epoch')
        self.handoff = handoff

    def _unit(self, conn, identity, *, skip_locked=False):
        suffix = ' FOR UPDATE SKIP LOCKED' if skip_locked else ' FOR UPDATE'
        return row_dict(
            conn, 'SELECT * FROM units WHERE namespace=%s AND unit_id=%s' + suffix, (self.namespace, identity)
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
        source=None,
    ):
        """Caller joins a proven FS admission intent; retries must use identical data.

        Fresh class and approximate owner rotation are REQUIRED inputs from the
        cohort admission policy, not re-derived by the database. Migration census
        must establish the same units_total before this API serves old recordings.
        """
        if source and self.handoff is None:
            raise AuthorityRefused('source-bound provider admission requires its handoff')
        self.fence.check_work_write(conn, owner, admission)
        acquire(conn, self.ticket)
        immutable = dict(
            owner=owner,
            recording=recording,
            capture_at=capture_at,
            units_total=units_total,
            custody_deadline=custody_deadline,
            fresh=fresh,
            owner_turn=owner_turn,
            **({'source': source} if source else {}),
        )
        digest = fingerprint(immutable)
        existing = row_dict(
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
        binding = row_dict(
            conn,
            'SELECT * FROM recordings WHERE namespace=%s AND recording_id=%s FOR UPDATE',
            (self.namespace, recording),
        )
        if (
            binding is None
            or binding['owner_key'] != owner
            or binding['units_total'] != units_total
            or binding['projection_state'] == 'revoked'
        ):
            raise AuthorityRefused('recording census/binding mismatch')
        conn.execute(
            'INSERT INTO units(namespace,unit_id,owner_key,recording_id,capture_at,stage,state,class,owner_turn,'
            'custody_deadline,privacy_generation,admission,created_at,source) '
            "VALUES (%s,%s,%s,%s,%s,'provider_stt','pending',%s,%s,%s,%s,%s,%s,%s)",
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
                jsonb(source or {}),
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
            candidates = []
            for cls, limit in ((0, count - backlog_share), (1, backlog_share)):
                if not limit:
                    continue
                rows = conn.execute(
                    "SELECT * FROM units WHERE namespace=%s AND stage='provider_stt' AND class=%s "
                    "AND state='pending' AND hold_reason IS NULL AND (due_at IS NULL OR due_at<=%s) "
                    'AND lease_until<=%s ORDER BY owner_turn,capture_at,unit_id LIMIT %s',
                    (self.namespace, cls, now, now, limit),
                )
                candidates.extend(dict(zip((column.name for column in rows.description), row)) for row in rows)
            # Discover without row/namespace locks; acquire all owner guards in
            # sorted order BEFORE authority, matching A2 admission. Re-read under
            # authority before mutation. Never acquire a newly discovered owner
            # while holding authority, nor upgrade a shared owner lock.
            for owner in sorted({job['owner_key'] for job in candidates}):
                lock(conn, owner)
            refused = {}
            for job in candidates:
                try:
                    self.fence.check_work_write(conn, job['owner_key'], job['admission'])
                except FenceRefused as error:
                    refused[job['unit_id']] = error.disposition
            acquire(conn, self.ticket)
            for candidate in candidates:
                identity = candidate['unit_id']
                job = self._unit(conn, identity, skip_locked=True)
                if (
                    not job
                    or job['owner_key'] != candidate['owner_key']
                    or job['admission'] != candidate['admission']
                    or job['state'] != 'pending'
                    or job['hold_reason'] is not None
                    or job['lease_until'] > now
                    or (job['due_at'] is not None and job['due_at'] > now)
                ):
                    continue
                if identity in refused:
                    # Status-only hold: retain custody through grace/purge. An
                    # admission refusal must not roll back another owner's lease
                    # or remain eligible to poison the next bounded pull.
                    conn.execute(
                        'UPDATE units SET hold_reason=%s,lease_token=NULL,lease_until=0 WHERE namespace=%s AND unit_id=%s',
                        (refused[identity], self.namespace, identity),
                    )
                elif job['attempt_token']:
                    # Unknown paid outcome is custody, never authority to send
                    # again. A receipt/reconciliation path must resolve it.
                    conn.execute(
                        "UPDATE units SET hold_reason='vendor' WHERE namespace=%s AND unit_id=%s",
                        (self.namespace, identity),
                    )
                else:
                    conn.execute(
                        'UPDATE units SET lease_token=%s,lease_until=%s,attempt_token=%s,attempts=attempts+1,'
                        'attempt_admission_id=%s '
                        'WHERE namespace=%s AND unit_id=%s',
                        (
                            uuid4().hex,
                            now + lease_seconds,
                            uuid4().hex,
                            job['admission']['admission_id'],
                            self.namespace,
                            identity,
                        ),
                    )
                    claimed.append(self._unit(conn, identity))
        return claimed

    def readmit(self, client, uid, conversation_ids, identity):
        """A9 restore through the production A1/walk/A2, never by clearing a flag.

        Caller supplies the original source targets; the new admission must
        still bind every old target (including redirects). An unresolved paid
        attempt keeps its token and enters a vendor hold. Its old result cannot
        be adopted under the newly minted admission.
        """
        owner = owner_key(uid)
        with self.pool.connection() as conn:
            before = row_dict(conn, 'SELECT * FROM units WHERE namespace=%s AND unit_id=%s', (self.namespace, identity))
        if before is None:
            return False
        if before['owner_key'] != owner:
            raise AuthorityRefused('restore owner binding mismatch')
        if before['state'] != 'pending' or before['hold_reason'] != 'privacy_deferred':
            return False

        def persist(conn, admission):
            # A2 already holds the owner guard, before namespace and row locks.
            acquire(conn, self.ticket)
            current = self._unit(conn, identity)
            if current is None or current != before:
                raise AdmissionChanged()
            old_targets = {t['conversation_key'] for t in before['admission']['privacy_targets']}
            new_targets = {t['conversation_key'] for t in admission['privacy_targets']}
            if not old_targets <= new_targets:
                raise AuthorityRefused('restore cannot drop an original privacy target')
            custody = row_dict(
                conn,
                'SELECT * FROM queue_custody WHERE namespace=%s AND identity=%s FOR UPDATE',
                (self.namespace, identity),
            )
            if not custody or custody['phase'] != 'admitted' or custody['owner_key'] != owner:
                raise AuthorityRefused('restore needs unresolved original custody')
            conn.execute(
                'UPDATE units SET admission=%s,privacy_generation=%s,hold_reason=%s,'
                'lease_token=NULL,lease_until=0,due_at=NULL WHERE namespace=%s AND unit_id=%s',
                (
                    jsonb(admission),
                    admission['privacy_generation'],
                    'vendor' if current['attempt_token'] else None,
                    self.namespace,
                    identity,
                ),
            )
            conn.execute(
                'UPDATE queue_custody SET admission_id=%s WHERE namespace=%s AND identity=%s',
                (admission['admission_id'], self.namespace, identity),
            )

        self.fence.admit_from_authority(client, uid, conversation_ids, persist)
        return True

    def _guarded_unit(self, conn, identity):
        before = row_dict(conn, 'SELECT * FROM units WHERE namespace=%s AND unit_id=%s', (self.namespace, identity))
        if before is None:
            return None
        self.fence.check_work_write(conn, before['owner_key'], before['admission'])
        acquire(conn, self.ticket)
        job = self._unit(conn, identity)
        if not job or job['owner_key'] != before['owner_key'] or job['admission'] != before['admission']:
            raise AuthorityRefused('unit binding changed; retry in a fresh transaction')
        return job

    def heartbeat(self, identity, lease_token, *, now, lease_seconds):
        if lease_seconds <= 0:
            raise ValueError('positive lease required')
        with self.pool.connection() as conn, conn.transaction():
            job = self._guarded_unit(conn, identity)
            if (
                not job
                or job['lease_token'] != lease_token
                or job['lease_until'] <= now
                or job['state'] != 'pending'
                or str(job['attempt_admission_id']) != job['admission']['admission_id']
            ):
                return False
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
        if self.handoff is not None and state == 'result_ready':
            from utils.batch_pipeline.contracts import WorkResult

            if not isinstance(result, dict) or WorkResult(**result).segment_id != identity:
                raise ValueError('typed provider completion requires its bound durable WorkResult')
        with self.pool.connection() as conn, conn.transaction():
            return self.settle_in_transaction(
                conn, identity, attempt, state, result, now=now, partial_wait=partial_wait
            )

    def settle_in_transaction(self, conn, identity, attempt, state, result, *, now, partial_wait, effect=None):
        """Join terminal custody to the caller's effect COMPLETE transaction."""
        if state not in {'result_ready', 'quarantined', 'privacy_blocked'} or partial_wait <= 0:
            raise ValueError('terminal state and explicit positive partial wait required')
        if self.handoff is not None and state == 'result_ready':
            from utils.batch_pipeline.contracts import WorkResult

            if not isinstance(result, dict) or WorkResult(**result).segment_id != identity:
                raise ValueError('typed provider completion requires its bound durable WorkResult')
        job = self._guarded_unit(conn, identity)
        if (
            not job
            or job['state'] != 'pending'
            or job['attempt_token'] != attempt
            or str(job['attempt_admission_id']) != job['admission']['admission_id']
        ):
            return False
        if job['provider_effect_id'] is not None and str(job['provider_effect_id']) != effect:
            raise AuthorityRefused('provider effect COMPLETE transaction required')
        if job['source'] and self.handoff is None:
            raise AuthorityRefused('source-bound provider settlement requires its handoff')
        # Status-only refusal is a separate API/integration gate. Do not let
        # a caller smuggle a result through a privacy_blocked status write.
        if state != 'result_ready' and result is not None:
            raise ValueError('refused units cannot carry a result')
        conn.execute("SELECT set_config('omi.queue_owner_key',%s,true)", (job['owner_key'],))
        conn.execute(
            'UPDATE units SET state=%s,result=%s,attempt_token=NULL,lease_token=NULL,lease_until=0,settled_at=%s '
            'WHERE namespace=%s AND unit_id=%s',
            (state, jsonb(result) if result is not None else None, now, self.namespace, identity),
        )
        recording = row_dict(
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
        if self.handoff is not None and recording['units_final'] == recording['units_total']:
            from database.jobstore.provider_handoff import seal_recording

            seal_recording(conn, self.handoff, recording)
        return True
