#!/usr/bin/env python3
"""Exercise the deployed What Matters Now route without logging user data or credentials."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from config.what_matters_now_smoke_fixture import WHAT_MATTERS_NOW_SMOKE_UID  # noqa: E402


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    admin_key: str
    timeout_seconds: float
    cloud_run_identity_token: str = ''


def _validate_base_url(value: str) -> str:
    base_url = value.rstrip('/')
    parsed = urlparse(base_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('base_url must be an absolute HTTP(S) URL')
    return base_url


def run_smoke(config: SmokeConfig, *, http_open: Callable = urlopen) -> int:
    url = f'{_validate_base_url(config.base_url)}/v1/what-matters-now'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {config.admin_key}{WHAT_MATTERS_NOW_SMOKE_UID}',
    }
    if config.cloud_run_identity_token:
        headers['X-Serverless-Authorization'] = f'Bearer {config.cloud_run_identity_token}'
    request = Request(
        url,
        method='GET',
        headers=headers,
    )
    try:
        with http_open(request, timeout=config.timeout_seconds) as response:
            status = response.status
    except HTTPError as exc:
        status = exc.code
    except (URLError, OSError, TimeoutError) as exc:
        raise RuntimeError('What Matters Now smoke could not reach the deployed backend') from exc
    if not 200 <= status < 300:
        raise RuntimeError(f'What Matters Now smoke received HTTP {status}')
    # Do not emit the URL, uid, response body, or any auth material.
    print(f'What Matters Now datastore smoke passed (HTTP {status})')
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--admin-key-env', default='ADMIN_KEY')
    parser.add_argument(
        '--cloud-run-identity-token-env',
        default='',
        help='optional environment variable holding an OIDC token for a tagged Cloud Run candidate',
    )
    parser.add_argument('--timeout-seconds', type=float, default=30.0)
    args = parser.parse_args()
    admin_key = os.environ.get(args.admin_key_env, '').strip()
    if not admin_key:
        print(f'ERROR: required admin-key environment variable {args.admin_key_env} is empty', file=sys.stderr)
        return 1
    identity_token = os.environ.get(args.cloud_run_identity_token_env, '').strip()
    if args.cloud_run_identity_token_env and not identity_token:
        print(
            f'ERROR: required Cloud Run identity token environment variable {args.cloud_run_identity_token_env} is empty',
            file=sys.stderr,
        )
        return 1
    try:
        run_smoke(
            SmokeConfig(
                base_url=args.base_url,
                admin_key=admin_key,
                timeout_seconds=args.timeout_seconds,
                cloud_run_identity_token=identity_token,
            )
        )
    except (RuntimeError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
