"""Production lifecycle operations over the stack's emulator and local objects.

Only GPU/provider leaves are synthetic. Registration, custody transactions,
drain discovery, scheduler leases, merge, projection and summary persistence
use their production implementations. Every tick is explicitly driven.
"""

import asyncio
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import random
import signal
import os
import time
import uuid

import httpx

from config.batch_pipeline_providers import ProviderConfig
from database import record_audio
from database.audio_timeline import span_blob_metadata
from database.batch_pipeline_store import FirestoreStore
from diarizer.batch_pipeline import PipelineWorker
from testing.lifecycle_sim.clock import age_job_row
from testing.lifecycle_sim.faults import BoundaryFault
from testing.lifecycle_sim.preflight import preflight
from testing.listen_pusher_stack.run import Stack, PYTHON, _wait_for_port
from testing.listen_pusher_stack.finalizer_leaves import install_finalizer_leaves
from testing.pipeline_sim.clock import VirtualClock, run_virtual
from testing.pipeline_sim.stt import FakeSTT, PlannedWords, SimSamples, SPEECH, STTProfile, vad_spans
from utils.batch_pipeline import live, record_seal_nojob, record_seal_sweeper
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
from utils.batch_pipeline.projection import Projector
from utils.batch_pipeline.serving import Serving
from utils.conversations.phase import derive_conversation_phase
from utils.conversations.factory import deserialize_conversation
from utils.conversations import process_conversation as processing
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.other.local_storage import create_storage_client
from utils.other.storage import upload_audio_chunks_batch

SERVER_FLAGS = {
    'K_SERVICE': 'lifecycle-simulator',
    'BATCH_PIPELINE_PERCENT': '100',
    'BATCH_LIVE_STT_RETIRE_PERCENT': '100',
}


