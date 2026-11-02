"""Operator-only, metadata-proven absence. Never completes a custody job."""

from copy import deepcopy
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from utils.batch_pipeline.scheduler import owner_key

REASON_CODE = 'batch_artifact_missing'
PROOF_MAX_AGE_SECONDS = 30


def artifact_missing(job: dict) -> bool:
    # Fail closed even if a later writer changes the state around this marker.
    return (job.get('artifact_disposition') or {}).get('state') == 'missing'


def fingerprint(job: dict) -> str:
    return hashlib.sha256(json.dumps(job, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


class ArtifactMissingStore:
    def __init__(self, store):
        self.store = store

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
            tx.put('owners', owner_key(binding.owner_id), owner)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)
