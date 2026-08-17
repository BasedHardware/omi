#!/usr/bin/env python3
"""Decide whether a source-SHA Agent VM release already exists and must be reused.

Protected prod workflow 32012710785 rebuilt the same source SHA with a new
image digest, then ``gcloud storage cp --no-clobber`` kept the prior
``startup.sh`` and ``cmp`` failed. The SHA-keyed object is the immutable
release; reruns must adopt its digest instead of publishing a competing one.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

IMAGE_DIGEST = re.compile(r'^.+@sha256:[0-9a-f]{64}$')
SOURCE_SHA = re.compile(r'^[0-9a-f]{40}$')
STARTUP_DIGEST = re.compile(r'^image_digest="([^"]+@sha256:[0-9a-f]{64})"$', re.MULTILINE)
INCIDENT = (
    'SCA-323 / workflow 32012710785: a same-SHA Agent VM rebuild produced a new '
    'digest, --no-clobber kept the existing startup.sh, and cmp failed.'
)

GcloudRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class ResolveError(Exception):
    """A deterministic SHA-keyed release resolution failure."""


@dataclass(frozen=True)
class ShaReleasePlan:
    reuse: bool
    image_digest: str | None = None
    boot_image: str | None = None
    startup_present: bool = False
    manifest_present: bool = False
    reason: str = ''

    def as_dict(self) -> dict[str, object]:
        return {
            'reuse': self.reuse,
            'image_digest': self.image_digest,
            'boot_image': self.boot_image,
            'startup_present': self.startup_present,
            'manifest_present': self.manifest_present,
            'reason': self.reason,
        }


def _run_gcloud(args: Sequence[str], *, runner: GcloudRunner | None = None) -> subprocess.CompletedProcess[str]:
    command = ['gcloud', *args]
    if runner is not None:
        return runner(command)
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _fail(message: str) -> None:
    raise ResolveError(f'{message} {INCIDENT}')


def object_exists(uri: str, *, runner: GcloudRunner | None = None) -> bool:
    result = _run_gcloud(['storage', 'objects', 'describe', uri], runner=runner)
    return result.returncode == 0


def download_text(uri: str, destination: Path, *, runner: GcloudRunner | None = None) -> str:
    result = _run_gcloud(['storage', 'cp', uri, str(destination)], runner=runner)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip() or f'exit {result.returncode}'
        _fail(f'could not read immutable Agent VM object {uri} ({detail}).')
    return destination.read_text(encoding='utf-8')


def digest_from_startup(startup: str) -> str:
    match = STARTUP_DIGEST.search(startup)
    if match is None or not IMAGE_DIGEST.fullmatch(match.group(1)):
        _fail(
            'existing SHA-keyed startup.sh does not embed an immutable image_digest; refusing to rebuild a competing digest.'
        )
    return match.group(1)


def plan_from_existing(
    *,
    startup: str | None,
    manifest_text: str | None,
    expected_source_sha: str,
) -> ShaReleasePlan:
    if not SOURCE_SHA.fullmatch(expected_source_sha):
        _fail(f'source SHA {expected_source_sha!r} is not a lowercase 40-character SHA.')
    if manifest_text is None and startup is None:
        return ShaReleasePlan(reuse=False, reason='no SHA-keyed Agent VM artifacts exist yet')
    if manifest_text is None:
        digest = digest_from_startup(startup or '')
        return ShaReleasePlan(
            reuse=True,
            image_digest=digest,
            boot_image=None,
            startup_present=True,
            manifest_present=False,
            reason='existing SHA-keyed startup.sh; reuse its digest and do not rebuild a competing image',
        )
    if startup is None:
        _fail('SHA-keyed manifest.json exists without startup.sh; the release pair is inconsistent.')
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        _fail(f'SHA-keyed manifest.json is not JSON: {exc}.')
    if not isinstance(manifest, Mapping):
        _fail('SHA-keyed manifest.json must be an object.')
    source_sha = str(manifest.get('sourceSha') or '')
    if source_sha != expected_source_sha:
        _fail(f'SHA-keyed manifest sourceSha {source_sha!r} does not match {expected_source_sha!r}.')
    digest = str(manifest.get('imageDigest') or '')
    if not IMAGE_DIGEST.fullmatch(digest):
        _fail('SHA-keyed manifest.json is missing an immutable imageDigest.')
    startup_digest = digest_from_startup(startup)
    if startup_digest != digest:
        _fail(
            f'SHA-keyed startup.sh digest {startup_digest} does not match manifest imageDigest {digest}; '
            'refusing to invent a third digest.'
        )
    boot_image = str(manifest.get('bootImage') or '').strip() or None
    return ShaReleasePlan(
        reuse=True,
        image_digest=digest,
        boot_image=boot_image,
        startup_present=True,
        manifest_present=True,
        reason='existing SHA-keyed manifest and startup.sh; reuse that digest',
    )


def resolve_sha_release(
    *,
    startup_uri: str,
    manifest_uri: str,
    expected_source_sha: str,
    workdir: Path,
    runner: GcloudRunner | None = None,
) -> ShaReleasePlan:
    startup_present = object_exists(startup_uri, runner=runner)
    manifest_present = object_exists(manifest_uri, runner=runner)
    startup = download_text(startup_uri, workdir / 'startup.sh', runner=runner) if startup_present else None
    manifest_text = download_text(manifest_uri, workdir / 'manifest.json', runner=runner) if manifest_present else None
    return plan_from_existing(
        startup=startup,
        manifest_text=manifest_text,
        expected_source_sha=expected_source_sha,
    )


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument('--startup-uri', required=True)
    command.add_argument('--manifest-uri', required=True)
    command.add_argument('--expected-source-sha', required=True)
    command.add_argument('--workdir', type=Path, required=True)
    command.add_argument('--output', type=Path)
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        args.workdir.mkdir(parents=True, exist_ok=True)
        plan = resolve_sha_release(
            startup_uri=args.startup_uri,
            manifest_uri=args.manifest_uri,
            expected_source_sha=args.expected_source_sha,
            workdir=args.workdir,
        )
    except ResolveError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    payload = json.dumps(plan.as_dict(), indent=2, sort_keys=True) + '\n'
    if args.output is not None:
        args.output.write_text(payload, encoding='utf-8')
    sys.stdout.write(payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
