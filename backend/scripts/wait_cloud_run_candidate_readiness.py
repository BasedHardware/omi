#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Wait for a Cloud Run candidate and emit bounded, safe readiness diagnostics.

The deploy action deliberately keeps the candidate at zero traffic until this
helper reports ``Ready=True``.  On failure, it reports only Cloud Run control
plane condition metadata and a filtered Cloud Logging URL; it never fetches or
prints container logs, command stderr, environment values, or secret payloads.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence
from urllib.parse import quote


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ''
    stderr: str = ''


class CommandRunner(Protocol):
    def run(self, command: Sequence[str]) -> CommandResult: ...


class SubprocessCommandRunner:
    """Small subprocess seam so unit tests never invoke gcloud."""

    def run(self, command: Sequence[str]) -> CommandResult:
        completed = subprocess.run(list(command), check=False, capture_output=True, text=True)
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True)
class CandidateConfig:
    project: str
    region: str
    service: str
    revision: str


@dataclass(frozen=True)
class ReadinessObservation:
    is_ready: bool
    status: str
    reason: str | None = None
    message: str | None = None
    diagnostic: str | None = None


_SENSITIVE_ASSIGNMENT = re.compile(r'''(?ix)
    (
        \b(?:
            [a-z0-9_]*(?:api_key|token|password|private_key|credential)[a-z0-9_]*
            | authorization
            | api[ _-]key
            | access[ _-]token
            | refresh[ _-]token
        )\b
        \s*(?:=|:)\s*
    )
    (?:(?:bearer\s+)?(?:"[^"]*"|'[^']*'|[^\s,;]+))
    ''')


def build_describe_revision_command(config: CandidateConfig) -> list[str]:
    return [
        'gcloud',
        'run',
        'revisions',
        'describe',
        config.revision,
        f'--project={config.project}',
        f'--region={config.region}',
        '--format=json',
    ]


def observe_candidate_readiness(config: CandidateConfig, *, runner: CommandRunner) -> ReadinessObservation:
    """Read one candidate revision without exposing gcloud output on failures."""

    result = runner.run(build_describe_revision_command(config))
    if result.returncode != 0:
        return ReadinessObservation(
            is_ready=False,
            status='unavailable',
            diagnostic=f'Cloud Run revision describe failed (exit={result.returncode}).',
        )

    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ReadinessObservation(
            is_ready=False,
            status='invalid',
            diagnostic='Cloud Run revision describe returned invalid JSON.',
        )
    if not isinstance(document, Mapping):
        return ReadinessObservation(
            is_ready=False,
            status='invalid',
            diagnostic='Cloud Run revision describe returned an unexpected JSON shape.',
        )

    status = document.get('status')
    if not isinstance(status, Mapping):
        return ReadinessObservation(
            is_ready=False,
            status='invalid',
            diagnostic='Cloud Run revision did not report a status object.',
        )
    conditions = status.get('conditions')
    if not isinstance(conditions, list):
        return ReadinessObservation(
            is_ready=False,
            status='invalid',
            diagnostic='Cloud Run revision status did not report a conditions list.',
        )
    ready = next(
        (condition for condition in conditions if isinstance(condition, Mapping) and condition.get('type') == 'Ready'),
        None,
    )
    if ready is None:
        return ReadinessObservation(
            is_ready=False,
            status='missing',
            diagnostic='Cloud Run revision did not report a Ready condition.',
        )

    ready_status = ready.get('status')
    if not isinstance(ready_status, str) or not ready_status:
        return ReadinessObservation(
            is_ready=False,
            status='invalid',
            diagnostic='Cloud Run Ready condition has an invalid status.',
        )
    reason = ready.get('reason')
    message = ready.get('message')
    return ReadinessObservation(
        is_ready=ready_status == 'True',
        status=ready_status,
        reason=reason if isinstance(reason, str) else None,
        message=message if isinstance(message, str) else None,
    )


