#!/usr/bin/env python3
"""Real Firestore cursor/CAS contract; run only against an isolated emulator."""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('ENCRYPTION_SECRET', 'quiet_replay_emulator_only_secret_32_bytes')

from google.cloud import firestore
from database import conversations, recording_sessions, proactivity, quiet_check_retirement
from database import oversized_conversation_terminal, stuck_backfill, user_data_deletion, batch_pipeline_purge
from database._client import delete_collection_recursive
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes
from config import stt_cap_dispatch
from models.conversation_enums import ConversationStatus
from database import conversation_finalization_jobs as jobs
from database import conversation_quiet_checks as checks
from services import conversation_finalization as service


def exercise_lifecycle_retirement(client):
    """Real commits + SDK field deletion across the public storage adapters."""
    uid = 'synthetic-retirement'
    col = client.collection('users').document(uid).collection('conversations')
    now = datetime.now(timezone.utc)

    def seed(cid, *, empty=False):
        row = {
            'id': cid,
            'source': 'omi',
            'status': 'in_progress',
            'created_at': now,
            'started_at': now,
            'finished_at': now,
            'has_content': not empty,
            'transcript_segments': [] if empty else [{'text': 'synthetic captured speech', 'start': 0, 'end': 1}],
            'data_protection_level': 'standard',
        }
        col.document(cid).set(row)
        armed = checks.arm_quiet_check(uid, cid, 120, firestore_client=client)
        assert armed is not None
        return client.collection('conversation_finalization_jobs').document(armed['job_id'])

    def retired(ref):
        row = ref.get().to_dict()
        assert row['status'] == 'quiet_done' and 'reconcile_after_at' not in row, row

    with ExitStack() as stack:
        stack.enter_context(patch.object(conversations, 'db', client))
        for module in (conversations, recording_sessions, jobs):
            stack.enter_context(patch.object(module, 'invalidate_people_stats_cache'))
        stack.enter_context(patch.object(conversations, '_sync_conversation_search_index'))
        stack.enter_context(patch.object(conversations, '_delete_conversation_search_index'))
        stack.enter_context(patch.object(conversations, 'leave_capture_group'))
        stack.enter_context(patch.object(proactivity, 'purge_source_items'))
        stack.enter_context(patch.object(stt_cap_dispatch, 'any_execution_admission_enabled', return_value=False))

        ref = seed('user-delete')
        conversations.delete_conversation(uid, 'user-delete')
        assert not col.document('user-delete').get().exists
        retired(ref)

        ref = seed('processing-rollback')
        old_generation = ref.get().to_dict()['dispatch_generation']
        assert conversations.claim_conversation_status(
            uid, 'processing-rollback', ConversationStatus.in_progress, ConversationStatus.processing
        )
        retired(ref)
        assert conversations.claim_conversation_status(
            uid, 'processing-rollback', ConversationStatus.processing, ConversationStatus.in_progress
        )
        restored = ref.get().to_dict()
        assert restored['status'] == 'waiting_quiet'
        assert restored['dispatch_generation'] == old_generation + 1
        assert restored['reconcile_after_at'] <= datetime.now(timezone.utc)
        checks.stop_quiet_check(ref.id, old_generation, firestore_client=client)
        assert ref.get().to_dict()['status'] == 'waiting_quiet'
        assert conversations.claim_conversation_status(
            uid, 'processing-rollback', ConversationStatus.in_progress, ConversationStatus.completed
        )
        retired(ref)

        ref = seed('empty-delete', empty=True)
        assert recording_sessions.tombstone_and_delete_empty_conversation(
            uid, 'empty-delete', None, firestore_client=client
        )
        retired(ref)

        ref = seed('capture-end')
        intent = jobs.create_or_get_finalization_intent(
            uid,
            'capture-end',
            requires_byok=False,
            finalization_admission=lambda row: {
                'accepted': True,
                'terminal': False,
                'reason': 'accepted',
                'fanout_key': 'synthetic-fanout',
            },
            firestore_client=client,
        )
        assert intent['created'] and col.document('capture-end').get().to_dict()['status'] == 'processing'
        retired(ref)

        for cid, writer in (
            (
                'status-complete',
                lambda cid: conversations.claim_conversation_status(
                    uid, cid, ConversationStatus.in_progress, ConversationStatus.completed
                ),
            ),
            ('discard', lambda cid: conversations.set_conversation_as_discarded(uid, cid)),
            ('legacy-transition', lambda cid: conversations.transition_conversation_status(uid, cid, 'failed')),
            (
                'processing-persist',
                lambda cid: conversations.persist_processing_result_with_lifecycle(
                    uid, {'id': cid, 'status': 'completed', 'data_protection_level': 'standard'}
                ),
            ),
            (
                'lifecycle-upsert',
                lambda cid: conversations.upsert_conversation_with_lifecycle(
                    uid, {'id': cid, 'status': 'completed', 'data_protection_level': 'standard'}
                ),
            ),
        ):
            ref = seed(cid)
            writer(cid)
            retired(ref)

        for cid, byok in (('dead-letter', False), ('byok-abandoned', True)):
            ref = seed(cid)
            job_id = 'terminal-' + cid
            col.document(cid).update(
                {'status': 'processing', 'finalization_job_id': job_id, 'finalization_revision': 1}
            )
            client.collection('conversation_finalization_jobs').document(job_id).set(
                {
                    'uid': uid,
                    'conversation_id': cid,
                    'status': 'blocked_byok' if byok else 'leased',
                    'requires_byok': byok,
                    'dispatch_generation': 1,
                    'lease_epoch': 1,
                    'finalization_revision': 1,
                    'fanout_status': 'pending',
                    'created_at': now - timedelta(days=2),
                    'updated_at': now - timedelta(days=2),
                    'lease_expires_at': now - timedelta(days=1),
                }
            )
            if byok:
                result = jobs.abandon_byok_finalization_job(
                    job_id,
                    expected_status='blocked_byok',
                    expected_dispatch_generation=1,
                    expected_lease_epoch=1,
                    abandoned_after=timedelta(days=1),
                    firestore_client=client,
                )
                assert result == {'status': 'abandoned', 'conversation_outcome': 'closed'}
            else:
                assert jobs.mark_finalization_dead_letter(job_id, 1, 1, 1, firestore_client=client)
            retired(ref)

        ref = seed('meeting-receipt')
        col.document('meeting-receipt').update({'status': 'completed'})
        receipt = jobs.record_meeting_receipt(
            uid,
            'meeting-receipt',
            finalization_job_id=None,
            eligible=False,
            reason='synthetic',
            duration_s=1,
            dedup_speech_s=1,
            firestore_client=client,
        )
        assert receipt['status'] == 'recorded'
        retired(ref)

        # Crash fallback adapters must also pay pre-existing quiet debt.
        for cid, fields, close in (
            (
                'orphan',
                {'status': 'processing', 'processing_admitted_at': now},
                lambda cid: jobs.complete_orphan_conversation(
                    uid, cid, expected_admitted_at=now, firestore_client=client
                ),
            ),
            (
                'unstampable',
                {'status': 'processing'},
                lambda cid: jobs.complete_unstampable_orphan_conversation(
                    uid, cid, stale_after=timedelta(0), firestore_client=client
                ),
            ),
            (
                'deferred-failure',
                {'status': 'processing', 'deferred': False},
                lambda cid: jobs.recover_deferred_processing_failure(uid, cid, firestore_client=client),
            ),
        ):
            ref = seed(cid)
            col.document(cid).update(fields)
            assert close(cid)
            retired(ref)

        # Use an actual near-ceiling document, with no estimator mock.
        ref = seed('oversized')
        row = col.document('oversized').get().to_dict()
        path = col.document('oversized').path
        row['oversized_fixture'] = b''
        size = estimate_firestore_document_bytes(row, path)
        row['oversized_fixture'] = b'x' * (FIRESTORE_MAX_DOCUMENT_BYTES - size - 40)
        col.document('oversized').set(row)
        assert (
            oversized_conversation_terminal.complete_oversized_in_progress_conversation(
                uid, 'oversized', quiet_for=timedelta(0), firestore_client=client
            )
            == 'closed'
        )
        retired(ref)

        ref = seed('noise-close', empty=True)
        snapshot = col.document('noise-close').get()
        stuck_backfill.close_noise(
            uid,
            'noise-close',
            expected_revision=stuck_backfill.revision(snapshot),
            cutoff=datetime.now(timezone.utc),
            expected_session_revision=None,
            run_id='synthetic-retirement-test',
            firestore_client=client,
        )
        retired(ref)

        # Cleanup from an old closure must preserve a reopened successor, while
        # terminal replay claims must really delete the indexed field in the SDK.
        ref = seed('reopened')
        assert not quiet_check_retirement.stop_quiet_check_for_conversation(uid, 'reopened', firestore_client=client)
        assert ref.get().to_dict()['status'] == 'waiting_quiet'
        terminal = client.collection('conversation_finalization_jobs').document('terminal-index')
        terminal.set({'status': 'completed', 'dispatch_generation': 1, 'reconcile_after_at': now})
        jobs.claim_finalization_replay(terminal.id, stale_after=timedelta(seconds=60), firestore_client=client)
        assert 'reconcile_after_at' not in terminal.get().to_dict()
        # Account erasure bypasses the single-conversation delete adapter and
        # must also remove global due indexes. Use the real recursive deleter.
        stack.enter_context(patch.object(batch_pipeline_purge, 'purge_batch_owner'))
        stack.enter_context(patch.object(user_data_deletion, 'get_data_plane_firestore_client', return_value=client))
        user_data_deletion.purge_user_subtree(uid, client, delete_collection_recursive)
        retired(ref)
        # Force several pages with equal UID index values; snapshot cursors
        # must retain the implicit document-name ordering across retirements.
        for number in range(5):
            cid = f'account-missing-{number}'
            client.collection('conversation_finalization_jobs').document(checks.quiet_check_id(uid, cid)).set(
                {
                    'kind': 'listen_quiet_check',
                    'status': 'waiting_quiet',
                    'uid': uid,
                    'conversation_id': cid,
                    'dispatch_generation': 1,
                    'reconcile_after_at': now,
                }
            )
        quiet_check_retirement.stop_quiet_checks_for_account(uid, firestore_client=client, page_size=2)
        for number in range(5):
            retired(
                client.collection('conversation_finalization_jobs').document(
                    checks.quiet_check_id(uid, f'account-missing-{number}')
                )
            )

    print(
        'PASS: user/empty deletion, capture_end, complete/discard/failed, processing persistence/upsert, live reopen and atomic processing rollback, orphan/deferred/oversized/noise fallback, dead-letter/BYOK/meeting terminal, account erasure and multipage cursor, terminal index deletion'
    )


