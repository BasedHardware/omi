#!/usr/bin/env python3
"""Render one staging Cloud Run service's deploy inputs from the composed staging manifest.

Used by deploy.sh. Writes the full env as a gcloud ``--env-vars-file`` (YAML map) and prints one
line per gcloud flag (``--set-secrets=...``, network, scale, identity) on stdout. Values reach
gcloud through the file, never the command line or logs. The env is checked by the staging fence
again here, with the release identity added, so the exact deployed env is fenced.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))

from scripts.render_backend_runtime_env import (  # noqa: E402
    _render_env_entries,
    _render_secret_entries,
)
from utils.staging_fence import staging_violations  # noqa: E402


def render(composed: dict, service: str, *, release_sha: str, release_tree: str) -> tuple[dict[str, str], list[str]]:
    services = composed['cloud_run']['services']
    if service not in services:
        raise SystemExit(f'unknown staging service {service!r}; have {sorted(services)}')
    config = services[service]
    env = {entry['name']: entry['value'] for entry in _render_env_entries(config.get('env', {}))}
    env['OMI_BACKEND_RELEASE_SHA'] = release_sha
    env['OMI_RELEASE_TREE'] = release_tree
    secrets = _render_secret_entries(config.get('secrets', {}))
    for entry in secrets:
        env.pop(entry['name'], None)
    violations = staging_violations(env)
    if violations:
        detail = ', '.join(f'{reason}:{name}' for reason, name in violations)
        raise SystemExit(f'staging fence refuses {service}: {detail}')
    flags = [f'--service-account={config["service_account"]}']
    if secrets:
        flags.append(
            '--set-secrets='
            + ','.join(
                f'{entry["name"]}={entry["valueFrom"]["secretKeyRef"]["name"]}:{entry["valueFrom"]["secretKeyRef"]["key"]}'
                for entry in secrets
            )
        )
    for name, value in {**composed['cloud_run']['network']['flags'], **config.get('flags', {})}.items():
        flags.append(f'{name}={value}')
    return env, flags


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or '').split('\n\n')[0])
    parser.add_argument('--composed', type=Path, required=True)
    parser.add_argument('--service', required=True, help='prod service key, e.g. backend-sync')
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--release-sha', required=True)
    parser.add_argument('--release-tree', required=True)
    parser.add_argument('--field', choices=('flags', 'deploy_name', 'url'), default='flags')
    args = parser.parse_args()
    composed = yaml.safe_load(args.composed.read_text(encoding='utf-8'))
    if args.field != 'flags':
        print(composed['cloud_run']['services'][args.service][args.field])
        return 0
    env, flags = render(composed, args.service, release_sha=args.release_sha, release_tree=args.release_tree)
    args.env_file.write_text(yaml.safe_dump(env, sort_keys=True), encoding='utf-8')
    args.env_file.chmod(0o600)
    print('\n'.join(flags))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
