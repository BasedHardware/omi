"""Production's batch speech worker on this machine's CPU.

In production a GPU pod runs ``python -m diarizer.batch_pipeline_runtime``: it
pulls recorded units, runs voice detection, Parakeet speech recognition and
pyannote speaker separation, and writes the result for projection. Phone
recordings are transcribed there, not by a live vendor stream.

This launcher runs that same process: ``diarizer.batch_pipeline_runtime.main``
with the same pinned model revisions and the same scheduler, leases, heartbeats
and compute-admission call. Three things are substituted, all of them compute
or identity infrastructure:

* the models load on CPU in FP32 through the repository's own
  ``load_local_models`` (production: one CUDA GPU, BF16). The repository states
  that this is not numerical parity; text can differ slightly from production;
* the CUDA synchronize and GPU memory probe are no-ops;
* the worker's identity token is the stack's local token; production fetches
  one from the metadata server. The control-plane call itself is unchanged and
  goes to the stack's HTTPS stand-in for backend-sync.

The repository's hermetic gauntlet (``backend/testing/sync_cloud_tasks_stack/batch_worker.py``)
runs the same runtime with fake models and no network; this launcher is the
long-running counterpart with the real ones.

It needs the separate model runtime (``backend/.venv-eval``, built from
``backend/scripts/diarization_eval/requirements-eval.txt``) and a Hugging Face
token that has accepted the terms of ``pyannote/speaker-diarization-community-1``.
"""

from __future__ import annotations

import os
import sys

THREADS_ENV = "OMI_HARNESS_BATCH_WORKER_THREADS"
WORKERS_ENV = "OMI_HARNESS_BATCH_WORKERS"
# Production runs a fleet of GPU replicas (charts/batch-pipeline-worker prod values). One CPU process transcribes about
# ten times faster than real time but spends several seconds per unit, and a
# phone uploads a unit every few seconds, so one process falls behind.
DEFAULT_WORKERS = 3

CPU_SIZING = {
    # One model set in memory, one unit at a time: sizing for a laptop CPU, where
    # production runs two processes with a pipeline depth of three on a GPU.
    "BATCH_PIPELINE_WORKER_PROCESSES": "1",
    "BATCH_PIPELINE_WORKER_PIPELINE_DEPTH": "1",
    "BATCH_PIPELINE_MODEL_BATCH_SIZE": "1",
    # CUDA-graph decoding does not exist off CUDA.
    "BATCH_PIPELINE_ASR_CUDA_GRAPHS_ENABLED": "false",
}


def main() -> int:
    from dev_harness import local_task_queue

    secret = os.environ.get(local_task_queue.SECRET_ENV, "").strip()
    if not secret:
        raise RuntimeError(f"the batch worker needs {local_task_queue.SECRET_ENV} (set by the dev harness)")
    if not os.environ.get("FIRESTORE_EMULATOR_HOST", "").strip():
        raise RuntimeError("the local batch worker only runs against the Firestore emulator")
    if not os.environ.get("HUGGINGFACE_TOKEN", "").strip():
        raise RuntimeError(
            "HUGGINGFACE_TOKEN is not set: production's speaker model (pyannote/speaker-diarization-community-1) "
            "is access-gated; add a token that has accepted its terms to backend/.env.local-dev"
        )

    import diarizer.batch_pipeline_runtime as runtime
    import diarizer.batch_pipeline_startup as startup
    from utils.batch_pipeline import compute_client

    batch_size = int(os.environ.get("BATCH_PIPELINE_MODEL_BATCH_SIZE", "1"))
    threads = int(os.environ.get(THREADS_ENV, "0") or 0)
    if threads > 0:
        # Several worker processes share this machine's cores (production gives each replica its own GPU).
        import torch

        torch.set_num_threads(threads)

    def load_worker(artifacts):
        return startup.load_local_worker(artifacts, device="cpu", dtype="float32", model_batch_size=batch_size)

    class CpuSynchronizedWorker(runtime.SynchronizedWorker):
        def __init__(self, worker, synchronize=None, on_fatal=None, memory_probe=None, timings=None):
            super().__init__(worker, synchronize=lambda: None, on_fatal=on_fatal, memory_probe=None, timings=timings)

    def local_identity_token(_request, audience):
        identity = os.environ["BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT"]
        return f"{local_task_queue.TOKEN_PREFIX}:{secret}:{audience}:{identity}"

    runtime.load_worker = load_worker
    runtime.SynchronizedWorker = CpuSynchronizedWorker
    runtime.ChainMemoryProbe = lambda: None
    compute_client.fetch_id_token = local_identity_token
    print("harness_batch_worker event=starting device=cpu dtype=float32", flush=True)
    runtime.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
