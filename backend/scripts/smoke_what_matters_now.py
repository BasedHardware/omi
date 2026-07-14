#!/usr/bin/env python3
"""Exercise the deployed What Matters Now route without logging user data or credentials."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    uid: str
    admin_key: str
    timeout_seconds: float


def _validate_base_url(value: str) -> str:
    base_url = value.rstrip('/')
    parsed = urlparse(base_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('base_url must be an absolute HTTP(S) URL')
    return base_url


def run_smoke(config: SmokeConfig, *, http_open: Callable = urlopen) -> int:
    url = f'{_validate_base_url(config.base_url)}/v1/what-matters-now'
    request = Request(
        url,
        method='GET',
        headers={'Accept': 'application/json', 'Authorization': f'Bearer {config.admin_key}{config.uid}'},
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
    parser.add_argument('--uid-env', default='OMI_TASK_INTELLIGENCE_SMOKE_UID')
    parser.add_argument('--admin-key-env', default='ADMIN_KEY')
    parser.add_argument('--timeout-seconds', type=float, default=30.0)
    args = parser.parse_args()
    uid = os.environ.get(args.uid_env, '').strip()
    admin_key = os.environ.get(args.admin_key_env, '').strip()
    if not uid:
        print(f'ERROR: required smoke UID environment variable {args.uid_env} is empty', file=sys.stderr)
        return 1
    if not admin_key:
        print(f'ERROR: required admin-key environment variable {args.admin_key_env} is empty', file=sys.stderr)
        return 1
    try:
        run_smoke(
            SmokeConfig(
                base_url=args.base_url,
                uid=uid,
                admin_key=admin_key,
                timeout_seconds=args.timeout_seconds,
            )
        )
    except (RuntimeError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
