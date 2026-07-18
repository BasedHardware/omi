#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Resolve one Cloud Run tagged URL only when it still targets one revision.

Candidate probes use Cloud Run tags to reach a no-traffic revision.  This
read-only helper refuses to follow a tag that is absent, duplicated, stale, or
not an HTTPS endpoint, so a probe cannot silently exercise another revision.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, cast
from urllib.parse import urlsplit


class TaggedUrlResolutionError(RuntimeError):
    """Cloud Run status cannot prove the requested tag/revision URL binding."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ''
    stderr: str = ''


class CommandRunner(Protocol):
    def run(self, command: Sequence[str], *, check: bool = True) -> CommandResult: ...


class SubprocessCommandRunner:
    """Small subprocess seam so unit tests never invoke gcloud."""

    def run(self, command: Sequence[str], *, check: bool = True) -> CommandResult:
        completed = subprocess.run(list(command), check=False, capture_output=True, text=True)
        result = CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and result.returncode != 0:
            raise TaggedUrlResolutionError(
                f'Cloud Run query failed (exit={result.returncode}): {" ".join(command[:4])}'
            )
        return result


@dataclass(frozen=True)
class TaggedUrlConfig:
    project: str
    region: str
    service: str
    revision: str
    tag: str


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


def _json_object(result: CommandResult, *, resource: str) -> dict[str, Any]:
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise TaggedUrlResolutionError(f'{resource} did not return JSON') from error
    if not isinstance(document, dict):
        raise TaggedUrlResolutionError(f'{resource} returned an unexpected JSON shape')
    return cast(dict[str, Any], document)


def _is_https_url(value: Any) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    parsed = urlsplit(value)
    return parsed.scheme == 'https' and bool(parsed.netloc)


def resolve_tagged_url(service_document: Mapping[str, Any], *, revision: str, tag: str) -> str:
    """Return the one HTTPS URL whose status traffic target proves the binding."""

    status = service_document.get('status')
    if not isinstance(status, Mapping):
        raise TaggedUrlResolutionError('Cloud Run service did not report a status')
    traffic = status.get('traffic')
    if not isinstance(traffic, list):
        raise TaggedUrlResolutionError('Cloud Run service did not report status traffic')

    tag_targets = [target for target in traffic if isinstance(target, Mapping) and target.get('tag') == tag]
    if not tag_targets:
        raise TaggedUrlResolutionError(f'Cloud Run tag {tag!r} is absent from service status traffic')
    if len(tag_targets) != 1:
        raise TaggedUrlResolutionError(f'Cloud Run tag {tag!r} appears more than once in service status traffic')

    target = tag_targets[0]
    target_revision = target.get('revisionName')
    if target_revision != revision:
        raise TaggedUrlResolutionError(
            f'Cloud Run tag {tag!r} targets revision {target_revision!r}, not requested {revision!r}'
        )
    url = target.get('url')
    if not _is_https_url(url):
        raise TaggedUrlResolutionError(f'Cloud Run tag {tag!r} has no valid HTTPS URL')
    return cast(str, url)


def resolve_live_tagged_url(config: TaggedUrlConfig, *, runner: CommandRunner) -> str:
    result = runner.run(
        build_describe_service_command(project=config.project, region=config.region, service=config.service)
    )
    service_document = _json_object(result, resource=f'Cloud Run service {config.service}')
    return resolve_tagged_url(service_document, revision=config.revision, tag=config.tag)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--service', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--tag', required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = TaggedUrlConfig(
        project=args.project,
        region=args.region,
        service=args.service,
        revision=args.revision,
        tag=args.tag,
    )
    try:
        url = resolve_live_tagged_url(config, runner=SubprocessCommandRunner())
    except TaggedUrlResolutionError as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    print(url)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
