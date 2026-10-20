#!/usr/bin/env python3
"""Provision checked-in Grafana dashboards via the HTTP API.

Called by .github/workflows/grafana_dashboard_provisioning.yml after a merge
touches backend/charts/monitoring/dashboards/. For every dashboard JSON in
the directory:

1. Parse and validate (must be an object with a uid).
2. Read existing folder metadata, then POST to /api/dashboards/db with
   overwrite=true, updating the served board without moving folders.
   New dashboards retain the API default (General); a source folderUid on a
   new dashboard is rejected rather than silently ignored.
3. Persist every pre-write dashboard/meta snapshot in an exclusive mode-0600 backup.
4. Verify desired content and the preserved folder after each POST; stop on failure.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(request):
    # Never forward Authorization to a redirected host or plaintext endpoint.
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=30)


def _post_dashboard(
    base: str, token: str, dashboard: dict, source_sha: str, folder_uid: str | None = None
) -> tuple[int, dict]:
    payload = {
        "dashboard": dashboard,
        "overwrite": True,
        "message": f"provisioned from main {source_sha}",
    }
    if folder_uid is not None:
        payload["folderUid"] = folder_uid
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        f"{base}/api/dashboards/db",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with _open(request) as response:
        return response.status, json.load(response)


def _get_dashboard(base: str, token: str, uid: str) -> dict:
    request = urllib.request.Request(
        f"{base}/api/dashboards/uid/{urllib.parse.quote(uid, safe='')}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with _open(request) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("invalid dashboard response")
    return payload


def desired_matches(desired, served, path=()):
    """Require every desired field; permit additional server defaults.

    Root id/version identify Grafana's saved revision. Panel pluginVersion is
    server/plugin metadata and can advance independently of panel/query content.
    Array length/order and all other desired fields remain exact.
    """
    if isinstance(desired, dict):
        if not isinstance(served, dict):
            return False
        for key, value in desired.items():
            if (not path and key in ('id', 'version')) or (key == 'pluginVersion' and 'panels' in path):
                continue
            if key not in served or not desired_matches(value, served[key], path + (key,)):
                return False
        return True
    if isinstance(desired, list):
        return (
            isinstance(served, list)
            and len(desired) == len(served)
            and all(
                desired_matches(left, right, path + (index,))
                for index, (left, right) in enumerate(zip(desired, served))
            )
        )
    if isinstance(desired, (int, float)) and not isinstance(desired, bool):
        return isinstance(served, (int, float)) and not isinstance(served, bool) and desired == served
    return type(desired) is type(served) and desired == served


def persist_backup(path, existing, new_uids, source_sha):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(
            {'source_sha': source_sha, 'dashboards': existing, 'created_uids': sorted(new_uids)}, handle, indent=2
        )
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dashboards-dir', type=Path, required=True)
    parser.add_argument('--grafana-url', required=True)
    parser.add_argument('--token-env', default='MONITOR_GRAFANA_TOKEN')
    parser.add_argument('--source-sha', default='main')
    parser.add_argument(
        '--backup-file',
        type=Path,
        required=True,
        help='New exclusive rollback snapshot; persisted before any dashboard POST',
    )
    parser.add_argument('--allowlist', default='', help='Comma-separated filenames; empty = all dashboards')
    args = parser.parse_args()
    token = os.environ.get(args.token_env) or ''
    if not token:
        print(f'FAIL: {args.token_env} is empty', file=sys.stderr)
        return 1
    base = args.grafana_url.rstrip('/')
    if base not in ('https://monitor.omi.me', 'https://monitor.omiapi.com'):
        print('FAIL: expected the production or development HTTPS Grafana endpoint', file=sys.stderr)
        return 1
    files = sorted(args.dashboards_dir.rglob('*.json'))
    if args.allowlist:
        allowed = {name.strip() for name in args.allowlist.split(',') if name.strip()}
        files = [path for path in files if path.name in allowed]
        if {path.name for path in files} != allowed:
            print('FAIL: dashboard allowlist contains absent filenames', file=sys.stderr)
            return 1
    if not files:
        print('FAIL: no selected dashboard JSON', file=sys.stderr)
        return 1
    planned, snapshots, new_uids, seen = [], {}, [], set()
    try:
        # Validate every source before any live read or mutation.
        sources = []
        for path in files:
            dashboard = json.loads(path.read_text())
            if not isinstance(dashboard, dict):
                raise ValueError('dashboard source must be an object')
            uid = dashboard.get('uid')
            if not isinstance(uid, str) or not uid or uid in seen:
                raise ValueError('dashboard source has missing or duplicate UID')
            seen.add(uid)
            sources.append((path, uid, dashboard))
        # Complete all reads and metadata checks before persisting the write plan.
        for path, uid, dashboard in sources:
            try:
                existing = _get_dashboard(base, token, uid)
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                existing = None
            if existing is None:
                if dashboard.get('folderUid'):
                    raise ValueError('new dashboard folder requires explicit provisioning')
                folder_uid = None
                new_uids.append(uid)
            else:
                if not isinstance(existing.get('dashboard'), dict) or existing['dashboard'].get('uid') != uid:
                    raise ValueError('invalid existing dashboard identity')
                folder_uid = existing['meta']['folderUid']
                if not isinstance(folder_uid, str):
                    raise ValueError('invalid existing folder metadata')
                snapshots[uid] = existing
            planned.append((path, uid, dashboard, folder_uid))
        persist_backup(args.backup_file, snapshots, new_uids, args.source_sha)
        # Abort immediately on a failed POST/readback; later dashboards remain untouched.
        for path, uid, dashboard, folder_uid in planned:
            _, body = _post_dashboard(base, token, dashboard, args.source_sha, folder_uid)
            if not isinstance(body, dict) or body.get('status') != 'success':
                raise ValueError('dashboard POST did not return success')
            post_version = body.get('version')
            if type(post_version) is not int or post_version < 1:
                raise ValueError('dashboard POST did not return a valid version')
            deadline = time.monotonic() + 20
            matched = False
            while time.monotonic() < deadline:
                try:
                    served = _get_dashboard(base, token, uid)
                except urllib.error.HTTPError as exc:
                    if exc.code == 404 and time.monotonic() < deadline - 5:
                        time.sleep(1.5)
                        continue
                    raise
                current = served.get('dashboard')
                if not isinstance(current, dict):
                    raise ValueError('invalid read-back dashboard')
                served_version = current.get('version')
                metadata = served.get('meta')
                if not isinstance(metadata, dict):
                    raise ValueError('invalid read-back folder metadata')
                # A newer concurrent revision is accepted only if desired fields and
                # the retained folder still match. Missing folder metadata is unsafe.
                if type(served_version) is int and served_version >= post_version:
                    if not desired_matches(dashboard, current) or metadata.get('folderUid') != (folder_uid or ''):
                        raise ValueError('dashboard read-back content or folder differs')
                    matched = True
                    break
                time.sleep(1.5)
            if not matched:
                raise ValueError('dashboard read-back did not reach the POST version')
            print(f'OK {path}: uid={uid} version={served_version}')
    except urllib.error.HTTPError as exc:
        print(f'FAIL: dashboard provisioning failed HTTP {exc.code}', file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print('FAIL: dashboard source, backup, transport or read-back validation failed', file=sys.stderr)
        return 1
    print(f'Provisioned {len(planned)} dashboard(s) to {base}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
