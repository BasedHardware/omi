#!/usr/bin/env python3
"""Run the local-only JIT processing dogfood proof.

The driver is intentionally a composition layer over the production contracts
and their existing Firestore-emulator proofs.  Its requests stay on managed
loopback endpoints and a demo Firestore project; it does not mutate shared data
or control planes and does not claim a provider-spend guarantee.  Every result
is emitted as one JSON document so Gate G evidence can be archived without
interpreting human-oriented subprocess output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from google.cloud import firestore

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_OWNER_ID = "jit-qa-orchestrated-dogfood-owner"
DESKTOP_ROUNDTRIP_MARKER = "[[MARKER:jit-orchestrated-dogfood]]"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
RUNTIME_ENV_KEYS = ("LANG", "LC_ALL", "LC_CTYPE", "PATH", "TZ")
FIXED_API_URL = "http://127.0.0.1:18080"
FIXED_DESKTOP_API_URL = "http://127.0.0.1:18081"
FIXED_CONTROL_PLANE_URL = "http://127.0.0.1:18085"
FIXED_FIRESTORE_HOST = "127.0.0.1:18082"
FIXED_FIRESTORE_PROJECT = "demo-omi-jit-qa"
FIXED_AUTOMATION_PORT = 47942
MANAGED_STATE_ROOT = REPO_ROOT / ".dev" / "jit-qa-local-dev-gcp"


class SafetyError(RuntimeError):
    """Raised before any scenario can run when local-only authority is absent."""


@dataclass(frozen=True)
class Scenario:
    name: str
    mode: str
    command: tuple[str, ...]
    contracts: tuple[str, ...]


@dataclass
class ScenarioResult:
    name: str
    mode: str
    status: str
    contracts: list[str]
    duration_ms: int
    detail: str


def _loopback_url(value: str, *, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS or parsed.username or parsed.password:
        raise SafetyError(f"{label} must be an unauthenticated http loopback URL")
    if parsed.query or parsed.fragment:
        raise SafetyError(f"{label} must not contain a query or fragment")
    return value.rstrip("/")


def _fixed_service_url(value: str, *, label: str, expected: str) -> str:
    normalized = _loopback_url(value, label=label)
    if normalized != expected:
        raise SafetyError(f"{label} must be the managed endpoint {expected}")
    return normalized


def _emulator_authority(env: dict[str, str]) -> tuple[str, str]:
    host = (env.get("FIRESTORE_EMULATOR_HOST") or "").strip()
    if not host:
        raise SafetyError("FIRESTORE_EMULATOR_HOST is required")
    if host != FIXED_FIRESTORE_HOST:
        raise SafetyError(f"Firestore emulator must be the managed endpoint {FIXED_FIRESTORE_HOST}")
    project = (env.get("GOOGLE_CLOUD_PROJECT") or env.get("GCLOUD_PROJECT") or "").strip()
    if project != FIXED_FIRESTORE_PROJECT:
        raise SafetyError(f"Firestore project must be {FIXED_FIRESTORE_PROJECT}")
    return host, project


def _subprocess_env(source: dict[str, str]) -> dict[str, str]:
    _, project = _emulator_authority(source)
    runtime_home = _managed_state_root() / "dogfood-home"
    if runtime_home.is_symlink():
        raise SafetyError("dogfood HOME must not be a symlink")
    runtime_home.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime_home, 0o700)
    env = {key: source[key] for key in RUNTIME_ENV_KEYS if source.get(key)}
    env["PATH"] = source.get("PATH") or os.defpath
    for directory in (
        runtime_home / ".cache",
        runtime_home / ".config",
        runtime_home / ".local" / "share",
    ):
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    env.update(
        {
            "HOME": str(runtime_home),
            "XDG_CACHE_HOME": str(runtime_home / ".cache"),
            "XDG_CONFIG_HOME": str(runtime_home / ".config"),
            "XDG_DATA_HOME": str(runtime_home / ".local" / "share"),
            "FIRESTORE_EMULATOR_HOST": source["FIRESTORE_EMULATOR_HOST"],
            "GOOGLE_CLOUD_PROJECT": project,
            "GCLOUD_PROJECT": project,
            "FIREBASE_PROJECT_ID": project,
            "OMI_JIT_QA_DOGFOOD": "1",
            "PROVIDER_MODE": "offline",
            # The production canonical intake fence defaults to off.  These
            # writes are confined to a demo-* emulator project, so explicitly
            # select the real read/write contract for the proof.
            "MEMORY_MODE": "read",
            "ENCRYPTION_SECRET": "omi_jit_orchestrated_dogfood_key_32_bytes",  # pragma: allowlist secret
            "GOOGLE_AUTH_DISABLE_GCE_CHECK": "true",
            "GCE_METADATA_HOST": "127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost,::1",
            "no_proxy": "127.0.0.1,localhost,::1",
        }
    )
    return env


def _managed_state_root() -> Path:
    declared = MANAGED_STATE_ROOT.absolute()
    if declared.is_symlink() or declared.resolve() != declared:
        raise SafetyError("managed JIT QA state root must not contain symlink components")
    return declared


def _scenario_manifest(python: str) -> tuple[Scenario, ...]:
    return (
        Scenario(
            "ledger-current-history-standalone-reopen",
            "emulator-only",
            (python, "scripts/knowledge_ledger_correction_emulator_test.py"),
            ("current_view", "history_view", "standalone_reopen", "privacy_fence"),
        ),
        Scenario(
            "daily-sweep",
            "emulator-only",
            (python, "scripts/daily_memory_sweep_emulator_test.py"),
            ("daily_sweep", "idempotent_retry", "deletion_fence", "generation_fence"),
        ),
        Scenario(
            "first-open-deferral",
            "emulator-only",
            (
                python,
                "-m",
                "pytest",
                "-q",
                "tests/unit/test_jit_first_open_policy.py",
                "tests/routers/test_conversation_first_open_dispatch.py",
            ),
            ("first_open_deferral", "first_open_retry", "rollout_authority_fence"),
        ),
        Scenario(
            "planned-and-ambient-arbitration",
            "emulator-only",
            (python, "scripts/jit_proactivity_reservation_emulator_test.py"),
            (
                "planned_reservation",
                "ambient_reservation",
                "full_turn_arbitration",
                "daily_budget",
            ),
        ),
        Scenario(
            "keyframe-retention-and-request-failures",
            "emulator-only",
            (
                python,
                "-m",
                "pytest",
                "-q",
                "tests/unit/test_keyframe_policy.py",
                "tests/unit/test_frame_request_policy.py",
                "tests/unit/test_frame_requests.py",
            ),
            (
                "permanent_conversation_keyframe",
                "temporary_frame_retention",
                "requested_frame_failure_states",
            ),
        ),
        Scenario(
            "writer-cutover-rollback-rollforward",
            "emulator-only",
            # This older proof intentionally has no sys.path bootstrap; module
            # execution preserves backend/ as the import root.
            (python, "-m", "scripts.knowledge_ledger_writer_transition_emulator_test"),
            (
                "writer_cutover",
                "writer_rollback",
                "writer_rollforward",
                "row_preservation",
            ),
        ),
    )


def _detail(stdout: str, stderr: str, *, limit: int = 1200) -> str:
    joined = "\n".join(part.strip() for part in (stdout, stderr) if part.strip())
    redacted = re.sub(r"\buid=[^, )]+", "uid=<synthetic-redacted>", joined)
    return redacted[-limit:]


def _cleanup_emulator_users(project: str, prefixes: tuple[str, ...]) -> int:
    """Delete only this harness's synthetic owner roots from the emulator."""

    client = firestore.Client(project=project)
    removed = 0
    for snapshot in client.collection("users").stream():
        if any(snapshot.id == prefix or snapshot.id.startswith(prefix) for prefix in prefixes):
            client.recursive_delete(snapshot.reference)
            snapshot.reference.delete()
            removed += 1
    return removed


