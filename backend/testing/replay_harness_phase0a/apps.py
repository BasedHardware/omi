"""Role-configured ASGI entrypoint for the Replay Harness Phase 0A.

FEASIBILITY-ONLY: The finalizer and every shortcut are declared fakes, labeled
feasibility-only. This entrypoint preserves production PCM decoding, upload
staging, task-protobuf construction, route authentication, Redis locks,
job/ledger transitions, fair-use metering, status polling, and conversation
persistence. Only external/provider leaves are replaced.

Capabilities installed (all feasibility-only unless noted):
  - google.auth.default → AnonymousCredentials (production emulator boundary)
  - google.cloud.storage.Client → local filesystem (production emulator boundary)
  - Cloud Tasks _tasks_client → HTTP client to out-of-process loopback scheduler
  - id_token.verify_oauth2_token → one exact local token (feasibility-only)
  - VAD/STT/process_conversation → deterministic leaves (feasibility-only finalizer fake)
  - terminal_guard_bypassed → declared fault control (real idempotency-boundary perturbation)
  - defeat_idempotency → declared fault control (full duplicate-delivery boundary defeat)
"""

from __future__ import annotations

import json
import os
import socket
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---- egress guard (install BEFORE any backend import) ----
from testing.replay_harness_phase0a.egress_guard import guard_from_env

_egress_sink = guard_from_env()

# ---- production emulator boundary overrides (not feasibility-only) ----
import google.auth  # noqa: E402
import google.auth.credentials as google_auth_credentials  # noqa: E402


def _anonymous_google_credentials(*_args: Any, **_kwargs: Any) -> tuple[Any, str]:
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("FIREBASE_PROJECT_ID") or "demo-omi-replay-harness"
    return google_auth_credentials.AnonymousCredentials(), project


google.auth.default = _anonymous_google_credentials


# ---- filesystem GCS fake (copy of sync_cloud_tasks_stack pattern, not import) ----
_STORAGE_ROOT = os.getenv("OMI_REPLAY_STORAGE_DIR", "").strip()
if not _STORAGE_ROOT:
    raise RuntimeError("OMI_REPLAY_STORAGE_DIR is required")
_storage_path = Path(_STORAGE_ROOT)
_storage_path.mkdir(parents=True, exist_ok=True)

from google.cloud import storage as _gcs  # noqa: E402


class _LocalBlob:
    def __init__(self, bucket: "_LocalBucket", name: str):
        self._bucket = bucket
        self.name = name
        self._path = bucket._root / name

    def upload_from_filename(self, filename: str) -> None:
        import shutil

        self._path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filename, self._path)

    def upload_from_string(self, data: str | bytes) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        raw = data.encode() if isinstance(data, str) else data
        self._path.write_bytes(raw)

    def download_to_filename(self, filename: str) -> None:
        import shutil

        shutil.copy2(self._path, filename)

    def exists(self) -> bool:
        return self._path.exists()

    def delete(self) -> None:
        self._path.unlink(missing_ok=True)

    def generate_signed_url(self, *args: Any, **kwargs: Any) -> str:
        return f"replay-harness://staged/{self.name}"


class _LocalBucket:
    def __init__(self, root: Path):
        self._root = root

    def blob(self, name: str) -> _LocalBlob:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe blob path: {name}")
        return _LocalBlob(self, name)

    def list_blobs(self, prefix: str = "") -> list[_LocalBlob]:
        if not self._root.exists():
            return []
        result = []
        for p in self._root.rglob("*"):
            if p.is_file() and str(p.relative_to(self._root)).startswith(prefix):
                result.append(_LocalBlob(self, str(p.relative_to(self._root))))
        return result


class _LocalStorageClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def bucket(self, name: str) -> _LocalBucket:
        bucket_root = _storage_path / name
        bucket_root.mkdir(parents=True, exist_ok=True)
        return _LocalBucket(bucket_root)


_gcs.Client = _LocalStorageClient  # type: ignore[misc,assignment]


