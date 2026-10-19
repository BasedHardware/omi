#!/usr/bin/env python3
"""Loopback-only real query/transaction, stage/seal race and operation proof."""

import os
import asyncio
import subprocess
import time
from types import SimpleNamespace
import sys
import tempfile
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_held_audio_emulator_secret_key_32_bytes')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
from google.api_core.exceptions import NotFound, PreconditionFailed
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.types import Document
from google.cloud.firestore_v1.transaction import Transaction
from database import cap_hold_redrive as redrive, legal_holds, processing_backlog, sync_cap_recovery
from utils.sync import cap_hold, live_cap_capacity as capacity, live_cap_staging as staging
from utils.sync.live_cap_publication import Publication


class Bucket:
    __module__ = 'google.cloud.storage.bucket'

    def __init__(self):
        self.objects = {}
        self.uploads = self.composes = self.deletes = 0
        self.generation = 0
        self.lose_upload_reply = self.lose_compose_reply = False

    def blob(self, name, generation=None):
        bucket = self

        class Blob:
            def __init__(self):
                self.name = name
                self.generation = generation

            @property
            def size(self):
                return len(bucket.objects[name][1])

            def reload(self, **kwargs):
                if name not in bucket.objects:
                    raise NotFound('missing')
                self.generation = bucket.objects[name][0]

            def upload_from_file(self, stream, **kwargs):
                assert kwargs['if_generation_match'] == 0 and kwargs['retry'] is None and kwargs['timeout'] == 10
                data = stream.read()
                assert kwargs['size'] == len(data)
                self.put(data)
                bucket.uploads += 1
                if bucket.lose_upload_reply:
                    bucket.lose_upload_reply = False
                    raise TimeoutError('lost upload reply')

            def put(self, data):
                if name in bucket.objects:
                    raise PreconditionFailed('immutable')
                bucket.generation += 1
                self.generation = bucket.generation
                bucket.objects[name] = (self.generation, data)

            def compose(self, sources, **kwargs):
                assert len(sources) <= 4
                assert kwargs == {'if_generation_match': 0, 'timeout': 10, 'retry': None}
                for source in sources:
                    assert bucket.objects[source.name][0] == source.generation
                self.put(b''.join(bucket.objects[source.name][1] for source in sources))
                bucket.composes += 1
                if bucket.lose_compose_reply:
                    bucket.lose_compose_reply = False
                    raise TimeoutError('lost compose reply')

            def delete(self, **kwargs):
                if name not in bucket.objects:
                    raise NotFound('missing')
                if kwargs.get('if_generation_match') != bucket.objects[name][0]:
                    raise PreconditionFailed('generation')
                bucket.objects.pop(name)
                bucket.deletes += 1

            def download_to_file(self, stream):
                stream.write(bucket.objects[name][1])

        return Blob()


def worker_patches(stack, client):
    from utils import processing_backlog_worker as worker

    stack.enter_context(patch.object(processing_backlog, 'get_firestore_client', lambda: client))
    stack.enter_context(patch.object(legal_holds, 'account_deletion_firestore_client', lambda **kwargs: client))
    stack.enter_context(patch.object(worker.funded_processing, 'enabled', lambda: True))
    stack.enter_context(patch.object(worker.funded_processing, 'period_id', lambda: '2026-10'))
    stack.enter_context(patch.object(worker.funded_processing, 'allowance', lambda uid: SimpleNamespace(managed=True)))
    stack.enter_context(patch.object(worker.funded_processing, 'capacity', lambda current: (100, 100)))
    stack.enter_context(patch.object(worker.cap_hold, 'recovery_cooldown', lambda uid: True))
    return worker


def crash_child(owner, marker, phase):
    client = firestore.Client(project='demo-held-audio', credentials=AnonymousCredentials())
    with ExitStack() as stack:
        worker = worker_patches(stack, client)

        async def attempt(uid, item):
            Path(marker).write_text('provider request in flight')
            await asyncio.sleep(3600)

        snap = SimpleNamespace(id='same-piece', to_dict=lambda: {'started_at': 20, 'queued_at': 10, 'units': 1})
        stack.enter_context(
            patch.object(
                worker, '_page', lambda uid, kind, cursor: [('text', snap)] if kind == 'text' and not cursor else []
            )
        )
        stack.enter_context(patch.object(worker, '_process', attempt))

        async def run():
            if phase == 'sleep':
                Path(marker).write_text('lost 60s wakeup')
                await asyncio.sleep(60)
            await worker.run(owner, max_items=1)

        asyncio.run(run())


