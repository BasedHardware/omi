#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Fail-closed Cloud Run cutover for the sync-ledger fencing protocol.

This is intentionally separate from ordinary backend deploys.  The transition
from the legacy protocol to epoch-fenced jobs cannot safely share traffic with
an older revision, so the workflow executes two protected phases:

* ``stage`` requires the protected runtime variable to read ``standby``.  It
  deploys the immutable candidate with no traffic, pauses both sync queues,
  then moves all three Cloud Run surfaces to the standby revision and removes
  every retired revision.
* ``activate-prepare`` requires ``active`` and a valid stage artifact.  It
  deploys the same immutable image with no traffic and creates a direct Cloud
  Run tag for the full-route protected capability probe.  The workflow invokes
  that probe before recording success and calling ``activate-promote``.

The state artifact intentionally stores only identifiers, lifecycle facts, and
hashes of environment contracts.  It never stores rendered environment values
or secrets.  Queue failures deliberately have no compensating resume path:
after a pause, a failed stage or activation leaves work paused for an operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Callable, Mapping, Protocol, Sequence, cast

SERVICES = ("backend", "backend-sync", "backend-sync-backfill")
QUEUES = ("sync-jobs", "sync-backfill")
FENCE_MODE_ENV = "SYNC_LEDGER_FENCE_MODE"
STATE_SCHEMA_VERSION = 1

STAGE_COMPLETE = "standby_complete"
ACTIVE_READY_FOR_PROBE = "active_ready_for_probe"
ACTIVE_PROBE_PASSED = "active_probe_passed"
ACTIVE_COMPLETE = "active_complete"
PROBE_EVIDENCE_SUITE = "omi_transcription_capability_probe"

_IMMUTABLE_IMAGE_RE = re.compile(r".+@sha256:[0-9a-fA-F]{64}$")
_NAME_RE = re.compile(r"[a-z]([a-z0-9-]{0,61}[a-z0-9])?$")


