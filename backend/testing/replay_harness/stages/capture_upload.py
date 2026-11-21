"""Observe persisted custody; optionally drive the real recorder seal transaction.

Fields/refusals: database/record_audio.py:17-45 (seal_record_audio), :48-85
(set_record_upload_pending), :90-113 (sticky record_upload_failed).
Recorder drain invokes that closer in utils/pusher_record_barrier.py:352-368.
A completed conversation is not proof of audio closure. Age is diagnostic only:
no timeout is allowed to clear another producer's token. ``seal`` explicitly
replays a recorder drain event; merely loading a captured case never invents one.
"""

from datetime import datetime, timezone

from testing.replay_harness.report import StageResult
from testing.replay_harness.seed import seed_case


def custody_reason(row, chunks):
    if row.get('record_upload_failed'):
        return 'upload_failed'
    if chunks == 0 and not row.get('record_audio_closed'):
        return 'empty_session'
    if row.get('record_upload_sessions'):
        return 'open_upload_session'
    if not row.get('record_audio_closed'):
        return 'audio_not_closed'
    return None


class CaptureUploadDriver:
    async def run(self, case, environment):
        ref = seed_case(case, environment)
        refusal = None
        if case.corpus.get('capture_upload', {}).get('seal'):
            from database.record_audio import seal_record_audio

            refusal = seal_record_audio(environment.replay_uid, environment.replay_cid)
        row = ref.get().to_dict()
        missing_buckets = set(case.manifest.prod_evidence.get('missing_input', []))
        complete = not missing_buckets.intersection({'BUCKET_PRIVATE_CLOUD_SYNC', 'BUCKET_AUDIO_DERIVED'})
        chunks = len(case.corpus.get('chunk_inventory', [])) if complete else None
        reason = custody_reason(row, chunks)
        created = row.get('created_at') or row.get('started_at')
        age = None
        if isinstance(created, datetime):
            snapshot_time = datetime.fromisoformat(case.manifest.created.replace('Z', '+00:00')).timestamp()
            age = max(0, snapshot_time - created.replace(tzinfo=created.tzinfo or timezone.utc).timestamp())
        return StageResult(
            'capture_upload',
            'stopped' if reason else 'pass',
            reason=f'capture_upload:{reason}' if reason else None,
            details={
                'age_seconds': age,
                'inventory_complete': complete,
                'chunks': chunks,
                'seal_refusal': refusal,
                'open_upload_sessions': len(row.get('record_upload_sessions') or {}),
                'audio_closed': row.get('record_audio_closed') is True,
            },
        )