def prove_sigkill_resume(client, directory, prefix):
    from utils.sync import cap_hold_redrive as coordinator

    for phase in ('sleep', 'run'):
        owner = prefix + '-kill-' + phase
        processing_backlog.start(owner, period='2026-10', remaining=5, cutoff=100, request_key=owner)
        marker = Path(directory) / phase
        process = subprocess.Popen([sys.executable, __file__, '--crash-child', owner, str(marker), phase])
        try:
            deadline = time.monotonic() + 60
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            assert marker.exists(), ('child did not reach crash boundary', phase, process.poll())
            process.kill()  # Actual SIGKILL: no finally/release or client wakeup.
            process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        ref = processing_backlog.summary_ref(owner)
        row = ref.get().to_dict()
        assert row['state'] == 'processing'
        if phase == 'run':
            assert row['reserved']['id'] == 'same-piece' and row['remaining'] == 4
            # Advance the durable lease's clock without waiting 30 wall minutes.
            ref.update({'lease_until': 1})
        called = []
        with ExitStack() as stack:
            worker = worker_patches(stack, client)
            stack.enter_context(patch.object(coordinator.store, 'get_firestore_client', lambda: client))
            stack.enter_context(patch.object(worker, '_page', lambda *args: []))

            async def complete(uid, item):
                called.append((uid, item['id']))
                return worker.AttemptOutcome.COMPLETE

            stack.enter_context(patch.object(worker, '_process', complete))
            # Use the actual sweep and persisted discovery cursor. Other users
            # on earlier pages cannot hide this pre-existing choice.
            for _ in range(10):
                asyncio.run(coordinator.sweep())
                current = ref.get().to_dict()
                if current.get('state') != 'processing':
                    break
            assert ref.get().to_dict()['state'] == 'waiting_choice'
            assert ref.get().to_dict()['remaining'] == (4 if phase == 'run' else 5)
            assert called == ([(owner, 'same-piece')] if phase == 'run' else [])
    print('PASS actual SIGKILL mid-sleep and mid-run, lease expiry, scheduler-only resume, no double chosen debit')


def prove_pipeline_result_restart(client, directory, uid):
    from utils.sync import pipeline

    path = Path(directory) / '1792152000.wav'
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\0' * 32000)
    ref = cap_hold.holds(uid).document('pipeline-result')
    ref.set(
        {
            'lease_token': 'lease',
            'lease_until': time.time() + 1800,
            'piece_receipts': {'p': {'state': 'dispatched', 'attempt': 1, 'provider': 'modulate', 'model': 'velma-2'}},
        }
    )
    post = Mock(return_value=([{'text': 'usable synthetic transcript', 'timestamp': [0, 1]}], 'en'))
    parser = Mock(side_effect=RuntimeError('crash at first boundary after durable result'))
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {'STT_CAP_DISPATCH_ENFORCEMENT': 'true'}))
        for name, value in {
            'ambiguous_binding_pending': lambda *a: False,
            'sync_allowed': lambda *a: True,
            'funded_allowance': lambda *a: SimpleNamespace(reason='available'),
            'get_syncing_file_temporal_signed_url': lambda *a: 'http://synthetic.invalid',
            'schedule_syncing_temporal_file_deletion': Mock(),
            'keyterms': AsyncMock(return_value=[]),
            'prerecorded': post,
            'postprocess_words': parser,
        }.items():
            stack.enter_context(patch.object(pipeline, name, value))
        for _ in range(2):
            # Restart receives only a fresh real Firestore snapshot, never the
            # in-memory context mutated by the first process_segment call.
            receipt = ref.get().to_dict()['piece_receipts']['p']
            errors = []
            assert not pipeline.process_segment(
                str(path),
                uid,
                {},
                threading.Lock(),
                errors,
                cap_recovery=True,
                cap_recovery_service=('modulate', None, 'velma-2'),
                cap_recovery_checkpoint={
                    'hold_id': ref.id,
                    'piece': 'p',
                    'lease_token': 'lease',
                    'attempt': 1,
                    'receipt': receipt,
                },
            )
            assert errors
        assert parser.call_count == 2 and post.call_count == 1
        assert 'provider_result' in ref.get().to_dict()['piece_receipts']['p']
    print(
        'PASS actual process_segment -> encrypted Firestore checkpoint -> crash boundary -> restart; one provider POST'
    )