def _logging_filter_value(value: str) -> str:
    """Quote a value for the Cloud Logging filter language before URL encoding it."""

    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def build_cloud_logging_url(config: CandidateConfig) -> str:
    """Return a console link filtered to this revision without query injection."""

    logging_query = '\n'.join(
        (
            'resource.type="cloud_run_revision"',
            f'resource.labels.service_name={_logging_filter_value(config.service)}',
            f'resource.labels.revision_name={_logging_filter_value(config.revision)}',
            f'resource.labels.location={_logging_filter_value(config.region)}',
        )
    )
    return f'https://console.cloud.google.com/logs/query;query={quote(logging_query, safe="")}?project={quote(config.project, safe="")}'


def _bounded_metadata(value: str | None, *, fallback: str, redact_sensitive_assignments: bool = False) -> str:
    """Make control-plane metadata single-line, bounded, and inert in Actions logs."""

    if not isinstance(value, str):
        return fallback
    compact = ' '.join(value.split()).replace('::', ': :')
    if redact_sensitive_assignments:
        compact = _SENSITIVE_ASSIGNMENT.sub(r'\1<redacted>', compact)
    if not compact:
        return fallback
    maximum_length = 500
    return compact if len(compact) <= maximum_length else f'{compact[:maximum_length - 1]}…'


def format_failure(config: CandidateConfig, observation: ReadinessObservation) -> str:
    """Format one actionable failure without command output or container logs."""

    lines = (
        'ERROR: Cloud Run candidate did not become Ready=True; production traffic was not changed.',
        f'candidate.project={_bounded_metadata(config.project, fallback="unknown")}',
        f'candidate.region={_bounded_metadata(config.region, fallback="unknown")}',
        f'candidate.service={_bounded_metadata(config.service, fallback="unknown")}',
        f'candidate.revision={_bounded_metadata(config.revision, fallback="unknown")}',
        f'ready.status={_bounded_metadata(observation.status, fallback="unknown")}',
        f'ready.reason={_bounded_metadata(observation.reason, fallback="not reported", redact_sensitive_assignments=True)}',
        f'ready.message={_bounded_metadata(observation.message, fallback="not reported", redact_sensitive_assignments=True)}',
        f'diagnostic={_bounded_metadata(observation.diagnostic, fallback="not reported")}',
        f'logs.url={build_cloud_logging_url(config)}',
    )
    return '\n'.join(lines)


def wait_for_candidate_ready(
    config: CandidateConfig,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    runner: CommandRunner,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> ReadinessObservation:
    """Poll until Ready=True or timeout, returning the final safe observation."""

    deadline = monotonic() + timeout_seconds
    while True:
        observation = observe_candidate_readiness(config, runner=runner)
        if observation.is_ready:
            return observation
        # Cloud Run has completed reconciliation with a failed Ready condition;
        # more polling cannot make this candidate actionable and only delays the
        # condition/message needed to repair it. Unknown remains pollable while
        # provisioning is still in progress.
        if observation.status == 'False':
            return observation
        remaining = deadline - monotonic()
        if remaining <= 0:
            return observation
        sleeper(min(poll_interval_seconds, remaining))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--service', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--timeout-seconds', type=float, default=150.0)
    parser.add_argument('--poll-interval-seconds', type=float, default=5.0)
    args = parser.parse_args(argv)
    if args.timeout_seconds < 0:
        parser.error('--timeout-seconds must be non-negative')
    if args.poll_interval_seconds <= 0:
        parser.error('--poll-interval-seconds must be positive')
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = CandidateConfig(
        project=args.project,
        region=args.region,
        service=args.service,
        revision=args.revision,
    )
    observation = wait_for_candidate_ready(
        config,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        runner=SubprocessCommandRunner(),
    )
    if observation.is_ready:
        print(
            'Cloud Run candidate is Ready=True: '
            f'service={_bounded_metadata(config.service, fallback="unknown")} '
            f'revision={_bounded_metadata(config.revision, fallback="unknown")}'
        )
        return 0
    print(format_failure(config, observation), file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
