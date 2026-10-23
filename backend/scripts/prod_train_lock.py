#!/usr/bin/env python3
"""Read the B5 `prod-train` lock: is any prod deploy or config-train running or queued?

Every prod deploy writer (backend train, listen Helm, LLM gateway, pusher, GPU
workers, config-train) takes the GitHub Actions concurrency group `prod-train`.
GitHub exposes no API for a concurrency group, so the lock is read from its
holders: active runs of those workflows whose environment is prod. A run's
environment comes from the deployment GitHub records for its `environment:`
job, or from its pending approval. A run whose environment is not known yet is
reported as a holder (fail closed), because the group is taken when the run
starts, before any environment job.

    prod_train_lock.py status [--json]     exit 0 free, 10 held, 1 unknown

The ramp controller (contract (g), lane 6) must refuse while `held` is true or
the read fails. Dispatchers should also check before dispatching: GitHub keeps
only one pending run per group, so a second queued prod deploy silently
replaces the first.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

REPO = 'BasedHardware/omi'
PROD_TRAIN_WORKFLOWS = frozenset(
    {
        '.github/workflows/config_train.yml',
        '.github/workflows/gcp_backend.yml',
        '.github/workflows/gcp_backend_listen_helm.yml',
        '.github/workflows/gcp_backend_pusher.yml',
        '.github/workflows/gcp_diarizer.yml',
        '.github/workflows/gcp_llm_gateway.yml',
        '.github/workflows/gcp_parakeet.yml',
    }
)
ACTIVE_RUN_STATES = ('in_progress', 'queued', 'waiting', 'requested', 'pending')
ACTIVE_DEPLOYMENT_STATES = frozenset({'queued', 'in_progress', 'pending', 'waiting'})
RUN_URL = re.compile(r'/actions/runs/(\d+)')
EXIT_FREE, EXIT_UNKNOWN, EXIT_HELD = 0, 1, 10
RUN_PAGE_SIZE, MAX_RUN_PAGES = 100, 10

Api = Callable[[str, Mapping[str, Any]], Any]


class LockReadError(RuntimeError):
    pass


@dataclass(frozen=True)
class Holder:
    run_id: int
    workflow: str
    status: str
    environment: str  # prod | unknown
    actor: str
    created_at: str
    url: str


@dataclass
class LockStatus:
    held: bool
    holders: list[Holder] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {'held': self.held, 'holders': [asdict(holder) for holder in self.holders]}


def gh_api(path: str, params: Mapping[str, Any]) -> Any:
    query = urllib.parse.urlencode(params)
    url = f'{path}?{query}' if query else path
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:
        request = urllib.request.Request(
            f'https://api.github.com{url}',
            headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed host
                return json.load(response)
        except OSError as exc:
            raise LockReadError(f'GitHub API {path}: {exc}') from exc
    proc = subprocess.run(['gh', 'api', url], capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise LockReadError(f'gh api {path}: {proc.stderr.strip()[:200]}')
    return json.loads(proc.stdout or 'null')


def _run_id(url: Any) -> int | None:
    match = RUN_URL.search(str(url or ''))
    return int(match.group(1)) if match else None


def _environments_by_run(api: Api, since: str) -> dict[int, set[str]]:
    """Map run id -> environments of the deployments it created since `since` (ISO 8601)."""

    out: dict[int, set[str]] = {}
    for environment in ('prod', 'development'):
        deployments = api(f'/repos/{REPO}/deployments', {'environment': environment, 'per_page': 30}) or []
        for deployment in deployments:
            if str(deployment.get('created_at', '')) < since:
                continue
            statuses = api(f'/repos/{REPO}/deployments/{deployment["id"]}/statuses', {'per_page': 1}) or []
            for status in statuses[:1]:
                run_id = _run_id(status.get('log_url')) or _run_id(status.get('target_url'))
                if run_id is not None:
                    out.setdefault(run_id, set()).add(environment)
    return out


def _registered_workflows(api: Api) -> dict[str, int]:
    """path -> workflow id for workflows GitHub knows. A prod-train workflow GitHub does not list
    (not yet on the default branch) cannot be dispatched, so it has no runs to hold the lock."""

    out: dict[str, int] = {}
    total = 0
    for page in range(1, MAX_RUN_PAGES + 1):
        payload = api(f'/repos/{REPO}/actions/workflows', {'per_page': RUN_PAGE_SIZE, 'page': page}) or {}
        batch = payload.get('workflows') or []
        total = int(payload.get('total_count', len(out) + len(batch)))
        out.update({str(item['path']): int(item['id']) for item in batch})
        if len(batch) < RUN_PAGE_SIZE or len(out) >= total:
            break
    if len(out) < total:
        raise LockReadError(f'workflows: read {len(out)} of {total}')
    return out


def _active_runs(api: Api, workflow_id: int, workflow: str, state: str) -> list[Mapping[str, Any]]:
    """Every run of one prod-train workflow in one state, all pages.

    Read per workflow, not repo-wide: a repo-wide page of 100 active runs is newest-first, so
    under a CI backlog a long prod train ages off it and the lock would read FREE (M1 L07-1).
    A listing that ends short of its own total_count fails the read (exit UNKNOWN).
    """

    path = f'/repos/{REPO}/actions/workflows/{workflow_id}/runs'
    out: list[Mapping[str, Any]] = []
    total = 0
    for page in range(1, MAX_RUN_PAGES + 1):
        payload = api(path, {'status': state, 'per_page': RUN_PAGE_SIZE, 'page': page}) or {}
        batch = payload.get('workflow_runs') or []
        total = int(payload.get('total_count', len(out) + len(batch)))
        out.extend(batch)
        if len(batch) < RUN_PAGE_SIZE or len(out) >= total:
            break
    if len(out) < total:
        raise LockReadError(f'{workflow} {state}: read {len(out)} of {total} runs')
    return out


def read_status(api: Api = gh_api) -> LockStatus:
    """Return the prod-train lock state. Raises LockReadError when GitHub cannot be read."""

    runs: dict[int, Mapping[str, Any]] = {}
    registered = _registered_workflows(api)
    for workflow in sorted(PROD_TRAIN_WORKFLOWS & registered.keys()):
        for state in ACTIVE_RUN_STATES:
            for run in _active_runs(api, registered[workflow], workflow, state):
                # Prod is reachable only through workflow_dispatch (environment input); push and
                # workflow_run entry points always target development.
                if run.get('event') == 'workflow_dispatch':
                    runs[int(run['id'])] = run
    if not runs:
        return LockStatus(held=False)
    since = min(str(run.get('created_at', '')) for run in runs.values())
    environments = _environments_by_run(api, since)
    holders: list[Holder] = []
    for run_id, run in sorted(runs.items()):
        envs = set(environments.get(run_id, set()))
        if run.get('status') == 'waiting':
            pending = api(f'/repos/{REPO}/actions/runs/{run_id}/pending_deployments', {}) or []
            envs |= {str((item.get('environment') or {}).get('name')) for item in pending}
        if 'prod' in envs:
            environment = 'prod'
        elif envs:
            continue  # development only: never holds prod-train
        else:
            environment = 'unknown'
        holders.append(
            Holder(
                run_id=run_id,
                workflow=str(run.get('path', '')).rsplit('/', 1)[-1],
                status=str(run.get('status')),
                environment=environment,
                actor=str((run.get('triggering_actor') or run.get('actor') or {}).get('login', '')),
                created_at=str(run.get('created_at', '')),
                url=str(run.get('html_url', '')),
            )
        )
    return LockStatus(held=bool(holders), holders=holders)


def main(argv: Sequence[str] | None = None, *, api: Api = gh_api) -> int:
    parser = argparse.ArgumentParser(description='Read the B5 prod-train lock.')
    sub = parser.add_subparsers(dest='command', required=True)
    status = sub.add_parser('status')
    status.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = read_status(api)
    except (LockReadError, KeyError, TypeError, ValueError) as exc:
        print(f'UNKNOWN: {exc}', file=sys.stderr)
        return EXIT_UNKNOWN
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    elif result.held:
        for holder in result.holders:
            print(
                f'HELD by {holder.workflow} run {holder.run_id} ({holder.status}, env={holder.environment}, actor={holder.actor})'
            )
    else:
        print('FREE')
    return EXIT_HELD if result.held else EXIT_FREE


if __name__ == '__main__':
    raise SystemExit(main())
