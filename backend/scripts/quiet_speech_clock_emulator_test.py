"""PL-158: quiet discovery and admission agree on the persisted speech clock."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from google.cloud import firestore


def exercise_pl158_quiet_discovery_and_admission(client):
    from database import conversation_finalization_jobs as jobs
    from database import conversation_quiet_checks as quiet
    from utils.conversations.lifecycle import _finalization_admission
    from utils.conversations.processing_trigger import ProcessingTrigger

    speech = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timeout = timedelta(seconds=30)
    deadline = speech + timeout
    owner = client.collection('users').document('synthetic-pl158')
    for case in ('speech-only', 'legacy-heartbeat', 'speech-after-discovery'):
        conversation = jobs._conversation_ref(client, owner.id, case)
        fields = {
            'source': 'omi',
            'status': 'in_progress',
            'last_speech_at': speech,
            'data_protection_level': 'standard',
            'has_content': True,
            'transcript_segments': [{'text': 'synthetic speech', 'start': 0, 'end': 1}],
            'external_data': {'recording_session_id': case},
        }
        if case == 'legacy-heartbeat':
            fields['finished_at'] = speech + timedelta(hours=1)
        conversation.set(fields)
        owner.collection('recording_sessions').document(case).set(
            {
                'uid': owner.id,
                'conversation_id': case,
                'recording_session_id': case,
                'lifecycle_phase': 'in_progress',
                'lease_expires_at': deadline,
            }
        )
        with patch.object(quiet, '_now', return_value=speech):
            armed = quiet.arm_quiet_check(owner.id, case, timeout.total_seconds(), firestore_client=client)
        assert armed is not None and armed['due_at'] == deadline, (case, armed)

        with patch.object(quiet, '_now', return_value=deadline):
            wake = quiet.evaluate_quiet_check(armed['job_id'], armed['dispatch_generation'], firestore_client=client)
        assert wake['status'] == 'ready' and wake['recovery_cutoff'] == speech, (case, wake)

        is_stale = case == 'speech-after-discovery'
        now = deadline
        if is_stale:
            later_speech = speech + timedelta(seconds=1)
            conversation.update({'last_speech_at': later_speech})
            # The new quiet deadline has also passed, so only the old cutoff
            # can keep this stale evaluation from finalizing newer speech.
            now = later_speech + timeout

        before = conversation.get()
        with patch.object(jobs, '_now', return_value=now), patch.object(jobs, 'invalidate_people_stats_cache'):
            intent = jobs.create_or_get_finalization_intent(
                owner.id,
                case,
                requires_byok=False,
                finalization_admission=lambda row: _finalization_admission(row, case),
                trigger=ProcessingTrigger.SERVER_RECOVERY,
                recovery_cutoff=wake['recovery_cutoff'],
                require_expired_recording_lease=True,
                firestore_client=client,
            )
        after = conversation.get()
        quiet_job = client.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(armed['job_id']).get().to_dict()
        if is_stale:
            assert intent['status'] == 'refused_not_stale' and not intent['created'], intent
            assert after.update_time == before.update_time, after.to_dict()
            assert quiet_job['status'] == 'waiting_quiet', quiet_job
            assert quiet_job['dispatch_generation'] == wake['dispatch_generation'], quiet_job
            job_id = jobs._job_id(owner.id, case, 1)
            assert not client.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(job_id).get().exists
        else:
            assert intent['created'] and after.get('status') == 'processing', (case, intent)
            assert after.get('finalization_job_id') == intent['job_id'], after.to_dict()
            assert quiet_job['status'] == 'quiet_done' and 'reconcile_after_at' not in quiet_job, quiet_job
            assert client.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(intent['job_id']).get().exists


def main():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '').rsplit(':', 1)[0]
    if host not in {'127.0.0.1', 'localhost', '[::1]'}:
        raise SystemExit('loopback Firestore emulator required')
    with patch.dict(os.environ, {'LIFECYCLE_V2_MODE': 'serve', 'LISTEN_QUIET_FINALIZATION_ENABLED': 'true'}):
        exercise_pl158_quiet_discovery_and_admission(firestore.Client(project='demo-pl158-quiet-clock'))
    print('PASS: quiet discovery and admission share the speech clock in all three PL-158 cases')


if __name__ == '__main__':
    main()
