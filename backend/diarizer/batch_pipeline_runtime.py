"""Dedicated GPU process entrypoint: python -m diarizer.batch_pipeline_runtime.

This deployment drains already admitted work; it never admits uploads or enables
a cohort. All storage and model construction happens after the explicit switch.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.request

from prometheus_client import CollectorRegistry, CONTENT_TYPE_LATEST, generate_latest
from prometheus_client.metrics_core import Metric
from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.registry import Collector

from config.stt_cap_dispatch import execution_admission_configured as cap_dispatch_enabled, offline_enforcement_enabled
from utils.observability.stt_cap_dispatch import AUDIO_SECONDS
from utils.observability.firestore_probe_export import register_probe_collectors
from config.batch_pipeline import worker_pipeline_depth, worker_processes
from config.batch_pipeline_providers import provider_config
from database._client import get_data_plane_firestore_client
from database.batch_pipeline_store import FirestoreStore
from database.privacy_check_metrics import NEGATIVE_LOOKUPS
from database.batch_pipeline_shadow_hook import shadow_from_env, shadow_parity_collectors
from diarizer.batch_pipeline import is_fatal_cuda_error
from diarizer.batch_pipeline_startup import ChainMemoryProbe, load_worker, synchronize_gpu
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.capacity import PoolCapacity
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.language_metrics import ROUTES as LANGUAGE_ROUTES
from utils.batch_pipeline.correctness_metrics import TRANSITIONS, DURATION, LABELS
from utils.batch_pipeline.gpu_skip_metrics import register_on as register_gpu_skip_counters
from utils.batch_pipeline.worker_metrics import COLLECTORS as WORKER_IO_COLLECTORS
from utils.batch_pipeline.errors import FatalGpuError
from utils.batch_pipeline.leader import PUMP_RECOVERY, LeaderLease
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.stage_timings import StageTimings
from database.batch_pipeline_shadow import ShadowStore
from utils.batch_pipeline.shadow_worker import ShadowRunner
from utils.batch_pipeline.shadow_metrics import COLLECTORS as SHADOW_COLLECTORS
from utils.executors import shutdown_executors
from utils.other.local_storage import create_storage_client
from utils.rollout_cohorts import configure_rollout_runtime
from utils.rollout.runtime_percent import register_runtime_percent

logger = logging.getLogger(__name__)


class RuntimeState:
    def __init__(self):
        self.ready = False
        self.stopping = False
        self.fatal = False
        self.ticked_at = time.monotonic()

    def healthy(self) -> bool:
        return time.monotonic() - self.ticked_at < 60


class SynchronizedWorker:
    def __init__(
        self,
        worker: Any,
        synchronize: Callable[[], None] = synchronize_gpu,
        on_fatal: Callable[[], None] | None = None,
        memory_probe: Any = None,
        timings: StageTimings | None = None,
    ):
        self.worker = worker
        self.synchronize = synchronize
        self.on_fatal = on_fatal
        self.memory_probe = memory_probe
        self.timings = timings or StageTimings()
        self._unavailable = False

    def process_batch(self, items, **kwargs):
        return self._process(items, self.worker.process_batch, **kwargs)

    def prepare_first(self, items):
        prepare = getattr(self.worker, 'prepare_first', None)
        return prepare(items) if prepare is not None else None

    def process_batch_deferred(self, items, **kwargs):
        process = getattr(self.worker, 'process_batch_deferred', self.worker.process_batch)
        return self._process(items, process, **kwargs)

    def _process(self, items, process, **kwargs):
        if self._unavailable:
            raise FatalGpuError('GPU chain unavailable; restart required')
        pending = None
        try:
            baseline = self.memory_probe.begin() if self.memory_probe else None
            try:
                pending = process(items, **kwargs)
                return pending
            finally:
                # Python completion is not CUDA completion. Never publish before
                # quiescence, even for a dedicated GPU with no live reservation.
                # Profiling times the existing synchronize; it adds no new one.
                self.timings.call('cuda_sync', self.synchronize)
                if self.memory_probe:
                    sample = self.memory_probe.finish(baseline)
                    logger.info(
                        'event=batch_chain_memory items=%d audio_seconds=%.3f sample=%s',
                        len(items),
                        sum(item.duration_seconds for item in items),
                        sample,
                    )
        except Exception as error:
            # Synchronization can fail after compute handed off writes. Fatal
            # CUDA must not leave those writes running beyond the receipt.
            # Keep the poisoned GPU slot held until that fatal drain completes.
            close = getattr(pending, 'close', None)
            if callable(close):
                close()
            if is_fatal_cuda_error(error):
                self._unavailable = True
                if self.on_fatal:
                    self.on_fatal()
                raise FatalGpuError('fatal CUDA error; restart GPU chain') from error
            raise


def health_server(
    state: RuntimeState, registry: CollectorRegistry, port: int, host: str = '0.0.0.0'
) -> ThreadingHTTPServer:
    register_runtime_percent(registry)
    register_probe_collectors(registry)  # Every child exports before the pod's merge_metrics.
    registry.register(LANGUAGE_ROUTES)
    for collector in WORKER_IO_COLLECTORS:
        registry.register(collector)
    for collector in SHADOW_COLLECTORS:
        registry.register(collector)
    if cap_dispatch_enabled() or offline_enforcement_enabled('batch'):
        registry.register(AUDIO_SECONDS)
    registry.register(TRANSITIONS)
    registry.register(DURATION)
    registry.register(LABELS)
    registry.register(NEGATIVE_LOOKUPS)
    register_gpu_skip_counters(registry)  # diarization decisions + per-unit FP32-parity counters
    for collector in shadow_parity_collectors():  # A2 shadow only; empty (no jobstore import) otherwise
        registry.register(collector)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/metrics':
                body, status, content_type = generate_latest(registry), 200, CONTENT_TYPE_LATEST
            elif self.path in {'/health', '/ready'}:
                ok = state.healthy() and (self.path == '/health' or (state.ready and not state.stopping))
                body, status, content_type = (b'ok' if ok else b'unavailable'), (200 if ok else 503), 'text/plain'
            else:
                body, status, content_type = b'not found', 404, 'text/plain'
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass  # Probe paths never become per-request logs.

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, name='batch-health', daemon=True).start()
    return server


# Prometheus-adapter drops a sampler series older than 60s
# (charts/batch-pipeline-worker/prometheus-adapter-rules.yaml); sample well inside it.
METRICS_SAMPLE_SECONDS = 15


async def supervise(pump: Any, state: RuntimeState, stop_event: asyncio.Event, sample_queue: bool = True) -> None:
    async def tick():
        while True:
            state.ticked_at = time.monotonic()
            await asyncio.sleep(5)

    async def sample():
        # Independent of run_once: a replica inside a multi-minute GPU batch
        # still refreshes its queue gauges, so the HPA never goes blind when
        # every replica is busy. Failures retain the last sample and freshness.
        while True:
            try:
                await pump.sample_metrics()
            except Exception as error:
                logger.warning('event=batch_queue_metrics outcome=retry exception_type=%s', type(error).__name__)
            await asyncio.sleep(METRICS_SAMPLE_SECONDS)

    tasks = [asyncio.create_task(tick())]
    if sample_queue and callable(getattr(pump, 'sample_metrics', None)):
        tasks.append(asyncio.create_task(sample()))
    state.ready = True
    try:
        await pump.run(stop_event)
        if state.fatal:
            raise RuntimeError('GPU chain quarantined; process restart required')
    finally:
        state.ready = False
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_process(store: Any, artifacts: Any, registry: CollectorRegistry, state: RuntimeState) -> None:
    config = provider_config()
    if config.pool_kind != 'dedicated_batch':
        raise ValueError('worker deployment requires the dedicated batch GPU pool')
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def stop():
        state.stopping = True
        stop_event.set()

    def fatal():
        state.fatal = True
        loop.call_soon_threadsafe(stop)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop)
    try:
        # Startup models off the event loop. Readiness remains closed until the
        # entire BF16 ASR / FP32 segmentation chain and graph policy are ready.
        worker = await asyncio.to_thread(load_worker, artifacts)
        # One shared stage-timing instance spans the worker chain, its CUDA
        # quiescence and the pump; samples land on the worker's own registry.
        timings = StageTimings(registry)
        worker.timings = timings
        from utils.batch_pipeline.compute_client import shadow_from_env

        # Lazy client creation keeps a dark rollout independent of API config.
        def shadow_recover(segment):
            return shadow_from_env().shadow_recover(segment)

        metrics = QueueMetrics(
            registry,
            worker_release=os.environ.get('BATCH_PIPELINE_WORKER_RELEASE', 'unscoped'),
            namespace=os.environ.get('POD_NAMESPACE', 'unscoped'),
            capacity_sampling=True,
            # The sampler heartbeat gates per-pod GPU busy-time in the adapter;
            # electing only one pod would hide healthy workers. Bound these
            # fleet queries independently; lever 0 restores the 15s sampler.
            oldest_min_refresh_seconds=60,
        )
        pump = Pump(
            Scheduler(store, metrics=metrics, pool='batch'),
            SynchronizedWorker(worker, on_fatal=fatal, memory_probe=ChainMemoryProbe(), timings=timings),
            metrics=metrics,
            timings=timings,
            batch_size=config.batch_size,
            flights=worker_pipeline_depth(),
            capacity=lambda: PoolCapacity(
                observed_at=time.time(), available_slots=config.batch_size, max_item_seconds=config.max_unit_seconds
            ),
            # One replica runs recovery/drain per tick; a holder stuck in a long
            # GPU batch hands over after the TTL. Fails open on store errors.
            leader=LeaderLease(store, PUMP_RECOVERY, ttl_seconds=30),
            inline_metrics=False,  # supervise() samples on its own task.
            shadow=ShadowRunner(ShadowStore(store), shadow_recover, process_index=process_index()),
        )
        # Sibling processes share the pod's queue view: one sampler per pod
        # keeps Firestore reads and the HPA's per-pod series as with one process.
        await supervise(pump, state, stop_event, sample_queue=os.getenv(PROCESS_INDEX_ENV, '0') == '0')
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


# Several pump processes per GPU (BATCH_PIPELINE_WORKER_PROCESSES): one
# process's CPU, IO and Python time inside its chain leaves the device idle, and
# a sibling's kernels fill that gap. Each child is the unchanged single-process
# runtime with its own models, leases and fences, exactly like another replica;
# it serves probes and metrics on loopback only. The parent owns the pod's port.
PROCESS_INDEX_ENV = 'BATCH_PIPELINE_WORKER_PROCESS_INDEX'


def process_index() -> int | None:
    """This child's index under the per-pod supervisor; None in a single-process pod."""
    raw = os.getenv(PROCESS_INDEX_ENV)
    return int(raw) if raw is not None and raw.isdigit() else None


