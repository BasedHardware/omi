#!/usr/bin/env python3
"""Render one staging Cloud Run service's deploy inputs from the composed staging manifest.

Used by deploy.sh. Writes the full env as a gcloud ``--env-vars-file`` (YAML map) and the gcloud
flags (identity, Secret Manager mount references, network, scale) to ``--flags-file``, one per
line. Nothing is printed: values reach gcloud through the files, never stdout or logs. Mount
references are built only from validated ``staging-*`` Secret Manager names, never payloads. The env is checked by the staging fence
again here, with the release identity added, so the exact deployed env is fenced.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))

from scripts.render_backend_runtime_env import _render_env_entries  # noqa: E402
from utils.staging_fence import staging_violations  # noqa: E402

_ENV_NAME = re.compile(r'[A-Z][A-Z0-9_]*')
_MOUNT_NAME = re.compile(r'staging-[a-z0-9-]+')
_MOUNT_VERSION = re.compile(r'latest|[0-9]+')


def mount_refs(config: dict) -> list[str]:
    """``ENV=staging-name:version`` per Secret Manager mount: names and versions only, all validated."""
    refs: list[str] = []
    for env_name, binding in (config.get('secrets') or {}).items():
        ref = str((binding or {}).get('secret', ''))
        version = str((binding or {}).get('version', 'latest'))
        if not (_ENV_NAME.fullmatch(env_name) and _MOUNT_NAME.fullmatch(ref) and _MOUNT_VERSION.fullmatch(version)):
            raise SystemExit(
                f'invalid staging mount reference for {env_name if _ENV_NAME.fullmatch(env_name) else "<name>"}'
            )
        refs.append(f'{env_name}={ref}:{version}')
    return refs


def render(composed: dict, service: str, *, release_sha: str, release_tree: str) -> tuple[dict[str, str], list[str]]:
    services = composed['cloud_run']['services']
    if service not in services:
        raise SystemExit(f'unknown staging service {service!r}; have {sorted(services)}')
    config = services[service]
    env = {entry['name']: entry['value'] for entry in _render_env_entries(config.get('env', {}))}
    env['OMI_BACKEND_RELEASE_SHA'] = release_sha
    env['OMI_RELEASE_TREE'] = release_tree
    refs = mount_refs(config)
    for ref in refs:
        env.pop(ref.split('=', 1)[0], None)
    violations = staging_violations(env)
    if violations:
        detail = ', '.join(f'{reason}:{name}' for reason, name in violations)
        raise SystemExit(f'staging fence refuses {service}: {detail}')
    flags = [f'--service-account={config["service_account"]}']
    if refs:
        flags.append('--set-secrets=' + ','.join(refs))
    for name, value in {**composed['cloud_run']['network']['flags'], **config.get('flags', {})}.items():
        flags.append(f'{name}={value}')
    return env, flags


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or '').split('\n\n')[0])
    parser.add_argument('--composed', type=Path, required=True)
    parser.add_argument('--service', required=True, help='prod service key, e.g. backend-sync')
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument(
        '--flags-file', type=Path, help='where the gcloud flags are written (required for --field flags)'
    )
    parser.add_argument('--release-sha', required=True)
    parser.add_argument('--release-tree', required=True)
    parser.add_argument('--field', choices=('flags', 'deploy_name', 'url'), default='flags')
    args = parser.parse_args()
    composed = yaml.safe_load(args.composed.read_text(encoding='utf-8'))
    if args.field != 'flags':
        print(composed['cloud_run']['services'][args.service][args.field])
        return 0
    if args.flags_file is None:
        parser.error('--flags-file is required to render flags')
    env, flags = render(composed, args.service, release_sha=args.release_sha, release_tree=args.release_tree)
    for path, text in (
        (args.env_file, yaml.safe_dump(env, sort_keys=True)),
        (args.flags_file, '\n'.join(flags) + '\n'),
    ):
        path.write_text(text, encoding='utf-8')
        path.chmod(0o600)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