def main():
    if not os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        raise RuntimeError('requires loopback Firestore emulator')
    client = firestore.Client(project='demo-held-audio', credentials=AnonymousCredentials())
    uid = f'cap-durable-{uuid4().hex}'
    bucket = Bucket()
    counts = {'reads': 0, 'writes': 0}
    original_get, original_commit, original_update = (
        DocumentReference.get,
        Transaction._commit,
        DocumentReference.update,
    )

    def counted_get(ref, *args, **kwargs):
        counts['reads'] += 1
        return original_get(ref, *args, **kwargs)

    def counted_update(ref, *args, **kwargs):
        counts['writes'] += 1
        return original_update(ref, *args, **kwargs)

    def counted_commit(tx):
        counts['writes'] += len(tx._write_pbs)
        return original_commit(tx)

    with ExitStack() as stack, tempfile.TemporaryDirectory() as directory:
        for module in (cap_hold, capacity, staging, redrive, processing_backlog, sync_cap_recovery):
            stack.enter_context(patch.object(module, 'get_firestore_client', lambda: client))
        stack.enter_context(patch.object(legal_holds, 'account_deletion_firestore_client', lambda **kwargs: client))
        stack.enter_context(patch.object(cap_hold, 'get_private_cloud_sync_bucket', lambda: bucket))
        stack.enter_context(patch.dict(os.environ, {'OMI_ENV_STAGE': '', 'PROVIDER_MODE': ''}))
        cap_hold.summary_ref(uid).set({'version': 2, 'seconds': 0, 'count': 0})
        path = Path(directory) / 'part.opus'
        path.write_bytes(b'synthetic-codec-payload')
        meta = {
            'timestamp': 1792152000,
            'origin': 'live',
            'audio_codec': 'ogg_opus',
            'sample_rate': 16000,
            'source_frames': 240000,
            'source': 'omi',
        }
        with patch.object(DocumentReference, 'get', counted_get), patch.object(
            Transaction, '_commit', counted_commit
        ), patch.object(DocumentReference, 'update', counted_update):
            cap_hold.ensure_summary(uid)
            lease = capacity.acquire(uid, '2026-10', 'block')
            for _ in range(64):
                group = Publication(uid)
                for part in range(4):
                    staging.append(
                        uid,
                        str(path),
                        group,
                        Publication(uid),
                        {**meta, 'timestamp': meta['timestamp'] + part * 15},
                        15,
                    )
                    if part == 0:
                        lease.consume()
                assert staging.seal(uid, group.identity)
            capacity.release(lease)
        assert counts == {'reads': 1221, 'writes': 514}, counts
        assert (bucket.uploads, bucket.composes, bucket.deletes, len(bucket.objects)) == (256, 64, 256, 64)
        print(
            f'64-minute proof: {counts}, uploads={bucket.uploads}, composes={bucket.composes}, deletes={bucket.deletes}; retained_objects=64'
        )
        # Kill before seal: an expired durable staging row seals without writer memory.
        group, part = Publication(uid), Publication(uid)
        staging.append(uid, str(path), group, part, meta, 15)
        staging.append(uid, str(path), group, part, meta, 15)
        ref = cap_hold.holds(uid).document(group.identity)
        assert len(ref.get().to_dict()['stage_parts']) == 1
        assert not staging.seal(uid, group.identity, expired_only=True)
        ref.update({'writer_until': 0})
        assert staging.seal(uid, group.identity, expired_only=True)
        assert ref.get().to_dict()['seconds'] == 15
        # An immutable orphan's stored length wins over encoder randomness on retry.
        random_group, random_part = Publication(uid), Publication(uid)
        original_bytes = path.read_bytes()
        cap_hold.upload_held_audio(uid, str(path), random_part.identity, meta, immutable=True)
        random_part.is_retry(uid)  # Model the first put dying before manifest commit.
        path.write_bytes(original_bytes + b'changed-encoder-container-length')
        row = staging.append(uid, str(path), random_group, random_part, meta, 15)
        assert row['stage_parts'][0]['bytes'] == len(original_bytes)
        path.write_bytes(original_bytes)
        # Recovery/purge keeps fragment membership as a late-writer barrier.
        ref.set({'state': 'purged', 'live_custody_version': 4, 'stage_fragment_ids': [part.identity]})
        uploads = bucket.uploads
        staging.append(uid, str(path), group, part, meta, 15)
        assert bucket.uploads == uploads and ref.get().to_dict()['state'] == 'purged'
        # Concurrent recovery/seal callers publish one summary increment.
        racing = Publication(uid)
        staging.append(uid, str(path), racing, Publication(uid), meta, 15)
        total_before = cap_hold.summary_ref(uid).get().to_dict()['count']
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: staging.seal(uid, racing.identity), range(2)))
        assert cap_hold.summary_ref(uid).get().to_dict()['count'] == total_before + 1
        # Lost compose reply freezes layout first, and retries never change published bytes.
        group, part = Publication(uid), Publication(uid)
        staging.append(uid, str(path), group, part, meta, 15)
        bucket.lose_compose_reply = True
        try:
            staging.seal(uid, group.identity)
        except TimeoutError:
            pass
        ref = cap_hold.holds(uid).document(group.identity)
        assert ref.get().to_dict()['state'] == 'sealing'
        try:
            staging.append(uid, str(path), group, Publication(uid), meta, 15)
        except RuntimeError:
            pass
        else:
            raise AssertionError('sealing source accepted mutation')
        assert staging.seal(uid, group.identity, expired_only=True)
        assert ref.get().to_dict()['source_frames'] == 240000
        # Real collection-group cursor order and wrap, including pre-existing choices.
        owners = [f'{uid}-{i}' for i in range(12)]
        for owner in owners:
            processing_backlog.summary_ref(owner).set({'state': 'processing', 'token': owner, 'period': '2026-10'})
        client.collection('cap_hold_redrive').document('choices').delete()
        seen = set()
        for _ in range(4):
            rows = redrive.discover('choices')
            assert len(rows) <= redrive.PAGE
            seen.update(s.reference.parent.parent.id for s in rows)
        assert set(owners) <= seen
        # A SIGKILL lease expires; concurrent redrives have exactly one winner.
        owner = owners[0]
        summary = processing_backlog.summary_ref(owner)
        summary.update({'lease_until': 1, 'reserved': {'kind': 'audio', 'id': 'same-piece'}})
        with ThreadPoolExecutor(max_workers=4) as pool:
            leases = list(pool.map(lambda _: processing_backlog.claim(owner, owner, '2026-10'), range(4)))
        assert sum(value is not None for value in leases) == 1
        assert summary.get().to_dict()['reserved']['id'] == 'same-piece'
        # Provider result commit fences old owners and remains durable for restart.
        hold = cap_hold.holds(uid).document('provider-result')
        hold.set(
            {
                'lease_token': 'lease',
                'lease_until': 9999999999,
                'piece_receipts': {'p': {'state': 'dispatched', 'attempt': 1}},
            }
        )
        context = {'hold_id': hold.id, 'piece': 'p', 'lease_token': 'lease', 'attempt': 1}
        assert sync_cap_recovery.provider_checkpoint(uid, context, {'provider_result': 'encrypted-result'})
        assert not sync_cap_recovery.provider_checkpoint(
            uid, {**context, 'lease_token': 'stale'}, {'provider_result': 'bad'}
        )
        assert hold.get().to_dict()['piece_receipts']['p']['provider_result'] == 'encrypted-result'
        # Aggregate checkpoint budget uses the real SDK document encoding and
        # real transaction, preserves old ciphertext, and permits first ingestion.
        # Oracle: map-Value encoding contains the same document fields plus
        # an outer envelope. Production can avoid the additional types import
        # without ever under-counting aggregate result bytes.
        for probe in ({'result': 'x' * 900000}, {'nested': {'a': [1, None, True, 'opaque']}}):
            assert (
                _helpers.encode_value(probe)._pb.ByteSize()
                >= Document.pb(Document(fields=_helpers.encode_dict(probe))).ByteSize()
            )
        old = 'opaque-prior-result' * 35000
        hold.update({'piece_receipts.old': {'provider_result': old}})
        context['receipt'] = {}
        assert sync_cap_recovery.provider_checkpoint(uid, context, {'provider_result': 'x' * 200000})
        saved = hold.get().to_dict()['piece_receipts']
        assert saved['old']['provider_result'] == old
        assert saved['p']['provider_result'] == 'encrypted-result'
        assert saved['p']['provider_cache_omitted']
        # Choice persisted while its final live source is still staging: the
        # actual bounded query/worker must neither finish nor pass its cursor.
        owner = uid + '-preseal'
        group = Publication(owner)
        staging.append(owner, str(path), group, Publication(owner), meta, 15)
        created = cap_hold.holds(owner).document(group.identity).get().to_dict()['created_at']
        processing_backlog.start(owner, period='2026-10', remaining=100, cutoff=time.time(), request_key=owner)
        with ExitStack() as worker_stack:
            worker = worker_patches(worker_stack, client)
            processed = []

            async def complete_sealed(uid, item):
                assert cap_hold.holds(uid).document(item['id']).get().to_dict()['state'] == 'held'
                processed.append(item['id'])
                return worker.AttemptOutcome.COMPLETE

            worker_stack.enter_context(patch.object(worker, '_process', complete_sealed))
            asyncio.run(worker.run(owner, max_items=100, time_budget=900))
            assert processing_backlog.read(owner)['state'] == 'processing' and not processed
            assert staging.seal(owner, group.identity)
            assert cap_hold.holds(owner).document(group.identity).get().to_dict()['created_at'] == created
            asyncio.run(worker.run(owner, max_items=100, time_budget=900))
            assert processed == [group.identity] and processing_backlog.read(owner)['state'] == 'waiting_choice'
        print('PASS aggregate result budget and persisted pre-seal choice across actual query/transaction/seal')
        print(
            'PASS expired staging, immutable seal retry, bounded rotating discovery, concurrent lease claim, fenced provider result'
        )
        prove_pipeline_result_restart(client, directory, uid)
        prove_sigkill_resume(client, directory, uid)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--crash-child':
        crash_child(*sys.argv[2:])
    else:
        main()
