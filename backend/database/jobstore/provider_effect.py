"""Explicit dark paid-provider ticket. No runner or provider routing is enabled.

REGISTER and START are separate short transactions. The actual provider seam
invokes START after allowance reservation and before its one paid POST. A lost
reply retains the original attempt/effect; it never authorizes another send.
Result object publication and its original lifetime remain the caller's custody.
"""

import math

from google.cloud import firestore

from database.batch_pipeline_privacy import assert_batch_write_allowed
from database.batch_privacy_attempt import TOKEN_FIELD, token_version
from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore import codec


class FenceTicket:
    def __init__(self, units, identity, attempt, *, lease_seconds):
        if not isinstance(lease_seconds, (int, float)) or not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError('explicit positive finite effect lease required')
        if units.handoff is None:
            raise AuthorityRefused('provider source handoff required')
        self.units, self.identity, self.attempt = units, identity, attempt
        self.handoff = units.handoff
        with units.pool.connection() as conn, conn.transaction():
            job = self._job(conn)
            self.source = codec.loads(codec.canonical(job['source']))
            self.admission = codec.loads(codec.canonical(job['admission']))
            self.owner = job['owner_key']
            row = self.handoff._required_row(conn, job['recording_id'])
            self.handoff._guard(conn, row)
            if row['admission'] != self.admission or fingerprint(
                row['intent']['payload']['jobs'].get(identity)
            ) != fingerprint(self.source):
                raise AuthorityRefused('provider effect differs from original handoff')
            self.conversation_ids = row['intent']['conversation_ids']
            if job['provider_effect_id'] is None:
                self.effect = units.fence.register(
                    conn, self.owner, identity, self.admission, 'provider', lease_seconds=lease_seconds
                )
                conn.execute(
                    'UPDATE units SET provider_effect_id=%s WHERE namespace=%s AND unit_id=%s',
                    (self.effect, units.namespace, identity),
                )
            else:
                self.effect = str(job['provider_effect_id'])

    def _job(self, conn):
        job = self.units._guarded_unit(conn, self.identity)
        if (
            not job
            or not job['source']
            or job['state'] != 'pending'
            or job['attempt_token'] != self.attempt
            or str(job['attempt_admission_id']) != job['admission']['admission_id']
        ):
            raise AuthorityRefused('original pending provider attempt required')
        return job

    def start(self, item, service):
        expected = {key: self.source.get(key) for key in item.to_dict()}
        if (
            fingerprint(expected) != fingerprint(item.to_dict())
            or service != self.source['stt_route']['provider_service']
        ):
            raise AuthorityRefused('provider dispatch differs from original source')

        @firestore.transactional
        def authority(transaction):
            self.handoff.authority.check(transaction, phases=('PG_OPEN',))
            token = (
                self.handoff.client.collection('batch_pipeline_privacy')
                .document(self.owner)
                .get(transaction=transaction)
            )
            if (
                token_version(token) is None
                or (token.to_dict() or {}).get(TOKEN_FIELD) != self.admission['privacy_token']
            ):
                raise AuthorityRefused('provider dispatch token changed')
            assert_batch_write_allowed(
                self.handoff.client,
                transaction,
                item.owner_id,
                conversation_ids=self.conversation_ids,
                expected_generation=item.privacy_generation,
                snapshots={},
            )

        # No SQL connection or owner guard crosses this authority RPC.
        authority(self.handoff.client.transaction())
        with self.units.pool.connection() as conn, conn.transaction():
            job = self._job(conn)
            if str(job['provider_effect_id']) != self.effect or job['admission'] != self.admission:
                raise AuthorityRefused('provider effect admission changed')
            self.units.fence.start(conn, self.owner, self.effect, self.admission)

    def complete(self, result, *, now, partial_wait):
        """WorkResult's durable reference and all terminal SQL share COMPLETE."""
        with self.units.pool.connection() as conn, conn.transaction():

            def persist(connection):
                job = self._job(connection)
                if str(job['provider_effect_id']) != self.effect or job['admission'] != self.admission:
                    raise AuthorityRefused('provider effect admission changed')
                if not self.units.settle_in_transaction(
                    connection,
                    self.identity,
                    self.attempt,
                    'result_ready',
                    result,
                    now=now,
                    partial_wait=partial_wait,
                    effect=self.effect,
                ):
                    raise AuthorityRefused('provider terminal CAS lost')

            return self.units.fence.complete(conn, self.owner, self.effect, self.admission, persist)
