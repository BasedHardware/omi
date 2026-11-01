"""Hermetic WQ21 investigation, NOT an implementation or a production test gate.

Run from the repository root with backend/.venv/bin/python. The real privacy
guard and real writer callbacks use the existing strict document transaction
fixture. It does not model Firestore snapshot isolation, contention or rollback.
"""

import json
import os
from pathlib import Path
import sys
from unittest.mock import patch


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'backend'))
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/dev/null'
    os.environ['ENCRYPTION_SECRET'] = 'synthetic-wq21-hermetic-secret-32-bytes-only'

    from testing.hermetic_network import block_outbound_network

    with block_outbound_network():
        from database import batch_pipeline_privacy as privacy
        from database import batch_pipeline_purge, conversation_tombstones, from_segments_chunks, speaker_auto_enroll
        from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument

        uid, cid = 'wq21-synthetic', 'source'
        generation_path = ('batch_pipeline_privacy', privacy.privacy_owner_key(uid))

        def database():
            return StrictFirestore(
                {
                    ('users', uid): {'data_protection_level': 'standard', 'private_cloud_sync_enabled': True},
                    generation_path: {'generation': 7},
                    ('users', uid, 'conversations', cid): {
                        'record_lane_owner': 'batch_live_v1',
                        'private_cloud_sync_enabled': True,
                    },
                }
            )

        def check(db, transaction=None, memo=None):
            return privacy.assert_batch_write_allowed(
                db,
                transaction or db.transaction(),
                uid,
                conversation_ids=[cid],
                expected_generation=7,
                memo=memo,
            )

        read_counts = {}
        original_get = StrictFirestoreDocument.get
        reads = []

        def get(reference, *args, **kwargs):
            reads.append(reference.path)
            return original_get(reference, *args, **kwargs)

        # Isolate the existing WQ12 gate without modifying runtime env values.
        for enabled, same_transaction, label in (
            (False, True, 'wq12_off_20_checks_one_transaction'),
            (True, True, 'wq12_on_20_checks_one_transaction'),
            (True, False, 'wq12_on_20_checks_20_transactions'),
        ):
            db = database()
            transaction = db.transaction()
            memo = privacy.BatchPrivacyMemo(db, transaction)
            reads.clear()
            with patch.object(privacy, 'lever_enabled', return_value=enabled), patch.object(
                StrictFirestoreDocument, 'get', get
            ):
                for _ in range(20):
                    if not same_transaction:
                        transaction = db.transaction()
                        memo = privacy.BatchPrivacyMemo(db, transaction)
                    assert check(db, transaction, memo) == 7
            expected = 5 if enabled and same_transaction else 100
            assert len(reads) == expected
            read_counts[label] = len(reads)

        counterexamples = []
        for writer, reason in (
            ('speaker_auto_enroll.update_privacy', 'recording_privacy_changed'),
            ('speaker_auto_enroll.retract_conversation', 'conversation_deleted'),
            ('conversation_tombstones.record_deletion', 'conversation_deleted'),
        ):
            db = database()
            assert check(db) == 7
            before = dict(db.rows[generation_path])
            if writer.endswith('update_privacy'):
                speaker_auto_enroll.update_privacy(uid, {'private_cloud_sync_enabled': False}, firestore_client=db)
            elif writer.endswith('retract_conversation'):
                speaker_auto_enroll.retract_conversation(uid, cid, firestore_client=db)
            else:
                # Inspect durable intent at the cleanup boundary. Both cleanup
                # functions are external effects, irrelevant to this commit.
                def cleanup_failed(*args, **kwargs):
                    raise RuntimeError('synthetic cleanup boundary')

                with patch.object(conversation_tombstones, 'db', db), patch.object(
                    from_segments_chunks, 'purge_chunks'
                ), patch.object(batch_pipeline_purge, 'purge_batch_owner', cleanup_failed):
                    try:
                        conversation_tombstones.record_deletion(uid, cid)
                    except RuntimeError as error:
                        assert str(error) == 'synthetic cleanup boundary'
                    else:
                        raise AssertionError('expected the synthetic cleanup boundary')
            assert db.rows[generation_path] == before == {'generation': 7}
            try:
                check(db)
            except privacy.BatchPrivacyBlocked as error:
                assert error.reason.value == reason
            else:
                raise AssertionError('live guard must deny after the real writer')
            counterexamples.append({'writer': writer, 'generation_before': 7, 'generation_after': 7, 'denial': reason})

        print(
            json.dumps(
                {
                    'status': 'BLOCKED_NO_IMPLEMENTATION',
                    'privacy_document_reads': read_counts,
                    'unchanged_generation_counterexamples': counterexamples,
                    'implemented_read_savings': 0,
                    'new_lever_registered': False,
                    'live_service_acceptance': 'NOT_RUN',
                },
                indent=2,
            )
        )


if __name__ == '__main__':
    main()