class CutoverError(RuntimeError):
    """An unsafe cutover precondition or cloud-state verification failure."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def run(self, command: Sequence[str], *, check: bool = True) -> CommandResult: ...


class SubprocessCommandRunner:
    """Small subprocess boundary so unit tests can inject a fake cloud runner."""

    def run(self, command: Sequence[str], *, check: bool = True) -> CommandResult:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
        )
        result = CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and result.returncode != 0:
            # Do not include provider stderr: a rendered command or response
            # can accidentally include sensitive runtime values.
            raise CutoverError(f"cloud command failed (exit={result.returncode}): {' '.join(command[:4])}")
        return result


@dataclass(frozen=True)
class CutoverConfig:
    project: str
    region: str
    candidate_image: str
    state_path: Path
    revision_suffix: str
    poll_attempts: int = 24
    poll_interval_seconds: float = 5.0


def _common_flags(*, project: str, region: str) -> list[str]:
    return [f"--project={project}", f"--region={region}"]


def build_describe_service_command(*, project: str, region: str, service: str) -> list[str]:
    return [
        "gcloud",
        "run",
        "services",
        "describe",
        service,
        *_common_flags(project=project, region=region),
        "--format=json",
    ]


def build_deploy_candidate_command(
    *,
    project: str,
    region: str,
    service: str,
    candidate_image: str,
    mode: str,
    revision_suffix: str,
    tag: str | None = None,
) -> list[str]:
    command = [
        "gcloud",
        "run",
        "services",
        "update",
        service,
        f"--image={candidate_image}",
        f"--update-env-vars={FENCE_MODE_ENV}={mode}",
        "--no-traffic",
        f"--revision-suffix={revision_suffix}",
        *_common_flags(project=project, region=region),
        "--quiet",
    ]
    if tag:
        command.append(f"--tag={tag}")
    return command


def build_describe_revision_command(*, project: str, region: str, revision: str) -> list[str]:
    return [
        "gcloud",
        "run",
        "revisions",
        "describe",
        revision,
        *_common_flags(project=project, region=region),
        "--format=json",
    ]


def build_list_revisions_command(*, project: str, region: str, service: str) -> list[str]:
    return [
        "gcloud",
        "run",
        "revisions",
        "list",
        f"--service={service}",
        *_common_flags(project=project, region=region),
        "--format=json",
    ]


def build_promote_traffic_command(*, project: str, region: str, service: str, revision: str) -> list[str]:
    return [
        "gcloud",
        "run",
        "services",
        "update-traffic",
        service,
        f"--to-revisions={revision}=100",
        *_common_flags(project=project, region=region),
        "--quiet",
    ]


def build_remove_tags_command(*, project: str, region: str, service: str, tags: Sequence[str]) -> list[str]:
    if not tags:
        raise ValueError("at least one Cloud Run tag is required")
    return [
        "gcloud",
        "run",
        "services",
        "update-traffic",
        service,
        f"--remove-tags={','.join(tags)}",
        *_common_flags(project=project, region=region),
        "--quiet",
    ]


def build_delete_revision_command(*, project: str, region: str, revision: str) -> list[str]:
    return [
        "gcloud",
        "run",
        "revisions",
        "delete",
        revision,
        *_common_flags(project=project, region=region),
        "--quiet",
    ]


def build_describe_queue_command(*, project: str, region: str, queue: str) -> list[str]:
    return [
        "gcloud",
        "tasks",
        "queues",
        "describe",
        queue,
        f"--location={region}",
        f"--project={project}",
        "--format=json",
    ]


def build_pause_queue_command(*, project: str, region: str, queue: str) -> list[str]:
    return [
        "gcloud",
        "tasks",
        "queues",
        "pause",
        queue,
        f"--location={region}",
        f"--project={project}",
        "--quiet",
    ]


def build_resume_queue_command(*, project: str, region: str, queue: str) -> list[str]:
    return [
        "gcloud",
        "tasks",
        "queues",
        "resume",
        queue,
        f"--location={region}",
        f"--project={project}",
        "--quiet",
    ]


def _mapping(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _required_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CutoverError(f"missing or invalid {field}")
    return value


def _json_document(result: CommandResult, *, resource: str) -> dict[str, Any]:
    try:
        loaded = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CutoverError(f"{resource} did not return JSON") from error
    if not isinstance(loaded, dict):
        raise CutoverError(f"{resource} returned an unexpected JSON shape")
    return cast(dict[str, Any], loaded)


def _json_list(result: CommandResult, *, resource: str) -> list[dict[str, Any]]:
    try:
        loaded = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CutoverError(f"{resource} did not return JSON") from error
    if isinstance(loaded, dict):
        loaded = loaded.get("items", [])
    if not isinstance(loaded, list) or not all(isinstance(item, dict) for item in loaded):
        raise CutoverError(f"{resource} returned an unexpected JSON shape")
    return [cast(dict[str, Any], item) for item in loaded]


def _containers(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    spec = _mapping(document.get("spec"))
    template = _mapping(spec.get("template"))
    candidates = (
        _list(_mapping(template.get("spec")).get("containers")),
        _list(template.get("containers")),
        _list(spec.get("containers")),
        _list(document.get("containers")),
    )
    for raw_containers in candidates:
        containers = [cast(dict[str, Any], item) for item in raw_containers if isinstance(item, dict)]
        if containers:
            return containers
    raise CutoverError("Cloud Run resource has no container contract")


def _revision_image(document: Mapping[str, Any]) -> str:
    images = []
    for container in _containers(document):
        image = container.get("image")
        if isinstance(image, str) and image:
            images.append(image)
    if len(images) != 1:
        raise CutoverError("Cloud Run candidate must have exactly one container image")
    return images[0]


def _mode_values(document: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for container in _containers(document):
        for raw_env in _list(container.get("env")):
            env = _mapping(raw_env)
            if env.get("name") != FENCE_MODE_ENV:
                continue
            value = env.get("value")
            if isinstance(value, str):
                values.append(value)
    return values


def environment_contract_fingerprint(document: Mapping[str, Any]) -> str:
    """Hash the non-fence environment shape without persisting values in state."""

    normalized_containers: list[dict[str, Any]] = []
    for index, container in enumerate(_containers(document)):
        normalized_env: list[dict[str, Any]] = []
        for raw_env in _list(container.get("env")):
            env = _mapping(raw_env)
            if env.get("name") == FENCE_MODE_ENV:
                continue
            if not isinstance(env.get("name"), str):
                raise CutoverError("Cloud Run environment contract contains an unnamed variable")
            # Values and Secret refs participate in the hash, but are never
            # emitted or saved in the artifact.
            normalized_env.append(env)
        normalized_containers.append(
            {
                "index": index,
                "name": container.get("name", ""),
                "env": sorted(normalized_env, key=lambda item: str(item["name"])),
            }
        )
    encoded = json.dumps(normalized_containers, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _latest_created_revision(service_document: Mapping[str, Any]) -> str:
    status = _mapping(service_document.get("status"))
    for field in ("latestCreatedRevisionName", "latestCreatedRevision"):
        value = status.get(field)
        if isinstance(value, str) and value:
            return value
    raise CutoverError("Cloud Run service did not report a latest created revision")


def _revision_names(revisions: Sequence[Mapping[str, Any]]) -> list[str]:
    result: list[str] = []
    for revision in revisions:
        name = _mapping(revision.get("metadata")).get("name")
        if isinstance(name, str) and name:
            result.append(name)
    return result


def traffic_by_revision(service_document: Mapping[str, Any]) -> dict[str, int]:
    traffic: dict[str, int] = {}
    status = _mapping(service_document.get("status"))
    for raw_target in _list(status.get("traffic")):
        target = _mapping(raw_target)
        revision = target.get("revisionName")
        if not isinstance(revision, str) or not revision:
            continue
        percent = target.get("percent", 0)
        try:
            normalized_percent = int(percent)
        except (TypeError, ValueError) as error:
            raise CutoverError("Cloud Run traffic percentage is invalid") from error
        traffic[revision] = traffic.get(revision, 0) + normalized_percent
    return traffic


def _tagged_target_url(service_document: Mapping[str, Any], *, tag: str, revision: str) -> str:
    status = _mapping(service_document.get("status"))
    for raw_target in _list(status.get("traffic")):
        target = _mapping(raw_target)
        if target.get("tag") != tag:
            continue
        if target.get("revisionName") != revision:
            raise CutoverError("candidate probe tag points at a different revision")
        return _required_string(target.get("url"), field="candidate probe tag URL")
    raise CutoverError("candidate probe tag is absent from Cloud Run status")


def _tags_for_retired_revisions(service_document: Mapping[str, Any], *, candidate_revision: str) -> list[str]:
    tags: list[str] = []
    status = _mapping(service_document.get("status"))
    for raw_target in _list(status.get("traffic")):
        target = _mapping(raw_target)
        tag = target.get("tag")
        if not isinstance(tag, str) or not tag:
            continue
        revision = _required_string(target.get("revisionName"), field="tagged Cloud Run revision")
        if revision != candidate_revision:
            tags.append(tag)
    return sorted(set(tags))


def _assert_no_candidate_traffic(service_document: Mapping[str, Any], *, candidate_revision: str) -> None:
    if traffic_by_revision(service_document).get(candidate_revision, 0) != 0:
        raise CutoverError("candidate revision received traffic before protected promotion")


def _assert_exact_candidate_traffic(service_document: Mapping[str, Any], *, candidate_revision: str) -> None:
    traffic = traffic_by_revision(service_document)
    if traffic.get(candidate_revision) != 100:
        raise CutoverError("candidate revision does not receive exactly 100% traffic")
    if any(revision != candidate_revision and percent != 0 for revision, percent in traffic.items()):
        raise CutoverError("a non-candidate revision still receives traffic")


def _queue_state(queue_document: Mapping[str, Any]) -> str:
    state = queue_document.get("state")
    if not isinstance(state, str) or not state:
        raise CutoverError("Cloud Tasks queue did not report a state")
    return state.upper()


def validate_candidate_image(candidate_image: str) -> None:
    if not _IMMUTABLE_IMAGE_RE.fullmatch(candidate_image):
        raise CutoverError("candidate image must be an immutable @sha256 digest reference")


def validate_name(value: str, *, field: str) -> None:
    if not _NAME_RE.fullmatch(value):
        raise CutoverError(f"{field} must be a lower-case Cloud Run-compatible identifier")


def require_fence_mode(expected: str, environ: Mapping[str, str] | None = None) -> None:
    actual = (environ or os.environ).get(FENCE_MODE_ENV, "")
    if actual != expected:
        raise CutoverError(f"protected {FENCE_MODE_ENV} must read back as {expected!r}")


def _new_state(config: CutoverConfig, *, mode: str) -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "project": config.project,
        "region": config.region,
        "candidate_image": config.candidate_image,
        "phase": "initialized",
        "mode_readbacks": [mode],
        "services": {},
        "queues": {},
        "phase_history": ["initialized"],
    }


def load_state(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CutoverError("cutover state artifact is missing") from error
    except json.JSONDecodeError as error:
        raise CutoverError("cutover state artifact is not valid JSON") from error
    if not isinstance(loaded, dict):
        raise CutoverError("cutover state artifact must be a JSON object")
    state = cast(dict[str, Any], loaded)
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise CutoverError("cutover state artifact schema is unsupported")
    return state


def write_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, path)


def _set_phase(state: dict[str, Any], phase: str, path: Path) -> None:
    state["phase"] = phase
    history = state.setdefault("phase_history", [])
    if isinstance(history, list) and (not history or history[-1] != phase):
        history.append(phase)
    write_state(path, state)


def _validate_state_identity(state: Mapping[str, Any], config: CutoverConfig) -> None:
    if state.get("project") != config.project or state.get("region") != config.region:
        raise CutoverError("cutover state artifact belongs to a different Cloud Run target")
    if state.get("candidate_image") != config.candidate_image:
        raise CutoverError("cutover state artifact belongs to a different candidate image")


def _require_passing_candidate_probe(evidence: bytes) -> None:
    """Accept only the redacted, full-route candidate proof produced by the probe.

    A zero exit code in the workflow is useful but not a durable state-machine
    boundary.  This intentionally validates only typed booleans and labels so
    the proof cannot persist a transcript, URL, bearer token, or other probe
    material in the cutover artifact.
    """

    try:
        document = json.loads(evidence.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CutoverError("candidate probe evidence is not valid redacted JSON") from error
    if not isinstance(document, dict):
        raise CutoverError("candidate probe evidence is not a JSON object")
    if document.get("suite") != PROBE_EVIDENCE_SUITE or document.get("status") != "PASS":
        raise CutoverError("candidate probe evidence did not report a passing transcription suite")
    if document.get("full_route_authoritative") is not True:
        raise CutoverError("candidate probe evidence did not mark the full route authoritative")
    if document.get("direct_diagnostic_only") is not True:
        raise CutoverError("candidate probe evidence did not preserve direct-route diagnostic semantics")

    checks = document.get("checks")
    if not isinstance(checks, list):
        raise CutoverError("candidate probe evidence has no checks list")
    full_route_checks = [check for check in checks if isinstance(check, dict) and check.get("name") == "full_route"]
    if len(full_route_checks) != 1 or full_route_checks[0].get("status") != "PASS":
        raise CutoverError("candidate probe evidence did not prove a passing full route")
    details = full_route_checks[0].get("details")
    if not isinstance(details, dict) or details.get("authority") != "candidate_gate":
        raise CutoverError("candidate probe evidence did not identify the full-route candidate gate")
    required_true_details = (
        "configured",
        "fixture_available",
        "json_object",
        "outcome_success",
        "phrase_match",
        "provider_checked",
        "provider_match",
        "model_checked",
        "model_match",
    )
    if any(details.get(field) is not True for field in required_true_details):
        raise CutoverError("candidate probe evidence did not prove transcript and route identity")


class CutoverOrchestrator:
    """Performs every mutation through a fakeable command runner."""

    def __init__(
        self,
        config: CutoverConfig,
        *,
        runner: CommandRunner,
        sleep: Callable[[float], None] = time.sleep,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self.runner = runner
        self.sleep = sleep
        self.environ = environ if environ is not None else os.environ

    def _run_json(self, command: Sequence[str], *, resource: str) -> dict[str, Any]:
        return _json_document(self.runner.run(command), resource=resource)

    def _describe_service(self, service: str) -> dict[str, Any]:
        return self._run_json(
            build_describe_service_command(project=self.config.project, region=self.config.region, service=service),
            resource=f"Cloud Run service {service}",
        )

    def _describe_queue(self, queue: str) -> dict[str, Any]:
        return self._run_json(
            build_describe_queue_command(project=self.config.project, region=self.config.region, queue=queue),
            resource=f"Cloud Tasks queue {queue}",
        )

    def _list_revisions(self, service: str) -> list[dict[str, Any]]:
        result = self.runner.run(
            build_list_revisions_command(project=self.config.project, region=self.config.region, service=service)
        )
        return _json_list(result, resource=f"Cloud Run revisions for {service}")

    def _wait_for_candidate_revision(self, *, service: str, revision_suffix: str) -> tuple[str, dict[str, Any]]:
        expected_suffix = f"-{revision_suffix}"
        for attempt in range(self.config.poll_attempts):
            service_document = self._describe_service(service)
            revision = _latest_created_revision(service_document)
            if revision.endswith(expected_suffix):
                return revision, service_document
            if attempt + 1 < self.config.poll_attempts:
                self.sleep(self.config.poll_interval_seconds)
        raise CutoverError(f"{service} did not create the expected cutover revision")

    def _wait_for_ready_revision(self, revision: str) -> dict[str, Any]:
        command = build_describe_revision_command(
            project=self.config.project,
            region=self.config.region,
            revision=revision,
        )
        for attempt in range(self.config.poll_attempts):
            result = self.runner.run(command, check=False)
            if result.returncode == 0:
                document = _json_document(result, resource=f"Cloud Run revision {revision}")
                conditions = _list(_mapping(document.get("status")).get("conditions"))
                ready = any(
                    _mapping(condition).get("type") == "Ready" and _mapping(condition).get("status") == "True"
                    for condition in conditions
                )
                if ready:
                    return document
            if attempt + 1 < self.config.poll_attempts:
                self.sleep(self.config.poll_interval_seconds)
        raise CutoverError(f"Cloud Run revision {revision} did not become Ready")

    def _verify_candidate_contract(
        self,
        *,
        service: str,
        revision: str,
        revision_document: Mapping[str, Any],
        expected_mode: str,
        expected_env_fingerprint: str,
    ) -> None:
        if _revision_image(revision_document) != self.config.candidate_image:
            raise CutoverError(f"{service} revision {revision} does not use the exact candidate image")
        if _mode_values(revision_document) != [expected_mode]:
            raise CutoverError(f"{service} revision {revision} does not have exactly one expected fence mode")
        if environment_contract_fingerprint(revision_document) != expected_env_fingerprint:
            raise CutoverError(f"{service} revision {revision} environment contract differs from the staged service")

    def _deploy_phase(
        self,
        *,
        state: dict[str, Any],
        mode: str,
        revision_suffix: str,
        phase_prefix: str,
        probe_tag: str | None = None,
    ) -> dict[str, str]:
        services_state = _mapping(state.setdefault("services", {}))
        deployed_revisions: dict[str, str] = {}
        for service in SERVICES:
            prior_service = self._describe_service(service)
            service_state = _mapping(services_state.setdefault(service, {}))
            baseline_fingerprint = environment_contract_fingerprint(prior_service)
            if "baseline_env_fingerprint" in service_state:
                if service_state["baseline_env_fingerprint"] != baseline_fingerprint:
                    raise CutoverError(f"{service} environment changed after stage state was recorded")
            else:
                service_state["baseline_env_fingerprint"] = baseline_fingerprint
                service_state["baseline_revision"] = _latest_created_revision(prior_service)
                write_state(self.config.state_path, state)

            tag = probe_tag if service == "backend" else None
            self.runner.run(
                build_deploy_candidate_command(
                    project=self.config.project,
                    region=self.config.region,
                    service=service,
                    candidate_image=self.config.candidate_image,
                    mode=mode,
                    revision_suffix=revision_suffix,
                    tag=tag,
                )
            )
            revision, service_document = self._wait_for_candidate_revision(
                service=service,
                revision_suffix=revision_suffix,
            )
            revision_document = self._wait_for_ready_revision(revision)
            self._verify_candidate_contract(
                service=service,
                revision=revision,
                revision_document=revision_document,
                expected_mode=mode,
                expected_env_fingerprint=baseline_fingerprint,
            )
            _assert_no_candidate_traffic(service_document, candidate_revision=revision)
            service_state[f"{phase_prefix}_revision"] = revision
            service_state[f"{phase_prefix}_env_fingerprint"] = environment_contract_fingerprint(revision_document)
            deployed_revisions[service] = revision
            write_state(self.config.state_path, state)
        return deployed_revisions

    def _record_and_pause_queues(self, state: dict[str, Any]) -> None:
        queues_state = _mapping(state.setdefault("queues", {}))
        for queue in QUEUES:
            state_before_pause = _queue_state(self._describe_queue(queue))
            if state_before_pause not in {"RUNNING", "PAUSED"}:
                raise CutoverError(f"Cloud Tasks queue {queue} is in unsupported state {state_before_pause}")
            queues_state[queue] = {
                "recorded_state": state_before_pause,
                "verified_paused": state_before_pause == "PAUSED",
                "paused_by_cutover": False,
                "resumed_by_cutover": False,
            }
            write_state(self.config.state_path, state)

        # There is deliberately no except/finally resume.  Once this starts,
        # every failure leaves queues paused (or as paused as Cloud Tasks allowed).
        for queue in QUEUES:
            queue_state = _mapping(queues_state[queue])
            if queue_state["recorded_state"] == "RUNNING":
                self.runner.run(
                    build_pause_queue_command(project=self.config.project, region=self.config.region, queue=queue)
                )
                queue_state["paused_by_cutover"] = True
            if _queue_state(self._describe_queue(queue)) != "PAUSED":
                raise CutoverError(f"Cloud Tasks queue {queue} did not become PAUSED")
            queue_state["verified_paused"] = True
            write_state(self.config.state_path, state)
        _set_phase(state, "queues_paused", self.config.state_path)

    def _verify_recorded_queues_are_paused(self, state: Mapping[str, Any]) -> None:
        queues_state = _mapping(state.get("queues"))
        if set(queues_state) != set(QUEUES):
            raise CutoverError("cutover state does not contain both sync queues")
        for queue in QUEUES:
            recorded = _mapping(queues_state.get(queue))
            if recorded.get("recorded_state") not in {"RUNNING", "PAUSED"}:
                raise CutoverError(f"cutover state has no safe original state for {queue}")
            if recorded.get("verified_paused") is not True:
                raise CutoverError(f"cutover state did not verify {queue} was paused")
            if _queue_state(self._describe_queue(queue)) != "PAUSED":
                raise CutoverError(f"Cloud Tasks queue {queue} is no longer paused")

    def _promote_all_services(
        self,
        *,
        state: dict[str, Any],
        phase_prefix: str,
        resumable: bool = False,
        persist_phase: bool = True,
    ) -> None:
        services_state = _mapping(state.get("services"))
        for service in SERVICES:
            service_state = _mapping(services_state.get(service))
            revision = _required_string(service_state.get(f"{phase_prefix}_revision"), field=f"{service} revision")
            verified_key = f"{phase_prefix}_traffic_verified"
            service_document = self._describe_service(service)
            if resumable:
                if service_state.get(verified_key) is True:
                    _assert_exact_candidate_traffic(service_document, candidate_revision=revision)
                    continue
                # A process can die after Cloud Run accepted the traffic update
                # but before it recorded the marker.  Adopt only an exact
                # active result; any mixed/unknown traffic fails closed.
                if traffic_by_revision(service_document).get(revision) == 100:
                    _assert_exact_candidate_traffic(service_document, candidate_revision=revision)
                    service_state[verified_key] = True
                    write_state(self.config.state_path, state)
                    continue
                standby_revision = _required_string(
                    service_state.get("standby_revision"), field=f"{service} standby revision"
                )
                _assert_exact_candidate_traffic(service_document, candidate_revision=standby_revision)
            self.runner.run(
                build_promote_traffic_command(
                    project=self.config.project,
                    region=self.config.region,
                    service=service,
                    revision=revision,
                )
            )
            _assert_exact_candidate_traffic(self._describe_service(service), candidate_revision=revision)
            if resumable:
                service_state[verified_key] = True
            write_state(self.config.state_path, state)
        if persist_phase:
            _set_phase(state, f"{phase_prefix}_traffic_promoted", self.config.state_path)

    def _poll_revision_absent(self, *, service: str, revision: str) -> None:
        for attempt in range(self.config.poll_attempts):
            if revision not in _revision_names(self._list_revisions(service)):
                return
            if attempt + 1 < self.config.poll_attempts:
                self.sleep(self.config.poll_interval_seconds)
        raise CutoverError(f"retired revision {revision} remains present after deletion")

    def _cleanup_retired_revisions(
        self,
        *,
        state: dict[str, Any],
        phase_prefix: str,
        persist_phase: bool = True,
    ) -> None:
        services_state = _mapping(state.get("services"))
        cleanup_key = f"{phase_prefix}_retired_revisions_deleted"
        for service in SERVICES:
            service_state = _mapping(services_state.get(service))
            candidate_revision = _required_string(
                service_state.get(f"{phase_prefix}_revision"), field=f"{service} candidate revision"
            )
            service_document = self._describe_service(service)
            _assert_exact_candidate_traffic(service_document, candidate_revision=candidate_revision)

            retired_tags = _tags_for_retired_revisions(service_document, candidate_revision=candidate_revision)
            if retired_tags:
                self.runner.run(
                    build_remove_tags_command(
                        project=self.config.project,
                        region=self.config.region,
                        service=service,
                        tags=retired_tags,
                    )
                )
                service_document = self._describe_service(service)
                _assert_exact_candidate_traffic(service_document, candidate_revision=candidate_revision)
                if _tags_for_retired_revisions(service_document, candidate_revision=candidate_revision):
                    raise CutoverError(f"retired revision tags remain on {service}")

            revisions = _revision_names(self._list_revisions(service))
            if candidate_revision not in revisions:
                raise CutoverError(f"candidate revision {candidate_revision} disappeared before cleanup")
            retired_revisions = [revision for revision in revisions if revision != candidate_revision]
            traffic = traffic_by_revision(service_document)
            if any(traffic.get(revision, 0) != 0 for revision in retired_revisions):
                raise CutoverError(f"cannot delete a retired revision that still receives traffic on {service}")
            deleted = _list(service_state.setdefault(cleanup_key, []))
            for revision in retired_revisions:
                self.runner.run(
                    build_delete_revision_command(
                        project=self.config.project,
                        region=self.config.region,
                        revision=revision,
                    )
                )
                self._poll_revision_absent(service=service, revision=revision)
                if revision not in deleted:
                    deleted.append(revision)
                service_state[cleanup_key] = deleted
                write_state(self.config.state_path, state)
            if _revision_names(self._list_revisions(service)) != [candidate_revision]:
                # Cloud Run's list order is not guaranteed, so compare sets.
                remaining = set(_revision_names(self._list_revisions(service)))
                if remaining != {candidate_revision}:
                    raise CutoverError(f"non-candidate Cloud Run revisions remain on {service}")
            _assert_exact_candidate_traffic(self._describe_service(service), candidate_revision=candidate_revision)
            write_state(self.config.state_path, state)
        if persist_phase:
            _set_phase(state, f"{phase_prefix}_cleanup_complete", self.config.state_path)

    def _remove_active_probe_tag(self, *, state: dict[str, Any], probe_tag: str) -> None:
        services_state = _mapping(state.get("services"))
        backend_state = _mapping(services_state.get("backend"))
        active_revision = _required_string(backend_state.get("active_revision"), field="backend active revision")
        service_document = self._describe_service("backend")
        status = _mapping(service_document.get("status"))
        tag_exists = any(_mapping(item).get("tag") == probe_tag for item in _list(status.get("traffic")))
        if state.get("probe_tag_removed") is True:
            if tag_exists:
                raise CutoverError("candidate probe tag reappeared after it was removed")
            # Promotion is intentionally resumable while queues stay paused.
            # A process may die after backend traffic moves but before another
            # service does, so no-traffic is no longer a valid retry
            # precondition once this irreversible tag-removal boundary was
            # recorded.  The tag's absence is the idempotence contract here;
            # _promote_all_services verifies traffic per service afterwards.
            return
        if not tag_exists:
            # A previous attempt can succeed in deleting the tag immediately
            # before its process dies.  Treat that precise state as a safe,
            # idempotent retry rather than making active promotion unrecoverable.
            state["probe_tag_removed"] = True
            write_state(self.config.state_path, state)
            return
        # The tag must name this exact active candidate before it is removed.
        _tagged_target_url(service_document, tag=probe_tag, revision=active_revision)
        self.runner.run(
            build_remove_tags_command(
                project=self.config.project,
                region=self.config.region,
                service="backend",
                tags=[probe_tag],
            )
        )
        refreshed = self._describe_service("backend")
        status = _mapping(refreshed.get("status"))
        if any(_mapping(item).get("tag") == probe_tag for item in _list(status.get("traffic"))):
            raise CutoverError("candidate probe tag remains after removal")
        _assert_no_candidate_traffic(refreshed, candidate_revision=active_revision)
        state["probe_tag_removed"] = True
        write_state(self.config.state_path, state)

    def _resume_only_originally_running_queues(self, state: dict[str, Any]) -> None:
        queues_state = _mapping(state.get("queues"))
        for queue in QUEUES:
            queue_state = _mapping(queues_state.get(queue))
            original_state = queue_state.get("recorded_state")
            if original_state == "RUNNING":
                current_state = _queue_state(self._describe_queue(queue))
                if queue_state.get("resumed_by_cutover") is True:
                    if current_state != "RUNNING":
                        raise CutoverError(f"Cloud Tasks queue {queue} resumed state drifted")
                    continue
                if current_state == "PAUSED":
                    self.runner.run(
                        build_resume_queue_command(project=self.config.project, region=self.config.region, queue=queue)
                    )
                    current_state = _queue_state(self._describe_queue(queue))
                if current_state != "RUNNING":
                    raise CutoverError(f"Cloud Tasks queue {queue} did not resume")
                queue_state["resumed_by_cutover"] = True
            elif original_state == "PAUSED":
                if _queue_state(self._describe_queue(queue)) != "PAUSED":
                    raise CutoverError(f"Cloud Tasks queue {queue} was originally paused and must remain paused")
            else:
                raise CutoverError(f"cutover state has no safe original state for {queue}")
            write_state(self.config.state_path, state)

    def stage(self) -> dict[str, Any]:
        validate_candidate_image(self.config.candidate_image)
        validate_name(self.config.revision_suffix, field="revision suffix")
        require_fence_mode("standby", self.environ)
        if self.config.state_path.exists():
            existing_state = load_state(self.config.state_path)
            _validate_state_identity(existing_state, self.config)
            if existing_state.get("phase") == STAGE_COMPLETE:
                self._verify_recorded_queues_are_paused(existing_state)
                self._verify_stage_traffic(existing_state)
                return existing_state
            # Never reconstruct queue origins from a partially paused state.
            # The artifact is the authoritative recovery record; replacing it
            # could turn an originally RUNNING queue into permanently PAUSED or
            # allow an unsafe resume.
            raise CutoverError(
                "refusing to overwrite incomplete standby state; queues may be paused, recover from this artifact manually"
            )
        state = _new_state(self.config, mode="standby")
        write_state(self.config.state_path, state)
        _set_phase(state, "standby_deploying", self.config.state_path)
        self._deploy_phase(
            state=state,
            mode="standby",
            revision_suffix=self.config.revision_suffix,
            phase_prefix="standby",
        )
        _set_phase(state, "standby_deployed", self.config.state_path)
        # Move every admission surface to standby before pausing tasks.  If we
        # paused first, an old backend revision could still accept a fresh
        # inline or queued job during the barrier and leave retry material
        # behind after workers are stopped.
        self._promote_all_services(state=state, phase_prefix="standby")
        self._record_and_pause_queues(state)
        self._cleanup_retired_revisions(state=state, phase_prefix="standby")
        _set_phase(state, STAGE_COMPLETE, self.config.state_path)
        return state

    def activate_prepare(self, *, probe_tag: str, github_output: Path | None = None) -> dict[str, Any]:
        validate_candidate_image(self.config.candidate_image)
        validate_name(self.config.revision_suffix, field="revision suffix")
        validate_name(probe_tag, field="probe tag")
        require_fence_mode("active", self.environ)
        state = load_state(self.config.state_path)
        _validate_state_identity(state, self.config)
        phase = state.get("phase")
        if phase == ACTIVE_READY_FOR_PROBE:
            probe = _mapping(state.get("probe"))
            if probe.get("tag") != probe_tag:
                raise CutoverError("active candidate recovery must use the persisted probe tag")
            self._verify_recorded_queues_are_paused(state)
            self._verify_stage_traffic(state)
            backend_revision = _required_string(probe.get("revision"), field="backend active revision")
            probe_url = _tagged_target_url(self._describe_service("backend"), tag=probe_tag, revision=backend_revision)
            if github_output is not None:
                with github_output.open("a", encoding="utf-8") as output:
                    output.write(f"candidate_probe_url={probe_url}\n")
            return state
        if phase != STAGE_COMPLETE:
            raise CutoverError("activation requires a completed standby stage artifact")
        self._verify_recorded_queues_are_paused(state)
        self._verify_stage_traffic(state)
        _set_phase(state, "active_deploying", self.config.state_path)
        self._deploy_phase(
            state=state,
            mode="active",
            revision_suffix=self.config.revision_suffix,
            phase_prefix="active",
            probe_tag=probe_tag,
        )
        backend_revision = _required_string(
            _mapping(_mapping(state.get("services")).get("backend")).get("active_revision"),
            field="backend active revision",
        )
        backend_service = self._describe_service("backend")
        probe_url = _tagged_target_url(backend_service, tag=probe_tag, revision=backend_revision)
        state["probe"] = {"tag": probe_tag, "url": probe_url, "revision": backend_revision}
        _set_phase(state, ACTIVE_READY_FOR_PROBE, self.config.state_path)
        if github_output is not None:
            with github_output.open("a", encoding="utf-8") as output:
                output.write(f"candidate_probe_url={probe_url}\n")
        return state

    def _verify_stage_traffic(self, state: Mapping[str, Any]) -> None:
        services_state = _mapping(state.get("services"))
        for service in SERVICES:
            standby_revision = _required_string(
                _mapping(services_state.get(service)).get("standby_revision"),
                field=f"{service} standby revision",
            )
            _assert_exact_candidate_traffic(self._describe_service(service), candidate_revision=standby_revision)

    def record_probe_success(self, *, evidence_path: Path) -> dict[str, Any]:
        require_fence_mode("active", self.environ)
        state = load_state(self.config.state_path)
        _validate_state_identity(state, self.config)
        if state.get("phase") == ACTIVE_PROBE_PASSED:
            if not isinstance(state.get("probe_evidence_sha256"), str):
                raise CutoverError("active probe state is missing its protected evidence digest")
            self._verify_recorded_queues_are_paused(state)
            return state
        if state.get("phase") != ACTIVE_READY_FOR_PROBE:
            raise CutoverError("probe success can only be recorded after active candidate readiness")
        self._verify_recorded_queues_are_paused(state)
        try:
            evidence = evidence_path.read_bytes()
        except FileNotFoundError as error:
            raise CutoverError("protected candidate probe evidence is missing") from error
        if not evidence.strip():
            raise CutoverError("protected candidate probe evidence is empty")
        _require_passing_candidate_probe(evidence)
        # Store a digest rather than the evidence, which can contain diagnostics.
        state["probe_evidence_sha256"] = hashlib.sha256(evidence).hexdigest()
        _set_phase(state, ACTIVE_PROBE_PASSED, self.config.state_path)
        return state

    def activate_promote(self, *, probe_tag: str) -> dict[str, Any]:
        require_fence_mode("active", self.environ)
        state = load_state(self.config.state_path)
        _validate_state_identity(state, self.config)
        probe = _mapping(state.get("probe"))
        if probe.get("tag") != probe_tag or not state.get("probe_evidence_sha256"):
            raise CutoverError("active traffic promotion has no matching protected probe proof")
        if state.get("phase") == ACTIVE_COMPLETE:
            # A successful cutover may be retried by GitHub Actions.  Never
            # issue a second traffic, deletion, or queue-resume mutation.
            return state
        if state.get("phase") != ACTIVE_PROBE_PASSED:
            raise CutoverError("active traffic promotion requires successful protected probe evidence")
        self._verify_recorded_queues_are_paused(state)
        self._remove_active_probe_tag(state=state, probe_tag=probe_tag)
        self._promote_all_services(
            state=state,
            phase_prefix="active",
            resumable=True,
            persist_phase=False,
        )
        self._cleanup_retired_revisions(state=state, phase_prefix="active", persist_phase=False)
        self._resume_only_originally_running_queues(state)
        _set_phase(state, ACTIVE_COMPLETE, self.config.state_path)
        return state


def _add_common_arguments(parser: argparse.ArgumentParser, *, needs_revision_suffix: bool) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--state-path", required=True, type=Path)
    if needs_revision_suffix:
        parser.add_argument("--revision-suffix", required=True)
    parser.add_argument("--poll-attempts", type=int, default=24)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    stage_parser = subcommands.add_parser("stage", help="deploy and promote the protected standby phase")
    _add_common_arguments(stage_parser, needs_revision_suffix=True)

    prepare_parser = subcommands.add_parser(
        "activate-prepare", help="deploy the active candidate and tag its probe URL"
    )
    _add_common_arguments(prepare_parser, needs_revision_suffix=True)
    prepare_parser.add_argument("--probe-tag", required=True)
    prepare_parser.add_argument("--github-output", type=Path)

    proof_parser = subcommands.add_parser("record-probe-success", help="record the passed protected full-route probe")
    _add_common_arguments(proof_parser, needs_revision_suffix=False)
    proof_parser.add_argument("--probe-evidence", required=True, type=Path)

    promote_parser = subcommands.add_parser(
        "activate-promote", help="promote the probed active candidate and resume safe queues"
    )
    _add_common_arguments(promote_parser, needs_revision_suffix=False)
    promote_parser.add_argument("--probe-tag", required=True)
    return parser.parse_args(argv)


def _config_from_args(args: argparse.Namespace) -> CutoverConfig:
    poll_attempts = int(args.poll_attempts)
    poll_interval_seconds = float(args.poll_interval_seconds)
    if poll_attempts <= 0 or poll_interval_seconds < 0:
        raise CutoverError("poll attempts must be positive and poll interval must be non-negative")
    revision_suffix = getattr(args, "revision_suffix", "not-used")
    return CutoverConfig(
        project=args.project,
        region=args.region,
        candidate_image=args.candidate_image,
        state_path=args.state_path,
        revision_suffix=revision_suffix,
        poll_attempts=poll_attempts,
        poll_interval_seconds=poll_interval_seconds,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: CommandRunner | None = None,
    sleep: Callable[[float], None] = time.sleep,
    environ: Mapping[str, str] | None = None,
) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        config = _config_from_args(args)
        orchestrator = CutoverOrchestrator(
            config,
            runner=runner or SubprocessCommandRunner(),
            sleep=sleep,
            environ=environ,
        )
        if args.command == "stage":
            orchestrator.stage()
        elif args.command == "activate-prepare":
            orchestrator.activate_prepare(probe_tag=args.probe_tag, github_output=args.github_output)
        elif args.command == "record-probe-success":
            orchestrator.record_probe_success(evidence_path=args.probe_evidence)
        elif args.command == "activate-promote":
            orchestrator.activate_promote(probe_tag=args.probe_tag)
        else:  # pragma: no cover - argparse makes this unreachable.
            raise CutoverError("unknown cutover command")
    except CutoverError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
