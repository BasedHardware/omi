#!/usr/bin/env python3
"""Enforce the backend route-policy missing-entry baseline against a base ref."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
BASELINE_PATH = 'backend/route_policy_legacy_missing_routes.txt'
GIT_LAYOUT_PARENT_LIMIT = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--base-ref',
        help='Git ref whose legacy missing-route baseline is the comparison boundary.',
    )
    return parser.parse_args()


def find_git_bash(git_exec_path: Path) -> Path:
    for parent in tuple(git_exec_path.parents)[:GIT_LAYOUT_PARENT_LIMIT]:
        for relative_path in ('bin/bash.exe', 'usr/bin/bash.exe'):
            candidate = parent / relative_path
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(f'Git Bash was not found above {git_exec_path}')


def bash_command(
    *args: str | Path,
    platform_name: str | None = None,
    git_exec_path: Path | None = None,
) -> list[str]:
    if (platform_name or os.name) == 'nt':
        if git_exec_path is None:
            git_environment = os.environ.copy()
            git_environment.pop('GIT_EXEC_PATH', None)
            git_exec_path = Path(
                subprocess.check_output(
                    ['git', '--exec-path'],
                    cwd=ROOT,
                    env=git_environment,
                    text=True,
                ).strip()
            )
        executable = str(find_git_bash(git_exec_path))
    else:
        executable = 'bash'
    return [executable, *(str(arg) for arg in args)]


def base_baseline(ref: str, destination: Path) -> Path:
    result = subprocess.run(
        ['git', 'show', f'{ref}:{BASELINE_PATH}'],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = result.stderr.decode(errors='replace').strip()
        raise RuntimeError(f'could not load route-policy baseline from {ref}: {detail}')
    destination.write_bytes(result.stdout)
    return destination


def run_inventory(baseline: Path) -> int:
    command = bash_command(
        'scripts/openapi_runner.sh',
        'scripts/route_policy_inventory.py',
        '--manifest',
        'route_policy_manifest.yaml',
        '--enforce-missing-baseline',
        '--base-missing-baseline',
        str(baseline),
    )
    return subprocess.run(command, cwd=BACKEND, check=False).returncode


def main() -> int:
    args = parse_args()
    if not args.base_ref:
        return run_inventory(BACKEND / 'route_policy_legacy_missing_routes.txt')
    with tempfile.TemporaryDirectory(prefix='omi-route-policy-') as temp_dir:
        try:
            baseline = base_baseline(args.base_ref, Path(temp_dir) / 'base-missing-routes.txt')
        except RuntimeError as exc:
            print(f'FAIL: {exc}')
            return 2
        return run_inventory(baseline)


if __name__ == '__main__':
    raise SystemExit(main())
