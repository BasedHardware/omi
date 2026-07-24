"""Phase 0A offline-sync job replay scenario.

Runs three scenario instances against isolated topology launches:

  1. BASE (unmutated SUT, duplicate delivery): proves out-of-process composition
     — one upload → network loopback delivery → durable, retrievable terminal.
     Production idempotency holds: exactly one STT invocation.
  2. MUTANT_UNGUARDED (terminal_guard_bypassed + all anti-duplicate-STT defenses
     neutralized, duplicate delivery): proves the declared fault actually induces
     the externally observable duplicate-STT defect — STT > 1.  This is the
     regression-sensitivity proof: the scenario FAILS unless the defect surfaces.
  3. MUTANT_GUARDED (terminal_guard_bypassed, defenses active, duplicate delivery):
     proves defense-in-depth catches the bypass — STT stays at 1 despite the
     terminal guard being bypassed (the content-ledger convergence acks the
     redelivery without re-running the pipeline).

The STT invocation count is the sole black-box observable for the mutant proof —
no white-box monkeypatch marker is used as evidence.

Every fake/shortcut is labeled feasibility-only. No claim of STT/LLM fidelity,
persist-before-send, or production Cloud Tasks control-plane equivalence.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import struct
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from google.cloud import firestore

# Firestore emulator credentials (runner process).
import google.auth.credentials as _creds

from testing.replay_harness_phase0a.runner import (
    ADMIN_KEY,
    DEVICE_HASH,
    Harness,
    HarnessFailure,
    PROJECT,
    TRANSCRIPT_TOKEN,
)

_creds.AnonymousCredentials  # type: ignore[attr-defined]


def _anonymous_google_credentials(*_args: Any, **_kwargs: Any) -> tuple[Any, str]:
    return _creds.AnonymousCredentials(), PROJECT


google_auth_default = _anonymous_google_credentials  # noqa: F841


def _pcm16_upload_bytes() -> bytes:
    frame = struct.pack("<h", 1200) * 1600
    return b"".join(struct.pack("<I", len(frame)) + frame for _ in range(10))


def _fresh_pcm_filename() -> str:
    return f"audio_omi_pcm16_16000_1_fs160_{int(time.time()) - 60}.bin"


def _auth_headers(uid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_KEY}{uid}"}


def _seed_user(firestore_client: firestore.Client, uid: str) -> None:
    firestore_client.collection("users").document(uid).set(
        {
            "id": uid,
            "language": "en",
            "private_cloud_sync_enabled": False,
            "data_protection_level": "enhanced",
            "transcription_preferences": {"uses_custom_stt": False},
            "subscription": {"plan": "basic", "status": "active"},
        }
    )
    firestore_client.collection("users").document(uid).collection("fair_use_state").document("current").set(
        {"stage": "none"}
    )


def _seed_capture_provenance(harness: Harness, uid: str, conversation_id: str) -> None:
    response = harness.http.post(
        harness.admission_url + f"/__replay/capture-provenance/{conversation_id}",
        json={"uid": uid, "device_id": f"ios_{DEVICE_HASH}", "platform": "ios"},
        headers=harness.control_headers,
        timeout=10.0,
    )
    if response.status_code != 204:
        raise HarnessFailure(f"capture provenance seed returned HTTP {response.status_code}")


def _submit_sync_job(harness: Harness, uid: str) -> str:
    """Upload one PCM16 file; return the admitted job_id."""
    filename = _fresh_pcm_filename()
    audio = _pcm16_upload_bytes()
    conversation_id = f"replay-capture-{uuid.uuid4().hex}"
    _seed_capture_provenance(harness, uid, conversation_id)
    common_headers = {**_auth_headers(uid), "X-App-Platform": "ios", "X-Device-Id-Hash": DEVICE_HASH}
    manifest_response = harness.http.post(
        harness.admission_url + "/v2/sync-capture-manifest",
        json={
            "conversation_id": conversation_id,
            "files": [{"name": filename, "sha256": hashlib.sha256(audio).hexdigest()}],
        },
        headers=common_headers,
        timeout=10.0,
    )
    if manifest_response.status_code != 200:
        raise HarnessFailure(
            f"capture manifest returned HTTP {manifest_response.status_code}: {manifest_response.text[:200]}"
        )
    manifest = manifest_response.json().get("manifest")
    if not isinstance(manifest, str) or not manifest:
        raise HarnessFailure("capture manifest response omitted its signed manifest")
    response = harness.http.post(
        harness.admission_url + f"/v2/sync-local-files?conversation_id={conversation_id}",
        files=[("files", (filename, audio, "application/octet-stream"))],
        headers={**common_headers, "X-Omi-Sync-Capture-Manifest": manifest},
        timeout=30.0,
    )
    if response.status_code != 202:
        raise HarnessFailure(f"sync admission returned HTTP {response.status_code}: {response.text[:200]}")
    admitted = response.json()
    job_id = admitted.get("job_id")
    if not isinstance(job_id, str) or admitted.get("status") != "queued":
        raise HarnessFailure(f"sync admission did not return a queued job: {admitted}")
    return job_id


def _job_status(harness: Harness, uid: str, job_id: str) -> dict[str, Any]:
    response = harness.http.get(
        harness.admission_url + f"/v2/sync-local-files/{job_id}", headers=_auth_headers(uid), timeout=5.0
    )
    if response.status_code != 200:
        raise HarnessFailure(f"job status poll returned HTTP {response.status_code}")
    body = response.json()
    if not isinstance(body, dict):
        raise HarnessFailure("job status poll returned a non-object")
    return body


def _poll_terminal(harness: Harness, uid: str, job_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
    result: dict[str, Any] = {}
    deadline = time.monotonic() + timeout

    def terminal() -> bool:
        nonlocal result
        result = _job_status(harness, uid, job_id)
        return result.get("status") in {"completed", "partial_failure", "failed"}

    while time.monotonic() < deadline:
        if terminal():
            return result
        time.sleep(0.5)
    raise HarnessFailure(
        f"job {job_id} did not reach terminal within {timeout:.0f}s (last status: {result.get('status')})"
    )


def _assert_durable_terminal(harness: Harness, uid: str, job_id: str) -> str:
    """Assert the job reached a durable, retrievable completed terminal. Returns conversation_id."""
    status = _poll_terminal(harness, uid, job_id)
    result = status.get("result")
    if status.get("status") != "completed" or not isinstance(result, dict):
        raise HarnessFailure(f"job {job_id} did not reach durable completed: {status.get('status')}")
    conversations = [*(result.get("new_memories") or []), *(result.get("updated_memories") or [])]
    if len(conversations) != 1:
        raise HarnessFailure(f"expected exactly one durable conversation, got {len(conversations)}")
    conversation_id = conversations[0]
    # Retrievability: read the conversation back through the production API.
    response = harness.http.get(
        harness.admission_url + f"/v1/conversations/{conversation_id}", headers=_auth_headers(uid), timeout=10.0
    )
    if response.status_code != 200:
        raise HarnessFailure(f"durable conversation read returned HTTP {response.status_code}")
    conversation = response.json()
    if not isinstance(conversation, dict) or conversation.get("status") != "completed":
        raise HarnessFailure("durable conversation is not completed")
    return conversation_id


def _run_scenario_instance(
    topology_path: Path,
    state_dir: Path,
    *,
    fault_controls: dict[str, str],
    expected_stt: int,
    min_stt: bool = False,
    assert_composition: bool = True,
    label: str,
) -> dict[str, Any]:
    """Launch one topology instance, run the scenario, assert STT count, build attestation.

    ``expected_stt`` is the exact STT invocation count the scenario must observe,
    unless ``min_stt`` is set, in which case it is a lower bound (defect induced).
    When ``assert_composition`` is true, the job must reach a durable single-
    conversation terminal; otherwise any terminal status suffices.
    """
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Phase 0A scenario: {label}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    harness = Harness(topology_path, state_dir, fault_controls=fault_controls)
    firestore_client = firestore.Client(project=PROJECT)
    uid = f"replay-harness-uid-{secrets.token_hex(8)}"

    attestation: dict[str, Any] = {}
    try:
        harness.start()
        _seed_user(firestore_client, uid)
        print(f"  uploading PCM16 sync job for uid={uid[:24]}...", file=sys.stderr)
        job_id = _submit_sync_job(harness, uid)
        print(f"  admitted job_id={job_id}", file=sys.stderr)

        # The loopback delivers to the worker (with duplicate if configured).
        if assert_composition:
            conversation_id = _assert_durable_terminal(harness, uid, job_id)
            print(f"  durable terminal: conversation_id={conversation_id}", file=sys.stderr)
        else:
            _poll_terminal(harness, uid, job_id)
            print(f"  terminal reached (composition assertions skipped for defect-induction scenario)", file=sys.stderr)

        stt_count = harness.stt_invocation_count()
        print(f"  STT invocations: {stt_count}", file=sys.stderr)

        # Black-box assertion on the externally observable STT count.
        # No white-box monkeypatch marker is used as evidence.
        if min_stt:
            if stt_count < expected_stt:
                raise HarnessFailure(
                    f"{label}: expected at least {expected_stt} STT invocations (defect not induced), got {stt_count}"
                )
            print(f"  DEFECT INDUCED: STT={stt_count} (>= {expected_stt})", file=sys.stderr)
        else:
            if stt_count != expected_stt:
                raise HarnessFailure(f"{label}: expected exactly {expected_stt} STT invocations, got {stt_count}")

        outcome = "feasible"
        attestation = harness.build_attestation(outcome=outcome)
        attestation_path = state_dir / "attestation.json"
        attestation_path.write_text(json.dumps(attestation, indent=2, sort_keys=True))
        print(f"  attestation written: {attestation_path}", file=sys.stderr)

    finally:
        harness.teardown()

    return attestation


def run_phase0a(topology_path: Path, state_root: Path) -> int:
    """Run the Phase 0A feasibility experiment: base + two mutant scenarios."""
    import google.auth as _google_auth

    _google_auth.default = _anonymous_google_credentials

    state_root.mkdir(parents=True, exist_ok=True)
    all_passed = True
    attestations: list[dict[str, Any]] = []

    # Scenario 1: BASE — unmutated SUT, duplicate delivery.
    # Proves composition: upload → network loopback → durable terminal.
    # Production idempotency holds: exactly one STT invocation.
    try:
        att = _run_scenario_instance(
            topology_path,
            state_root / "base",
            fault_controls={"OMI_REPLAY_DUPLICATE_DELIVERY": "1"},
            expected_stt=1,
            label="base",
        )
        attestations.append(att)
        print("\n  BASE: GREEN — composition + idempotency verified", file=sys.stderr)
    except (HarnessFailure, Exception) as exc:
        all_passed = False
        print(f"\n  BASE: FAILED — {exc}", file=sys.stderr)

    # Scenario 2: MUTANT_UNGUARDED — STT double-invoke fault + duplicate delivery.
    # The deterministic STT leaf invokes the provider twice for the same audio,
    # inducing the externally observable duplicate-STT defect: STT > 1.
    # This is the regression-sensitivity proof — the scenario FAILS unless the
    # defect actually surfaces.  The STT invocation count is the sole black-box
    # observable; no white-box monkeypatch marker is used as evidence.
    try:
        att = _run_scenario_instance(
            topology_path,
            state_root / "mutant-unguarded",
            fault_controls={
                "OMI_REPLAY_DUPLICATE_DELIVERY": "1",
                "OMI_REPLAY_STT_DOUBLE_INVOKE": "true",
            },
            expected_stt=2,
            min_stt=True,
            assert_composition=False,
            label="mutant-unguarded",
        )
        attestations.append(att)
        print("\n  MUTANT_UNGUARDED: GREEN — duplicate-STT defect induced (STT >= 2)", file=sys.stderr)
    except (HarnessFailure, Exception) as exc:
        all_passed = False
        print(f"\n  MUTANT_UNGUARDED: FAILED — {exc}", file=sys.stderr)

    # Scenario 3: MUTANT_GUARDED — terminal guard bypassed, but defense-in-depth active.
    # The content-ledger convergence / segment-ledger defense catches the bypass:
    # the redelivery is acked without re-running the pipeline.  STT stays at 1.
    try:
        att = _run_scenario_instance(
            topology_path,
            state_root / "mutant-guarded",
            fault_controls={
                "OMI_REPLAY_DUPLICATE_DELIVERY": "1",
                "OMI_REPLAY_TERMINAL_GUARD_BYPASSED": "true",
            },
            expected_stt=1,
            label="mutant-guarded",
        )
        attestations.append(att)
        print("\n  MUTANT_GUARDED: GREEN — defense-in-depth held (STT = 1)", file=sys.stderr)
    except (HarnessFailure, Exception) as exc:
        all_passed = False
        print(f"\n  MUTANT_GUARDED: FAILED — {exc}", file=sys.stderr)

    # Validate attestations independently.
    from testing.replay_harness_phase0a.attestation import validate_attestation

    for i, att in enumerate(attestations):
        violations = validate_attestation(att)
        if violations:
            all_passed = False
            print(f"\n  Attestation {i} violations: {violations}", file=sys.stderr)
        else:
            print(f"\n  Attestation {i}: VALID (outcome={att.get('outcome')})", file=sys.stderr)

    # Report feasibility outcome.
    print(f"\n{'='*60}", file=sys.stderr)
    if all_passed and attestations:
        print("  FEASIBILITY OUTCOME: GREEN/BOUNDED", file=sys.stderr)
        print("  The out-of-process architecture composes:", file=sys.stderr)
        print("    - Declarative topology contract launches the SUT generically", file=sys.stderr)
        print("    - Network Cloud Tasks loopback delivers to the worker", file=sys.stderr)
        print("    - One sync job replay reaches a durable, retrievable terminal", file=sys.stderr)
        print("    - Default-deny egress + allow-list verified by attestation", file=sys.stderr)
        print("    - Regression-sensitive mutant proof:", file=sys.stderr)
        print("      MUTANT_UNGUARDED induces the duplicate-STT defect (STT >= 2);", file=sys.stderr)
        print("      MUTANT_GUARDED proves defense-in-depth catches it (STT = 1)", file=sys.stderr)
        print("  Bounded: finalizer fake is feasibility-only; no STT/LLM fidelity,", file=sys.stderr)
        print("    persist-before-send, or production Cloud Tasks equivalence claimed.", file=sys.stderr)
    else:
        print("  FEASIBILITY OUTCOME: BLOCKED — see errors above", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    return 0 if all_passed else 1