CHILD_PORT_BASE = 8081
CHILD_PROBE_SECONDS = 5


class WorkerProcess:
    def __init__(self, index: int, port: int, process: Any):
        self.index = index
        self.port = port
        self.process = process

    @classmethod
    def spawn(cls, index: int) -> 'WorkerProcess':
        port = CHILD_PORT_BASE + index
        env = {**os.environ, PROCESS_INDEX_ENV: str(index), 'PORT': str(port)}
        return cls(index, port, subprocess.Popen([sys.executable, '-m', 'diarizer.batch_pipeline_runtime'], env=env))

    def poll(self) -> int | None:
        return self.process.poll()

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)

    def get(self, path: str) -> tuple[int, bytes]:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=CHILD_PROBE_SECONDS) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, b''
        except OSError:
            return 0, b''


class SupervisorState:
    def __init__(self, children: list):
        self.children = children
        self.stopping = False
        self.ticked_at = time.monotonic()

    def probe(self, children: list, path: str) -> list[tuple[int, bytes]]:
        # Concurrent, so one pod probe costs one child round trip, not N,
        # inside the kubelet's probe timeout.
        if not children:
            return []
        with ThreadPoolExecutor(max_workers=len(children)) as pool:
            return list(pool.map(lambda child: child.get(path), children))

    def healthy(self) -> bool:
        # A child that already exited is the supervisor's to handle; a running
        # child whose event loop stalls fails liveness exactly as one process would.
        running = [child for child in self.children if child.poll() is None]
        ticking = time.monotonic() - self.ticked_at < 60
        return ticking and all(status == 200 for status, _ in self.probe(running, '/health'))

    def ready(self) -> bool:
        # The pod takes no traffic of its own, but readiness gates rollout:
        # open only once every child has loaded its whole chain. A child's own
        # /ready already requires its event loop to tick.
        if self.stopping or time.monotonic() - self.ticked_at >= 60:
            return False
        if any(child.poll() is not None for child in self.children):
            return False
        return all(status == 200 for status, _ in self.probe(self.children, '/ready'))