class LifecycleSim:
    """Reusable WP-B fixture: one synthetic capture, bounded explicit ticks."""

    def __init__(self, stack: Stack, *, fault: BoundaryFault | None = None, stt_profile: STTProfile | None = None):
        preflight(stack.state_dir)
        self.stack = stack
        self.uid = 'synthetic-lifecycle-' + uuid.uuid4().hex[:12]
        self.cid = str(uuid.uuid4())
        self.fault = fault
        self.store = FirestoreStore(f'batch_pipeline_test_lifecycle_{self.cid[:8]}', firestore_client=stack.firestore)
        self.storage = create_storage_client()
        self.artifacts = artifacts_for(self.store)
        self.ref = stack.firestore.collection('users').document(self.uid).collection('conversations').document(self.cid)
        self.content, self.segment = live.record_identity(self.uid, self.cid)
        self.job_ref = stack.firestore.collection(f'{self.store.namespace}_jobs').document(self.segment)
        self.clock = VirtualClock()
        self.stt = FakeSTT(self.clock, stt_profile or STTProfile(latency_sigma=0), random.Random(0))
        self.words = PlannedWords()
        self.worker = PipelineWorker(
            decode=lambda item: SimSamples.for_seconds(item.segment_id, SPEECH, item.duration_seconds),
            vad=vad_spans,
            words_providers={'parakeet': self.words},
            diarizers={'pyannote': lambda samples: {'turns': []}},
            persist=self.artifacts.persist_result,
            config=ProviderConfig(),
            recover_words=self.words.recover_words,
            gpu_lock=nullcontext(),
            io_concurrency=1,
            language_of=lambda item: 'en',
        )
        self.projector = Projector(self.store, self.artifacts.load_result, publish=lambda *a, **kw: None)
        self.serving = Serving(self.store, projector=self.projector)
        self.ticks = 0
        self.reports = []
        self.proof_time = None

    def seed(self, *, sessions: dict | None = None) -> None:
        self.stack.seed_user(self.uid)
        start = datetime.now(timezone.utc) - timedelta(minutes=5)
        start = start.replace(microsecond=0)
        self.ref.set(
            {
                'id': self.cid,
                'created_at': start,
                'started_at': start,
                'finished_at': start + timedelta(seconds=2),
                'recorded_start': start,
                'recorded_end': start + timedelta(seconds=2),
                'status': 'completed',
                'record_lane_owner': 'batch_live_v1',
                'private_cloud_sync_enabled': True,
                'data_protection_level': 'standard',
                'language': 'en',
                'source': 'omi',
                'record_audio_closed': False,
                'record_upload_sessions': sessions or {},
                'record_upload_revision': 0,
                'transcript_segments': [],
                'photos': [],
                'structured': {'title': '', 'overview': '', 'emoji': '', 'category': 'other'},
                'discarded': False,
                'deleted': False,
            }
        )
        # Exact synthetic PCM object; real listing, generation pins, manifest,
        # privacy fences and encrypted artifact IO still execute.
        blob = self.storage.bucket(os.environ['BUCKET_PRIVATE_CLOUD_SYNC']).blob(
            f'chunks/{self.uid}/{self.cid}/{start.timestamp():.3f}.batch.bin'
        )
        blob.metadata = span_blob_metadata({'start': start.timestamp(), 'samples': 32000, 'sample_rate': 16000})
        blob.upload_from_string(b'\x01\x00' * 32000, if_generation_match=0)
        assert live.list_audio_chunks(self.uid, self.cid, require_archive=True), 'fixture has no retained audio'

    def row(self) -> dict:
        return self.ref.get().to_dict() or {}

    def reupload(self):
        start = self.row()['started_at'].timestamp()
        paths = upload_audio_chunks_batch(
            [
                {
                    'data': b'\x01\x00' * 32000,
                    'timestamp': start,
                    'span': {'start': start, 'samples': 32000, 'sample_rate': 16000},
                }
            ],
            self.uid,
            self.cid,
            'standard',
            sample_rate=16000,
        )
        assert paths, 'successful re-upload returned no durable source'
        return paths

    def job(self) -> dict:
        return self.job_ref.get().to_dict() or {}

    @property
    def phase(self):
        return derive_conversation_phase(self.row())

    def _boundary(self, name):
        if self.fault:
            self.fault.check(name, self.uid, self.cid)

    def seal(self):
        self._boundary('seal')
        return record_audio.seal_record_audio(self.uid, self.cid, firestore_client=self.stack.firestore)

    def register(self):
        self._boundary('register')
        return live.register_recording(self.uid, self.row(), store=self.store, server_flags=SERVER_FLAGS)

    def age(self, seconds=10 * 3600):
        if self.job():
            age_job_row(self.job_ref, seconds)

    def proof(self, *, live_producer=False):
        tokens = self.row().get('record_upload_sessions') or {}
        pods = {value['pod']: value['process_started_at'] for value in tokens.values() if isinstance(value, dict)}
        return {
            'namespace': 'prod-omi-backend',
            'captured_at': self.proof_time or time.time(),
            'resource_version': 'synthetic-1',
            'pods': pods if live_producer else {},
            'file_sha256': '0' * 64,
        }

    def sweep(self, *, live_producer=False):
        report = record_seal_sweeper.sweep(
            self.store,
            self.storage,
            self.artifacts,
            inventory=lambda: self.proof(live_producer=live_producer),
        )
        assert report['outcome'] == 'ok', 'fixture sweep failed before lifecycle classification'
        self.reports.append(report)
        return report

    def recover_nojob(self):
        plan = record_seal_nojob.plan_backfill(
            self.store,
            [self.ref.path],
            self.storage,
            self.artifacts,
            server_flags=SERVER_FLAGS,
            producer_proof=self.proof(),
        )
        dispositions = [entry['disposition'] for entry in plan['entries']]
        assert not set(dispositions) & {
            'read_error',
            'unavailable',
            'proof_refused',
            'privacy_refused',
            'not_batch_owned',
            'not_completed',
            'upload_pending',
        }, 'fixture no-job proof or authority failed'
        result = record_seal_nojob.apply_backfill(self.store, plan, plan['plan_sha256'])
        assert not result.get('write_error'), 'fixture no-job transaction failed'
        return result

    async def drain(self):
        self._boundary('admit')
        await live.drain_recordings(self.store)

    async def tick(self):
        self.ticks += 1
        if self.ticks > 20:
            raise ValueError('lifecycle scenario exceeds twenty ticks')
        await self.drain()
        now = time.time()
        leases = self.serving.queue().pull(now, 4, capacity=PoolCapacity(now, 4))
        for lease in leases:
            outcome = await asyncio.to_thread(
                run_virtual, self.clock, lambda: self.stt.request(SPEECH, lease.item.duration_seconds)
            )
            self.words.plan[lease.item.segment_id] = {'first': outcome, 'retry': None}
            results = self.worker.process_batch([lease.item])
            for result in results:
                assert isinstance(result, WorkResult), 'synthetic worker did not produce a valid result'
                assert self.serving.complete(result, lease.token), 'real scheduler rejected its owned lease'
                self.projector.project(result.segment_id)

    async def complete(self):
        """Run the real recovery processing coordinator with the stack's leaves."""
        install_finalizer_leaves()
        conversation = deserialize_conversation(processing.conversations_db.get_conversation(self.uid, self.cid))
        await asyncio.to_thread(
            processing.process_conversation,
            self.uid,
            'en',
            conversation,
            trigger=ProcessingTrigger.SERVER_RECOVERY,
            defer_memory_extraction=True,
            defer_derived_effects=True,
        )

    def kill_pusher(self):
        child = self.stack.children['pusher']
        os.killpg(child.process.pid, signal.SIGKILL)
        child.process.wait(timeout=10)
        self.stack.children.pop('pusher')

    async def start_pusher_with_live_token(self):
        child = self.stack._start(
            'pusher',
            [
                str(PYTHON),
                '-m',
                'uvicorn',
                'testing.lifecycle_sim.pusher_app:app',
                '--host',
                '127.0.0.1',
                '--port',
                str(self.stack.pusher_port),
            ],
            extra_env={'HOSTNAME': 'synthetic-pusher'},
        )
        await asyncio.to_thread(
            _wait_for_port, self.stack.pusher_port, label='lifecycle pusher', timeout=120, child=child
        )
        async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
            response = await client.post(
                f'http://127.0.0.1:{self.stack.pusher_port}/__lifecycle/begin',
                json={'uid': self.uid, 'conversation_id': self.cid},
            )
        assert response.status_code == 200, 'real pusher did not persist its live custody token'
        assert self.row().get('record_upload_sessions'), 'pusher returned without a durable token'

    def close(self):
        if self.worker._io is not None:
            self.worker._io.shutdown(wait=True, cancel_futures=True)