def _purge_emulator_marker_documents(project: str, marker: str) -> tuple[int, int]:
    """Remove only documents that still contain this harness's exact marker."""

    if not project.startswith("demo-") or marker != DESKTOP_ROUNDTRIP_MARKER:
        raise SafetyError("marker cleanup requires the fixed harness marker in a demo project")
    client = firestore.Client(project=project)

    def matching_documents() -> list[Any]:
        matches: list[Any] = []

        def walk(reference: Any) -> None:
            for collection in reference.collections():
                for snapshot in collection.stream():
                    walk(snapshot.reference)
                    if marker in json.dumps(snapshot.to_dict(), default=str, sort_keys=True):
                        matches.append(snapshot.reference)

        for owner in client.collection("users").stream():
            walk(owner.reference)
        return matches

    matches = matching_documents()
    for reference in matches:
        reference.delete()
    return len(matches), len(matching_documents())


def _run_scenario(scenario: Scenario, *, env: dict[str, str], timeout_seconds: int) -> ScenarioResult:
    started = time.monotonic()
    cleanup_by_scenario = {
        "ledger-current-history-standalone-reopen": (
            env["GOOGLE_CLOUD_PROJECT"],
            ("knowledge-ledger-correction-emulator-",),
        ),
        "daily-sweep": (env["GOOGLE_CLOUD_PROJECT"], ("daily-memory-sweep-",)),
        "planned-and-ambient-arbitration": (
            env["GOOGLE_CLOUD_PROJECT"],
            ("jit-proactivity-emulator-",),
        ),
        "writer-cutover-rollback-rollforward": (
            "demo-memory",
            ("writer-transition-emulator-user",),
        ),
    }
    cleanup = cleanup_by_scenario.get(scenario.name)
    precleaned = 0
    if cleanup is not None:
        try:
            precleaned = _cleanup_emulator_users(*cleanup)
        except Exception as exc:  # noqa: BLE001 - never run on ambiguous fixture ownership
            return ScenarioResult(
                name=scenario.name,
                mode=scenario.mode,
                status="FAIL",
                contracts=list(scenario.contracts),
                duration_ms=round((time.monotonic() - started) * 1000),
                detail=f"synthetic_precleanup=failed error={type(exc).__name__}",
            )
    try:
        completed = subprocess.run(
            scenario.command,
            cwd=BACKEND_DIR,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        status = "PASS" if completed.returncode == 0 else "FAIL"
        detail = _detail(completed.stdout, completed.stderr) or f"exit={completed.returncode}"
    except subprocess.TimeoutExpired as exc:
        status = "FAIL"
        detail = f"timed out after {timeout_seconds}s: {_detail(exc.stdout or '', exc.stderr or '')}"
    if cleanup is not None:
        try:
            removed = _cleanup_emulator_users(*cleanup)
            detail = f"{detail}\nsynthetic_cleanup=confirmed owner_roots={removed} precleaned={precleaned}"
        except Exception as exc:  # noqa: BLE001 - cleanup failure must fail the evidence
            status = "FAIL"
            detail = f"{detail}\nsynthetic_cleanup=failed error={type(exc).__name__}"
    return ScenarioResult(
        name=scenario.name,
        mode=scenario.mode,
        status=status,
        contracts=list(scenario.contracts),
        duration_ms=round((time.monotonic() - started) * 1000),
        detail=detail,
    )


def _request_json(
    url: str,
    *,
    timeout_seconds: int = 5,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode()
    request = Request(url, headers=request_headers, data=data, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL is loopback validated
            payload = response.read(1024 * 1024)
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("response was not JSON") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("response must be a JSON object")
    return decoded


def _health_scenario(api_urls: Iterable[str]) -> ScenarioResult:
    started = time.monotonic()
    observations: dict[str, Any] = {}
    try:
        for index, api_url in enumerate(api_urls):
            observations[f"api_{index}"] = _request_json(f"{api_url}/health")
        status = "PASS"
        detail = json.dumps(observations, sort_keys=True, separators=(",", ":"))
    except RuntimeError as exc:
        status = "FAIL"
        detail = str(exc)
    return ScenarioResult(
        name="loopback-api-health",
        mode="integrated",
        status=status,
        contracts=["main_api_health", "desktop_api_health"],
        duration_ms=round((time.monotonic() - started) * 1000),
        detail=detail,
    )


def _omi_ctl(port: int, *arguments: str, timeout_seconds: int = 20) -> dict[str, Any]:
    env = {key: os.environ[key] for key in RUNTIME_ENV_KEYS if os.environ.get(key)}
    env["PATH"] = os.environ.get("PATH") or os.defpath
    env["HOME"] = str(_managed_state_root() / "dogfood-home")
    env["OMI_AUTOMATION_PORT"] = str(port)
    try:
        completed = subprocess.run(
            (str(REPO_ROOT / "desktop/macos/scripts/omi-ctl"), *arguments),
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"omi-ctl {' '.join(arguments[:2])} timed out") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"omi-ctl {' '.join(arguments[:2])} failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"omi-ctl {' '.join(arguments[:2])} did not return JSON") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError(f"omi-ctl {' '.join(arguments[:2])} returned a failing envelope")
    return payload


def _desktop_owner_roundtrip(
    port: int, *, api_url: str, desktop_api_url: str, firestore_project: str
) -> ScenarioResult:
    """Create, observe, and clean one synthetic row through the signed-in QA app."""

    started = time.monotonic()
    create_attempted = False
    created = False
    created_id: str | None = None
    cleanup = "not_needed"
    precleaned = 0
    try:
        precleaned, remaining = _purge_emulator_marker_documents(firestore_project, DESKTOP_ROUNDTRIP_MARKER)
        if remaining:
            raise RuntimeError("synthetic marker pre-clean did not converge")
        health = _omi_ctl(port, "health")
        if health.get("bundleIdentifier") != "com.omi.omi-jit-qa":
            raise SafetyError("automation port is not owned by the omi-jit-qa bundle")
        if _loopback_url(str(health.get("pythonBackendURL", "")), label="bundle python backend") != api_url:
            raise SafetyError("bundle main backend does not match --api-url")
        if _loopback_url(str(health.get("rustBackendURL", "")), label="bundle desktop backend") != desktop_api_url:
            raise SafetyError("bundle desktop backend does not match --desktop-api-url")

        # Remove only our exact marker if an interrupted prior run left it in
        # this local demo account. Authentication and the owner UID stay inside
        # the bridge and are never returned in evidence.
        _omi_ctl(port, "action", "delete_test_memory", f"marker={DESKTOP_ROUNDTRIP_MARKER}")
        try:
            create_attempted = True
            create = _omi_ctl(
                port,
                "action",
                "create_test_memory",
                f"content={DESKTOP_ROUNDTRIP_MARKER} synthetic canonical owner fixture",
                "source=harness",
            )
        except RuntimeError as exc:
            raise RuntimeError(
                "desktop canonical create failed; verify the local backend was launched with MEMORY_ENABLED=on"
            ) from exc
        create_detail = create.get("result", {}).get("detail", {})
        created = str(create_detail.get("created", "")).lower() == "true"
        candidate_id = create_detail.get("memory_id")
        created_id = candidate_id if isinstance(candidate_id, str) and candidate_id else None
        if not created or created_id is None:
            raise RuntimeError("desktop bridge did not confirm canonical memory creation")
        _omi_ctl(port, "action", "refresh_all_data")
        snapshot = _omi_ctl(port, "action", "memories_snapshot")
        detail = snapshot.get("result", {}).get("detail", {})
        if str(detail.get("is_signed_in", "")).lower() != "true":
            raise RuntimeError("desktop memory snapshot is not signed in")
        if str(detail.get("memory_count_valid", "")).lower() != "true":
            raise RuntimeError("desktop memory snapshot did not expose a valid count")
        if int(detail.get("api_page_count", "-1")) < 1:
            raise RuntimeError("desktop API page did not expose the synthetic canonical row")
        status = "PASS"
        observation = {
            "signed_in": True,
            "memory_count_valid": True,
            "api_page_nonempty": True,
            # There is currently no Swift bridge action for history/reopen;
            # that contract remains covered by the real emulator proof.
            "history_reopen_bridge_action": "missing",
        }
        result_detail = json.dumps(observation, sort_keys=True, separators=(",", ":"))
    except (RuntimeError, SafetyError, ValueError) as exc:
        status = "FAIL"
        result_detail = str(exc)
    finally:
        product_delete_confirmed = False
        if create_attempted:
            if created and created_id is not None:
                try:
                    deleted = _omi_ctl(port, "action", "delete_test_memory", f"id={created_id}")
                    deleted_id = deleted.get("result", {}).get("detail", {}).get("deleted")
                    if not isinstance(deleted_id, str) or not deleted_id:
                        raise RuntimeError("desktop bridge did not confirm deletion")
                    product_delete_confirmed = True
                except RuntimeError:
                    pass
            try:
                removed, remaining = _purge_emulator_marker_documents(firestore_project, DESKTOP_ROUNDTRIP_MARKER)
                if remaining:
                    cleanup = "failed"
                elif product_delete_confirmed:
                    cleanup = "product_delete_confirmed"
                elif created:
                    cleanup = "emulator_content_purge_confirmed"
                else:
                    cleanup = "no_marker_after_failed_create" if removed == 0 else "emulator_content_purge_confirmed"
            except (RuntimeError, SafetyError):
                cleanup = "failed"
            try:
                _omi_ctl(port, "action", "refresh_all_data")
            except RuntimeError:
                cleanup = "failed"
        if cleanup == "failed":
            status = "FAIL"
            result_detail = f"{result_detail}; synthetic marker cleanup failed"
    return ScenarioResult(
        name="desktop-owner-memory-roundtrip",
        mode="integrated",
        status=status,
        contracts=[
            "actual_qa_owner",
            "canonical_create",
            "app_visible_api_page",
            "synthetic_cleanup",
        ],
        duration_ms=round((time.monotonic() - started) * 1000),
        detail=f"{result_detail}; cleanup={cleanup}; precleaned={precleaned}",
    )


def _private_token(path: Path, *, expected_name: str) -> str:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if candidate.is_symlink():
        raise SafetyError(f"{expected_name} must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise SafetyError(f"{expected_name} is unavailable") from exc
    expected_root = _managed_state_root()
    expected_path = expected_root / expected_name
    if resolved != expected_path:
        raise SafetyError(f"{expected_name} must remain in a managed JIT QA state root")
    current = expected_root
    for part in Path(expected_name).parts:
        current = current / part
        if current.is_symlink():
            raise SafetyError(f"{expected_name} must not contain symlink components")
    details = resolved.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1 or details.st_mode & 0o077:
        raise SafetyError(f"{expected_name} must be one private regular file")
    token = resolved.read_text().strip()
    if len(token) < 32:
        raise SafetyError(f"{expected_name} is malformed")
    return token


def _control_plane_scenario(
    control_plane_url: str | None,
    owner_id: str,
    *,
    api_url: str,
    control_token_file: Path,
    admin_key_file: Path,
) -> ScenarioResult:
    """Drive the local PostHog fixture and observe production rollout decisions."""

    started = time.monotonic()
    if control_plane_url is None:
        return ScenarioResult(
            name="rollout-and-kill-control-plane",
            mode="integrated",
            status="FAIL",
            contracts=[
                "fail_closed_unknown",
                "rollout_enabled",
                "kill_switch_enabled",
                "rollforward_restored",
            ],
            duration_ms=0,
            detail="--control-plane-url is required for Gate G",
        )
    try:
        control_token = _private_token(control_token_file, expected_name="posthog-control.secret")
        admin_key = _private_token(admin_key_file, expected_name="admin.secret")
        control_headers = {"Authorization": f"Bearer {control_token}"}
        initial = _request_json(f"{control_plane_url}/control/flags", headers=control_headers)
        observations: dict[str, bool] = {}
        phases = (
            ("fail_closed_unknown", "unknown", "disabled", "unknown"),
            ("rollout_enabled", "enabled", "disabled", "enabled"),
            ("kill_switch_enabled", "enabled", "enabled", "disabled"),
            ("rollforward_restored", "enabled", "disabled", "enabled"),
        )
        try:
            for index, (name, rollout, kill_switch, effective) in enumerate(phases):
                _request_json(
                    f"{control_plane_url}/control/flags",
                    method="POST",
                    headers=control_headers,
                    body={"rollout": rollout, "kill_switch": kill_switch},
                )
                phase_owner = f"{owner_id}-{index}"
                decision = _request_json(
                    f"{api_url}/v1/jit/rollout-decision",
                    headers={"Authorization": f"Bearer {admin_key}{phase_owner}"},
                )
                observations[name] = (
                    decision.get("rollout") == rollout
                    and decision.get("kill_switch") == kill_switch
                    and decision.get("effective") == effective
                )
        finally:
            _request_json(
                f"{control_plane_url}/control/flags",
                method="POST",
                headers=control_headers,
                body={
                    "rollout": initial["rollout"],
                    "kill_switch": initial["kill_switch"],
                },
            )
        missing = [name for name, passed in observations.items() if not passed]
        if missing:
            raise RuntimeError(f"production rollout decision mismatched phases: {missing}")
        status = "PASS"
        detail = json.dumps(observations, sort_keys=True, separators=(",", ":"))
    except (RuntimeError, SafetyError, KeyError, OSError) as exc:
        status = "FAIL"
        detail = str(exc)
    return ScenarioResult(
        name="rollout-and-kill-control-plane",
        mode="integrated",
        status=status,
        contracts=[
            "fail_closed_unknown",
            "rollout_enabled",
            "kill_switch_enabled",
            "rollforward_restored",
        ],
        duration_ms=round((time.monotonic() - started) * 1000),
        detail=detail,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.environ.get("OMI_JIT_QA_API_URL", FIXED_API_URL))
    parser.add_argument(
        "--desktop-api-url",
        default=os.environ.get("OMI_JIT_QA_DESKTOP_API_URL", FIXED_DESKTOP_API_URL),
    )
    parser.add_argument("--control-plane-url", default=os.environ.get("OMI_JIT_QA_CONTROL_PLANE_URL"))
    state_root = MANAGED_STATE_ROOT
    parser.add_argument("--control-token-file", type=Path, default=state_root / "posthog-control.secret")
    parser.add_argument("--admin-key-file", type=Path, default=state_root / "admin.secret")
    parser.add_argument("--owner-id", default=DEFAULT_OWNER_ID)
    parser.add_argument(
        "--automation-port",
        type=int,
        default=int(os.environ.get("OMI_AUTOMATION_PORT", str(FIXED_AUTOMATION_PORT))),
    )
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--only", action="append", default=[], metavar="SCENARIO")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    started_at = time.time()
    try:
        _, project = _emulator_authority(dict(os.environ))
        api_url = _fixed_service_url(args.api_url, label="--api-url", expected=FIXED_API_URL)
        desktop_api_url = _fixed_service_url(
            args.desktop_api_url,
            label="--desktop-api-url",
            expected=FIXED_DESKTOP_API_URL,
        )
        control_plane_url = (
            _fixed_service_url(
                args.control_plane_url,
                label="--control-plane-url",
                expected=FIXED_CONTROL_PLANE_URL,
            )
            if args.control_plane_url
            else None
        )
        if args.owner_id != DEFAULT_OWNER_ID:
            raise SafetyError(f"--owner-id must remain the fixed synthetic owner {DEFAULT_OWNER_ID}")
        if args.timeout_seconds < 1 or args.timeout_seconds > 1800:
            raise SafetyError("--timeout-seconds must be between 1 and 1800")
        if args.automation_port != FIXED_AUTOMATION_PORT:
            raise SafetyError(f"--automation-port must remain the managed port {FIXED_AUTOMATION_PORT}")
        env = _subprocess_env(dict(os.environ))
    except SafetyError as exc:
        evidence = {
            "schema_version": "omi.jit.orchestrated_dogfood.v1",
            "status": "FAIL",
            "safety_error": str(exc),
            "results": [],
        }
        rendered = json.dumps(evidence, sort_keys=True, indent=2)
        print(rendered)
        if args.output:
            args.output.write_text(rendered + "\n")
        return 2

    selected = set(args.only)
    manifest = _scenario_manifest(sys.executable)
    unknown = selected.difference(
        {scenario.name for scenario in manifest}
        | {
            "loopback-api-health",
            "desktop-owner-memory-roundtrip",
            "rollout-and-kill-control-plane",
        }
    )
    if unknown:
        raise SystemExit(f"unknown --only scenario(s): {', '.join(sorted(unknown))}")

    results: list[ScenarioResult] = []
    if not selected or "loopback-api-health" in selected:
        results.append(_health_scenario((api_url, desktop_api_url)))
    if not selected or "desktop-owner-memory-roundtrip" in selected:
        results.append(
            _desktop_owner_roundtrip(
                args.automation_port,
                api_url=api_url,
                desktop_api_url=desktop_api_url,
                firestore_project=project,
            )
        )
    for scenario in manifest:
        if not selected or scenario.name in selected:
            results.append(_run_scenario(scenario, env=env, timeout_seconds=args.timeout_seconds))
    if not selected or "rollout-and-kill-control-plane" in selected:
        results.append(
            _control_plane_scenario(
                control_plane_url,
                args.owner_id,
                api_url=api_url,
                control_token_file=args.control_token_file,
                admin_key_file=args.admin_key_file,
            )
        )

    overall = "PASS" if results and all(result.status == "PASS" for result in results) else "FAIL"
    evidence = {
        "schema_version": "omi.jit.orchestrated_dogfood.v1",
        "status": overall,
        "mode_summary": {
            "integrated": sum(result.mode == "integrated" for result in results),
            "emulator_only": sum(result.mode == "emulator-only" for result in results),
        },
        "owner_id": args.owner_id,
        "firestore_project": project,
        "driver_model_invocation": "not_exercised",
        "provider_spend_guarantee": "not_claimed",
        "dev_vertex_gateway_configured": True,
        "shared_service_mutation": False,
        "duration_ms": round((time.time() - started_at) * 1000),
        "results": [asdict(result) for result in results],
    }
    rendered = json.dumps(evidence, sort_keys=True, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
