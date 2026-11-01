"""WQ20 atomic increments, rollback, external writers and memo races; loopback only.

Run from backend with FIRESTORE_EMULATOR_HOST=127.0.0.1:<owned-port> .venv/bin/python
scripts/fsr_people_generation_emulator_test.py. Uses anonymous credentials and a
unique synthetic owner; never falls through to cloud authentication.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from contextvars import Context
from datetime import datetime, timezone
from uuid import uuid4

# ruff: noqa: E402 -- synthetic emulator environment must precede backend imports.
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_wq20_synthetic_emulator_secret_32_bytes')

from google.api_core.exceptions import NotFound
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import _client, chat_edits, conversations, people, person_aliases, speaker_auto_enroll
from database import speaker_learning, speaker_learning_jobs, users, review_changes, review_store
from models.review import ReviewChange
from database.people_generation import generation_ref, read_people_generation, write_person
from utils.person_evidence_backfill import backfill_person
from utils.speakers import auto_enroll as policy


def main():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith('127.0.0.1:'):
        raise RuntimeError('requires an explicitly selected loopback Firestore emulator')
    os.environ['FIRESTORE_READ_LEVERS'] = '{"people_scan_dedupe":100}'
    os.environ.setdefault('ENCRYPTION_SECRET', 'omi_wq20_synthetic_emulator_secret_32_bytes')
    client = firestore.Client(project='demo-wq20-people', credentials=AnonymousCredentials())
    uid = 'wq20-' + uuid4().hex
    owner = client.collection('users').document(uid)
    ref = owner.collection('people').document('p')
    meta = generation_ref(owner)
    users.db = client
    checks = []
    now = datetime.now(timezone.utc)

    def count():
        return (meta.get().to_dict() or {}).get('generation', 0)

    def seed_person(**updates):
        write_person(
            client,
            ref,
            'set',
            dict(
                id='p',
                name='Alice',
                is_user_created=True,
                updated_at=now,
                speech_samples=['one.wav'],
                speech_sample_transcripts=['one'],
                **updates,
            ),
        )

    def check(label, operation, *, delta=1):
        before = count()
        with person_aliases.people_scan_attempt():
            person_aliases.list_people(client, uid, memoize=True)
            Context().run(operation)
            assert count() == before + delta, label
            hinted = person_aliases.list_people(client, uid, memoize=True)
            assert hinted == person_aliases.list_people(client, uid), label
        checks.append(label)

    try:
        owner.set(
            {
                'private_cloud_sync_enabled': True,
                'save_other_voice_profiles': True,
                'speaker_embedding': [1.0, *([0.0] * 255)],
            }
        )
        check('create_person', lambda: users.create_person(uid, {'id': 'p', 'name': 'Alice', 'updated_at': now}))
        check('rename', lambda: person_aliases.rename_person_retaining_aliases(client, uid, 'p', 'Alicia'))
        check('dismiss', lambda: person_aliases.dismiss_person_soft(client, uid, 'p'))
        seed_person()
        check('pin', lambda: people.set_person_pinned(uid, 'p', True, firestore_client=client))
        check('sample_add', lambda: users.add_person_speech_sample(uid, 'p', 'two.wav', 'two'))
        check('sample_remove', lambda: users.remove_person_speech_sample(uid, 'p', 'two.wav'))
        check('sample_transcript', lambda: users.set_person_speech_sample_transcript(uid, 'p', 0, 'updated'))
        check(
            'sample_migration',
            lambda: users.update_person_speech_samples_after_migration(uid, 'p', ['three.wav'], ['three'], 3),
        )
        check('clear_embedding', lambda: users.clear_person_speaker_embedding(uid, 'p'))
        check('sample_version', lambda: users.update_person_speech_samples_version(uid, 'p', 4))
        expected = ref.get().to_dict()['updated_at']
        check(
            'replace_profile',
            lambda: users._replace_speech_profile_transaction(
                client.transaction(),
                ref,
                expected,
                {
                    'speech_samples': ['four.wav'],
                    'speech_sample_transcripts': ['four'],
                    'speaker_embedding': [0.0, 1.0],
                },
                user_ref=owner,
            ),
        )
        check('invalidate_profile', lambda: users.invalidate_person_speech_profile(uid, 'p', 'c', ['s0']))
        expected = ref.get().to_dict()['updated_at']
        check(
            'learning_state',
            lambda: speaker_learning.update_person_voice_learning(
                uid,
                'p',
                expected,
                outcome='no_audio',
                state='unknown',
                speech_seconds=0,
                needed_seconds=10,
                firestore_client=client,
            ),
        )
        before = chat_edits.snapshot(uid, 'person', 'p', firestore_client=client)
        after = {}
        check(
            'chat_apply',
            lambda: after.update(
                chat_edits.apply_update(uid, 'person', 'p', before, {'name': 'Chat name'}, firestore_client=client)
            ),
        )
        check('chat_restore', lambda: chat_edits.restore(uid, 'person', 'p', after, before, firestore_client=client))
        review_store.client = lambda: client
        os.environ['REVIEW_SURFACE_MODE'] = 'on'
        change = ReviewChange(change_id='wq20-review', kind='update_person', title='Synthetic rename', created_at=now)
        check(
            'review_apply',
            lambda: review_changes.record_agent_change(
                uid,
                change,
                [review_changes.AgentEdit(collection='people', document_id='p', patch={'name': 'Review name'})],
                edit_key='wq20-review',
            ),
        )
        check('review_undo', lambda: review_changes.set_undone(uid, change.change_id, True))
        check('review_redo', lambda: review_changes.set_undone(uid, change.change_id, False))
        seed_person()
        source = owner.collection('conversations').document('c')
        segments = [
            dict(
                id=f's{i}',
                start=i * 6.0,
                end=i * 6.0 + 5,
                speaker_id=1,
                speaker_id_scope='capture',
                text='Synthetic speech.',
                person_id='p',
                is_user=False,
            )
            for i in range(2)
        ]
        source.set(
            {'id': 'c', 'status': 'completed', 'private_cloud_sync_enabled': True, 'transcript_segments': segments}
        )
        check(
            'assignment_effects',
            lambda: conversations.assign_conversation_speaker(
                uid, 'c', person_id='p', speaker_id=1, use_for_speech_training=True, firestore_client=client
            ),
        )
        claimed = {}
        check(
            'job_claim', lambda: claimed.update(speaker_learning_jobs.claim_next_job(uid, 'c', firestore_client=client))
        )
        check(
            'job_finish',
            lambda: speaker_learning_jobs.finish_job(
                uid, 'c', claimed['job_id'], claimed['lease_token'], 'insufficient_speech', firestore_client=client
            ),
        )
        # Backfill another explicitly labeled conversation with no prior evidence.
        source2 = owner.collection('conversations').document('c2')
        source2.set(
            {
                'transcript_segments': segments,
                'manual_speaker_assignments': {'generation': 1, 'speakers': {'1': {'person_id': 'p', 'generation': 1}}},
            }
        )
        check('evidence_backfill', lambda: backfill_person(client, uid, 'p', ['c2'], now, apply=True))
        # Publish retained vector-only evidence through the real authorization fence.
        source.update(
            {
                'manual_speaker_assignments': {
                    'generation': 1,
                    'speakers': {
                        '1': {'person_id': 'p', 'is_user': False, 'use_for_speech_training': True, 'generation': 1}
                    },
                }
            }
        )
        voice = [0.0, 1.0, *([0.0] * 254)]
        evidence = {
            s['id']: dict(binding=policy.binding(s), window=[s['start'], s['end']], seconds=5, vector=voice)
            for s in segments
        }
        expected = ref.get().to_dict()['updated_at']
        check(
            'auto_enroll_publish',
            lambda: speaker_auto_enroll.publish(
                uid, 'p', 'c', ['s0', 's1'], evidence, expected, 1, firestore_client=client
            ),
        )
        check(
            'auto_enroll_retract', lambda: speaker_auto_enroll.retract_conversation(uid, 'c', firestore_client=client)
        )
        # Privacy clears indexed profiles even when their pool was already retracted.
        check(
            'auto_enroll_privacy',
            lambda: speaker_auto_enroll.update_privacy(
                uid, {'save_other_voice_profiles': False}, firestore_client=client
            ),
        )
        check('auto_enroll_revoke', lambda: speaker_auto_enroll.revoke_person(uid, 'p', firestore_client=client))
        check('delete_person', lambda: users.delete_person(uid, 'p'), delta=2)
        seed_person()
        check(
            'recursive_people_delete',
            lambda: _client.delete_collection_recursive(owner.collection('people'), client=client),
        )
        seed_person()
        # Increment must compose: set without merge repeatedly stores 1, not N.
        before = count()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: write_person(client, ref, 'update', {'worker': i}), range(12)))
        assert count() == before + 12
        checks.append('concurrent_atomic_increments')
        before = count()
        try:
            write_person(client, owner.collection('people').document('missing'), 'update', {'name': 'missing'})
        except NotFound:
            pass
        else:
            raise AssertionError('missing-person write should fail')
        assert count() == before
        checks.append('failed_commit_does_not_bump')
        old = read_people_generation(client, uid)
        with person_aliases.people_scan_attempt():
            assert person_aliases.list_people(client, uid, memoize=True)[0]['name'] == 'Alice'
            meta.delete()
            assert read_people_generation(client, uid) is None
            # Recreated metadata may repeat its integer after account erasure.
            # Its commit timestamp must still retire the old memo entry.
            batch = client.batch()
            batch.update(ref, {'name': 'Recreated'})
            batch.set(meta, {'generation': old[0]})
            batch.commit()
            assert read_people_generation(client, uid) != old
            assert person_aliases.list_people(client, uid, memoize=True)[0]['name'] == 'Recreated'
        checks.append('metadata_recreation_cannot_reuse_old_token')
        print(f'PASS: {len(checks)} emulator checks: ' + ', '.join(checks))
    finally:
        client.recursive_delete(owner)
        client.close()


if __name__ == '__main__':
    main()
