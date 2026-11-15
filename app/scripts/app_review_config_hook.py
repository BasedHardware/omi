#!/usr/bin/env python3
"""Send successful Codemagic store submissions to the app-review config service."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ENDPOINT = 'https://api.omi.me/v2/internal/app-review-config/submissions'


def post_receipts(
    receipt_path: Path,
    *,
    endpoint: str | None = None,
    opener=urllib.request.urlopen,
) -> int:
    endpoint = endpoint or os.environ.get("APP_REVIEW_CONFIG_ENDPOINT", DEFAULT_ENDPOINT)
    try:
        content = receipt_path.read_text(encoding='utf-8').strip()
        records = json.loads(content) if content else []
    except (OSError, ValueError):
        print(
            "app review config hook: invalid submission receipt file; continuing after store submission",
            file=sys.stderr,
        )
        return 0
    if not isinstance(records, list):
        print(
            "app review config hook: invalid submission receipt data; continuing after store submission",
            file=sys.stderr,
        )
        return 0
    if not records:
        return 0
    token = os.environ.get('APP_REVIEW_CONFIG_SUBMISSION_TOKEN', '')
    if not token:
        print(
            "app review config hook: submission token is missing; receipt will be reconciled or expire",
            file=sys.stderr,
        )
        return 0

    parsed_endpoint = urllib.parse.urlparse(endpoint)
    if parsed_endpoint.scheme != "https" or not parsed_endpoint.netloc:
        print(
            "app review config hook: endpoint must be an HTTPS URL; receipt was not sent",
            file=sys.stderr,
        )
        return 0

    sent = 0
    failed = 0
    for record in records:
        if not isinstance(record, dict):
            print(
                "app review config hook: invalid submission receipt item; skipping it",
                file=sys.stderr,
            )
            failed += 1
            continue
        payload = json.dumps(record, separators=(',', ':')).encode('utf-8')
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'X-Review-Config-Token': token,
            },
            method='POST',
        )
        try:
            with opener(request, timeout=15) as response:
                if response.status < 200 or response.status >= 300:
                    raise urllib.error.HTTPError(
                        endpoint,
                        response.status,
                        'request rejected',
                        response.headers,
                        None,
                    )
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            platform = record.get('platform', 'unknown')
            version = record.get('version', 'unknown')
            print(
                f"app review config hook: receipt failed platform={platform} version={version}; "
                "continuing after store submission",
                file=sys.stderr,
            )
            failed += 1
            continue
        sent += 1
    print(f"app review config hook: sent {sent} receipt(s); {failed} skipped or failed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("APP_REVIEW_CONFIG_ENDPOINT", DEFAULT_ENDPOINT),
        help="HTTPS receipt endpoint (defaults to APP_REVIEW_CONFIG_ENDPOINT or production)",
    )
    args = parser.parse_args()
    return post_receipts(args.receipt, endpoint=args.endpoint)


if __name__ == '__main__':
    raise SystemExit(main())