class _Families(Collector):
    def __init__(self, families: list[Metric]):
        self.families = families

    def collect(self) -> list[Metric]:
        return self.families


def merge_metrics(pages: list[tuple[int, bytes]]) -> bytes:
    """One exposition for the pod: each child's series gain ``worker_process``.

    Queue gauges come only from the sampling child, and the HPA rules take a max
    per pod, so neither queue depth nor chain occupancy multiplies by the count.
    """
    merged: dict[str, Metric] = {}
    for index, page in pages:
        for family in text_string_to_metric_families(page.decode()):
            target = merged.setdefault(family.name, Metric(family.name, family.documentation, family.type, family.unit))
            target.samples.extend(
                sample._replace(labels={**sample.labels, 'worker_process': str(index)}) for sample in family.samples
            )
    registry = CollectorRegistry(auto_describe=False)
    registry.register(_Families(list(merged.values())))
    return generate_latest(registry)


def pod_server(state: SupervisorState, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/metrics':
                pages = zip(state.children, state.probe(state.children, '/metrics'))
                # An unreachable child drops out of one scrape; its series go
                # stale and the adapter's freshness gate treats them as missing.
                body = merge_metrics([(child.index, page) for child, (status, page) in pages if status == 200])
                status, content_type = 200, CONTENT_TYPE_LATEST
            elif self.path in {'/health', '/ready'}:
                ok = state.healthy() if self.path == '/health' else state.ready()
                body, status, content_type = (b'ok' if ok else b'unavailable'), (200 if ok else 503), 'text/plain'
            else:
                body, status, content_type = b'not found', 404, 'text/plain'
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass  # Probe paths never become per-request logs.

    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    threading.Thread(target=server.serve_forever, name='batch-pod-health', daemon=True).start()
    return server


def supervise_processes(
    count: int,
    port: int,
    spawn: Callable[[int], Any] = WorkerProcess.spawn,
    poll_seconds: float = 1.0,
) -> int:
    """Run ``count`` worker processes until SIGTERM or the first child exit.

    SIGTERM reaches every child, and each drains its own chain. Any child that
    exits unrequested, including a fatal-CUDA quarantine, drains its siblings
    and returns non-zero so Kubernetes replaces the whole pod and its GPU state.
    """
    stop = threading.Event()
    handlers = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
    state = SupervisorState([])
    server = None
    exited = None
    try:
        for index in range(count):
            state.children.append(spawn(index))
        server = pod_server(state, port)
        while not stop.is_set() and exited is None:
            state.ticked_at = time.monotonic()
            exited = next((child for child in state.children if child.poll() is not None), None)
            if exited is None:
                stop.wait(poll_seconds)
    finally:
        state.stopping = True
        if exited is not None:
            logger.error(
                'event=batch_worker_process outcome=exited index=%d returncode=%s', exited.index, exited.poll()
            )
        for child in state.children:
            child.terminate()
        # Keep liveness ticking: the drain is bounded by each child's chain and
        # the pod's termination grace, never by a supervisor deadline.
        while any(child.poll() is None for child in state.children):
            state.ticked_at = time.monotonic()
            time.sleep(poll_seconds)
        if server is not None:
            server.shutdown()
            server.server_close()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    if exited is not None:
        return exited.poll() or 1  # An unrequested clean exit still restarts the pod.
    drained = [child.poll() for child in state.children]
    return next((code for code in drained if code not in (0, -signal.SIGTERM)), 0)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if os.getenv('BATCH_PIPELINE_WORKER_ENABLED', 'false').lower() != 'true':
        logger.info('event=batch_worker outcome=disabled')
        return
    processes = worker_processes()
    if processes > 1 and PROCESS_INDEX_ENV not in os.environ:
        logger.info('event=batch_worker outcome=supervising processes=%d', processes)
        raise SystemExit(supervise_processes(processes, int(os.getenv('PORT', '8080'))))
    # Namespace validation is mandatory before either cloud client is touched.
    namespace = os.environ['BATCH_PIPELINE_NAMESPACE']
    store = FirestoreStore(namespace)
    if not os.getenv('FIRESTORE_EMULATOR_HOST') and not os.getenv('OMI_FIRESTORE_DATA_PLANE_PROJECT'):
        raise RuntimeError('explicit customer data-plane project required')
    store = shadow_from_env(FirestoreStore(namespace, firestore_client=get_data_plane_firestore_client()))
    # The worker evaluates live-reuse admission (sync_live_dedupe_active_for)
    # on admitted work items; bind the cached cohort resolver before pumping.
    configure_rollout_runtime()
    artifacts = create_artifact_store(
        store,
        create_storage_client(),
        os.environ['BUCKET_BATCH_PIPELINE'],
        os.environ.get('ENCRYPTION_SECRET', '').encode(),
    )
    state = RuntimeState()
    registry = CollectorRegistry()
    # A supervised child is reachable only through the parent's pod port.
    host = '127.0.0.1' if PROCESS_INDEX_ENV in os.environ else '0.0.0.0'
    server = health_server(state, registry, int(os.getenv('PORT', '8080')), host)
    try:
        asyncio.run(run_process(store, artifacts, registry, state))
    finally:
        state.stopping = True
        server.shutdown()
        server.server_close()
        shutdown_executors()


if __name__ == '__main__':
    main()
