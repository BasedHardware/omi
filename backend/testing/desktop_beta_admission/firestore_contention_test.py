#!/usr/bin/env python3
"""Real Firestore-emulator proof for the final Beta admission fence.

The emulator uses pessimistic transactions.  The stale-capture cases therefore
commit the competing control transition before the final production control
read, which is the serializable state the admission transaction must reject.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore import transactional
from google.cloud.firestore_v1.document import DocumentReference

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
EMULATOR_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database.desktop_update_channels import (  # noqa: E402
    BETA_ADMISSION_COLLECTION,
    BETA_ADMISSION_DOCUMENT,
    CHANNELS_COLLECTION,
    MANIFESTS_COLLECTION,
    admit_qualified_beta_manifest,
    capture_beta_admission,
    reserve_beta_candidate,
    set_beta_admission_enabled,
)

_WAIT_SECONDS = 20


def _require_safe_emulator() -> None:
    host, separator, port = EMULATOR_HOST.rpartition(":")
    if not separator or not port.isdigit() or host not in {"127.0.0.1", "localhost", "::1", "[::1]"}:
        raise SystemExit("Refusing to run: FIRESTORE_EMULATOR_HOST must be a loopback host and port.")
    if not PROJECT_ID.startswith("demo-"):
        raise SystemExit("Refusing to run: GOOGLE_CLOUD_PROJECT must start with demo-.")
    try:
        socket.getaddrinfo(host.strip("[]"), int(port), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SystemExit(f"Refusing to run: emulator host is not resolvable: {exc}") from exc


def _manifest(tag: str) -> dict[str, Any]:
    version, build_and_suffix = tag[1:].split("+", 1)
    build = int(build_and_suffix.removesuffix("-macos"))
    return {
        "schema_version": 1,
        "release_id": tag,
        "platform": "macos",
        "version": version,
        "build_number": build,
        "app_source_sha": "a" * 40,
        "zip_url": f"https://github.com/BasedHardware/omi/releases/download/{tag}/Omi.zip",
        "dmg_url": f"https://github.com/BasedHardware/omi/releases/download/{tag}/omi.dmg",
        "ed_signature": "emulator-sparkle-signature",
        "qualification_evidence_asset": f"qualification-evidence-{tag}.json",
        "qualification_evidence_sha256": "sha256:" + "d" * 64,
        "qualification_tier": "T2",
        "qualification_passed": True,
        "backend_mode": "app_only",
        "compatibility_contract": {
            "schema_version": 1,
            "app_release_id": tag,
            "app_version": version,
            "app_build_number": build,
            "backend_mode": "app_only",
            "environment_contract_version": "desktop-backend-env-v1",
        },
        "environment_contract_version": "desktop-backend-env-v1",
        "created_at": "2026-07-21T12:00:00Z",
        "published_at": "2026-07-21T12:00:00Z",
        "changelog": ["Firestore emulator admission proof"],
        "mandatory": False,
        "zip_sha256": "sha256:" + "b" * 64,
        "dmg_sha256": "sha256:" + "c" * 64,
    }


def _fresh_tags() -> tuple[str, str]:
    build = 100_000 + (uuid.uuid4().int % 800_000)
    return f"v0.12.64+{build}-macos", f"v0.12.64+{build + 1}-macos"


def _delete_if_present(ref: Any) -> None:
    if ref.get().exists:
        ref.delete()


def _seed_stable_pointer(client: Any, run_id: str) -> tuple[Any, dict[str, Any]]:
    stable_ref = client.collection(CHANNELS_COLLECTION).document("macos-stable")
    stable_manifest = {"release_id": f"stable-{run_id}", "generation": 77, "sentinel": run_id}
    stable_ref.set(stable_manifest)
    return stable_ref, stable_manifest


def _direct_generation_transition(client: Any) -> None:
    """Commit a schema-valid direct control generation transition in another client."""
    control_ref = client.collection(BETA_ADMISSION_COLLECTION).document(BETA_ADMISSION_DOCUMENT)

    @transactional
    def transition(transaction: Any) -> None:
        snapshot = control_ref.get(transaction=transaction)
        assert snapshot.exists
        control = snapshot.to_dict()
        assert isinstance(control, dict)
        control["control_generation"] += 1
        control["admission_updated_at"] = datetime.now(timezone.utc)
        transaction.set(control_ref, control)

    transition(client.transaction())


def _prepare_case(client: Any) -> tuple[str, str, Any, Any, Any, Any, dict[str, Any]]:
    tag_a, tag_b = _fresh_tags()
    run_id = uuid.uuid4().hex
    control_ref = client.collection(BETA_ADMISSION_COLLECTION).document(BETA_ADMISSION_DOCUMENT)
    manifest_ref = client.collection(MANIFESTS_COLLECTION).document(tag_a)
    beta_ref = client.collection(CHANNELS_COLLECTION).document("macos-beta")
    stable_ref, stable_before = _seed_stable_pointer(client, run_id)
    for ref in (control_ref, manifest_ref, beta_ref):
        _delete_if_present(ref)

    reserve_beta_candidate(tag_a, firestore_client=client)
    enabled = set_beta_admission_enabled(True, firestore_client=client)
    captured = capture_beta_admission(tag_a, firestore_client=client)
    assert captured["control_generation"] == enabled["control_generation"]
    return tag_a, tag_b, control_ref, manifest_ref, beta_ref, stable_ref, stable_before


def _assert_stale_zero_writes(
    name: str, error: object, manifest_ref: Any, beta_ref: Any, stable_ref: Any, stable: dict[str, Any]
) -> str:
    assert isinstance(error, ValueError), f"{name}: stale A unexpectedly committed: {error!r}"
    message = str(error)
    assert any(token in message for token in ("generation", "reservation", "disabled")), f"{name}: {message}"
    assert not manifest_ref.get().exists, f"{name}: stale A created an immutable manifest"
    assert not beta_ref.get().exists, f"{name}: stale A mutated the Beta pointer"
    assert stable_ref.get().to_dict() == stable, f"{name}: stale A changed Stable"
    if "generation" in message:
        return "generation_mismatch"
    if "reservation" in message:
        return "reservation_mismatch"
    return "disabled"


def _run_stale_capture_case(name: str, mutate: Callable[[Any, str], None]) -> None:
    """Commit B in A's evidence window, before A's final production control read."""
    client_a = firestore.Client(project=PROJECT_ID, credentials=AnonymousCredentials())
    client_b = firestore.Client(project=PROJECT_ID, credentials=AnonymousCredentials())
    tag_a, tag_b, control_ref, manifest_ref, beta_ref, stable_ref, stable_before = _prepare_case(client_a)
    before_control_read = threading.Event()
    allow_control_read = threading.Event()
    finished = threading.Event()
    state: dict[str, Any] = {"control_reads": 0, "error": None}
    original_get = DocumentReference.get
    worker_name = f"beta-admit-{uuid.uuid4().hex}"

    def wrapped_get(reference: Any, *args: Any, **kwargs: Any) -> Any:
        is_control_read = reference.path == control_ref.path and kwargs.get("transaction") is not None
        if threading.current_thread().name == worker_name and is_control_read:
            state["control_reads"] += 1
            before_control_read.set()
            if not allow_control_read.wait(_WAIT_SECONDS):
                raise TimeoutError("control transition did not complete before A's final read")
        return original_get(reference, *args, **kwargs)

    def admit_a() -> None:
        try:
            admit_qualified_beta_manifest(
                _manifest(tag_a), control_generation=captured["control_generation"], firestore_client=client_a
            )
        except Exception as exc:  # The production transaction must reject the now-stale capture.
            state["error"] = exc
        finally:
            finished.set()

    captured = capture_beta_admission(tag_a, firestore_client=client_a)
    DocumentReference.get = wrapped_get
    worker = threading.Thread(target=admit_a, name=worker_name, daemon=True)
    try:
        worker.start()
        assert before_control_read.wait(_WAIT_SECONDS), f"{name}: A did not reach the final control-read barrier"
        mutate(client_b, tag_b)
        allow_control_read.set()
        assert finished.wait(_WAIT_SECONDS), f"{name}: stale A did not finish"
        worker.join(timeout=1)
        rejection = _assert_stale_zero_writes(name, state["error"], manifest_ref, beta_ref, stable_ref, stable_before)
        print(
            f"{name}: transition=committed rejection={rejection} control_reads={state['control_reads']} "
            "manifest_writes=0 beta_writes=0 stable_unchanged=true"
        )
    finally:
        allow_control_read.set()
        worker.join(timeout=2)
        DocumentReference.get = original_get
        for ref in (control_ref, manifest_ref, beta_ref, stable_ref):
            _delete_if_present(ref)


def _run_pessimistic_serialization_case() -> None:
    """Prove a queued transition serializes after an admission holding the control read lock."""
    name = "pessimistic-serialization"
    client_a = firestore.Client(project=PROJECT_ID, credentials=AnonymousCredentials())
    client_b = firestore.Client(project=PROJECT_ID, credentials=AnonymousCredentials())
    tag_a, tag_b, control_ref, manifest_ref, beta_ref, stable_ref, stable_before = _prepare_case(client_a)
    a_read_control = threading.Event()
    release_a = threading.Event()
    a_finished = threading.Event()
    b_started = threading.Event()
    b_finished = threading.Event()
    state: dict[str, Any] = {"control_reads": 0, "a_error": None, "b_error": None}
    original_get = DocumentReference.get
    a_name = f"beta-admit-lock-{uuid.uuid4().hex}"
    b_name = f"beta-reserve-lock-{uuid.uuid4().hex}"
    captured = capture_beta_admission(tag_a, firestore_client=client_a)

    def wrapped_get(reference: Any, *args: Any, **kwargs: Any) -> Any:
        is_control_read = reference.path == control_ref.path and kwargs.get("transaction") is not None
        if threading.current_thread().name == b_name and is_control_read:
            b_started.set()
        snapshot = original_get(reference, *args, **kwargs)
        if threading.current_thread().name == a_name and is_control_read:
            state["control_reads"] += 1
            a_read_control.set()
            if not release_a.wait(_WAIT_SECONDS):
                raise TimeoutError("queued control transition did not start")
        return snapshot

    def admit_a() -> None:
        try:
            admit_qualified_beta_manifest(
                _manifest(tag_a), control_generation=captured["control_generation"], firestore_client=client_a
            )
        except Exception as exc:
            state["a_error"] = exc
        finally:
            a_finished.set()

    def reserve_b() -> None:
        try:
            reserve_beta_candidate(tag_b, firestore_client=client_b)
        except Exception as exc:
            state["b_error"] = exc
        finally:
            b_finished.set()

    DocumentReference.get = wrapped_get
    worker_a = threading.Thread(target=admit_a, name=a_name, daemon=True)
    worker_b = threading.Thread(target=reserve_b, name=b_name, daemon=True)
    try:
        worker_a.start()
        assert a_read_control.wait(_WAIT_SECONDS), f"{name}: A did not acquire the control read lock"
        worker_b.start()
        assert b_started.wait(_WAIT_SECONDS), f"{name}: B did not start its control transition"
        assert not b_finished.wait(1), f"{name}: B finished while A held the control read lock"
        release_a.set()
        assert a_finished.wait(_WAIT_SECONDS), f"{name}: A did not finish after release"
        assert b_finished.wait(_WAIT_SECONDS), f"{name}: B did not commit after A released the control lock"
        worker_a.join(timeout=1)
        worker_b.join(timeout=1)
        assert state["a_error"] is None, f"{name}: A was incorrectly stale: {state['a_error']!r}"
        assert state["b_error"] is None, f"{name}: B failed after serialization: {state['b_error']!r}"
        assert manifest_ref.get().exists, f"{name}: A did not create its manifest"
        assert beta_ref.get().to_dict().get("release_id") == tag_a, f"{name}: A did not advance Beta"
        assert stable_ref.get().to_dict() == stable_before, f"{name}: A or B changed Stable"
        print(
            f"{name}: transition=queued_then_committed a_rejection=none control_reads={state['control_reads']} "
            "a_manifest=true beta_pointer=true stable_unchanged=true"
        )
    finally:
        release_a.set()
        worker_a.join(timeout=2)
        worker_b.join(timeout=2)
        DocumentReference.get = original_get
        for ref in (control_ref, manifest_ref, beta_ref, stable_ref):
            _delete_if_present(ref)


def main() -> int:
    _require_safe_emulator()
    _run_stale_capture_case(
        "reservation-before-final-read", lambda client, tag_b: reserve_beta_candidate(tag_b, firestore_client=client)
    )
    _run_stale_capture_case(
        "pause-resume-before-final-read",
        lambda client, _tag_b: (
            set_beta_admission_enabled(False, firestore_client=client),
            set_beta_admission_enabled(True, firestore_client=client),
        ),
    )
    _run_stale_capture_case(
        "direct-generation-before-final-read", lambda client, _tag_b: _direct_generation_transition(client)
    )
    _run_pessimistic_serialization_case()
    print("desktop Beta admission Firestore emulator proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
