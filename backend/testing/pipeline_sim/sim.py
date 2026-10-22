"""The simulation: real batch-pipeline state machine + small named models, in virtual time.

REAL product code exercised on the ``batch`` path (unmodified, imported):
  - ``database.batch_pipeline_intake.admit``           (atomic admission + projection binding)
  - ``utils.batch_pipeline.scheduler.Scheduler``      (DRR pull, leases, retry, quarantine, recover)
  - ``utils.batch_pipeline.pump.Pump``                (pull/heartbeat/complete/fail/drain loop)
  - ``diarizer.batch_pipeline.PipelineWorker``         (VAD/window/ASR/padded-retry/empty-ASR classification)
  - ``utils.batch_pipeline.merge.OrderedMerge``       (capture-ordered result log)
  - ``utils.batch_pipeline.serving.Serving.reconcile`` (supervisor tick: recovery sweep, recover, drain)
  - ``utils.batch_pipeline.quarantine_recovery.QuarantineRecovery`` (sweep, dispatch, recover)
  - ``database.batch_pipeline_quarantine_recovery.RecoveryStore`` (prepare/start/settle fences)
  - ``database.batch_pipeline_privacy.assert_batch_write_allowed`` (privacy fence)
  - ``utils.batch_pipeline.provider_stt`` (C8: route, admission ``enqueue`` hook, ProviderSttStage)

Module attributes patched for the duration of a run (restored afterwards):
  ``pump.time``/``serving.time`` -> virtual clock; ``pump.run_blocking`` -> inline
  in virtual time; ``quarantine_recovery.{recovery_candidates,enqueue_named_task,
  cancel_fenced_recovery}`` -> models over the in-memory store (the originals
  need Firestore queries or Cloud Tasks). The Pump's ``authorize_compute`` hook is
  a model of ``admission.authorize`` (Redis fair-use leaves).

MODELLED (see models.py / stt.py): ASR fleet capacity, paid fallback, Cloud Tasks,
CPU executors, projection + first summary, revision replacement, the legacy
sync path and its per-owner sequencer.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import hashlib
import logging
import math
import random
from dataclasses import dataclass, field, replace
from unittest.mock import patch

from config.policy import BatchUnitPolicy, FirstSummaryPolicy, resolve_batch_policy, resolve_stage_policy
from config.policy.listen import ListenSessionPolicy
from config.policy.stages import STAGE_TYPES
from database.batch_pipeline_shadow_hook import mirror_refresh
from database import batch_pipeline_policy as policy_store
from config.policy.batch import SNAPSHOT_ENV_KEYS
from types import SimpleNamespace
from typing import Any

from config.batch_pipeline import priority_for, recovery_dispatch_interval_seconds
from database import batch_pipeline_intake
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from diarizer.batch_pipeline import PipelineWorker, padded_retry_fits, padded_retry_seconds
from config.batch_pipeline_providers import ProviderConfig
from utils.batch_pipeline import pump as pump_module
from utils.batch_pipeline import quarantine_recovery as recovery_module
from utils.batch_pipeline import serving as serving_module
from utils.batch_pipeline.contracts import PoolCapacity, ProjectionBinding, WorkItem
from utils.batch_pipeline.provider_stt import ProviderSttStage, provider_enqueue, resolve_route
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.recovery_disposition import MultilingualEmpty, RecoveryFailure
from utils.batch_pipeline.quarantine_recovery import QuarantineRecovery
from utils.batch_pipeline.scheduler import Scheduler, owns_lease
from utils.batch_pipeline.serving import Serving
from utils.sync.capture import chunk_identity

from testing.pipeline_sim.clock import VirtualClock, run_virtual
from testing.pipeline_sim.scorer import score
from testing.pipeline_sim.models import ExecutorModel, RevisionModel, SequencerModel
from testing.pipeline_sim.store import CustomerData, SimStore
from testing.pipeline_sim.stt import (
    EMPTY,
    ERROR,
    SILENCE,
    SPEECH,
    TIMEOUT,
    WORDS,
    FakeModulate,
    FakeSTT,
    ModulateProfile,
    PlannedWords,
    ProviderUnavailable,
    SimSamples,
    STTProfile,
    vad_spans,
)
from testing.pipeline_sim.workload import (
    PRIVACY_AT_ADMISSION,
    PRIVACY_MIDFLIGHT,
    TARGET_DELETED,
    TARGET_MERGED,
    UploadSpec,
    Workload,
    WorkloadSpec,
    generate,
)

logger = logging.getLogger(__name__)

# Assumed production-like flag set (overridable per scenario). Recorded run
# state disagrees across dates, so these are explicit simulation inputs.
DEFAULT_FLAGS = {
    'OMI_ENV_STAGE': 'dev',
    'FIRST_SUMMARY_DEADLINE_ENABLED': 'true',
    'FIRST_SUMMARY_DEADLINE_PERCENT': '100',
    'BATCH_PIPELINE_ENABLED': 'true',
    'BATCH_PIPELINE_PERCENT': '100',
    'BATCH_PIPELINE_UID_ALLOWLIST': '',
    'BATCH_PIPELINE_MAX_ATTEMPTS': '5',
    'BATCH_PIPELINE_SHARED_LIVE_ENABLED': 'false',
    'BATCH_PIPELINE_HEAD_PRIORITY_ENABLED': 'false',
    'BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED': 'false',
    'BATCH_PIPELINE_RECOVERY_MODE': 'on',
    'BATCH_PIPELINE_RECOVERY_ALL_ADMITTED': 'true',
    'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST': '',
    'BATCH_PIPELINE_RECOVERY_TASKS_ENABLED': 'true',
    'BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE': 'https://pipeline-sim.invalid',
    'SYNC_TASKS_QUEUE': 'pipeline-sim-sync-jobs',
    'SYNC_TASKS_INVOKER_SA': 'pipeline-sim@invalid',
    'BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED': 'true',
    # Disposition needs real WAV bytes + strict local VAD; the simulation has no audio.
    'BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED': 'false',
    'BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED': 'true',
    'BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED': 'true',
    'BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED': 'false',
    'BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED': 'true',
    'BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED': 'false',
    'STT_CAP_DISPATCH_ENFORCEMENT': 'false',
}

BACKFILL_SPEECH_SECONDS_PER_UID_DAY = 4 * 3600  # backend/AGENTS.md: four processed speech hours per UID/day


@dataclass
class SimConfig:
    name: str = 'custom'
    seed: int = 1
    path: str = 'batch'  # batch (real state machine) | legacy (sequenced sync jobs, modelled)
    workload: WorkloadSpec = field(default_factory=WorkloadSpec)
    stt: STTProfile = field(default_factory=STTProfile)
    modulate: ModulateProfile = field(default_factory=ModulateProfile)
    horizon_seconds: float = 3 * 3600.0
    # Batch path.
    gpu_pumps: int = 2
    pump_batch_size: int = 8
    gpu_seconds_per_item: float = 0.5
    serving_interval_seconds: float = 20.0  # serving.start_serving_from_env supervise loop
    task_hop_seconds: float = 2.0
    recovery_duplicate_delivery_rate: float = 0.0
    worker_rpc_duplicate_rate: float = 0.0  # duplicate complete/fail delivery from a lease-holding worker
    projection_seconds: float = 1.0
    projection_cursor_blocks: bool = True
    backfill_speech_seconds_per_day: float = BACKFILL_SPEECH_SECONDS_PER_UID_DAY
    # CPU executors (utils/executors.py: sync_executor=16, llm_executor=6).
    sync_executor_workers: int = 16
    summary_pool: str = 'shared'  # shared: sync_executor | isolated: own pool
    summary_pool_workers: int = 6
    summary_seconds: float = 20.0
    summary_sigma: float = 0.4
    summary_dispatch: str = 'awaited'  # awaited | task | background
    summary_repair_seconds: float | None = None
    # Legacy path.
    sequencer_per_owner_concurrency: int = 1
    sequencer_dispatch_seconds: float = 1.5
    legacy_overhead_seconds: float = 3.0
    legacy_stt_attempts: int = 2
    # Revision replacement of the CPU service (and SIGTERM of GPU pumps).
    revision_replacement_at: float | None = None
    revision_grace_seconds: float = 10.0
    revision_request_timeout: float = 3600.0
    serving_restart_seconds: float = 30.0
    restart_pumps_at_replacement: bool = True
    pump_restart_seconds: float = 60.0
    purge_on_fence: bool = True  # production purges synchronously after the tombstone / privacy advance
    flags: dict[str, str] = field(default_factory=dict)
    policy: BatchUnitPolicy | None = None
    listen_policy: ListenSessionPolicy | None = None
    role_environments: dict[str, dict[str, str]] = field(default_factory=dict)
    stage_roles: dict[str, str] = field(default_factory=dict)
    trace_policy: bool = False
    policy_parts: dict[str, dict] = field(default_factory=dict)  # Persisted owner parts for replay.
    gate_poll_seconds: float = 300.0  # fleet_gate.sh POLL_SECONDS
    # C8 admission route (intake.accept_upload): stored language, BYOK, legacy_sync mode.
    language: str = 'en'
    byok: bool = False
    legacy_sync: str = 'on'  # on | draining | dark

    def __post_init__(self):
        if isinstance(self.policy, dict):
            self.policy = BatchUnitPolicy.from_dict(self.policy)
        if isinstance(self.listen_policy, dict):
            self.listen_policy = ListenSessionPolicy.from_dict(self.listen_policy)


@dataclass
class UploadRecord:
    spec: UploadSpec
    policy: BatchUnitPolicy | None = None
    first_summary_policy: FirstSummaryPolicy | None = None
    status: str = 'pending'  # admitted | rejected_privacy | deduplicated | rejected_other
    accepted_at: float | None = None
    job_id: str | None = None
    segment_ids: tuple[str, ...] = ()
    conversation_id: str | None = None
    projecting: bool = False
    projected_at: float | None = None
    excluded: str | None = None
    fenced_at: float | None = None
    has_words: bool = False
    summary_pending_at: float | None = None
    summary_completed_at: float | None = None
    summary_inflight: bool = False
    summary_dispatches: int = 0
    failed_segments: int = 0
    speech_seconds: float = 0.0


@dataclass
class SimResult:
    config: SimConfig
    clock: VirtualClock
    workload: Workload
    records: list[UploadRecord]
    store: SimStore | None
    customer: CustomerData
    stt: FakeSTT
    modulate: FakeModulate
    revision: RevisionModel
    sequencer: SequencerModel | None
    executors: dict[str, ExecutorModel]
    counters: dict[str, int]
    truth: dict[str, dict]
    ended_at: float
    polls: list[tuple[float, str, int]] = field(default_factory=list)


class ArtifactsModel:
    """Encrypted-object store stand-in: payloads stay in memory, URIs are synthetic."""

    def __init__(self):
        self.objects: dict[str, dict] = {}

    def persist_worker(self, item, payload) -> str:
        uri = f'sim://result/{item.segment_id}'
        self.objects[uri] = payload
        return uri

    def fetch_audio(self, item) -> bytes:
        return b'synthetic-audio-placeholder'

    def find_recovery_result(self, item, token):
        uri = f'sim://recovery/{item.segment_id}/{token}'
        return uri if uri in self.objects else None

    def persist_recovery_result(self, item, payload, token) -> str:
        uri = f'sim://recovery/{item.segment_id}/{token}'
        self.objects[uri] = payload
        return uri

    def load_result(self, item, uri) -> dict:
        return self.objects[uri]


class SimWorker:
    """GPU chain adapter: decides ASR outcomes in virtual time, then runs the REAL worker."""

    def __init__(self, sim: 'Simulation', index: int):
        self.sim = sim
        self.planned = PlannedWords()
        self.config = ProviderConfig()
        self.worker = PipelineWorker(
            decode=self._decode,
            vad=vad_spans,
            words_providers={'parakeet': self.planned},
            diarizers={'pyannote': lambda samples: {'turns': []}},
            persist=sim.artifacts.persist_worker,
            config=self.config,
            recover_words=self.planned.recover_words,
            gpu_lock=contextlib.nullcontext(),
            language_of=lambda item: 'en',  # This virtual corpus is declared English.
        )
        self.index = index

    def _decode(self, item):
        truth = self.sim.truth[item.segment_id]
        return SimSamples.for_seconds(item.segment_id, truth['kind'], item.duration_seconds)

    def process_batch(self, items, **kwargs):  # BatchWorker protocol; executed via process_async
        raise RuntimeError('the simulation drives process_async through the patched run_blocking')

    async def _plan(self, item) -> None:
        sim = self.sim
        kind = sim.truth[item.segment_id]['kind']
        first, retry = None, None
        if kind != SILENCE:
            first = await sim.stt.request(kind, item.duration_seconds, purpose='batch')
            samples = self._decode(item)
            if first == EMPTY and padded_retry_fits(samples, self.config.max_padded_seconds):
                retry = await sim.stt.request(kind, padded_retry_seconds(samples), purpose='padded_retry')
        self.planned.plan[item.segment_id] = {'first': first, 'retry': retry}
        sim.counters[f'asr_{first or "skipped_silence"}'] += 1

    async def process_async(self, items, **kwargs):
        await asyncio.sleep(self.sim.config.gpu_seconds_per_item * len(items))
        await asyncio.gather(*(self._plan(item) for item in items))
        return self.worker.process_batch(items, **kwargs)


class _ProviderOutbox:
    """Outbox stand-in for the admission ``enqueue`` hook: every new row asks for one wake."""

    def enqueue(self, row_id, owner_id, payload, available_at, *, tx=None, now=None):
        return SimpleNamespace(row_id=row_id, wake_token=f'wake-{row_id}')


class Simulation:
    def __init__(self, config: SimConfig):
        self.config = config
        self.clock = VirtualClock()
        self.rng = {name: random.Random(f'{config.seed}:{name}') for name in ('workload', 'stt', 'modulate', 'misc')}
        self.workload = generate(config.workload, self.rng['workload'])
        self.customer = CustomerData()
        self.store = SimStore(self.customer) if config.path == 'batch' else None
        self.truth: dict[str, dict] = {}
        self.stt = FakeSTT(self.clock, config.stt, self.rng['stt'])
        self.modulate = FakeModulate(self.clock, config.modulate, self.rng['modulate'], self.truth)
        self.artifacts = ArtifactsModel()
        self.revision = RevisionModel(
            self.clock, request_timeout=config.revision_request_timeout, grace_seconds=config.revision_grace_seconds
        )
        self.sync_exec = ExecutorModel('sync_executor', config.sync_executor_workers, self.clock)
        self.summary_exec = (
            self.sync_exec
            if config.summary_pool == 'shared'
            else ExecutorModel('summary_pool', config.summary_pool_workers, self.clock)
        )
        self.records: list[UploadRecord] = []
        self.by_job: dict[str, UploadRecord] = {}
        self.by_segment: dict[str, UploadRecord] = {}
        self.counters: collections.Counter = collections.Counter()
        self.sequencer: SequencerModel | None = None
        self.backfill_used: dict[tuple[str, int], float] = {}
        self.backfill_reserved: dict[tuple[str, str], bool] = {}
        self._task_names: set[str] = set()
        self._live_tasks: set[str] = set()  # created and not yet answered
        self._pumps: list[tuple[Pump, asyncio.Event, asyncio.Task]] = []
        self._supervisor: Any = None
        self.serving: Serving | None = None
        self.recovery: QuarantineRecovery | None = None
        self.polls: list[tuple[float, str, int]] = []
        self.provider_stage = (
            None
            if self.store is None
            else ProviderSttStage(
                self.store,
                self.artifacts,
                stt=self._provider_call,
                allowed=lambda *_: True,
                inspect=self._provider_inspect,
                clock=self.clock.time,
            )
        )
        self._seed_customers()

    # ------------------------------------------------------------------ setup
    def _seed_customers(self) -> None:
        for owner, kind in self.workload.owners.items():
            self.customer.add_user(owner)
            if kind == PRIVACY_AT_ADMISSION:
                self.customer.block_privacy(owner)
        for upload in self.workload.uploads:
            if upload.target:
                self.customer.add_conversation(upload.owner, self._target_id(upload))
            for segment in upload.segments:
                sid = self._segment_id(upload, segment.index)
                self.truth.setdefault(
                    sid,
                    {'kind': segment.kind, 'duration': segment.duration, 'owner': upload.owner, 'upload': upload},
                )

    @staticmethod
    def _segment_id(upload: UploadSpec, index: int) -> str:
        return hashlib.sha256(f'{upload.content_id}:{index}'.encode()).hexdigest()

    @staticmethod
    def _target_id(upload: UploadSpec) -> str:
        source = upload.duplicate_of or upload.upload_id
        return 'sim-conv-' + hashlib.sha256(source.encode()).hexdigest()[:24]

    def _policy_flags(self, stage):
        role = self.config.stage_roles.get(stage, stage)
        return {**DEFAULT_FLAGS, **self.config.flags, **self.config.role_environments.get(role, {})}

    def _stage_policy(self, uid, stage):
        raw = self.config.policy_parts.get(stage)
        return (
            STAGE_TYPES[stage].from_dict(raw)
            if raw is not None
            else resolve_stage_policy(uid, stage, flags=self._policy_flags(stage))
        )

    # --------------------------------------------------------------- patching
    @contextlib.contextmanager
    def _patched(self):
        flags = {**DEFAULT_FLAGS, **self.config.flags}
        # Only E1b worker dispositions and process/provider config use env.
        # Per-unit E1 inputs are supplied exclusively through the resolver.
        outside_scope = {
            key: value
            for key, value in flags.items()
            if key not in SNAPSHOT_ENV_KEYS and not key.startswith(('FIRST_SUMMARY_', 'TRANSCRIPTION_FINAL_PASS_'))
        }
        env_patch = patch.dict('os.environ', outside_scope)
        patches = [
            (policy_store, 'resolve_stage_policy', self._stage_policy),
            (pump_module, 'time', self.clock.module()),
            (pump_module, 'run_blocking', self._run_blocking),
            (serving_module, 'time', self.clock.module()),
            (recovery_module, 'recovery_candidates', self._recovery_candidates),
            (recovery_module, 'enqueue_named_task', self._enqueue_named_task),
            (recovery_module, 'named_task_exists', self._named_task_exists),
            (recovery_module, 'cancel_fenced_recovery', self._cancel_fenced_recovery),
        ]
        originals = [(module, name, getattr(module, name)) for module, name, _ in patches]
        try:
            env_patch.start()
            for module, name, value in patches:
                setattr(module, name, value)
            yield
        finally:
            for module, name, value in originals:
                setattr(module, name, value)
            env_patch.stop()

    async def _run_blocking(self, executor, fn, *args, **kwargs):
        owner = getattr(fn, '__self__', None)
        if isinstance(owner, SimWorker) and getattr(fn, '__name__', '') == 'process_batch':
            return await owner.process_async(*args, **kwargs)
        await asyncio.sleep(0)
        result = fn(*args, **kwargs)
        name = getattr(fn, '__name__', '')
        if (
            isinstance(owner, Scheduler)
            and name in {'complete', 'fail'}
            and self.rng['misc'].random() < self.config.worker_rpc_duplicate_rate
        ):
            # The same worker RPC delivered twice (lost reply + retry) with the same lease token.
            duplicate = fn(*args, **kwargs)
            self.counters[f'duplicate_{name}_returned_{bool(duplicate)}'.lower()] += 1
        return result

    # ---- models replacing Firestore-query / Cloud Tasks / Redis leaves ----
    def _recovery_candidates(self, client, namespace, owner_id, limit=10, *, after_id=None):
        """Model of recovery_candidates(): recovery_state in held/prepared/running, ordered by doc id."""
        rows = []
        for (table, key), row in sorted(self.store.rows.items()):
            if table != 'jobs' or row.get('recovery_state') not in {'held', 'prepared', 'running'}:
                continue
            if owner_id is not None and row.get('owner_id') != owner_id:
                continue
            if owner_id is None and after_id is not None and key <= after_id:
                continue
            rows.append((key, row['owner_id']))
            if len(rows) >= max(1, min(limit, 64)):
                break
        return rows

    def _enqueue_named_task(self, queue, url, task_id, payload, *, audience=None, invoker_sa=None, schedule_at=None):
        """Cloud Tasks model: named-task dedupe, one hop of latency, optional duplicate delivery."""
        if task_id in self._task_names:
            return None
        self._task_names.add(task_id)
        self._live_tasks.add(task_id)
        self.counters['recovery_tasks_enqueued'] += 1
        deliveries = 2 if self.rng['misc'].random() < self.config.recovery_duplicate_delivery_rate else 1
        loop = asyncio.get_running_loop()
        for n in range(deliveries):
            if n:
                self.counters['recovery_duplicate_deliveries'] += 1
            loop.call_later(
                self.config.task_hop_seconds * (1 + n),
                lambda sid=payload['segment_id'], tid=task_id: loop.create_task(
                    self.revision.request('recover-quarantine', self._recover_handler(sid, tid))
                ),
            )
        return None

    def _named_task_exists(self, queue, task_id):
        """Cloud Tasks custody model: a named task exists until a delivery answers it."""
        return task_id in self._live_tasks

    async def _recover_handler(self, segment_id: str, task_id: str | None = None) -> str:
        """Mirrors routers/batch_pipeline.recover_quarantine (request-scoped paid STT)."""
        job = self.store.get('jobs', segment_id)
        if not job:
            return 'held'
        if job.get('recovery_state') == 'prepared':
            await self.modulate.occupy(job['duration_seconds'])
        outcome = self.recovery.recover(segment_id, job['owner_id'])
        self.counters[f'recovery_{outcome}'] += 1
        if outcome == 'held':
            try:  # Mirrors the handler's held re-arm, including its swallowed fence errors.
                self.recovery.delivered(segment_id, outcome, task_id)
            except Exception:
                pass
        if outcome in {'recovered', 'reconciled'}:
            self.serving.reconcile()
        self._live_tasks.discard(task_id)
        return outcome

    async def _provider_delivery(self, segment_id: str) -> None:
        """Mirrors ProviderSttConsumer.process: one REAL ProviderSttStage.run per delivery."""
        job = self.store.get('jobs', segment_id)
        if job.get('state') == 'provider_pending':
            await self.modulate.occupy(job['duration_seconds'])
        unit = self.provider_stage.run(segment_id)
        self.counters[f'provider_stt_{unit.outcome}'] += 1
        if unit.outcome in {'deferred', 'retry'}:
            delay = max(self.config.task_hop_seconds, (unit.available_at or 0.0) - self.clock.now)
            loop = asyncio.get_running_loop()
            loop.call_later(delay, lambda: loop.create_task(self._provider_delivery(segment_id)))
        elif self.serving is not None:
            self.serving.reconcile()

    def _provider_inspect(self, item, audio):
        """Strict-VAD stand-in: the segment's synthetic speech spans (inspect_audio's shape)."""
        samples = SimSamples.for_seconds(item.segment_id, self.truth[item.segment_id]['kind'], item.duration_seconds)
        spans = [{'start': start, 'end': end} for start, end in vad_spans(samples)]
        return b'', item.duration_seconds, spans

    def _provider_call(self, item, language, inspected, *, service):
        """The stage's vendor seam on the paid-provider model; errors map as ``transcribe`` maps them."""
        try:
            payload = self.modulate(item, None, b'')
        except ProviderUnavailable:
            raise RecoveryFailure('provider', 'provider_failed')
        except MultilingualEmpty:
            raise RecoveryFailure('response_validation', 'empty_asr')
        return {**payload, 'words_provider': service, 'language': language}

    def _cancel_fenced_recovery(self, store, segment_id):
        """Model of cancel_fenced_recovery(): revocation-only write after the fence rejects."""
        job = store.rows.get(('jobs', segment_id), {})
        if not job or not job.get('recovery'):
            return False
        binding = job['projection_binding']
        ids = [v for v in (job.get('conversation_id'), binding.get('target_conversation_id')) if v]
        if self.customer.blocked(binding['owner_id'], ids, binding.get('privacy_generation')):
            store.mutate('jobs', segment_id, lambda row: row.update(recovery_state='cancelled'))
            return True
        return False

    def _day(self) -> int:
        return int(self.clock.now // 86400)

    def _reserve_backfill_speech(self, uid, content_id, milliseconds):
        """Model of utils.sync.backfill.reserve_backfill_speech: per-UID daily speech budget, once per content."""
        if self.backfill_reserved.get((uid, content_id)):
            return SimpleNamespace(allowed=True, retry_after=None)
        key = (uid, self._day())
        seconds = milliseconds / 1000
        if self.backfill_used.get(key, 0.0) + seconds > self.config.backfill_speech_seconds_per_day:
            self.counters['backfill_budget_deferrals'] += 1
            return SimpleNamespace(allowed=False, retry_after=self._retry_after_next_day())
        self.backfill_used[key] = self.backfill_used.get(key, 0.0) + seconds
        self.backfill_reserved[(uid, content_id)] = True
        return SimpleNamespace(allowed=True, retry_after=None)

    def _retry_after_next_day(self) -> int:
        return max(1, int((self._day() + 1) * 86400 - self.clock.now))

    def _authorize_compute(self, leases):
        """MODEL of utils/batch_pipeline/admission.authorize (the backend spend-policy RPC).

        Same lease-ownership and privacy checks and the same lease-bound
        ``compute_admission_token`` seal that the real ``Scheduler.complete``
        enforces. Fair-use restriction and the daily audio ceiling always allow;
        backfill-lane uploads (by recorded lane, else priority) reserve against a
        per-UID daily speech budget. Not
        imported for real: its fair-use dependency chain costs ~5 s of imports.
        """
        now = self.clock.now
        allowed, retries = [], {}
        for lease in leases:
            segment, token = lease.item.segment_id, lease.token

            def read(tx):
                job = tx.get('jobs', segment)
                if not owns_lease(job, token, now):
                    return None
                tx.check_privacy(
                    job['owner_id'],
                    (job['conversation_id'],) if job.get('conversation_id') else (),
                    job.get('privacy_generation'),
                )
                return job, tx.get('intakes', (job.get('projection_binding') or {}).get('job_id', 'missing'))

            try:
                snapshot = self.store.run(read)
            except BatchPrivacyBlocked:
                snapshot = None
            if snapshot is None:
                retries[segment] = 30
                continue
            job, intake = snapshot
            fresh_lane = intake['lane'] == 'fresh' if intake.get('lane') else int(job['priority']) == 0
            if not fresh_lane:
                reservation = self._reserve_backfill_speech(
                    job['owner_id'],
                    job['projection_binding']['content_id'],
                    math.ceil(intake['total_audio_seconds'] * 1000),
                )
                if not reservation.allowed:
                    retries[segment] = max(1, min(86400, reservation.retry_after or 3600))
                    continue

            def seal(tx):
                latest = tx.get('jobs', segment)
                if not owns_lease(latest, token, now):
                    return False
                latest['compute_admission_token'] = token
                tx.put('jobs', segment, latest)
                return True

            try:
                sealed = self.store.run(seal)
            except BatchPrivacyBlocked:
                sealed = False
            if sealed:
                allowed.append(segment)
            else:
                retries[segment] = 30
        return {'allowed': allowed, 'retry_after': retries}

    # ------------------------------------------------------------- batch path
    def _items_for(self, upload: UploadSpec, generation: int, *, compute: bool = True) -> list[WorkItem]:
        base = self.clock.start + upload.at - upload.recording_age
        priority = priority_for(upload.lane, upload.recording_age)
        items, offset = [], 0.0
        target = self._target_id(upload) if upload.target else None
        for segment in upload.segments:
            capture_at = round(base + offset, 3)
            offset += segment.duration
            items.append(
                WorkItem(
                    self._segment_id(upload, segment.index),
                    upload.owner,
                    capture_at,
                    f'sim://audio/{self._segment_id(upload, segment.index)}',
                    segment.duration,
                    priority,
                    unit_kind='conversation' if target else 'capture_span',
                    conversation_id=target or chunk_identity(upload.owner, 'omi', None, False, capture_at),
                    privacy_generation=generation,
                    requires_compute_admission=compute,
                )
            )
        return items

    def _accept_batch(self, record: UploadRecord) -> None:
        """Mirrors utils/batch_pipeline/intake.accept_upload around the REAL admit() transaction."""
        upload = record.spec
        record.policy = self.config.policy or resolve_batch_policy(upload.owner, flags=self._policy_flags('admission'))
        if not record.policy.batch_enabled:
            record.status = 'rejected_other'
            return
        # C8, as intake: a language Parakeet cannot serve takes the provider stage once legacy is
        # draining or dark; the admission policy records the route actually taken.
        route = resolve_route(self.config.language, byok=self.config.byok)
        provider = self.config.legacy_sync != 'on' and route.stt_route == 'provider'
        stamp = {
            'stt_route': 'provider' if provider else 'parakeet',
            'provider_reason': route.provider_reason if provider else ('byok' if self.config.byok else 'none'),
            'provider_service': route.provider_service if provider else 'none',
        }
        if any(getattr(record.policy, key) != value for key, value in stamp.items()):
            record.policy = replace(record.policy, **stamp)  # an explicit replay policy is kept as given
        wakes: dict[str, str] = {}
        target = self._target_id(upload) if upload.target else None
        try:
            generation = self.customer.check(upload.owner, (target,) if target else ())
            items = self._items_for(upload, generation, compute=not provider)
            binding = ProjectionBinding(
                owner_id=upload.owner,
                job_id='bp_' + (upload.duplicate_of or upload.upload_id),
                content_id=upload.content_id,
                segment_ids=tuple(item.segment_id for item in items),
                target_conversation_id=target,
                privacy_generation=generation,
                language=self.config.language,
            )
            outcome = batch_pipeline_intake.admit(
                self.store,
                items,
                binding,
                self.clock.now,
                namespace=self.store.namespace,
                policy=record.policy,
                intake={
                    'owner_id': upload.owner,
                    'content_id': upload.content_id,
                    'segment_ids': list(binding.segment_ids),
                    'total_audio_seconds': sum(item.duration_seconds for item in items),
                    'lane': upload.lane,
                },
                enqueue=provider_enqueue(route, _ProviderOutbox(), wakes) if provider else None,
            )
        except BatchPrivacyBlocked:
            record.status = 'rejected_privacy'  # accept_upload -> 409 sync_batch_privacy_blocked
            return
        if outcome.get('outcome') != 'batch':
            record.status = 'rejected_other'
            return
        if upload.duplicate_of is not None or binding.job_id in self.by_job:
            record.status = 'deduplicated'
            self.counters['duplicate_uploads_deduplicated'] += 1
            return
        loop = asyncio.get_running_loop()
        for row_id in wakes:  # Cloud Tasks model: one hop after the admission transaction commits
            loop.call_later(
                self.config.task_hop_seconds, lambda sid=row_id: loop.create_task(self._provider_delivery(sid))
            )
        record.status = 'admitted'
        record.accepted_at = self.clock.now
        record.job_id = binding.job_id
        record.segment_ids = binding.segment_ids
        record.conversation_id = target
        self.by_job[binding.job_id] = record
        for sid in record.segment_ids:
            self.by_segment[sid] = record
        if upload.target in {TARGET_MERGED, TARGET_DELETED}:
            delay = self.rng['misc'].uniform(*self.config.workload.retarget_delay_seconds)
            asyncio.get_running_loop().call_later(delay, self._retarget, upload)

    def _retarget(self, upload: UploadSpec) -> None:
        target = self._target_id(upload)
        if upload.target == TARGET_MERGED:
            self.customer.merge_conversation(upload.owner, target, target + '-merged')
        else:
            self.customer.delete_conversation(upload.owner, target)
            if self.config.purge_on_fence:
                self.counters['purged_jobs'] += self.store.purge(upload.owner, target)
            for record in self.records:
                if record.spec.upload_id == upload.upload_id:
                    record.fenced_at = self.clock.now

    def _fenced(self, record: UploadRecord) -> str | None:
        upload = record.spec
        ids = (record.conversation_id,) if record.conversation_id else ()
        if not self.customer.blocked(upload.owner, ids):
            return None
        if upload.target == TARGET_DELETED:
            return 'deleted_target'
        return 'privacy_blocked'

    def _projector_sweep(self) -> None:
        """MODEL of Projector.sweep: ordered per-owner publication of complete bindings.

        Only complete multipart projection advances an owner's publication cursor
        (utils/batch_pipeline/README.md); with ``projection_cursor_blocks`` a
        binding whose quarantined sibling is unresolved holds later bindings.
        """
        by_owner: dict[str, list[UploadRecord]] = {}
        for record in self.by_job.values():
            if record.projected_at is None and record.excluded is None:
                by_owner.setdefault(record.spec.owner, []).append(record)
        for owner in sorted(by_owner):
            ordered = sorted(by_owner[owner], key=lambda r: (r.spec.at - r.spec.recording_age, r.job_id))
            for record in ordered:
                if record.projecting:
                    break
                reason = self._fenced(record)
                if reason:
                    record.excluded = reason
                    self.counters[f'excluded_{reason}'] += 1
                    continue
                jobs = [self.store.rows.get(('jobs', sid), {}) for sid in record.segment_ids]
                if all(job.get('state') == 'committed' for job in jobs):
                    record.projecting = True
                    self.revision.spawn('projection', self._project(record))
                    break
                if self.config.projection_cursor_blocks and any(
                    job.get('state') in {'committed', 'quarantined', 'result_ready'} for job in jobs
                ):
                    break  # partially committed binding holds the cursor

    async def _project(self, record: UploadRecord) -> None:
        policy_store.load_stage_policy(self.store, record.segment_ids[0], 'projection')
        try:
            audio = sum(self.truth[sid]['duration'] for sid in record.segment_ids)
            await self.sync_exec.run('projection', self.config.projection_seconds + 0.001 * audio)
            if self._fenced(record):
                record.excluded = self._fenced(record)
                return
            now = self.clock.now
            for sid in record.segment_ids:
                result = self.store.rows[('results', sid)]['result']
                payload = self.artifacts.objects.get(result['result_uri'], {})
                speech = float(payload.get('speech_seconds', 0.0)) if result['outcome'] == 'success' else 0.0
                record.has_words = record.has_words or bool(payload.get('words'))
                record.speech_seconds += speech
                self.store.mutate(
                    'results',
                    sid,
                    lambda row, s=speech: row.update(
                        projection_state='completed', projection={'state': 'completed', 'speech_seconds': s}
                    ),
                )
                self.store.mutate('jobs', sid, lambda row: row.update(client_status='completed'))
                self._advance_projection_watermark(sid)
            self.store.mutate(
                'content',
                f'{record.spec.owner}/{record.spec.content_id}',
                lambda row: row.update(status='completed', updated_at=now),
            )
            # Production ProjectionStore re-copies its siblings to the A2 shadow after commit (no-op otherwise).
            mirror_refresh(
                getattr(self.store, 'namespace', ''), [(t, s) for s in record.segment_ids for t in ('jobs', 'results')]
            )
            record.projected_at = now
            if record.has_words:
                await self._start_summary(record)
        finally:
            record.projecting = False

    def _advance_projection_watermark(self, segment_id: str) -> None:
        """MODEL of ProjectionSession.persist: the owner's projection watermark is its furthest projected log row."""
        entry = self.store.rows[('results', segment_id)]
        owner = self.store.rows.get(('owners', entry['owner_key']), {})
        current = self.store.rows.get(('results', owner.get('projection_watermark') or ''), {})
        if entry['log_sequence'] > current.get('log_sequence', 0):
            self.store.mutate('owners', entry['owner_key'], lambda row: row.update(projection_watermark=segment_id))

    # ---------------------------------------------------------- first summary
    async def _start_summary(self, record: UploadRecord) -> None:
        if record.first_summary_policy is None:
            record.first_summary_policy = self._stage_policy(record.spec.owner, 'first_summary')
        if record.summary_pending_at is None:
            record.summary_pending_at = self.clock.now
            for sid in record.segment_ids:
                self.store.mutate(
                    'jobs',
                    sid,
                    lambda row: row.update(
                        policy_parts={
                            **row.get('policy_parts', {}),
                            'first_summary': record.first_summary_policy.to_dict(),
                        }
                    ),
                )
            mirror_refresh(getattr(self.store, 'namespace', ''), [('jobs', s) for s in record.segment_ids])
        record.summary_dispatches += 1
        record.summary_inflight = True
        mode = self.config.summary_dispatch
        if mode == 'awaited':
            await self._summarize(record)
        elif mode == 'background':
            self.revision.spawn('first-summary', self._summarize(record))
        else:
            loop = asyncio.get_running_loop()
            loop.call_later(
                self.config.task_hop_seconds,
                lambda: loop.create_task(self.revision.request('summary-task', self._summarize(record))),
            )

    async def _summarize(self, record: UploadRecord) -> None:
        try:
            sigma = self.config.summary_sigma
            seconds = self.config.summary_seconds * math.exp(self.rng['misc'].gauss(0, sigma) - sigma**2 / 2)
            await self.summary_exec.run('summary', seconds)
            if record.summary_completed_at is None:
                record.summary_completed_at = self.clock.now
        finally:
            record.summary_inflight = False

    async def _summary_repair(self) -> None:
        """MODEL of summary_debt_repair.tick (2-minute owner scan of conversation debt)."""
        while True:
            await asyncio.sleep(self.config.summary_repair_seconds)
            for record in self.records:
                if (
                    record.summary_pending_at is not None
                    and record.summary_completed_at is None
                    and not record.summary_inflight
                ):
                    self.counters['summary_repairs'] += 1
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.revision.request('summary-repair', self._summarize(record)))
                    record.summary_inflight = True

    # -------------------------------------------------------- batch processes
    def _start_pumps(self) -> None:
        loop = asyncio.get_running_loop()
        self._pumps = []
        for index in range(self.config.gpu_pumps):
            worker = SimWorker(self, index)
            pump = Pump(
                Scheduler(self.store, pool='batch'),
                worker,
                batch_size=self.config.pump_batch_size,
                capacity=lambda: PoolCapacity(
                    observed_at=self.clock.now, available_slots=self.config.pump_batch_size, max_item_seconds=7200
                ),
                authorize_compute=self._authorize_compute,
            )
            stop = asyncio.Event()
            self._pumps.append((pump, stop, loop.create_task(pump.run(stop), name=f'pump-{index}')))

    def _start_supervisor(self) -> None:
        async def supervise():
            while True:
                try:
                    self.serving.reconcile(recover_quarantine=True)
                except Exception as error:  # mirrors start_serving_from_env: log and retry next tick
                    self.counters[f'serving_error_{type(error).__name__}'] += 1
                await asyncio.sleep(self.config.serving_interval_seconds)

        async def dispatch_recovery():
            # Mirrors start_serving_from_env's recovery dispatch loop.
            while True:
                interval = recovery_dispatch_interval_seconds()
                if interval > 0:
                    try:
                        self.serving.dispatch_recovery()
                    except Exception as error:
                        self.counters[f'recovery_dispatch_error_{type(error).__name__}'] += 1
                await asyncio.sleep(interval if interval > 0 else self.config.serving_interval_seconds)

        async def run():
            await asyncio.gather(supervise(), dispatch_recovery())

        self._supervisor = self.revision.spawn('batch_pipeline_serving', run())

    async def _replace_revision(self) -> None:
        await asyncio.sleep(self.config.revision_replacement_at)
        self.counters['revision_replacements'] += 1
        pumps = list(self._pumps)
        if self.config.restart_pumps_at_replacement:
            for _, stop, _ in pumps:
                stop.set()  # SIGTERM: the current chain drains with heartbeats intact
        await self.revision.replace()
        await asyncio.sleep(self.config.serving_restart_seconds)
        if self.config.path == 'batch':
            self._start_supervisor()
            if self.config.restart_pumps_at_replacement:
                await asyncio.gather(*(task for _, _, task in pumps), return_exceptions=True)
                await asyncio.sleep(max(0.0, self.config.pump_restart_seconds - self.config.serving_restart_seconds))
                self._start_pumps()

    # ------------------------------------------------------------ legacy path
    async def _legacy_job(self, record: UploadRecord) -> None:
        await self.revision.request('sync-job', self._legacy_body(record))

    async def _legacy_segment(self, record: UploadRecord, index: int) -> None:
        segment = record.spec.segments[index]

        async def work():
            await asyncio.sleep(self.config.legacy_overhead_seconds)
            if segment.kind == SILENCE:
                return SILENCE
            outcome = ERROR
            for _ in range(self.config.legacy_stt_attempts):
                outcome = await self.stt.request(segment.kind, segment.duration, purpose='legacy')
                if outcome not in {ERROR, TIMEOUT}:
                    break
            return outcome

        outcome = await self.sync_exec.run('transcription', work)  # process_segment holds a sync_executor thread
        self.counters[f'legacy_asr_{outcome}'] += 1
        if outcome == WORDS:
            record.has_words = True
            record.speech_seconds += segment.duration
        elif outcome in {ERROR, TIMEOUT} and segment.kind == SPEECH:
            record.failed_segments += 1

    async def _legacy_body(self, record: UploadRecord) -> None:
        await asyncio.gather(*(self._legacy_segment(record, i) for i in range(len(record.spec.segments))))
        await self.sync_exec.run('projection', self.config.projection_seconds)
        record.projected_at = self.clock.now
        if record.has_words:
            await self._start_summary(record)

    def _accept_legacy(self, record: UploadRecord) -> None:
        upload = record.spec
        if self.customer.blocked(upload.owner):
            record.status = 'rejected_privacy'
            return
        if upload.duplicate_of is not None:
            record.status = 'deduplicated'
            self.counters['duplicate_uploads_deduplicated'] += 1
            return
        record.status = 'admitted'
        record.accepted_at = self.clock.now
        record.job_id = 'legacy_' + upload.upload_id
        self.by_job[record.job_id] = record
        if upload.lane == 'backfill':
            self.sequencer.register(upload.owner, record, upload.at - upload.recording_age)
        else:
            # Fresh sync jobs go straight to queue sync-jobs (no per-UID sequencing).
            loop = asyncio.get_running_loop()
            loop.call_later(self.config.sequencer_dispatch_seconds, lambda: loop.create_task(self._legacy_job(record)))

    # ------------------------------------------------------------------ main
    async def _arrivals(self) -> None:
        for upload in self.workload.uploads:
            await asyncio.sleep(max(0.0, upload.at - self.clock.elapsed()))
            record = UploadRecord(upload)
            self.records.append(record)
            if self.config.path == 'batch':
                self._accept_batch(record)
            else:
                self._accept_legacy(record)

    async def _privacy_midflight(self) -> None:
        await asyncio.sleep(self.config.workload.privacy_midflight_at)
        for owner, kind in self.workload.owners.items():
            if kind == PRIVACY_MIDFLIGHT:
                self.customer.block_privacy(owner)
                if self.config.purge_on_fence and self.store is not None:
                    self.counters['purged_jobs'] += self.store.purge(owner)
                for record in self.records:
                    if record.spec.owner == owner and record.fenced_at is None:
                        record.fenced_at = self.clock.now

    def _drained(self) -> bool:
        if self.clock.elapsed() < max((u.at for u in self.workload.uploads), default=0.0):
            return False
        for record in self.records:
            if record.status != 'admitted' or record.excluded:
                continue
            if record.projected_at is None:
                return False
            if record.summary_pending_at is not None and record.summary_completed_at is None:
                return False
        return True

    async def _main(self) -> float:
        loop = asyncio.get_running_loop()
        tasks = [loop.create_task(self.stt.autoscaler()), loop.create_task(self._arrivals())]
        for window in self.config.stt.exhaustion:
            for edge in (window.start, window.end):
                loop.call_at(self.clock.start + edge, self.stt.refresh_capacity)
        if self.config.workload.privacy_midflight_owners:
            tasks.append(loop.create_task(self._privacy_midflight()))
        if self.config.summary_repair_seconds:
            tasks.append(loop.create_task(self._summary_repair()))
        if self.config.path == 'batch':
            self.recovery = QuarantineRecovery(self.store, self.artifacts, stt=self.modulate, clock=self.clock.time)
            self.serving = Serving(
                self.store, recovery=self.recovery, projector=SimpleNamespace(sweep=self._projector_sweep)
            )
            self._start_pumps()
            self._start_supervisor()
        else:
            self.sequencer = SequencerModel(
                self.clock,
                self._legacy_job,
                per_owner_concurrency=self.config.sequencer_per_owner_concurrency,
                dispatch_seconds=self.config.sequencer_dispatch_seconds,
            )
        if self.config.revision_replacement_at is not None:
            tasks.append(loop.create_task(self._replace_revision()))
        deadline = self.clock.start + self.config.horizon_seconds
        next_poll = self.clock.now + self.config.gate_poll_seconds
        while self.clock.now < deadline:
            await asyncio.sleep(min(60.0, deadline - self.clock.now))
            if self.clock.now >= next_poll:
                next_poll += self.config.gate_poll_seconds
                sample = score(self._result(self.clock.now), final=False)
                self.polls.append((round(self.clock.elapsed(), 1), sample['verdict'], sample['verdict_code']))
            if self._drained() and (
                self.config.revision_replacement_at is None
                or self.clock.elapsed() > self.config.revision_replacement_at
            ):
                break
        ended = self.clock.now
        for _, stop, _ in self._pumps:
            stop.set()
        for task in tasks:
            task.cancel()
        return ended

    def run(self) -> SimResult:
        with self._patched():
            ended = run_virtual(self.clock, self._main)
        return self._result(ended)

    def _result(self, ended: float) -> SimResult:
        return SimResult(
            config=self.config,
            clock=self.clock,
            workload=self.workload,
            records=self.records,
            store=self.store,
            customer=self.customer,
            stt=self.stt,
            modulate=self.modulate,
            revision=self.revision,
            sequencer=self.sequencer,
            executors={'sync_executor': self.sync_exec, 'summary': self.summary_exec},
            counters=dict(sorted(self.counters.items())),
            truth=self.truth,
            ended_at=ended,
            polls=list(self.polls),
        )


def simulate(config: SimConfig) -> SimResult:
    return Simulation(config).run()
