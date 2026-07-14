#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Fail closed unless every serving sync surface has one proven fence mode.

The sync-ledger fence protocol changes Redis ownership semantics, so its
rollout cannot infer a serving revision from a service template or from the
most recently created revision.  This read-only verifier selects only the
positive-traffic revision recorded in each Cloud Run service *status*, then
reads that revision's literal ``SYNC_LEDGER_FENCE_MODE`` value.

The only bootstrap exception is a fleet where every serving revision predates
the setting and therefore omits it entirely; that is equivalent to the
runtime's documented ``legacy`` default.  A partial omission, traffic split,
or a mode other than the requested one is unsafe and fails the gate.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol, Sequence, cast

SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill')
FENCE_MODE_ENV = 'SYNC_LEDGER_FENCE_MODE'
FENCE_MODES = frozenset({'legacy', 'standby', 'active'})


class FenceTransitionVerificationError(RuntimeError):
    """Cloud Run state cannot safely prove a fence-mode transition."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ''
    stderr: str = ''


class CommandRunner(Protocol):
    def run(self, command: Sequence[str], *, check: bool = True) -> CommandResult:
        ...


class SubprocessCommandRunner:
    """Small subprocess seam so tests never invoke gcloud."""

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
            raise FenceTransitionVerificationError(
                f'Cloud Run query failed (exit={result.returncode}): {" ".join(command[:4])}'
            )
        return result


@dataclass(frozen=True)
class TransitionVerificationConfig:
    project: str
    region: str
    desired_mode: str


@dataclass(frozen=True)
class ServingRevision:
    service: str
    revision: str
    mode: str | None


@dataclass(frozen=True)
class TransitionVerificationResult:
    desired_mode: str
    bootstrap_legacy: bool
    serving_revisions: tuple[ServingRevision, ...]


def build_describe_service_command(*, project: str, region: str, service: str) -> list[str]:
    return [
        'gcloud',
        'run',
        'services',
        'describe',
        service,
        f'--project={project}',
        f'--region={region}',
        '--format=json',
    ]


def build_describe_revision_command(*, project: str, region: str, revision: str) -> list[str]:
    return [
        'gcloud',
        'run',
        'revisions',
        'describe',
        revision,
        f'--project={project}',
        f'--region={region}',
        '--format=json',
    ]


def _json_object(result: CommandResult, *, resource: str) -> dict[str, Any]:
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise FenceTransitionVerificationError(f'{resource} did not return JSON') from error
    if not isinstance(document, dict):
        raise FenceTransitionVerificationError(f'{resource} returned an unexpected JSON shape')
    return cast(dict[str, Any], document)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _traffic_percent(value: Any, *, service: str) -> int:
    if isinstance(value, bool):
        raise FenceTransitionVerificationError(f'{service} has a non-integer Cloud Run traffic percentage')
    if isinstance(value, int):
        percent = value
    elif isinstance(value, str) and value.isdecimal():
        percent = int(value)
    else:
        raise FenceTransitionVerificationError(f'{service} has a non-integer Cloud Run traffic percentage')
    if not 0 <= percent <= 100:
        raise FenceTransitionVerificationError(f'{service} has an out-of-range Cloud Run traffic percentage')
    return percent


def serving_revision_from_status(service_document: Mapping[str, Any], *, service: str) -> str:
    """Return the one positive-traffic revision from service status only."""

    status = service_document.get('status')
    if not isinstance(status, Mapping):
        raise FenceTransitionVerificationError(f'{service} did not report a Cloud Run status')
    traffic = status.get('traffic')
    if not isinstance(traffic, list):
        raise FenceTransitionVerificationError(f'{service} did not report Cloud Run status traffic')

    positive_traffic: dict[str, int] = {}
    for index, raw_target in enumerate(traffic):
        if not isinstance(raw_target, Mapping):
            raise FenceTransitionVerificationError(f'{service} status traffic target {index} is invalid')
        percent = _traffic_percent(raw_target.get('percent'), service=service)
        if percent == 0:
            continue
        revision = raw_target.get('revisionName')
        if not isinstance(revision, str) or not revision:
            raise FenceTransitionVerificationError(f'{service} has positive traffic without a concrete revision name')
        positive_traffic[revision] = positive_traffic.get(revision, 0) + percent

    if not positive_traffic:
        raise FenceTransitionVerificationError(f'{service} has no positive-traffic serving revision')
    if len(positive_traffic) != 1:
        revisions = ', '.join(sorted(positive_traffic))
        raise FenceTransitionVerificationError(f'{service} splits positive traffic across revisions: {revisions}')
    if sum(positive_traffic.values()) != 100:
        raise FenceTransitionVerificationError(f'{service} does not report exactly 100% positive serving traffic')
    return next(iter(positive_traffic))


def fence_mode_from_revision(revision_document: Mapping[str, Any], *, service: str, revision: str) -> str | None:
    """Read the literal fence-mode declaration from exactly one revision env entry."""

    spec = _mapping(revision_document.get('spec'))
    containers = spec.get('containers')
    if not isinstance(containers, list) or not containers:
        raise FenceTransitionVerificationError(f'{service} serving revision {revision} has no container contract')

    declarations: list[Mapping[str, Any]] = []
    for container_index, raw_container in enumerate(containers):
        if not isinstance(raw_container, Mapping):
            raise FenceTransitionVerificationError(
                f'{service} serving revision {revision} has an invalid container at index {container_index}'
            )
        environment = raw_container.get('env', [])
        if not isinstance(environment, list):
            raise FenceTransitionVerificationError(
                f'{service} serving revision {revision} has an invalid environment contract'
            )
        for raw_entry in environment:
            if not isinstance(raw_entry, Mapping):
                raise FenceTransitionVerificationError(
                    f'{service} serving revision {revision} has an invalid environment entry'
                )
            if raw_entry.get('name') == FENCE_MODE_ENV:
                declarations.append(raw_entry)

    if not declarations:
        return None
    if len(declarations) != 1:
        raise FenceTransitionVerificationError(
            f'{service} serving revision {revision} declares {FENCE_MODE_ENV} more than once'
        )
    mode = declarations[0].get('value')
    if not isinstance(mode, str) or mode not in FENCE_MODES:
        raise FenceTransitionVerificationError(
            f'{service} serving revision {revision} has an invalid {FENCE_MODE_ENV} value'
        )
    return mode


def _read_serving_revision(
    config: TransitionVerificationConfig,
    *,
    runner: CommandRunner,
    service: str,
) -> ServingRevision:
    service_result = runner.run(
        build_describe_service_command(project=config.project, region=config.region, service=service)
    )
    service_document = _json_object(service_result, resource=f'Cloud Run service {service}')
    revision = serving_revision_from_status(service_document, service=service)
    revision_result = runner.run(
        build_describe_revision_command(project=config.project, region=config.region, revision=revision)
    )
    revision_document = _json_object(revision_result, resource=f'Cloud Run revision {revision}')
    mode = fence_mode_from_revision(revision_document, service=service, revision=revision)
    return ServingRevision(service=service, revision=revision, mode=mode)


def verify_transition(config: TransitionVerificationConfig, *, runner: CommandRunner) -> TransitionVerificationResult:
    if config.desired_mode not in FENCE_MODES:
        raise FenceTransitionVerificationError(f'desired mode must be one of: {", ".join(sorted(FENCE_MODES))}')

    serving_revisions = tuple(_read_serving_revision(config, runner=runner, service=service) for service in SERVICES)
    modes = tuple(observation.mode for observation in serving_revisions)
    if all(mode is None for mode in modes):
        if config.desired_mode != 'legacy':
            raise FenceTransitionVerificationError(
                'all serving revisions omit SYNC_LEDGER_FENCE_MODE; only a legacy bootstrap is permitted'
            )
        return TransitionVerificationResult(
            desired_mode=config.desired_mode,
            bootstrap_legacy=True,
            serving_revisions=serving_revisions,
        )

    if any(mode is None for mode in modes):
        missing_services = ', '.join(
            observation.service for observation in serving_revisions if observation.mode is None
        )
        raise FenceTransitionVerificationError(
            f'SYNC_LEDGER_FENCE_MODE is missing from serving revision(s): {missing_services}'
        )

    configured_modes = {cast(str, mode) for mode in modes}
    if len(configured_modes) != 1:
        observed = ', '.join(f'{item.service}={item.mode}' for item in serving_revisions)
        raise FenceTransitionVerificationError(f'serving revisions have mixed fence modes: {observed}')
    actual_mode = next(iter(configured_modes))
    if actual_mode != config.desired_mode:
        raise FenceTransitionVerificationError(
            f'serving revisions remain in {actual_mode!r}, not requested {config.desired_mode!r}'
        )

    return TransitionVerificationResult(
        desired_mode=config.desired_mode,
        bootstrap_legacy=False,
        serving_revisions=serving_revisions,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--desired-mode', required=True, choices=sorted(FENCE_MODES))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = TransitionVerificationConfig(
        project=args.project,
        region=args.region,
        desired_mode=args.desired_mode,
    )
    try:
        result = verify_transition(config, runner=SubprocessCommandRunner())
    except FenceTransitionVerificationError as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