def main():
    assert os.environ.get('FIRESTORE_EMULATOR_HOST'), 'emulator required'
    project = os.environ.get('GOOGLE_CLOUD_PROJECT', 'demo-quiet-replay')
    assert project.startswith('demo-'), 'isolated demo project required'
    client = firestore.Client(project=project)
    exercise_lifecycle_retirement(client)
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
    # A crash-reserved prefix must be revisited even if a full later page
    # becomes due every minute. Freeze the sweep's cutoff across invocations.
    for snapshot in col.stream():
        snapshot.reference.delete()
    state.delete()
    for key in ('a', 'b', 'c', 'd'):
        col.document(key).set({'reconcile_after_at': now - timedelta(hours=1)})
    clock = [now]
    with patch.object(jobs, '_now', side_effect=lambda: clock[0]):
        assert [j['job_id'] for j in jobs.get_finalization_replay_candidates(limit=2, firestore_client=client)] == [
            'a',
            'b',
        ]
        page = jobs.get_finalization_replay_candidates(limit=2, firestore_client=client)
        assert [j['job_id'] for j in page] == ['c', 'd']
        for row in page:
            col.document(row['job_id']).update({'reconcile_after_at': now + timedelta(seconds=60)})
        clock[0] += timedelta(seconds=60)
        assert jobs.get_finalization_replay_candidates(limit=2, firestore_client=client) == []
        assert [j['job_id'] for j in jobs.get_finalization_replay_candidates(limit=2, firestore_client=client)] == [
            'a',
            'b',
        ]
    print(
        'PASS: 101-row starvation, deleted boundary, wrap, increased limit, oldest age, missing-conversation retirement, crash-safe bounded sweep'
    )


if __name__ == '__main__':
    main()
