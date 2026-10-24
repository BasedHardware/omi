#!/usr/bin/env python3
"""Real Firestore cursor/CAS contract; run only against an isolated emulator."""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('ENCRYPTION_SECRET', 'quiet_replay_emulator_only_secret_32_bytes')

from google.cloud import firestore
from database import conversation_finalization_jobs as jobs
from database import conversation_quiet_checks as checks
from services import conversation_finalization as service


def main():
    assert os.environ.get('FIRESTORE_EMULATOR_HOST'), 'emulator required'
    project = os.environ.get('GOOGLE_CLOUD_PROJECT', 'demo-quiet-replay')
    assert project.startswith('demo-'), 'isolated demo project required'
    client = firestore.Client(project=project)
    col = client.collection(jobs.FINALIZATION_JOBS_COLLECTION)
    now = datetime.now(timezone.utc)
    # A page full of stuck rows must not hide the valid check behind it, even
    # when backoff also fails. This exercises the real SDK's implicit name
    # ordering, value cursor, and committed cursor transaction across passes.
    batch = client.batch()
    for i in range(101):
        batch.set(
            col.document(f'quiet-{i:03}'),
            {
                'kind': 'listen_quiet_check',
                'status': 'waiting_quiet',
                'dispatch_generation': 1,
                'due_at': now - timedelta(hours=1),
                'reconcile_after_at': now - timedelta(hours=1),
            },
        )
    batch.commit()
    processed = []

    def run(job_id, generation, **kwargs):
        if job_id == 'quiet-100':
            processed.append(job_id)
            col.document(job_id).update({'status': 'quiet_done', 'reconcile_after_at': firestore.DELETE_FIELD})
            return 'done'
        return 'stale'

    with patch.object(service, 'is_listen_finalization_dispatch_enabled', return_value=True), patch.object(
        jobs, 'recover_stranded_byok_jobs', return_value={'blocked': 0, 'errors': 0}
    ), patch.object(service, '_publish_job_metrics'), patch.object(
        service.quiet_finalization, 'run', side_effect=run
    ), patch.object(
        jobs, 'defer_finalization_replay', return_value=False
    ):
        first = service.reconcile_listen_finalization_jobs(limit=100, firestore_client=client)
        assert first['stale'] == 100 and first['requeued'] == 0
        second = service.reconcile_listen_finalization_jobs(limit=100, firestore_client=client)
        assert second['retired'] == 1 and processed == ['quiet-100']

    # Reset, capture a full page, mutate/delete its last row. The persisted
    # ordered value must still select the next row, not its new future position.
    state = client.collection('conversation_recovery_state').document('finalization_replay')
    state.delete()
    col.document('quiet-100').set({'status': 'queued', 'reconcile_after_at': now - timedelta(hours=1)})
    page = jobs.get_finalization_replay_candidates(firestore_client=client)
    assert len(page) == 100
    col.document(page[-1]['job_id']).delete()
    assert [j['job_id'] for j in jobs.get_finalization_replay_candidates(firestore_client=client)] == ['quiet-100']
    assert jobs.get_finalization_replay_oldest_overdue_age_seconds(firestore_client=client) >= 3600
    # Exhaustion wraps, and the elevated cap actually reaches beyond 100.
    assert len(jobs.get_finalization_replay_candidates(limit=1000, firestore_client=client)) == 100
    # Exercise the real evaluate transaction and SDK field deletion, rather
    # than relying on the narrow unit fixture's DELETE_FIELD sentinel.
    missing = col.document('quiet-missing-conversation')
    missing.set(
        {
            'kind': 'listen_quiet_check',
            'status': 'waiting_quiet',
            'dispatch_generation': 1,
            'uid': 'synthetic-emulator',
            'conversation_id': 'absent',
            'quiet_timeout_seconds': 120,
            'due_at': now - timedelta(hours=1),
            'reconcile_after_at': now - timedelta(hours=1),
        }
    )
    assert checks.quiet_deadline({}) is None
    assert jobs.recovery_admission_refusal('synthetic-emulator', {}, now) == 'status'
    result = checks.evaluate_quiet_check(missing.id, 1, firestore_client=client)
    retired = missing.get().to_dict()
    assert result == {'status': 'done', 'reason': 'missing_conversation'}
    assert retired['status'] == 'quiet_done' and 'reconcile_after_at' not in retired
    assert retired['updated_at'] >= now
    print(
        'PASS: 101-row starvation, deleted boundary, wrap, increased limit, oldest age, missing-conversation retirement'
    )


if __name__ == '__main__':
    main()
