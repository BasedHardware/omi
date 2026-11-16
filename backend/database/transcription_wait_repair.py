"""One-time display-only observation for legacy queued audio missing seal clocks.

Never changes jobs, audio custody, wait generations, or first-admission metrics.
The caller enumerates a bounded owner scope; this CAS rechecks every sampled
job and only writes the separate observation when the original seal stamp and
an earlier observation are both absent.
"""

from datetime import datetime
import math

from google.cloud import firestore

from database._client import run_transactional

OBSERVED_FIELD = 'home_transcription_queue_observed_at'
ROW_FIELDS = [
    OBSERVED_FIELD,
    'record_admitted_at',
    'status',
    'record_lane_owner',
    'home_transcription_deadline_at',
    'episode_transcription_deadline_at',
    'deleted',
    'discarded',
    'is_locked',
    'record_projection_revision',
    'record_upload_failed',
    'record_audio_partial',
    'record_upload_sessions',
]
JOB_FIELDS = ['owner_id', 'conversation_id', 'state', 'audio_uri']


def observe_legacy_queue(client, uid, cid, job_refs, now, *, apply=False):
    if type(now) not in (int, float) or not math.isfinite(now) or now <= 0:
        raise ValueError('positive finite observation clock required')
    if len(job_refs) > 32:
        raise ValueError('bounded job scope required')
    row_ref = client.collection('users').document(uid).collection('conversations').document(cid)

    @firestore.transactional
    def commit(tx):
        row = row_ref.get(transaction=tx, field_paths=ROW_FIELDS, timeout=3, retry=None).to_dict() or {}
        if row.get(OBSERVED_FIELD) is not None or row.get('record_admitted_at') is not None:
            return 'already_stamped'
        if (
            row.get('status') != 'completed'
            or row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}
            or not any(
                isinstance(row.get(key), datetime)
                for key in ('home_transcription_deadline_at', 'episode_transcription_deadline_at')
            )
            or any(
                row.get(key)
                for key in (
                    'deleted',
                    'discarded',
                    'is_locked',
                    'record_projection_revision',
                    'record_upload_failed',
                    'record_audio_partial',
                    'record_upload_sessions',
                )
            )
            or not job_refs
        ):
            return 'row_ineligible'
        for ref in job_refs:
            job = ref.get(transaction=tx, field_paths=JOB_FIELDS, timeout=3, retry=None).to_dict() or {}
            if (
                job.get('owner_id') != uid
                or job.get('conversation_id') != cid
                or job.get('state') not in {'ready', 'retry'}
                or not job.get('audio_uri')
            ):
                return 'job_ineligible'
        if apply:
            tx.update(row_ref, {OBSERVED_FIELD: now})
        return 'observed' if apply else 'eligible'

    return run_transactional(client, commit, transient=True)
