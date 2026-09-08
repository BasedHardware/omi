#!/usr/bin/env python3
"""Probe one tagged Cloud Run candidate's health contract without logging credentials or response bodies."""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HealthSmokeConfig:
    base_url: str
    cloud_run_identity_token: str
    timeout_seconds: float
    attempts: int
    retry_delay_seconds: float


def _validate_base_url(value: str) -> str:
    base_url = value.rstrip('/')
    parsed = urlparse(base_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('base_url must be an absolute HTTP(S) URL')
    return base_url


def run_smoke(
    config: HealthSmokeConfig,
    *,
    http_open: Callable = urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    if config.attempts <= 0:
        raise ValueError('attempts must be positive')
    if config.timeout_seconds <= 0:
        raise ValueError('timeout_seconds must be positive')
    if config.retry_delay_seconds < 0:
        raise ValueError('retry_delay_seconds must not be negative')
    url = f'{_validate_base_url(config.base_url)}/v1/health'
    headers = {'Accept': 'application/json'}
    if config.cloud_run_identity_token:
        headers['X-Serverless-Authorization'] = f'Bearer {config.cloud_run_identity_token}'
    status: int | None = None
    for attempt in range(config.attempts):
        request = Request(url, method='GET', headers=headers)
        try:
            with http_open(request, timeout=config.timeout_seconds) as response:
                status = int(response.status)
        except HTTPError as error:
            status = error.code
        except (URLError, OSError, TimeoutError) as error:
            if attempt + 1 == config.attempts:
                raise RuntimeError('Cloud Run health smoke could not reach the candidate') from error
        if status is not None and 200 <= status < 300:
            print(f'Cloud Run health smoke passed (HTTP {status})')
            return status
        if attempt + 1 < config.attempts:
            sleep(config.retry_delay_seconds)
    raise RuntimeError(f'Cloud Run health smoke received HTTP {status or "unreachable"}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--cloud-run-identity-token-env', default='')
    parser.add_argument('--timeout-seconds', type=float, default=30.0)
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--retry-delay-seconds', type=float, default=2.0)
    args = parser.parse_args()
    identity_token = os.environ.get(args.cloud_run_identity_token_env, '').strip()
    if args.cloud_run_identity_token_env and not identity_token:
        print(
            f'ERROR: required Cloud Run identity token environment variable {args.cloud_run_identity_token_env} is empty',
            file=sys.stderr,
        )
        return 1
    try:
        run_smoke(
            HealthSmokeConfig(
                base_url=args.base_url,
                cloud_run_identity_token=identity_token,
                timeout_seconds=args.timeout_seconds,
                attempts=args.attempts,
                retry_delay_seconds=args.retry_delay_seconds,
            )
        )
    except (RuntimeError, ValueError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
