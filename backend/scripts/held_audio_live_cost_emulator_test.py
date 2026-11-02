#!/usr/bin/env python3
"""Loopback-only cost counters, real transaction retries and deletion ordering."""

import asyncio
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_held_audio_emulator_secret_key_32_bytes')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
from google.api_core.exceptions import Aborted, NotFound, PreconditionFailed
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.transaction import Transaction
from google.cloud.firestore_v1.batch import WriteBatch
from database import legal_holds
from utils.sync import cap_hold, live_cap_capacity as capacity, live_cap_manifest as manifest
from utils.sync.live_cap_publication import Publication


class Bucket:
    # Exercise the *real* nested owner_storage_write_gate, not its fake shortcut.
    __module__ = 'google.cloud.storage.bucket'

    def __init__(self):
        self.objects = {}
        self.generations = {}
        self.generation_counter = 0
        self.fail_next_upload_reply = False
        self.uploads = 0
        self.barrier = None

    def blob(self, name):
        bucket = self

        class Blob:
            generation = None

            def reload(self, **kwargs):
                if name not in bucket.objects:
                    raise NotFound('missing source')
                self.generation = bucket.generations.get(name, 1)

            def delete(self, **kwargs):
                expected = kwargs.get('if_generation_match')
                if expected and bucket.generations.get(name, 1) != expected:
                    raise PreconditionFailed('generation changed')
                bucket.objects.pop(name, None)
                bucket.generations.pop(name, None)

            def upload_from_file(self, stream, **kwargs):
                assert kwargs == {
                    'content_type': 'application/octet-stream',
                    'if_generation_match': 0,
                    'timeout': 10,
                    'retry': None,
                    'size': len(b'synthetic-codec-payload') + 32,
                }
                bucket.uploads += 1
                if bucket.barrier:
                    bucket.barrier()
                if name in bucket.objects:
                    raise PreconditionFailed('immutable object already exists')
                bucket.objects[name] = stream.read()
                bucket.generation_counter += 1
                self.generation = bucket.generation_counter
                bucket.generations[name] = self.generation
                if bucket.fail_next_upload_reply:
                    bucket.fail_next_upload_reply = False
                    raise TimeoutError('synthetic lost successful upload reply')

        return Blob()