# ---- role selection ----
def _role() -> str:
    value = os.getenv("OMI_REPLAY_ROLE", "").strip()
    if value not in {"admission", "worker"}:
        raise RuntimeError(f"OMI_REPLAY_ROLE must be 'admission' or 'worker', got {value!r}")
    return value


ROLE = _role()

# ---- Cloud Tasks client → HTTP loopback (admission only) ----
if ROLE == "admission":
    import httpx as _httpx  # noqa: E402
    from google.api_core.exceptions import AlreadyExists  # noqa: E402
    from google.cloud import tasks_v2  # noqa: E402
    import utils.cloud_tasks as production_cloud_tasks  # noqa: E402

    _LOOPBACK_URL = os.getenv("OMI_REPLAY_LOOPBACK_URL", "")

    class _CloudTasksHTTPClient:
        """HTTP client that forwards create_task to the out-of-process loopback scheduler.

        FEASIBILITY-ONLY seam: production _get_tasks_client() has no endpoint override,
        so the _tasks_client global is swapped. The enqueue hop is a labeled seam,
        not a production Cloud Tasks transport.
        """

        @staticmethod
        def queue_path(project: str, location: str, queue: str) -> str:
            return f"projects/{project}/locations/{location}/queues/{queue}"

        @staticmethod
        def task_path(project: str, location: str, queue: str, task: str) -> str:
            return f"projects/{project}/locations/{location}/queues/{queue}/tasks/{task}"

        def create_task(self, *, parent: str, task: tasks_v2.Task, **_kwargs: Any) -> tasks_v2.Task:
            http_req = task.http_request
            body_bytes = http_req.body or b"{}"
            payload = {
                "parent": parent,
                "task_name": task.name,
                "body": json.loads(body_bytes),
                "url": http_req.url,
                "http_method": "POST",
                "headers": dict(http_req.headers),
                "oidc_sa": http_req.oidc_token.service_account_email if http_req.oidc_token else "",
                "oidc_audience": http_req.oidc_token.audience if http_req.oidc_token else "",
                "dispatch_deadline_seconds": task.dispatch_deadline.seconds if task.dispatch_deadline else 0,
            }
            with _httpx.Client(timeout=10.0, trust_env=False) as client:
                response = client.post(f"{_LOOPBACK_URL}/__replay/enqueue", json=payload)
            if response.status_code == 409:
                raise AlreadyExists(f"task {task.name} already exists")
            if response.status_code >= 400:
                raise RuntimeError(f"loopback enqueue failed: HTTP {response.status_code}")
            return task

    production_cloud_tasks._tasks_client = _CloudTasksHTTPClient()  # type: ignore[assignment]

else:
    # Worker: swap only the OIDC verifier leaf (feasibility-only).
    from google.oauth2 import id_token  # noqa: E402

    _LOCAL_OIDC_TOKEN = os.getenv("OMI_REPLAY_OIDC_TOKEN", "")
    _LOCAL_OIDC_SA = os.getenv("OMI_REPLAY_OIDC_SA", "")
    _LOCAL_OIDC_AUDIENCE = os.getenv("OMI_REPLAY_OIDC_AUDIENCE", "")

    def _verify_local_oidc(token: str, _request: Any, *, audience: str | None = None, **_kwargs: Any) -> dict[str, Any]:
        if token != _LOCAL_OIDC_TOKEN:
            raise ValueError("OIDC token mismatch")
        if audience is not None and audience != _LOCAL_OIDC_AUDIENCE:
            raise ValueError(f"OIDC audience mismatch: expected {_LOCAL_OIDC_AUDIENCE!r}, got {audience!r}")
        return {"email": _LOCAL_OIDC_SA, "email_verified": True}

    id_token.verify_oauth2_token = _verify_local_oidc


# ---- import the real backend ----
from main import app  # noqa: E402
from fastapi import Header, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


@app.get("/__replay/health", include_in_schema=False)
def replay_health() -> dict[str, str]:
    return {"status": "ok", "role": ROLE}


# ---- admission control endpoints ----
_CONTROL_TOKEN = os.getenv("OMI_REPLAY_CONTROL_TOKEN", "")


