"""Fail-closed service scope for the manual backend deployment controls.

Blank preserves the full stack default. Explicit selectors are accepted only
for manual Cloud Run deploys; outputs contain allowlisted tokens, never input
shell fragments. This module deliberately has no cloud dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CLOUD_RUN_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


def parse_services(raw: str) -> tuple[str, ...]:
    if raw == '':
        return CLOUD_RUN_SERVICES
    parts = raw.split(',')
    if any(part not in CLOUD_RUN_SERVICES for part in parts):
        raise ValueError(
            'services must be a comma list of exact backend Cloud Run names (no whitespace or empty entries)'
        )
    if len(set(parts)) != len(parts):
        raise ValueError('services must not contain duplicates')
    return tuple(service for service in CLOUD_RUN_SERVICES if service in parts)


def validate_scope(
    raw: str, *, mode: str, profile: str, targets: str, gateway: str, service_images: str = ''
) -> tuple[str, ...]:
    services = parse_services(raw)
    if mode not in ('deploy', 'build-only', 'repair-traffic-only'):
        raise ValueError('unsupported workflow mode')
    if profile not in ('manual', 'auto-dev'):
        raise ValueError('unsupported deploy profile')
    if raw and (mode != 'deploy' or profile != 'manual' or targets != 'cloud-run-only' or gateway != 'false'):
        raise ValueError(
            'services requires mode=deploy, profile=manual, deploy_targets=cloud-run-only, deploy_gateway=false'
        )
    if service_images and (mode != 'deploy' or profile != 'manual'):
        raise ValueError('service_images requires a manual deploy')
    if service_images and not service_images.strip(' \t\r\n,'):
        raise ValueError('service_images must contain service=image pairs or be exactly blank')
    if raw and service_images:
        names = {item.partition('=')[0] for item in re.split(r'[\s,]+', service_images) if item}
        outside = names - set(services)
        if outside:
            raise ValueError(f'service_images names unselected services: {sorted(outside)}')
    return services


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--services', default='')
    parser.add_argument('--mode', default='deploy')
    parser.add_argument('--profile', default='manual')
    parser.add_argument('--targets', default='cloud-run-only')
    parser.add_argument('--gateway', default='false')
    parser.add_argument('--service-images', default='')
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--github-env', type=Path)
    args = parser.parse_args()
    try:
        services = validate_scope(
            args.services,
            mode=args.mode,
            profile=args.profile,
            targets=args.targets,
            gateway=args.gateway,
            service_images=args.service_images,
        )
    except ValueError as error:
        parser.error(str(error))
    outputs = {
        'services': json.dumps(services, separators=(',', ':')),
        'service_args': ' '.join(f'--service {service}' for service in services),
        'migration_args': ' '.join(f'--migrate-legacy-public-binding {service}' for service in services),
    }
    if args.github_output:
        with args.github_output.open('a') as output:
            output.write(''.join(f'{key}={value}\n' for key, value in outputs.items()))
    if args.github_env:
        with args.github_env.open('a') as output:
            output.write(f'BACKEND_DEPLOY_SERVICES={" ".join(services)}\n')


if __name__ == '__main__':
    main()
