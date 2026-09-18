"""session-evidence-v1: the frozen session/evidence receipt contract.

Executable form of ``contracts/session/session-evidence-v1.schema.json``.
Consumers (C2 journeys, C3 capture replay, C4 verification, C5 device
qualification) validate receipts with :func:`validate_evidence` rather than
re-implementing the rules. The schema file is the wire contract; this module
adds the cross-field semantics a JSON Schema cannot express (artifact/source
binding, honest accounting, credential-free keys, timestamps ordering).

V8 freezes validation structure; only documentation annotations may change.
The optional live extension is reserved for the V1 builder; see contracts/session/README.md.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

SCHEMA_ID = "session-evidence-v1"
SCHEMA_VERSION = 1
SCHEMA_RELPATH = Path("contracts") / "session" / "session-evidence-v1.schema.json"

STATES = ("creating", "ready", "running", "blocked", "stopped", "released", "failed")
PLATFORMS = ("android", "ios-simulator", "ios-device")
FLAVORS = ("dev", "prod")
# A session receipt is a *local synthetic lane* artifact by definition; the
# production-family profiles are not valid targets for it.
SESSION_PROFILES = ("local_dev", "local_prod")
EGRESS_POLICY = "loopback-only"

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
PRODUCTION_HOSTS = frozenset({"api.omi.me", "api.omiapi.com"})

SESSION_ID_RE = re.compile(r"^oms-[a-z0-9][a-z0-9-]{0,63}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FIXTURE_VERSION_RE = re.compile(r"^v\d+$")
DIRTY_DIGEST_RE = re.compile(r"^(clean|dirty:sha256:[0-9a-f]{64})$")
# Credential-shaped keys are rejected anywhere in the document, including
# nested runner/extension maps: a receipt is evidence, not a secret store.
_CREDENTIAL_KEY_RE = re.compile(r"(token|secret|password|passwd|credential|api[_-]?key)", re.IGNORECASE)


class EvidenceError(ValueError):
    """Raised when a session-evidence document violates the v1 contract."""


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def schema_path(repo_root: Path) -> Path:
    return Path(repo_root) / SCHEMA_RELPATH


# ---------------------------------------------------------------------------
# Source identity
# ---------------------------------------------------------------------------


def _run_git(repo_root: Path, args: Sequence[str]) -> str:
    # Identity probing must fail closed as EvidenceError (exit 2 at the CLI),
    # never an unhandled FileNotFoundError/CalledProcessError traceback.
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise EvidenceError(f"git is not installed: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()[:200]
        raise EvidenceError(f"git {' '.join(args)} failed (exit {exc.returncode}): {detail}") from exc
    return completed.stdout.strip()


def source_identity(repo_root: Path) -> dict[str, str]:
    """HEAD SHA plus a digest binding any uncommitted diff.

    ``dirty_digest`` is ``clean`` only when ``git status --porcelain`` is
    empty; otherwise it is a sha256 over the porcelain output plus the full
    diff, so two different dirty states cannot share a receipt identity.
    """

    root = Path(repo_root)
    git_sha = _run_git(root, ["rev-parse", "HEAD"])
    porcelain = _run_git(root, ["status", "--porcelain"])
    if not porcelain:
        dirty_digest = "clean"
    else:
        diff = _run_git(root, ["diff", "HEAD"])
        payload = (porcelain + "\0" + diff).encode("utf-8")
        dirty_digest = f"dirty:sha256:{hashlib.sha256(payload).hexdigest()}"
    return {"git_sha": git_sha, "dirty_digest": dirty_digest, "repo": "BasedHardware/omi"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Endpoint guards (fail closed before any traffic)
# ---------------------------------------------------------------------------


def validate_local_http_url(url: str, *, what: str = "endpoint") -> str:
    """Reject non-loopback or non-plain-HTTP URLs before a request is made."""

    parsed = urlparse(url)
    host = (parsed.hostname or "").strip("[]").lower()
    if host in PRODUCTION_HOSTS:
        raise EvidenceError(
            f"{what} {url!r} points at the production host {host!r}; session traffic must stay loopback"
        )
    if parsed.scheme != "http":
        raise EvidenceError(f"{what} {url!r} must use plain http for local emulators, got scheme {parsed.scheme!r}")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise EvidenceError(f"{what} {url!r} has an invalid port {parsed.port}")
    if host not in LOOPBACK_HOSTS:
        raise EvidenceError(f"{what} {url!r} must resolve to loopback (127.0.0.1/localhost/::1), got {host!r}")
    return url


def validate_local_host_port(value: str, *, what: str = "emulator host") -> str:
    host, separator, port = value.rpartition(":")
    host = host.strip("[]")
    if not separator or not host or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise EvidenceError(f"{what} {value!r} must be <loopback-host>:<port>")
    if host.lower() not in LOOPBACK_HOSTS:
        raise EvidenceError(f"{what} {value!r} must point at loopback, got host {host!r}")
    return value


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_evidence(
    *,
    session_id: str,
    source: Mapping[str, str],
    target: Mapping[str, Any],
    endpoints: Mapping[str, Any],
    fixtures: Mapping[str, Any],
    runners: Mapping[str, str],
    status: Mapping[str, Any],
    timestamps: Mapping[str, str],
    artifact: Mapping[str, Any] | None = None,
    counts: Mapping[str, int] | None = None,
    artifacts: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Assemble a v1 document; validates before returning."""

    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "source": dict(source),
        "target": dict(target),
        "endpoints": dict(endpoints),
        "fixtures": dict(fixtures),
        "runners": dict(runners),
        "timestamps": dict(timestamps),
        "status": dict(status),
    }
    if artifact is not None:
        document["artifact"] = dict(artifact)
    if counts is not None:
        document["counts"] = dict(counts)
    if artifacts is not None:
        document["artifacts"] = {key: list(value) for key, value in artifacts.items()}
    errors = validate_evidence(document)
    if errors:
        raise EvidenceError("invalid session evidence: " + "; ".join(errors))
    return document


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _walk_credential_keys(node: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            key_text = str(key)
            if _CREDENTIAL_KEY_RE.search(key_text):
                errors.append(f"{path}.{key_text}: credential-shaped key is not allowed in evidence")
            errors.extend(_walk_credential_keys(value, f"{path}.{key_text}"))
    elif isinstance(node, (list, tuple)):
        for index, item in enumerate(node):
            errors.extend(_walk_credential_keys(item, f"{path}[{index}]"))
    return errors


def _validate_relative(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{path}: must be a non-empty relative path")
        return
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        errors.append(f"{path}: must be relative to the session directory and not escape it, got {value!r}")


def validate_evidence(document: Mapping[str, Any]) -> list[str]:
    """Return every contract violation (empty list = valid)."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return ["document must be a JSON object"]

    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}, got {document.get('schema_version')!r}")

    session_id = document.get("session_id")
    if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
        errors.append(f"session_id must match {SESSION_ID_RE.pattern}, got {session_id!r}")

    source = document.get("source")
    if not isinstance(source, Mapping):
        errors.append("source: required object")
    else:
        git_sha = source.get("git_sha")
        if not isinstance(git_sha, str) or not GIT_SHA_RE.match(git_sha):
            errors.append(f"source.git_sha must be a 40-char hex sha, got {git_sha!r}")
        dirty = source.get("dirty_digest")
        if not isinstance(dirty, str) or not DIRTY_DIGEST_RE.match(dirty):
            errors.append(f"source.dirty_digest must be 'clean' or 'dirty:sha256:<64hex>', got {dirty!r}")
        if not isinstance(source.get("repo"), str) or not source.get("repo"):
            errors.append("source.repo must be a non-empty string")

    status = document.get("status")
    state = status.get("state") if isinstance(status, Mapping) else None
    if not isinstance(status, Mapping):
        errors.append("status: required object")
    else:
        if state not in STATES:
            errors.append(f"status.state must be one of {STATES}, got {state!r}")
        reason = status.get("blocked_reason")
        if state == "blocked" and (not isinstance(reason, str) or not reason.strip()):
            errors.append("status.blocked_reason is required when state is 'blocked'")
        if state != "blocked" and reason not in (None, ""):
            errors.append(f"status.blocked_reason must be empty unless state is 'blocked', got {reason!r}")

    target = document.get("target")
    if not isinstance(target, Mapping):
        errors.append("target: required object")
    else:
        if target.get("platform") not in PLATFORMS:
            errors.append(f"target.platform must be one of {PLATFORMS}, got {target.get('platform')!r}")
        if target.get("flavor") not in FLAVORS:
            errors.append(f"target.flavor must be one of {FLAVORS}, got {target.get('flavor')!r}")
        if target.get("profile") not in SESSION_PROFILES:
            errors.append(
                f"target.profile must be one of {SESSION_PROFILES} for session evidence, "
                f"got {target.get('profile')!r}"
            )
        if not isinstance(target.get("app_id"), str) or not target.get("app_id"):
            errors.append("target.app_id must be a non-empty string")
        for optional in ("device", "os"):
            value = target.get(optional)
            if value is not None and not isinstance(value, str):
                errors.append(f"target.{optional} must be a string or null")

    endpoints = document.get("endpoints")
    if not isinstance(endpoints, Mapping):
        errors.append("endpoints: required object")
    else:
        api_base = endpoints.get("api_base_url")
        if not isinstance(api_base, str):
            errors.append("endpoints.api_base_url: required string")
        else:
            try:
                validate_local_http_url(api_base, what="endpoints.api_base_url")
            except EvidenceError as exc:
                errors.append(str(exc))
        for host_key in ("auth_emulator_host", "firestore_emulator_host"):
            value = endpoints.get(host_key)
            if not isinstance(value, str):
                errors.append(f"endpoints.{host_key}: required string")
            else:
                try:
                    validate_local_host_port(value, what=f"endpoints.{host_key}")
                except EvidenceError as exc:
                    errors.append(str(exc))
        if endpoints.get("egress_policy") != EGRESS_POLICY:
            errors.append(f"endpoints.egress_policy must be {EGRESS_POLICY!r}, got {endpoints.get('egress_policy')!r}")
        redis_url = endpoints.get("redis_url")
        if redis_url is not None:
            parsed = urlparse(str(redis_url))
            if (parsed.hostname or "").lower() not in LOOPBACK_HOSTS:
                errors.append(f"endpoints.redis_url must point at loopback, got {redis_url!r}")

    fixtures = document.get("fixtures")
    if not isinstance(fixtures, Mapping):
        errors.append("fixtures: required object")
    else:
        version = fixtures.get("fixture_version")
        if not isinstance(version, str) or not FIXTURE_VERSION_RE.match(version):
            errors.append(f"fixtures.fixture_version must match {FIXTURE_VERSION_RE.pattern}, got {version!r}")

    runners = document.get("runners")
    if not isinstance(runners, Mapping) or not runners:
        errors.append("runners: required non-empty object of runner name -> version")
    else:
        for name, version in runners.items():
            if not isinstance(version, str) or not version.strip():
                errors.append(f"runners.{name}: version must be a non-empty string")

    timestamps = document.get("timestamps")
    if not isinstance(timestamps, Mapping):
        errors.append("timestamps: required object")
    else:
        for key in ("created_at", "started_at", "ended_at"):
            value = timestamps.get(key)
            if value is None:
                if key == "created_at":
                    errors.append("timestamps.created_at is required")
                continue
            if not isinstance(value, str) or not RFC3339_UTC_RE.match(value):
                errors.append(f"timestamps.{key} must be RFC3339 UTC (…Z), got {value!r}")
        created = timestamps.get("created_at")
        started = timestamps.get("started_at")
        ended = timestamps.get("ended_at")
        if isinstance(created, str) and isinstance(started, str) and started < created:
            errors.append("timestamps.started_at must not precede created_at")
        if isinstance(started, str) and isinstance(ended, str) and ended < started:
            errors.append("timestamps.ended_at must not precede started_at")

    artifact = document.get("artifact")
    if artifact is not None:
        if not isinstance(artifact, Mapping):
            errors.append("artifact: must be an object")
        else:
            if artifact.get("kind") not in ("apk", "ios-app-bundle"):
                errors.append(f"artifact.kind must be apk or ios-app-bundle, got {artifact.get('kind')!r}")
            artifact_sha = artifact.get("sha256")
            if not isinstance(artifact_sha, str) or not SHA256_RE.match(artifact_sha):
                errors.append(f"artifact.sha256 must be 64-char hex, got {artifact_sha!r}")
            artifact_git = artifact.get("git_sha")
            if not isinstance(artifact_git, str) or not GIT_SHA_RE.match(artifact_git):
                errors.append(f"artifact.git_sha must be a 40-char hex sha, got {artifact_git!r}")
            artifact_path = artifact.get("path")
            if artifact_path is not None:
                _validate_relative(artifact_path, "artifact.path", errors)
        if state in ("ready", "running"):
            source_git = source.get("git_sha") if isinstance(source, Mapping) else None
            artifact_git = artifact.get("git_sha") if isinstance(artifact, Mapping) else None
            if isinstance(source_git, str) and isinstance(artifact_git, str) and source_git != artifact_git:
                errors.append(
                    "artifact.git_sha does not match source.git_sha: a stale build cannot be reported "
                    f"ready (source={source_git}, artifact={artifact_git})"
                )
    elif state in ("ready", "running"):
        errors.append(f"artifact is required when status.state is {state!r}: ready/running must bind the built app")

    counts = document.get("counts")
    if counts is not None:
        if not isinstance(counts, Mapping):
            errors.append("counts: must be an object")
        else:
            numbers: dict[str, Any] = {}
            for key in ("executed", "passed", "failed", "skipped"):
                value = counts.get(key, 0 if key != "executed" else None)
                if value is None:
                    errors.append("counts.executed is required")
                    continue
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    errors.append(f"counts.{key} must be a non-negative integer, got {value!r}")
                else:
                    numbers[key] = value
            if {"executed", "passed", "failed", "skipped"} <= numbers.keys():
                executed = numbers["executed"]
                accounted = numbers["passed"] + numbers["failed"] + numbers["skipped"]
                if accounted != executed:
                    errors.append(
                        f"counts must account exactly: passed+failed+skipped={accounted} != executed={executed}"
                    )
                if executed == 0 and state in ("running", "stopped", "released", "failed"):
                    errors.append(
                        f"counts.executed is 0 in state {state!r}: a claimed run must not report zero results"
                    )

    artifacts = document.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, Mapping):
            errors.append("artifacts: must be an object")
        else:
            for key in ("logs", "screenshots", "assertions"):
                value = artifacts.get(key)
                if value is None:
                    continue
                if not isinstance(value, (list, tuple)):
                    errors.append(f"artifacts.{key} must be an array of relative paths")
                else:
                    for index, item in enumerate(value):
                        _validate_relative(item, f"artifacts.{key}[{index}]", errors)

    if "live" in document:
        from .live_session import validate_live_evidence

        errors.extend(validate_live_evidence(document))
    errors.extend(_walk_credential_keys(document))
    return errors


def validate_or_raise(document: Mapping[str, Any]) -> dict[str, Any]:
    errors = validate_evidence(document)
    if errors:
        raise EvidenceError("invalid session evidence: " + "; ".join(errors))
    return dict(document)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def write_evidence(path: Path, document: Mapping[str, Any]) -> Path:
    validate_or_raise(document)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def read_evidence(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise EvidenceError(f"{path}: session evidence must be a JSON object")
    return validate_or_raise(data)