def _require_control(request: Request, control_token: str | None) -> None:
    client_host = request.client.host if request.client else None
    if client_host not in _LOOPBACK_HOSTS or control_token != _CONTROL_TOKEN:
        raise HTTPException(status_code=403, detail="replay control is loopback-only")


if ROLE == "admission":
    from database import conversations as conversations_db  # noqa: E402
    from database._client import get_firestore_client  # noqa: E402

    @app.post("/__replay/capture-provenance/{conversation_id}", include_in_schema=False, status_code=204)
    def replay_capture_provenance(
        conversation_id: str,
        payload: dict[str, Any],
        request: Request,
        control_token: str | None = Header(None, alias="X-Omi-Replay-Control"),
    ) -> Response:
        _require_control(request, control_token)
        uid = payload.get("uid")
        device_id = payload.get("device_id")
        platform = payload.get("platform")
        if not all(isinstance(v, str) and v for v in (uid, device_id, platform)):
            raise HTTPException(status_code=422, detail="capture provenance requires uid and device context")
        now = datetime.now(timezone.utc)
        capture = {
            "id": conversation_id,
            "created_at": now,
            "started_at": now,
            "finished_at": now,
            "source": "omi",
            "language": "en",
            "structured": {
                "title": "Replay harness capture provenance",
                "overview": "",
                "emoji": "🧪",
                "category": "other",
                "action_items": [],
                "events": [],
            },
            "transcript_segments": [],
            "private_cloud_sync_enabled": False,
            "status": "completed",
            "discarded": False,
            "is_locked": False,
            "data_protection_level": "enhanced",
            "client_device_id": device_id,
            "client_platform": platform,
        }
        encoded = conversations_db.encode_conversation_for_write(uid, capture, level="enhanced")
        if isinstance(encoded.get("transcript_segments"), list):
            raise RuntimeError("replay capture provenance was not encrypted by the production encoder")
        get_firestore_client().collection("users").document(uid).collection("conversations").document(
            conversation_id
        ).set(encoded)
        return Response(status_code=204)

