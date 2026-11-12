"""Operator-only, metadata-proven absence. Never completes a custody job."""

from copy import deepcopy
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_projection_protocol import normalized_binding
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from utils.batch_pipeline.scheduler import owner_key
from database.sync_ledger import LEDGER_RETENTION_DAYS
from database.sync_ledger_ownership import batch_projection_ledger_owner_matches
from utils.batch_pipeline.input_retention import input_expiring

REASON_CODE = 'batch_artifact_missing'
PROOF_MAX_AGE_SECONDS = 30


def artifact_missing(job: dict) -> bool:
    # Fail closed even if a later writer changes the state around this marker.
    # An expiring GPU input uses the SAME exact-bundle repair protocol. This
    # marker authorizes replacement, never a claim that GCS confirmed absence.
    return (job.get('artifact_disposition') or {}).get('state') == 'missing' or (
        input_expiring(job) and job.get('input_expiring_leg') == 'gpu'
    )


def fingerprint(job: dict) -> str:
    return hashlib.sha256(json.dumps(job, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


class ArtifactMissingStore:
    def __init__(self, store):
        self.store = store

    def _reupload_content(self, tx, uid, content_id):
        ledger = tx.get('content', f'{uid}/{content_id}')
        route = ledger.get('batch_pipeline') or {}
        ids = route.get('segment_ids') or []
        if (
            ledger.get('dispatch_protocol') != 'batch_v1'
            or route.get('namespace') != self.store.namespace
            or not 1 <= len(ids) <= 128
            or ledger.get('status') not in {'processing', 'partial'}
        ):
            raise ProjectionBlocked('original missing-input content owner required')
        jobs = [tx.get('jobs', sid) for sid in ids]
        try:
            binding = normalized_binding(jobs[0]['projection_binding'])
            matched = all(normalized_binding(job['projection_binding']) == binding for job in jobs)
        except (KeyError, TypeError, ValueError):
            raise ProjectionBlocked('original missing-input binding required') from None
        if (
            not matched
            or binding.owner_id != uid
            or binding.content_id != content_id
            or list(binding.segment_ids) != ids
            or not batch_projection_ledger_owner_matches(ledger, binding.job_id, binding.run_token, binding.run_epoch)
            or binding.native_record
            or binding.record_origin
            or binding.partial_record
        ):
            raise ProjectionBlocked('original upload repair binding required')
        return ledger, binding, jobs

    def reupload_snapshot(self, uid, content_id):
        """Read-only repair plan for the exact, server-derived upload content ID."""
        from database.batch_pipeline_projection import held_without_recovery

        def read(tx):
            _ledger, binding, jobs = self._reupload_content(tx, uid, content_id)
            missing = {job['segment_id']: job for job in jobs if artifact_missing(job)}
            if not missing:
                return None
            for sid, job in missing.items():
                RecoveryStore(self.store).checked(tx, sid)
                if (
                    not held_without_recovery(job)
                    or not (
                        (job.get('state') == 'quarantined' and job.get('recovery_state') == 'failed_held')
                        or (input_expiring(job) and job.get('input_expiring_leg') == 'gpu')
                    )
                    or job.get('result')
                    or tx.get('results', sid)
                    or (job.get('stt_route') or {}).get('stt_route') == 'provider'
                ):
                    raise ProjectionBlocked('idle missing GPU upload required')
            return binding, jobs, missing

        return self.store.run(read)

    def restore_reupload(self, uid, content_id, snapshots, uris, now):
        """Reclaim only missing inputs, retaining owner, dedupe and charge checkpoints.

        A fresh legacy owner would use different per-segment IDs and cannot
        dedupe batch projections. Reuse this exact upload and queue only the
        absent units; projected siblings never re-enter compute or assignment.
        """
        from database.batch_pipeline_staging import artifact_id
        from utils.batch_pipeline.scheduler import Scheduler
        from database.batch_pipeline_projection import held_without_recovery

        if not snapshots or set(snapshots) != set(uris):
            raise ProjectionBlocked('complete missing-input repair set required')

        def commit(tx):
            ledger, binding, jobs = self._reupload_content(tx, uid, content_id)
            missing = {job['segment_id']: job for job in jobs if artifact_missing(job)}
            if set(missing) != set(snapshots):
                raise ProjectionBlocked('missing-input repair cohort changed')
            owner = tx.get('owners', owner_key(uid))
            prepared = []
            for sid, job in missing.items():
                RecoveryStore(self.store).checked(tx, sid)
                uri = uris[sid]
                parsed = urlsplit(uri)
                reservation = tx.get('artifacts', artifact_id(sid, uri))
                expiring = input_expiring(job)
                if (
                    job != snapshots[sid]
                    or not held_without_recovery(job)
                    or (
                        not expiring
                        and job['artifact_disposition'].get('privacy_generation') != binding.privacy_generation
                    )
                    or (
                        not expiring
                        and job['artifact_disposition'].get('evidence', {}).get('uri_sha256')
                        != hashlib.sha256(job['audio_uri'].encode()).hexdigest()
                    )
                    or tx.get('results', sid)
                    or parsed.scheme != 'gs'
                    or not re.fullmatch(r'[1-9][0-9]{0,19}', parsed.fragment)
                    or uri == job.get('audio_uri')
                    or reservation.get('owner_id') != uid
                    or reservation.get('privacy_generation') != binding.privacy_generation
                    or reservation.get('segment_id') != sid
                    or reservation.get('kind') != 'audio'
                    or reservation.get('uri', '').split('#')[0] != uri.split('#')[0]
                    or reservation.get('cleanup_after')
                    or reservation.get('erasure_requested')
                ):
                    raise ProjectionBlocked('repair input or staging reservation changed')
                prepared.append((sid, job, uri, reservation))
            # All authority and staging reads precede queue/artifact writes.
            for sid, job, uri, reservation in prepared:
                reservation.pop('write_pending_until', None)
                tx.put('artifacts', artifact_id(sid, uri), reservation)
                job['audio_uri'] = uri
                job['audio_staged_at'] = now
                job['artifact_disposition'] = {
                    **(job.get('artifact_disposition') or {}),
                    'state': 'restored',
                    'restored_at': now,
                    'restored_uri_sha256': hashlib.sha256(uri.encode()).hexdigest(),
                }
                if input_expiring(job):
                    # The existing restore CAS requires a dormant quarantined
                    # unit. Paid history and sibling receipts remain untouched.
                    job.update(state='quarantined', recovery_state='failed_held', merge_pending=False)
                Scheduler.restore_audio_in_transaction(tx, job, now)
            # Keep partial status and usage_steps: changing it to processing
            # would charge already projected speech a second time on completion.
            ledger['artifact_reupload'] = {'segment_ids': list(snapshots), 'restored_at': now}
            ledger.pop('artifact_missing_units', None)
            ledger['updated_at'] = datetime.fromtimestamp(now, timezone.utc)
            ledger['expires_at'] = datetime.fromtimestamp(now, timezone.utc) + timedelta(days=LEDGER_RETENTION_DAYS)
            owner['revision'] = owner.get('revision', 0) + 1
            tx.put('owners', owner_key(uid), owner)
            tx.put('content', f'{uid}/{content_id}', ledger)
            return binding.job_id

        return self.store.run(commit)

    def apply(self, segment_id, snapshot, evidence, plan_digest, now):
        """CAS the exact idle held unit and its content/privacy fences.

        The caller obtains fresh evidence from ArtifactStore.missing_audio_evidence;
        unknown/error metadata never reaches this transaction as proof. No ledger
        ownership is released here: whole-content re-upload needs a separate
        dedupe proof before it can take custody from this job.
        """
        from database.batch_pipeline_projection import held_without_recovery

        def commit(tx):
            job, binding = RecoveryStore(self.store).checked(tx, segment_id)
            result = tx.get('results', segment_id)
            owner = tx.get('owners', owner_key(binding.owner_id))
            ledger = tx.get('content', f'{binding.owner_id}/{binding.content_id}')
            marker = job.get('artifact_disposition') or {}
            current = {key: value for key, value in job.items() if key != 'artifact_disposition'}
            if current != snapshot or not re.fullmatch(r'[0-9a-f]{64}', plan_digest):
                raise ProjectionBlocked('artifact disposition snapshot changed')
            if marker:
                if (
                    marker.get('state') != 'missing'
                    or marker.get('plan_digest') != plan_digest
                    or marker.get('snapshot_sha256') != fingerprint(snapshot)
                    or marker.get('privacy_generation') != binding.privacy_generation
                ):
                    raise ProjectionBlocked('artifact disposition changed')
                return True
            generation = urlsplit(job.get('audio_uri', '')).fragment
            verified_at = evidence.get('verified_at')
            if (
                not re.fullmatch(r'[1-9][0-9]{0,19}', generation)
                or type(evidence.get('generation')) is not int
                or evidence.get('generation') != int(generation)
                or evidence.get('status') != 404
                or evidence.get('uri_sha256') != hashlib.sha256(job['audio_uri'].encode()).hexdigest()
                or type(verified_at) not in (int, float)
                or not math.isfinite(verified_at)
                or not 0 <= now - verified_at <= PROOF_MAX_AGE_SECONDS
            ):
                raise ProjectionBlocked('fresh generation-pinned metadata 404 required')
            if (
                not held_without_recovery(job)
                or job.get('recovery_state') != 'failed_held'
                or job.get('quarantine_reason') != 'worker_failed'
                or job.get('token')
                or job.get('lease_until', 0) > now
                or job.get('merge_pending') is not False
                or result
            ):
                raise ProjectionBlocked('idle failed-held unit required')
            job['artifact_disposition'] = {
                'state': 'missing',
                'evidence': deepcopy(evidence),
                'verified_at': verified_at,
                'plan_digest': plan_digest,
                'snapshot_sha256': fingerprint(snapshot),
                'privacy_generation': binding.privacy_generation,
            }
            # Wake projection probes without changing the owner/worker cursor.
            owner['revision'] = owner.get('revision', 0) + 1
            hints = ledger.get('artifact_missing_units') or []
            if not isinstance(hints, list) or not set(hints) <= set(binding.segment_ids):
                raise ProjectionBlocked('artifact disposition content hints changed')
            ledger['artifact_missing_units'] = sorted(set(hints) | {segment_id})
            tx.put('owners', owner_key(binding.owner_id), owner)
            tx.put('jobs', segment_id, job)
            tx.put('content', f'{binding.owner_id}/{binding.content_id}', ledger)
            return True

        return self.store.run(commit)
