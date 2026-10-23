"""Batch GPU-worker process for the gauntlet: the real runtime minus CUDA.

``python -m testing.sync_cloud_tasks_stack.batch_worker`` runs the production
``diarizer.batch_pipeline_runtime.run_process`` (SIGTERM/SIGINT handling,
supervised ``Pump`` over a real ``Scheduler(FirestoreStore)``, heartbeats,
ordered merge, and the OIDC spend-admission RPC) against the loopback
Firestore emulator and the shared filesystem artifact bucket.  Only these are
replaced:

* ``load_worker`` builds the real ``PipelineWorker`` with fake words/diarizer/
  model-VAD leaves (``batch_providers``) instead of CUDA models;
* ``SynchronizedWorker``'s CUDA synchronize and memory probe become no-ops;
* the compute-admission client posts to the loopback serving process with one
  exact local OIDC token (the URL keeps the production HTTPS audience shape);
* optionally, ``LEASE_SECONDS``/``HEARTBEAT_SECONDS`` are time-compressed so
  lease-expiry recovery after a hard kill fits in CI.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .isolation import install_no_egress_guard

install_no_egress_guard()

from .events import write_event  # noqa: E402
from .storage import configure_storage_dir, patch_google_storage  # noqa: E402

WORKER_NAME = os.getenv('OMI_BATCH_STACK_WORKER_NAME', 'batch-worker')


def _loopback_send(serving_origin: str):
    """Deliver the production HTTPS RPC to the serving process over loopback."""

    def send(request: Request, timeout: float = 5) -> Any:
        target = urlsplit(request.full_url)
        expected = urlsplit(os.environ['BATCH_PIPELINE_API_URL'])
        if (target.scheme, target.netloc) != (expected.scheme, expected.netloc):
            raise RuntimeError('compute admission targeted an unexpected origin')
        loopback = Request(
            serving_origin + target.path,
            data=request.data,
            method=request.get_method(),
            headers=dict(request.header_items()),
        )
        return urlopen(loopback, timeout=timeout)

    return send


def _record_lease_transitions(scheduler_class: Any) -> None:
    """Evidence for every lease this replica was granted or refunded.

    The job row's ``attempt`` is a retry budget, not a grant count: a refund
    (``defer``) decrements it, and it cannot attribute grants to replicas. The
    two-replica scenario bounds compute by these grant events instead.
    """
    pull, defer = scheduler_class.pull, scheduler_class.defer

    def recorded_pull(self: Any, *args: Any, **kwargs: Any) -> Any:
        leases = pull(self, *args, **kwargs)
        for lease in leases:
            write_event(
                'providers',
                {
                    'event': 'lease_granted',
                    'segment_id': lease.item.segment_id,
                    'attempt': lease.attempt,
                    'worker_name': WORKER_NAME,
                },
            )
        return leases

    def recorded_defer(self: Any, segment_id: str, *args: Any, **kwargs: Any) -> Any:
        refunded = defer(self, segment_id, *args, **kwargs)
        write_event(
            'providers',
            {
                'event': 'lease_refunded',
                'segment_id': segment_id,
                'refunded': bool(refunded),
                'worker_name': WORKER_NAME,
            },
        )
        return refunded

    scheduler_class.pull, scheduler_class.defer = recorded_pull, recorded_defer


def main() -> int:
    storage_root = os.getenv('OMI_SYNC_STACK_STORAGE_DIR', '').strip()
    serving_origin = os.getenv('OMI_BATCH_STACK_SERVING_ORIGIN', '').strip()
    if not storage_root or not serving_origin.startswith('http://127.0.0.1:'):
        raise RuntimeError('batch worker requires local storage and a loopback serving origin')
    configure_storage_dir(storage_root)
    patch_google_storage()

    from prometheus_client import CollectorRegistry

    import diarizer.batch_pipeline_runtime as runtime
    from database.batch_pipeline_store import FirestoreStore
    from utils.batch_pipeline import pump as pump_module
    from utils.batch_pipeline import scheduler as scheduler_module
    from utils.batch_pipeline.artifact_policy import create_artifact_store
    from utils.batch_pipeline.compute_client import ComputeClient
    from utils.other.local_storage import create_storage_client
    from utils.rollout_cohorts import configure_rollout_runtime

    from .batch_providers import ModeRoutingWorker
    from .local_oidc import local_oidc_token

    lease_seconds = os.getenv('OMI_BATCH_STACK_LEASE_SECONDS', '').strip()
    heartbeat_seconds = os.getenv('OMI_BATCH_STACK_HEARTBEAT_SECONDS', '').strip()
    if lease_seconds:
        scheduler_module.LEASE_SECONDS = float(lease_seconds)
    if heartbeat_seconds:
        pump_module.HEARTBEAT_SECONDS = float(heartbeat_seconds)
    _record_lease_transitions(scheduler_module.Scheduler)

    namespace = os.environ['BATCH_PIPELINE_NAMESPACE']
    store = FirestoreStore(namespace)
    configure_rollout_runtime()
    artifacts = create_artifact_store(
        store,
        create_storage_client(),
        os.environ['BUCKET_BATCH_PIPELINE'],
        os.environ.get('ENCRYPTION_SECRET', '').encode(),
    )

    def load_worker(loaded_artifacts: Any) -> ModeRoutingWorker:
        write_event('worker', {'event': 'batch_worker_ready', 'worker_name': WORKER_NAME})
        return ModeRoutingWorker(loaded_artifacts)

    class CpuSynchronizedWorker(runtime.SynchronizedWorker):
        def __init__(self, worker: Any, synchronize: Any = None, on_fatal: Any = None, memory_probe: Any = None):
            super().__init__(worker, synchronize=lambda: None, on_fatal=on_fatal, memory_probe=None)

    token = local_oidc_token(
        os.environ['BATCH_PIPELINE_WORKER_AUDIENCE'], os.environ['BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT']
    )
    runtime.load_worker = load_worker
    runtime.SynchronizedWorker = CpuSynchronizedWorker
    runtime.ChainMemoryProbe = lambda: None
    pump_module.compute_client_from_env = lambda: ComputeClient(
        os.environ['BATCH_PIPELINE_API_URL'],
        os.environ['BATCH_PIPELINE_WORKER_AUDIENCE'],
        os.environ['OMI_ENV_STAGE'],
        token=lambda: token,
        send=_loopback_send(serving_origin),
    )

    state = runtime.RuntimeState()
    started = time.monotonic()
    write_event('worker', {'event': 'batch_worker_started', 'worker_name': WORKER_NAME, 'pid': os.getpid()})
    try:
        asyncio.run(runtime.run_process(store, artifacts, CollectorRegistry(), state))
    finally:
        write_event(
            'worker',
            {
                'event': 'batch_worker_exited',
                'worker_name': WORKER_NAME,
                'stopping': state.stopping,
                'fatal': state.fatal,
                'uptime_ms': int((time.monotonic() - started) * 1000),
            },
        )
        runtime.shutdown_executors()
    return 0


if __name__ == '__main__':
    sys.exit(main())