else:
    # ---- worker: deterministic provider leaves (FEASIBILITY-ONLY finalizer fake) ----
    from models.conversation import Conversation  # noqa: E402
    from models.conversation_enums import ConversationStatus  # noqa: E402
    from models.structured import Structured  # noqa: E402
    import utils.sync.pipeline as sync_pipeline  # noqa: E402
    from utils.conversations import lifecycle as lifecycle_service  # noqa: E402
    from routers import sync as sync_router  # noqa: E402

    _TRANSCRIPT_TOKEN = os.getenv("OMI_REPLAY_TRANSCRIPT_TOKEN", "replay-harness-transcript")
    _TERMINAL_GUARD_BYPASSED = os.getenv("OMI_REPLAY_TERMINAL_GUARD_BYPASSED", "false").lower() == "true"
    _DEFEAT_IDEMPOTENCY = os.getenv("OMI_REPLAY_DEFEAT_IDEMPOTENCY", "false").lower() == "true"

    def _job_id_from_path(path: str) -> str:
        return Path(path).parent.name

    def _local_vad(path: str, *, return_segments: bool = False, **_kwargs: Any) -> Any:
        """FEASIBILITY-ONLY: deterministic VAD leaf proving the production decoder made WAV."""
        with wave.open(path, "rb") as wav_file:
            duration = wav_file.getnframes() / float(wav_file.getframerate())
        segments = [{"start": 0.0, "end": min(duration, 1.0)}] if duration >= 1.0 else []
        if _egress_sink:
            _egress_sink({"event": "vad_result", "job_id": _job_id_from_path(path), "segment_count": len(segments)})
        return segments if return_segments else bool(segments)

    def _local_prerecorded(audio_url: str, *, return_language: bool = False, **_kwargs: Any) -> Any:
        """FEASIBILITY-ONLY: deterministic STT leaf; emits no transcript into evidence."""
        job_id = audio_url.rsplit("/", 1)[-1]
        if _egress_sink:
            _egress_sink({"event": "stt_completed", "job_id": job_id, "word_count": 1})
        words = [{"timestamp": [0.0, 1.0], "speaker": "SPEAKER_00", "text": _TRANSCRIPT_TOKEN}]
        return (words, "en") if return_language else words

    def _local_process_conversation(
        uid: str,
        language: str | None = None,
        conversation: Any = None,
        *,
        language_code: str | None = None,
        persistence_observer: Any = None,
        **_kwargs: Any,
    ) -> Conversation:
        """FEASIBILITY-ONLY: declared finalizer fake — marks conversation completed via real lifecycle."""
        if conversation is None:
            raise ValueError("replay harness deterministic processor requires a conversation")
        conversation_id = getattr(conversation, "id", None)
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ValueError("replay harness processor requires a durable conversation id")
        effective_language = language_code or language or "en"
        started_at = getattr(conversation, "started_at", None) or datetime.now(timezone.utc)
        finished_at = getattr(conversation, "finished_at", None) or started_at
        completed = Conversation(
            id=conversation_id,
            created_at=getattr(conversation, "created_at", None) or started_at,
            started_at=started_at,
            finished_at=finished_at,
            source=getattr(conversation, "source", None),
            language=effective_language,
            structured=Structured(
                title="Replay harness deterministic conversation",
                overview="FEASIBILITY-ONLY finalizer fake result.",
                emoji="🧪",
                category="other",
            ),
            transcript_segments=list(getattr(conversation, "transcript_segments", [])),
            private_cloud_sync_enabled=bool(getattr(conversation, "private_cloud_sync_enabled", False)),
            status=ConversationStatus.completed,
            is_locked=bool(getattr(conversation, "is_locked", False)),
            client_device_id=getattr(conversation, "client_device_id", None),
            client_platform=getattr(conversation, "client_platform", None),
        )
        persisted = lifecycle_service.persist_processed_conversation(uid, completed.model_dump())
        if persistence_observer is not None:
            persistence_observer(persisted)
        if _egress_sink:
            _egress_sink({"event": "conversation_persisted", "conversation_id": completed.id})
        return completed

    def _delete_segment_blob_immediately(path: str, *_args: Any, **_kwargs: Any) -> None:
        sync_pipeline.delete_syncing_temporal_file(path)

    # Replace only external/provider leaves.
    sync_pipeline.vad_is_empty = _local_vad
    sync_pipeline.get_prerecorded_service = lambda _language="en": ("parakeet", "en", "parakeet")
    sync_pipeline.prerecorded = _local_prerecorded
    sync_pipeline.process_conversation = _local_process_conversation

    # ---- DECLARED FAULT CONTROL: terminal_guard_bypassed (boundary perturbation) ----
    # When enabled, the worker's terminal-status guard returns a non-terminal view
    # of completed jobs, so a duplicate Cloud Tasks delivery re-enters the handler
    # past the real idempotency boundary at routers/sync.py run_sync_job. Alone
    # (deeper defenses active), the content-ledger convergence acks the redelivery
    # without re-running the pipeline — STT stays at 1 (defense-in-depth holds).
    # Used by MUTANT_GUARDED to prove a specific defense layer catches a specific
    # boundary perturbation. The STT leaf itself is never altered.
    _apply_terminal_guard_bypass = _TERMINAL_GUARD_BYPASSED or _DEFEAT_IDEMPOTENCY
    if _apply_terminal_guard_bypass:
        _original_get_sync_job = sync_router.get_sync_job

        def _mutated_get_sync_job(job_id: str, *_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
            """FEASIBILITY-ONLY mutant: return a non-terminal view of completed jobs.

            This perturbs the real terminal-ownership boundary (the
            ``job['status'] in TERMINAL_STATUSES`` check in run_sync_job) so a
            duplicate delivery is not acked as already-terminal. It does NOT touch
            the STT leaf — any duplicate-STT defect must arise from the composed
            SUT re-running the real pipeline on the redelivery.
            """
            result = _original_get_sync_job(job_id, *_args, **_kwargs)
            if result and result.get("status") in ("completed", "done"):
                if _egress_sink:
                    _egress_sink({"event": "terminal_guard_mutant_activated", "job_id": job_id})
                mutated = dict(result)
                mutated["status"] = "processing"
                return mutated
            return result

        sync_router.get_sync_job = _mutated_get_sync_job

    # ---- DECLARED FAULT CONTROL: defeat_idempotency (full boundary defeat) ----
    # When enabled, the duplicate-delivery idempotency boundary in the composed
    # SUT is defeated so a real duplicate Cloud Tasks delivery genuinely re-runs
    # the real STT leaf once per delivery:
    #   1. terminal-status READ guard (above) — redelivery is not acked as terminal;
    #   2. terminal-ownership WRITE guard (update_sync_job) — a completed job can be
    #      re-opened (mark_job_processing) so the redelivery re-enters the pipeline;
    #   3. ledger fence — the job is forced onto the legacy (non-fenced) path, so
    #      there is no content-claim ownership and no content-ledger convergence
    #      (convergence is what otherwise acks a redelivery without re-running);
    #   4. staged-audio cleanup — no-op so the redelivery can re-download audio;
    #   5. processed-segment ledger reads — empty so segments are not skipped.
    # The STT leaf (_local_prerecorded) is unchanged: it invokes the provider
    # exactly once per real pipeline run. STT > 1 therefore arises ONLY because
    # two real deliveries each run the real pipeline — not from a self-calling
    # fake. Used by MUTANT_UNGUARDED to prove the scenario is regression-
    # sensitive: it FAILS unless the real boundary defeat surfaces the defect.
    if _DEFEAT_IDEMPOTENCY:
        _original_uses_fence = sync_router.sync_job_uses_ledger_fence

        def _defeated_uses_fence(_job: Any) -> bool:
            """FEASIBILITY-ONLY mutant: force the legacy non-fenced path.

            Removing the ledger fence disables content-claim ownership and
            content-ledger convergence — the real boundary that otherwise acks a
            redelivery from the durable ledger without re-running the pipeline.
            The non-fenced run-lock + finalization still operate, so the
            redelivery re-runs the pipeline and reaches a terminal cleanly.
            """
            if _egress_sink:
                _egress_sink({"event": "idempotency_boundary_defeated", "checkpoint": "ledger_fence"})
            return False

        sync_router.sync_job_uses_ledger_fence = _defeated_uses_fence
        # Defeat the WRITE-level terminal-ownership boundary: update_sync_job
        # (database/sync_jobs.py) rejects any mutation of a job whose status is in
        # TERMINAL_STATUSES — the real guard that prevents re-opening a completed
        # job. Emptying the module global lets a redelivery mark-job-processing
        # and finalize on the legacy path. (The handler-level READ guard is
        # defeated separately by the terminal-guard bypass above.)
        import database.sync_jobs as _sync_jobs_db  # noqa: E402

        _sync_jobs_db.TERMINAL_STATUSES = ()
        if _egress_sink:
            _egress_sink({"event": "idempotency_boundary_defeated", "checkpoint": "write_level_terminal_guard"})

        async def _noop_delete_blobs(_paths: Any) -> None:
            """FEASIBILITY-ONLY mutant: keep staged audio so a redelivery re-downloads."""
            if _egress_sink:
                _egress_sink({"event": "idempotency_boundary_defeated", "checkpoint": "staged_audio_cleanup"})

        sync_router._delete_staged_blobs_async = _noop_delete_blobs

        _original_get_processed = sync_pipeline.get_processed_segments
        _original_get_durable = sync_pipeline.get_processed_sync_segment_ids

        def _empty_processed(_job_id: str) -> set[str]:
            if _egress_sink:
                _egress_sink({"event": "idempotency_boundary_defeated", "checkpoint": "processed_segment_ledger"})
            return set()

        def _empty_durable(_uid: str, _content_id: str) -> set[str]:
            return set()

        sync_pipeline.get_processed_segments = _empty_processed
        sync_pipeline.get_processed_sync_segment_ids = _empty_durable
