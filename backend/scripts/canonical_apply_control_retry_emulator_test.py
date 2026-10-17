#!/usr/bin/env python3
"""Exercise the canonical apply-control read retry against the Firestore emulator.

This is the incident-specific proof for the CanonicalApplyStateUnavailable
retry fix (memory_system.py:64 error group): it drives the production
``ensure_canonical_apply_control_state`` against a real Firestore client so the
retry boundary, the per-attempt SDK-retry disable/timeout kwargs, and the
deletion-fence re-check all execute through the true client/emulator boundary —
the class of coverage ``backend/AGENTS.md`` requires for retry-behavior
incidents before any hermetic fake is trusted.

Scenarios:
1. A transient fault injected at the client's API layer (below
   ``DocumentReference.get``) is retried and recovered within the boundary's
   three-attempt budget.
2. A sustained transient fault exhausts the budget and fails closed with
   CanonicalApplyStateUnavailable; no control document is provisioned.
3. A deletion that starts while the retry loop is waiting cannot re-enroll a
   wiped account: the post-retry deletion-fence re-check refuses the
   first-write path even though the pre-loop fence read was clear.
4. The per-attempt read really passes ``retry=None`` and a bounded timeout: a
   probe records the kwargs seen at the API boundary.

No production project is touched; loopback emulator only.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "demo-omi-jit-qa")
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("ENCRYPTION_SECRET", "omi_apply_control_retry_emulator_key_32_bytes")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.api_core.exceptions import ServiceUnavailable  # noqa: E402
from google.cloud import firestore  # noqa: E402

from database.memory_collections import MemoryCollections  # noqa: E402
from utils.memory.memory_system import (  # noqa: E402
    CanonicalApplyStateUnavailable,
    ensure_canonical_apply_control_state,
)


def _assert_emulator_only() -> None:
    host = (os.environ.get("FIRESTORE_EMULATOR_HOST") or "").strip()
    if not host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"refusing non-loopback Firestore emulator host: {hostname}")
    if not PROJECT_ID.startswith("demo-"):
        raise RuntimeError(f"refusing non-demo Firestore project: {PROJECT_ID}")


def _install_flaky_batch_get(db_client: Any, *, fail_first: int, control_path_suffix: str) -> dict[str, Any]:
    """Inject transient ServiceUnavailable faults at the client's API layer.

    ``DocumentReference.get`` funnels into ``_client._firestore_api.batch_get_documents``;
    faulting there exercises the full production call path including the
    retry/timeout kwargs handling, rather than a bespoke fake ``_Ref.get``.
    Faults are scoped to requests for the apply-control document: the deletion
    fence read intentionally has no retry budget of its own, so an unscoped
    injector would fail the gate before the retried read under proof runs.
    """
    state: dict[str, Any] = {"calls": 0, "failures": 0, "kwargs": []}
    api = db_client._firestore_api
    original = api.batch_get_documents

    def _targets_control(request: Any) -> bool:
        # The gapic layer passes a plain request dict with a "documents" list of
        # fully-qualified resource paths.
        documents = list(
            (request or {}).get("documents", [])
            if isinstance(request, dict)
            else getattr(request, "documents", None) or []
        )
        return any(str(path).endswith(control_path_suffix) for path in documents)

    def flaky_batch_get(*args: Any, **kwargs: Any) -> Any:
        request = kwargs.get("request") or (args[0] if args else None)
        if not _targets_control(request):
            return original(*args, **kwargs)
        state["calls"] += 1
        state["kwargs"].append({k: repr(v) for k, v in kwargs.items() if k in {"retry", "timeout"}})
        if state["failures"] < fail_first:
            state["failures"] += 1
            raise ServiceUnavailable("synthetic transient blip at the API layer")
        return original(*args, **kwargs)

    api.batch_get_documents = flaky_batch_get
    state["restore"] = lambda: setattr(api, "batch_get_documents", original)
    return state


def _install_permanent_batch_get(db_client: Any, *, control_path_suffix: str) -> dict[str, Any]:
    """Sustained transient outage: every apply-control read fails with ServiceUnavailable."""
    state: dict[str, Any] = {"calls": 0, "kwargs": []}
    api = db_client._firestore_api
    original = api.batch_get_documents

    def _targets_control(request: Any) -> bool:
        # The gapic layer passes a plain request dict with a "documents" list of
        # fully-qualified resource paths.
        documents = list(
            (request or {}).get("documents", [])
            if isinstance(request, dict)
            else getattr(request, "documents", None) or []
        )
        return any(str(path).endswith(control_path_suffix) for path in documents)

    def unavailable_batch_get(*args: Any, **kwargs: Any) -> Any:
        request = kwargs.get("request") or (args[0] if args else None)
        if not _targets_control(request):
            return original(*args, **kwargs)
        state["calls"] += 1
        state["kwargs"].append({k: repr(v) for k, v in kwargs.items() if k in {"retry", "timeout"}})
        raise ServiceUnavailable("synthetic sustained outage at the API layer")

    api.batch_get_documents = unavailable_batch_get
    state["restore"] = lambda: setattr(api, "batch_get_documents", original)
    return state


def _cleanup(db_client: Any, uids: list[str]) -> None:
    for uid in uids:
        collections = MemoryCollections(uid=uid)
        db_client.document(collections.memory_apply_control_state).delete()
        db_client.document(f"canonical_memory_maintenance_registry/{uid}").delete()
        db_client.document(f"account_deletions/{uid}").delete()


def main() -> int:
    _assert_emulator_only()
    db_client: Any = firestore.Client(project=PROJECT_ID)
    uids: list[str] = []

    try:
        # --- Scenario 1: transient blip recovers within the budget -----------
        uid = f"uid-apply-retry-recover-{uuid4().hex[:8]}"
        uids.append(uid)
        control_suffix = MemoryCollections(uid=uid).memory_apply_control_state
        state = _install_flaky_batch_get(db_client, fail_first=1, control_path_suffix=control_suffix)
        control = ensure_canonical_apply_control_state(uid, db_client=db_client)
        state["restore"]()
        if control.uid != uid or control.account_generation != 1:
            raise AssertionError(f"recovered control state is wrong: {control}")
        if state["failures"] != 1:
            raise AssertionError(f"expected exactly one injected fault, saw {state['failures']}")

        # --- Scenario 4: per-attempt retry/timeout kwargs reach the API -------
        seen = list(state["kwargs"])
        if not seen or not all(entry.get("retry") == "None" for entry in seen):
            raise AssertionError(f"read did not disable the SDK retry per attempt: {seen}")
        if not all(float(entry.get("timeout", "0") or 0) > 0 for entry in seen):
            raise AssertionError(f"read did not pass a bounded per-attempt timeout: {seen}")
        registry = db_client.document(f"canonical_memory_maintenance_registry/{uid}").get()
        if not registry.exists:
            raise AssertionError("maintenance registry entry missing after recovery")
        print("PASS: transient blip recovered through the real client boundary with bounded per-attempt reads")

        # --- Scenario 2: sustained outage fails closed after the budget ------
        uid = f"uid-apply-retry-exhaust-{uuid4().hex[:8]}"
        uids.append(uid)
        control_suffix = MemoryCollections(uid=uid).memory_apply_control_state
        outage_state = _install_permanent_batch_get(db_client, control_path_suffix=control_suffix)
        started = time.monotonic()
        try:
            ensure_canonical_apply_control_state(uid, db_client=db_client)
            raise AssertionError("sustained outage must fail closed")
        except CanonicalApplyStateUnavailable as exc:
            if "unreadable" not in str(exc):
                raise AssertionError(f"unexpected fail-closed message: {exc}") from exc
        finally:
            outage_state["restore"]()
        elapsed = time.monotonic() - started
        # 3 attempts + 0.1s + 0.3s backoff; must be seconds, not minutes.
        if elapsed > 30:
            raise AssertionError(f"exhaustion took {elapsed:.1f}s; per-attempt budget is not bounded")
        if outage_state["calls"] != 3:
            raise AssertionError(f"expected exactly 3 attempts, saw {outage_state['calls']}")
        control_after = db_client.document(MemoryCollections(uid=uid).memory_apply_control_state).get()
        if control_after.exists:
            raise AssertionError("control document provisioned despite exhausted budget")
        print("PASS: sustained outage failed closed after exactly 3 bounded attempts")

        # --- Scenario 3: deletion race during the retry window ---------------
        uid = f"uid-apply-retry-wipe-race-{uuid4().hex[:8]}"
        uids.append(uid)
        control_suffix = MemoryCollections(uid=uid).memory_apply_control_state
        wipe_state = _install_flaky_batch_get(db_client, fail_first=1, control_path_suffix=control_suffix)

        import utils.memory.memory_system as memory_system_module

        real_fence = memory_system_module.read_account_deletion_projection_fence

        def wiping_fence_reader(uid_arg: str, *, db_client: Any = None) -> Any:
            calls = getattr(wiping_fence_reader, "calls", 0)
            wiping_fence_reader.calls = calls + 1  # type: ignore[attr-defined]
            if calls > 0:
                # Simulate deletion completing between attempts: the wipe marker
                # now blocks projection writes, and the control doc is gone.
                db_client.document(f"account_deletions/{uid_arg}").set({"wipe_status": "completed"})
                db_client.document(MemoryCollections(uid=uid_arg).memory_apply_control_state).delete()
            return real_fence(uid_arg, db_client=db_client)

        memory_system_module.read_account_deletion_projection_fence = wiping_fence_reader
        try:
            try:
                ensure_canonical_apply_control_state(uid, db_client=db_client)
                raise AssertionError("post-retry wipe must refuse provisioning")
            except CanonicalApplyStateUnavailable as exc:
                if "account deletion" not in str(exc):
                    raise AssertionError(f"unexpected deletion-race message: {exc}") from exc
            control_after = db_client.document(MemoryCollections(uid=uid).memory_apply_control_state).get()
            if control_after.exists:
                raise AssertionError("control document recreated after completed wipe")
            registry = db_client.document(f"canonical_memory_maintenance_registry/{uid}").get()
            if registry.exists:
                raise AssertionError("maintenance registry entry recreated after completed wipe")
        finally:
            memory_system_module.read_account_deletion_projection_fence = real_fence
            wipe_state["restore"]()
        print("PASS: deletion completing during the retry window refused re-enrollment")

        print(
            "PASS: canonical apply-control retry Firestore emulator proof "
            "(transient-recovery/exhausted-fail-closed/deletion-race/bounded-attempt-kwargs)"
        )
        return 0
    finally:
        _cleanup(db_client, uids)


if __name__ == "__main__":
    raise SystemExit(main())
