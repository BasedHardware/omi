"""Dedicated GPU process entrypoint: python -m diarizer.batch_pipeline_runtime.

This deployment drains already admitted work; it never admits uploads or enables
a cohort. All storage and model construction happens after the explicit switch.
"""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import os
import signal
import threading
import time
from typing import Any, Callable

from prometheus_client import CollectorRegistry, CONTENT_TYPE_LATEST, generate_latest

from config.stt_cap_dispatch import execution_admission_configured as cap_dispatch_enabled
from utils.observability.stt_cap_dispatch import AUDIO_SECONDS
from config.batch_pipeline import worker_pipeline_depth
from config.batch_pipeline_providers import provider_config
from database._client import get_data_plane_firestore_client
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_shadow_hook import shadow_from_env, shadow_parity_collectors
from diarizer.batch_pipeline import is_fatal_cuda_error
from diarizer.batch_pipeline_startup import ChainMemoryProbe, load_worker, synchronize_gpu
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.capacity import PoolCapacity
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.language_metrics import ROUTES as LANGUAGE_ROUTES
from utils.batch_pipeline.correctness_metrics import TRANSITIONS, DURATION, LABELS
from utils.batch_pipeline.errors import FatalGpuError
from utils.batch_pipeline.leader import PUMP_RECOVERY, LeaderLease
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler
from database.batch_pipeline_shadow import ShadowStore
from utils.batch_pipeline.shadow_worker import ShadowRunner
from utils.batch_pipeline.shadow_metrics import COLLECTORS as SHADOW_COLLECTORS
from utils.executors import shutdown_executors
from utils.other.local_storage import create_storage_client
from utils.rollout_cohorts import configure_rollout_runtime

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
    ):
        self.worker = worker
        self.synchronize = synchronize
        self.on_fatal = on_fatal
        self.memory_probe = memory_probe
        self._unavailable = False

    def process_batch(self, items, **kwargs):
        if self._unavailable:
            raise FatalGpuError('GPU chain unavailable; restart required')
        try:
            baseline = self.memory_probe.begin() if self.memory_probe else None
            try:
                return self.worker.process_batch(items, **kwargs)
            finally:
                # Python completion is not CUDA completion. Never publish before
                # quiescence, even for a dedicated GPU with no live reservation.
                self.synchronize()
                if self.memory_probe:
                    sample = self.memory_probe.finish(baseline)
                    logger.info(
                        'event=batch_chain_memory items=%d audio_seconds=%.3f sample=%s',
                        len(items),
                        sum(item.duration_seconds for item in items),
                        sample,
                    )
        except Exception as error:
            if is_fatal_cuda_error(error):
                self._unavailable = True
                if self.on_fatal:
                    self.on_fatal()
                raise FatalGpuError('fatal CUDA error; restart GPU chain') from error
            raise


def health_server(state: RuntimeState, registry: CollectorRegistry, port: int) -> ThreadingHTTPServer:
    registry.register(LANGUAGE_ROUTES)
    for collector in SHADOW_COLLECTORS:
        registry.register(collector)
    if cap_dispatch_enabled():
        registry.register(AUDIO_SECONDS)
    registry.register(TRANSITIONS)
    registry.register(DURATION)
    registry.register(LABELS)
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

    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    threading.Thread(target=server.serve_forever, name='batch-health', daemon=True).start()
    return server


# Prometheus-adapter drops a sampler series older than 60s
# (charts/batch-pipeline-worker/prometheus-adapter-rules.yaml); sample well inside it.
METRICS_SAMPLE_SECONDS = 15


async def supervise(pump: Any, state: RuntimeState, stop_event: asyncio.Event) -> None:
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
    if callable(getattr(pump, 'sample_metrics', None)):
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
        from utils.batch_pipeline.compute_client import shadow_from_env

        # Lazy client creation keeps a dark rollout independent of API config.
        def shadow_recover(segment):
            return shadow_from_env().shadow_recover(segment)

        metrics = QueueMetrics(
            registry,
            worker_release=os.environ.get('BATCH_PIPELINE_WORKER_RELEASE', 'unscoped'),
            namespace=os.environ.get('POD_NAMESPACE', 'unscoped'),
        )
        pump = Pump(
            Scheduler(store, metrics=metrics, pool='batch'),
            SynchronizedWorker(worker, on_fatal=fatal, memory_probe=ChainMemoryProbe()),
            metrics=metrics,
            batch_size=config.batch_size,
            flights=worker_pipeline_depth(),
            capacity=lambda: PoolCapacity(
                observed_at=time.time(), available_slots=config.batch_size, max_item_seconds=config.max_unit_seconds
            ),
            # One replica runs recovery/drain per tick; a holder stuck in a long
            # GPU batch hands over after the TTL. Fails open on store errors.
            leader=LeaderLease(store, PUMP_RECOVERY, ttl_seconds=30),
            inline_metrics=False,  # supervise() samples on its own task.
            shadow=ShadowRunner(ShadowStore(store), shadow_recover),
        )
        await supervise(pump, state, stop_event)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if os.getenv('BATCH_PIPELINE_WORKER_ENABLED', 'false').lower() != 'true':
        logger.info('event=batch_worker outcome=disabled')
        return
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
    server = health_server(state, registry, int(os.getenv('PORT', '8080')))
    try:
        asyncio.run(run_process(store, artifacts, registry, state))
    finally:
        state.stopping = True
        server.shutdown()
        server.server_close()
        shutdown_executors()


if __name__ == '__main__':
    main()