def main():
    if not os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        raise RuntimeError('requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-held-audio', credentials=AnonymousCredentials())
    uid = f'held-cost-{uuid4().hex}'
    bucket = Bucket()
    original_get, original_commit = DocumentReference.get, Transaction._commit
    counts = {'reads': 0, 'writes': 0}

    def get(ref, *args, **kwargs):
        counts['reads'] += 1  # Includes missing-doc reads and ready-summary read.
        return original_get(ref, *args, **kwargs)

    def commit(tx):
        counts['writes'] += len(tx._write_pbs)  # Includes each summary transform as one doc write.
        return original_commit(tx)

    with ExitStack() as stack, tempfile.TemporaryDirectory() as directory:
        for module in (cap_hold, capacity, manifest):
            stack.enter_context(patch.object(module, 'get_firestore_client', lambda: client))
        stack.enter_context(patch.object(legal_holds, 'account_deletion_firestore_client', lambda **kwargs: client))
        stack.enter_context(patch.object(cap_hold, 'get_private_cloud_sync_bucket', lambda: bucket))
        # Do not set local/offline: that would bypass the storage gate under test.
        stack.enter_context(patch.dict(os.environ, {'OMI_ENV_STAGE': '', 'PROVIDER_MODE': ''}))
        path = str(Path(directory) / 'minute.opus')
        Path(path).write_bytes(b'synthetic-codec-payload')
        metadata = {
            'timestamp': 1792152000,
            'audio_codec': 'ogg_opus',
            'sample_rate': 16000,
            'source_frames': 960000,
            'source': 'omi',
            'origin': 'live',
        }
        cap_hold.summary_ref(uid).set({'version': 2, 'seconds': 0, 'count': 0})
        sources = {i: Publication(uid) for i in range(64)}
        with patch.object(DocumentReference, 'get', get), patch.object(Transaction, '_commit', commit):
            cap_hold.ensure_summary(uid)
            lease = capacity.acquire(uid, '2026-10', 'block')
            for i in range(64):
                lease.consume()
                manifest.publish(uid, path, sources[i], metadata, 60)
            capacity.release(lease)
        assert counts == {'reads': 133, 'writes': 130}, counts
        assert bucket.uploads == 64, bucket.uploads
        print(f"64-minute cost proof: {counts}, uploads={bucket.uploads}; per minute R={133/64}, W={130/64}, uploads=1")
        total = cap_hold.summary_ref(uid).get().to_dict()
        assert total == {'version': 2, 'seconds': 3840.0, 'count': 64}
        # A partial block is refunded once; ambiguous acquire replies are idempotent.
        before = client.document(f'users/{uid}/stt_cap_live_storage/2026-10').get().to_dict()
        tail = capacity.acquire(uid, '2026-10', 'tail')
        assert capacity.acquire(uid, '2026-10', 'tail') == tail
        tail.consume()
        capacity.release(tail)
        capacity.release(tail)
        after = client.document(f'users/{uid}/stt_cap_live_storage/2026-10').get().to_dict()
        assert after['chunks'] == before['chunks'] + 1
        assert after['bytes'] == before['bytes'] + capacity.SLOT_BYTES
        # SDK automatic retry: immutable upload + atomic create/increment.
        abort = True

        def aborted_commit(tx):
            nonlocal abort
            if abort:
                abort = False
                raise Aborted('synthetic commit abort')
            return original_commit(tx)

        aborted = Publication(uid)
        with patch.object(Transaction, '_commit', aborted_commit):
            manifest.publish(uid, path, aborted, metadata, 60)
        assert cap_hold.summary_ref(uid).get().to_dict()['count'] == 65

        # Lost successful commit reply -> writer retry must not upload/count twice.
        def lost_reply(tx):
            original_commit(tx)
            raise RuntimeError('synthetic lost commit reply')

        lost = Publication(uid)
        with patch.object(Transaction, '_commit', lost_reply):
            try:
                manifest.publish(uid, path, lost, metadata, 60)
            except (RuntimeError, ValueError):
                pass  # SDK rollback may mask a simulated lost successful commit reply.
            else:
                raise AssertionError('lost reply was not injected')
        uploads = bucket.uploads
        manifest.publish(uid, path, lost, metadata, 60)
        assert bucket.uploads == uploads
        assert cap_hold.summary_ref(uid).get().to_dict()['count'] == 66
        ref = cap_hold.holds(uid).document(lost.identity)
        assert cap_hold.claim(uid, ref, cap_hold.time.time())  # Immediately sealed.
        bucket.objects.pop(f'chunks/{uid}/cap-held/{lost.identity}.opus.enc')
        ref.set({'state': 'purged', 'live_custody_version': 4})
        manifest.publish(uid, path, lost, metadata, 60)
        assert bucket.uploads == uploads and ref.get().to_dict()['state'] == 'purged'

        unknown = Publication(uid)
        bucket.fail_next_upload_reply = True
        try:
            manifest.publish(uid, path, unknown, metadata, 60)
        except TimeoutError:
            pass
        else:
            raise AssertionError('ambiguous upload reply was not injected')
        unknown_path = f'chunks/{uid}/cap-held/{unknown.identity}.opus.enc'
        assert unknown_path not in bucket.objects
        assert not cap_hold.holds(uid).document(unknown.identity).get().exists
        manifest.publish(uid, path, unknown, metadata, 60)
        assert unknown_path in bucket.objects

        # Real GCS generations change after delete/recreate. A second ambiguous
        # upload must not reuse the generation receipt from a cleaned attempt.
        repeated = Publication(uid)
        repeated_path = f'chunks/{uid}/cap-held/{repeated.identity}.opus.enc'

        def rejected_commit(tx):
            raise RuntimeError('synthetic failed publication')

        with patch.object(Transaction, '_commit', rejected_commit):
            try:
                manifest.publish(uid, path, repeated, metadata, 60)
            except RuntimeError:
                pass
            else:
                raise AssertionError('commit failure not injected')
        assert repeated_path not in bucket.objects
        bucket.fail_next_upload_reply = True
        try:
            manifest.publish(uid, path, repeated, metadata, 60)
        except TimeoutError:
            pass
        else:
            raise AssertionError('second upload reply failure not injected')
        assert repeated_path not in bucket.objects, 'cleanup reused the previous generation'
        manifest.publish(uid, path, repeated, metadata, 60)
        assert repeated_path in bucket.objects

        # Context reuse is scoped to exact account, transaction AND client.
        @firestore.transactional
        def nested(tx):
            with legal_holds.external_write_fence(uid, firestore_client=client, transaction=tx):
                for kwargs in (
                    {'uid': 'other'},
                    {'uid': uid, 'transaction': object()},
                    {'uid': uid, 'firestore_client': object()},
                ):
                    try:
                        with legal_holds.external_write_fence(**kwargs):
                            raise AssertionError('authority switch was accepted')
                    except legal_holds.DestructiveOperationInProgress:
                        pass

        nested(client.transaction())
        assert legal_holds._EXTERNAL_TRANSACTION.get() is None
        # Count the real recovery coordinator's persistence, excluding the
        # pre-existing allowance/preferences, provider ingest and usage writers.
        from utils.sync import cap_hold_recovery as recovery
        from types import SimpleNamespace

        original_batch_commit = WriteBatch.commit

        def batch_commit(batch, *args, **kwargs):
            counts['writes'] += len(batch._write_pbs)
            return original_batch_commit(batch, *args, **kwargs)

        async def frozen_plan(uid, snapshot, row, meta, directory, prepare, save):
            pieces = {f'{i}.wav': {'seconds': 60 / pieces_count} for i in range(pieces_count)}
            assert await save(uid, snapshot, row, {'piece_plan': pieces})
            return pieces, {}, {}

        def processed(*args, **kwargs):
            kwargs['deferred_outcome']['provider_called'] = True
            return True

        async def recover_one(snapshot, row):
            assert await recovery._recover_row(uid, snapshot, row)
            assert await recovery._save(uid, snapshot, row, {'state': 'completed'})
            recovery._settle_and_erase(uid, snapshot, row)
            cap_hold.release(uid, snapshot.reference, row['lease_token'])

        for pieces_count in (1, 4):
            ref = cap_hold.holds(uid).document(sources[pieces_count].identity)
            snapshot = ref.get()
            counts = {'reads': 0, 'writes': 0}
            with ExitStack() as recovery_stack:
                recovery_stack.enter_context(patch.object(DocumentReference, 'get', get))
                recovery_stack.enter_context(patch.object(Transaction, '_commit', commit))
                recovery_stack.enter_context(patch.object(WriteBatch, 'commit', batch_commit))
                recovery_stack.enter_context(patch.object(recovery, 'enabled', lambda: True))
                recovery_stack.enter_context(patch.object(recovery, '_new_dispatch_allowed', lambda uid: True))
                recovery_stack.enter_context(
                    patch.object(recovery.users_db, 'get_user_transcription_preferences', lambda uid: {})
                )
                recovery_stack.enter_context(
                    patch.object(recovery.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)
                )
                recovery_stack.enter_context(patch.object(recovery, 'build_person_embeddings_cache', lambda uid: {}))
                recovery_stack.enter_context(patch.object(recovery.cap_recovery_plan, 'ensure_plan', frozen_plan))

                async def stage(*args):
                    return path, {}

                recovery_stack.enter_context(patch.object(recovery.cap_recovery_plan, 'stage_piece', stage))
                recovery_stack.enter_context(
                    patch.object(recovery, 'get_prerecorded_service', lambda language: ('modulate', 'en', 'model'))
                )
                recovery_stack.enter_context(patch.object(recovery, 'process_segment', processed))
                recovery_stack.enter_context(patch.object(recovery, 'record_usage', lambda *args, **kwargs: None))
                recovery_stack.enter_context(
                    patch.object(recovery, 'finalize_recovered_sync_segment', lambda *args: None)
                )
                row = cap_hold.claim(uid, ref, cap_hold.time.time())
                asyncio.run(recover_one(snapshot, row))
            assert ref.get().to_dict()['state'] == 'purged'
            print(
                f'Recovery coordinator {pieces_count} piece(s): {counts}; provider/ingest/usage and allowance reads excluded, one source GET modeled separately'
            )
        # A failed publication must clean an orphan even in a deployment using
        # optimistic concurrency. Rollback releases emulator locks, then inject
        # marker/purge/late-put before surfacing the failed commit to the writer.
        failed_uid = uid + '-failed'
        failed = Publication(failed_uid)
        failed_path = f'chunks/{failed_uid}/cap-held/{failed.identity}.opus.enc'

        def failed_commit(tx):
            tx._rollback()
            client.document(f'account_deletions/{failed_uid}').set({'wipe_status': 'in_progress'})
            bucket.objects.pop(failed_path, None)
            bucket.objects[failed_path] = b'synthetic late source'
            raise RuntimeError('synthetic optimistic conflict after deletion')

        with patch.object(Transaction, '_commit', failed_commit):
            try:
                manifest.publish(failed_uid, path, failed, metadata, 60)
            except (RuntimeError, ValueError):
                pass
            else:
                raise AssertionError('failed commit did not surface')
        assert failed_path not in bucket.objects
        assert not cap_hold.holds(failed_uid).document(failed.identity).get().exists
        client.document(f'account_deletions/{failed_uid}').delete()
        # Real concurrent marker write: starts during GCS upload, cannot finish
        # until the source transaction commits (or is retried and refused).
        original_uid, uid = uid, uid + '-race'
        bucket.objects.clear()  # Scope the deletion race to a fresh synthetic account.
        entered, release, deleting = threading.Event(), threading.Event(), threading.Event()

        def barrier():
            entered.set()
            assert release.wait(10)

        def delete_account():
            deleting.set()
            client.document(f'account_deletions/{uid}').set({'wipe_status': 'in_progress'})
            bucket.objects.clear()  # The existing owner-prefix purge follows marker acquisition.
            client.recursive_delete(client.document(f'users/{uid}'))

        bucket.barrier = barrier
        with ThreadPoolExecutor(max_workers=2) as pool:
            publication = pool.submit(manifest.publish, uid, path, Publication(uid), metadata, 60)
            assert entered.wait(5)
            deletion = pool.submit(delete_account)
            assert deleting.wait(5)
            assert not deletion.done()
            release.set()
            try:
                publication.result(timeout=20)
            except legal_holds.DestructiveOperationInProgress:
                pass  # Optimistic emulator conflict is also a valid serialization.
            deletion.result(timeout=20)
        bucket.barrier = None
        assert not bucket.objects and not list(cap_hold.holds(uid).stream())
        uploads = bucket.uploads
        try:
            manifest.publish(uid, path, Publication(uid), metadata, 60)
        except legal_holds.DestructiveOperationInProgress:
            pass
        else:
            raise AssertionError('deleted account accepted custody')
        assert bucket.uploads == uploads
        assert legal_holds._EXTERNAL_TRANSACTION.get() is None
        client.document(f'account_deletions/{uid}').delete()
        client.recursive_delete(client.document(f'users/{original_uid}'))
    print(
        'PASS: cost budget, nested gate reuse, reservation refund/retry, atomic/ambiguous retries, immediate lease, tombstone, deletion ordering'
    )


if __name__ == '__main__':
    main()
