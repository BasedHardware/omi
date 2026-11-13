"""G2 locks, admission, per-sequence close, work checks and effect custody.

No connection is held over the Firestore walk or a sink call. All SQL uses the
primary, READ COMMITTED and transaction-scoped settings/locks. A fresh admission
is returned to be persisted by the caller in the SAME committing transaction.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import uuid4

from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from database.jobstore.postgres_store import jsonb

owner_key = privacy_owner_key


def conversation_key(owner: str, cid: str) -> str:
    if not cid or '/' in cid or len(cid.encode()) > 256:
        raise ValueError('bounded conversation ID required')
    return hashlib.sha256(f'{owner}/{cid}'.encode()).hexdigest()


class FenceRefused(BatchPrivacyBlocked):
    def __init__(self, disposition='privacy_deferred'):
        super().__init__('privacy_generation_changed')
        self.disposition = disposition


class AdmissionChanged(FenceRefused):
    """Retry the full A1/walk/A2 protocol in a NEW transaction; never upgrade."""


def _one(conn, query, params=()):
    cursor = conn.execute(query, params)
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip((c.name for c in cursor.description), row))


def lock(conn, owner, *, exclusive=False):
    conn.execute("SET LOCAL lock_timeout = '2s'")
    conn.execute("SET LOCAL statement_timeout = '5s'")
    conn.execute("SET LOCAL omi.privacy_fence_protocol = '2'")
    operation = 'pg_advisory_xact_lock' if exclusive else 'pg_advisory_xact_lock_shared'
    conn.execute(f'SELECT {operation}(privacy_lock_key(%s))', (owner,))


def _owner(conn, owner):
    return _one(conn, 'SELECT * FROM privacy_owner_fence WHERE owner_key=%s', (owner,))


def _targets(conn, owner, keys):
    result = {}
    for key in sorted(set(keys)):
        row = _one(
            conn,
            'SELECT generation,state FROM privacy_conversation_fence ' 'WHERE owner_key=%s AND conversation_key=%s',
            (owner, key),
        )
        result[key] = row or {'generation': 0, 'state': 'open'}
    return result


class Fence:
    def __init__(self, pool):
        self.pool = pool

    def admit_from_authority(self, client, uid, conversation_ids, persist):
        """Full A1/W/A2 protocol using production CustomerData, with bounded retries.

        `persist(conn, admission)` joins the admission and its payload in A2. It
        must be pure SQL and idempotent on the caller's durable admission intent.
        The returned generation here is PG's generation; the walk generation is
        recorded separately and never substituted for a Postgres fence check.
        """
        from google.cloud import firestore
        from database.batch_pipeline_privacy import assert_batch_write_allowed, mint_token, STRUCTURAL_REASONS
        from database.batch_privacy_attempt import TOKEN_FIELD, token_version

        owner = owner_key(uid)
        cids = tuple(conversation_ids)
        keys = [conversation_key(owner, cid) for cid in cids]
        token_ref = client.collection('batch_pipeline_privacy').document(owner)

        @firestore.transactional
        def walk(transaction):
            snapshot = token_ref.get(transaction=transaction)
            snapshots = {}
            generation = assert_batch_write_allowed(
                client, transaction, uid, conversation_ids=cids, snapshots=snapshots
            )
            if token_version(snapshot) is None:
                return None
            targets = [conversation_key(owner, cid) for cid in snapshots.get('conversations', {})]
            return snapshot.to_dict()[TOKEN_FIELD], targets, generation

        for _ in range(3):
            before = self.snapshot(owner, keys)
            try:
                result = walk(client.transaction())
            except BatchPrivacyBlocked as error:
                if error.reason not in STRUCTURAL_REASONS:
                    deleted_cid = error.conversation_id
                    self.close(
                        owner,
                        local=True,
                        reason='detector',
                        conversation=conversation_key(owner, deleted_cid) if deleted_cid else None,
                        state='deleted' if deleted_cid else 'closed',
                    )
                raise
            if result is None:
                mint_token(client, token_ref)
                continue
            token, targets, fs_generation = result
            try:
                with self.pool.connection() as conn, conn.transaction():
                    admission = self.admit(conn, owner, before, token, targets)
                    admission['fs_privacy_generation'] = fs_generation
                    persist(conn, admission)
                    return admission
            except AdmissionChanged:
                continue
        raise AdmissionChanged()

    def snapshot(self, owner, keys=()):
        """A1; release the connection and shared lock before the authority walk."""
        with self.pool.connection() as conn, conn.transaction():
            lock(conn, owner)
            row = _owner(conn, owner)
            if row and (row['pending_changes'] or row['state'] in {'purging', 'erased'}):
                raise FenceRefused('privacy_blocked' if row['state'] in {'purging', 'erased'} else 'privacy_deferred')
            return row, _targets(conn, owner, keys)

    def admit(self, conn, owner, before, token, keys=()):
        """A2 after an allowing walk. Caller persists this fingerprint before COMMIT.

        `before` is the A1 snapshot; `keys` MUST include redirect targets exported
        by that same Firestore walk. A missing/invalid token never grants work.
        """
        old, pcs = before
        need_x = old is None or old['state'] == 'closed' or any(r['state'] == 'closed' for r in pcs.values())
        lock(conn, owner, exclusive=need_x)
        current = _owner(conn, owner)  # separate statement AFTER lock grant (H-12)
        if current != old or not isinstance(token, str) or not token:
            raise AdmissionChanged()
        targets = _targets(conn, owner, keys)
        if any(targets.get(k) != v for k, v in pcs.items()) or (current and current['pending_changes']):
            raise AdmissionChanged()
        if any(r['state'] == 'deleted' for r in targets.values()):
            raise FenceRefused('privacy_blocked')
        if not need_x and any(r['state'] == 'closed' for r in targets.values()):
            raise AdmissionChanged()  # restart, acquire L_x from the beginning
        if current is None:
            conn.execute("INSERT INTO privacy_owner_fence(owner_key,generation,state) VALUES (%s,1,'open')", (owner,))
        elif current['state'] == 'closed':
            conn.execute(
                "UPDATE privacy_owner_fence SET generation=generation+1,state='open',close_reason=NULL,"
                'updated_at=now() WHERE owner_key=%s',
                (owner,),
            )
        elif current['state'] != 'open':
            raise FenceRefused('privacy_blocked')
        for key, row in targets.items():
            if row['state'] == 'closed':
                conn.execute(
                    "UPDATE privacy_conversation_fence SET generation=generation+1,state='open',updated_at=now() "
                    'WHERE owner_key=%s AND conversation_key=%s',
                    (owner, key),
                )
        current = _owner(conn, owner)
        targets = _targets(conn, owner, keys)
        now = conn.execute('SELECT now()').fetchone()[0]
        return {
            'admission_id': str(uuid4()),
            'admission_version': 2,
            'admitted_at': now,
            'privacy_generation': current['generation'],
            'privacy_change_seq': current['change_seq'],
            'privacy_token': token,
            'privacy_targets': [
                dict(conversation_key=k, generation=v['generation']) for k, v in sorted(targets.items())
            ],
        }

    def check_work_write(self, conn, owner, job):
        lock(conn, owner)
        row = _owner(conn, owner)
        now = conn.execute('SELECT now()').fetchone()[0]
        if row is None or row['state'] != 'open':
            raise FenceRefused(
                'privacy_blocked' if row and row['state'] in {'purging', 'erased'} else 'privacy_deferred'
            )
        admitted = job.get('admitted_at')
        if (
            job.get('admission_version') != 2
            or not job.get('admission_id')
            or not job.get('privacy_token')
            or admitted is None
            or not admitted <= now < admitted + timedelta(minutes=15)
            or row['generation'] != job.get('privacy_generation')
        ):
            raise AdmissionChanged()
        targets = job.get('privacy_targets')
        if not isinstance(targets, list):
            raise AdmissionChanged()
        for target in targets:
            pc = _targets(conn, owner, [target['conversation_key']])[target['conversation_key']]
            if pc['state'] not in {'open', 'redirected'} or pc['generation'] != target['generation']:
                raise AdmissionChanged()
        return row

    def close(self, owner, *, reason='unknown', conversation=None, state='closed', guard_version=None, local=False):
        """Close before the narrowing Commit. Legal holds must never call this."""
        with self.pool.connection() as conn, conn.transaction():
            lock(conn, owner, exclusive=True)
            row = _owner(conn, owner)
            if row is None:
                conn.execute(
                    "INSERT INTO privacy_owner_fence(owner_key,generation,state,close_reason) "
                    "VALUES (%s,0,'closed',%s)",
                    (owner, reason),
                )
                row = _owner(conn, owner)
            if row['state'] == 'erased':
                raise FenceRefused('privacy_blocked')
            seq = row['change_seq'] + 1
            conn.execute(
                'UPDATE privacy_owner_fence SET change_seq=%s,pending_changes=pending_changes+%s,'
                'updated_at=now() WHERE owner_key=%s',
                (seq, 0 if local else 1, owner),
            )
            conn.execute(
                'INSERT INTO privacy_fence_change(owner_key,seq,state,guard_version) VALUES (%s,%s,%s,%s)',
                (owner, seq, 'local' if local else 'pending', guard_version),
            )
            if conversation is None:
                conn.execute(
                    "UPDATE privacy_owner_fence SET generation=generation+1,state=CASE WHEN state='purging' "
                    "THEN state ELSE 'closed' END,close_reason=%s WHERE owner_key=%s",
                    (reason, owner),
                )
            else:
                if state not in {'closed', 'deleted', 'redirected'}:
                    raise ValueError('invalid conversation close state')
                conn.execute(
                    'INSERT INTO privacy_conversation_fence(owner_key,conversation_key,generation,state) '
                    'VALUES (%s,%s,1,%s) ON CONFLICT (owner_key,conversation_key) DO UPDATE '
                    'SET generation=privacy_conversation_fence.generation+1,state=EXCLUDED.state,updated_at=now() '
                    "WHERE privacy_conversation_fence.state <> 'deleted'",
                    (owner, conversation, state),
                )
            return seq

    def settle(self, owner, seq, proof):
        """Only call after exact Commit ack, observed array membership, or committed kill.

        No sequence maximum is accepted. The reconciler owns the Firestore proof.
        """
        if proof not in {'landed', 'abandoned'}:
            raise ValueError('exact per-sequence proof required')
        with self.pool.connection() as conn, conn.transaction():
            lock(conn, owner, exclusive=True)
            changed = conn.execute(
                'UPDATE privacy_fence_change SET state=%s WHERE owner_key=%s AND seq=%s '
                "AND state='pending' RETURNING seq",
                (proof, owner, seq),
            ).fetchone()
            if changed:
                conn.execute(
                    'UPDATE privacy_owner_fence SET pending_changes=pending_changes-1 WHERE owner_key=%s', (owner,)
                )

    def register(self, conn, owner, job_key, job, kind, *, lease_seconds, sink=None):
        row = self.check_work_write(conn, owner, job)
        if lease_seconds <= 0 or (kind == 'gcs_put') != (sink is not None):
            raise ValueError('positive lease and GCS-only sink required')
        effect = str(uuid4())
        conn.execute(
            'INSERT INTO privacy_effect_inflight(effect_id,owner_key,job_key,kind,admission_id,owner_generation,'
            'change_seq,target_gens,conversation_keys,state,lease_until,sink) '
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'registered',now()+(%s * interval '1 second'),%s)",
            (
                effect,
                owner,
                job_key,
                kind,
                job['admission_id'],
                row['generation'],
                row['change_seq'],
                jsonb(job['privacy_targets']),
                [t['conversation_key'] for t in job['privacy_targets']],
                lease_seconds,
                jsonb(sink) if sink is not None else None,
            ),
        )
        return effect

    def _effect(self, conn, owner, effect):
        lock(conn, owner)
        return _one(
            conn,
            'SELECT * FROM privacy_effect_inflight WHERE owner_key=%s AND effect_id=%s FOR UPDATE',
            (owner, effect),
        )

    def start(self, conn, owner, effect, job):
        row = self.check_work_write(conn, owner, job)
        inflight = self._effect(conn, owner, effect)
        now = conn.execute('SELECT now()').fetchone()[0]
        if not (
            inflight
            and inflight['state'] == 'registered'
            and inflight['lease_until'] > now
            and self._fingerprint(inflight, job)
            and inflight['change_seq'] == row['change_seq']
        ):
            raise FenceRefused()
        conn.execute("UPDATE privacy_effect_inflight SET state='started' WHERE effect_id=%s", (effect,))

    @staticmethod
    def _fingerprint(effect, job):
        return (
            str(effect['admission_id']) == job['admission_id']
            and effect['owner_generation'] == job['privacy_generation']
            and effect['target_gens'] == job['privacy_targets']
        )

    def complete(self, conn, owner, effect, job, persist, *, gcs_absent=False):
        """Persist under this same transaction or discard; ambiguous COMMIT keeps custody.

        GCS refusal keeps its registry row until terminal status AND own-generation
        absence have been established by the sink adapter outside the transaction.
        """
        inflight = self._effect(conn, owner, effect)
        if inflight is None:
            return False
        try:
            self.check_work_write(conn, owner, job)
            allowed = inflight['state'] == 'started' and self._fingerprint(inflight, job)
        except FenceRefused:
            allowed = False
        if allowed:
            persist(conn)
            conn.execute('DELETE FROM privacy_effect_inflight WHERE effect_id=%s', (effect,))
        elif inflight['kind'] != 'gcs_put' or gcs_absent:
            self._retire(conn, inflight)
        return allowed

    @staticmethod
    def _retire(conn, row):
        if row['kind'] == 'vector' and row['state'] == 'started':
            for key in row['conversation_keys'] or [None]:
                conn.execute(
                    "INSERT INTO privacy_residue_target(owner_key,conversation_key,kind) VALUES (%s,%s,'vector')",
                    (row['owner_key'], key),
                )
        conn.execute('DELETE FROM privacy_effect_inflight WHERE effect_id=%s', (row['effect_id'],))

    def drain_pass(self, owner, *, conversation=None, janitor=False, fence_gcs=None):
        """One bounded pass. Return remaining rows; caller retries without holding L_x.

        `fence_gcs(sink)` must cancel/query the C4 session and verify absence, and
        returns True ONLY on that proof. An absent adapter preserves custody.
        """
        with self.pool.connection() as conn:
            rows = conn.execute(
                'SELECT effect_id,sink,kind FROM privacy_effect_inflight WHERE owner_key=%s '
                'AND (%s::text IS NULL OR %s=ANY(conversation_keys)) '
                'AND (NOT %s OR lease_until<=now()) '
                'ORDER BY lease_until,effect_id LIMIT 100',
                (owner, conversation, conversation, janitor),
            ).fetchall()
        for effect, sink, kind in rows:
            terminal = kind == 'gcs_put' and fence_gcs is not None and fence_gcs(sink)
            with self.pool.connection() as conn, conn.transaction():
                lock(conn, owner, exclusive=True)
                row = self._effect(conn, owner, effect)
                if row is None:
                    continue
                expired = row['lease_until'] <= conn.execute('SELECT now()').fetchone()[0]
                if janitor and not expired:
                    continue
                if kind == 'gcs_put' and not terminal:
                    continue
                if row['state'] == 'registered' or expired or terminal:
                    self._retire(conn, row)
        with self.pool.connection() as conn:
            return conn.execute(
                'SELECT count(*) FROM privacy_effect_inflight WHERE owner_key=%s '
                'AND (%s::text IS NULL OR %s=ANY(conversation_keys))',
                (owner, conversation, conversation),
            ).fetchone()[0]
