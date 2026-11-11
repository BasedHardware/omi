#!/usr/bin/env python3
"""Send successful Codemagic store submissions to the app-review config service."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_ENDPOINT = 'https://api.omi.me/v2/internal/app-review-config/submissions'


def post_receipts(receipt_path: Path, *, opener=urllib.request.urlopen) -> int:
    try:
        content = receipt_path.read_text(encoding='utf-8').strip()
        records = json.loads(content) if content else []
    except (OSError, ValueError):
        print('app review config hook: invalid submission receipt file', file=sys.stderr)
        return 1
    if not isinstance(records, list):
        print('app review config hook: invalid submission receipt data', file=sys.stderr)
        return 1
    if not records:
        return 0
    token = os.environ.get('APP_REVIEW_CONFIG_SUBMISSION_TOKEN', '')
    if not token:
        print('app review config hook: submission token is missing', file=sys.stderr)
        return 1

    endpoint = DEFAULT_ENDPOINT
    for record in records:
        if not isinstance(record, dict):
            print('app review config hook: invalid submission receipt item', file=sys.stderr)
            return 1
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
                    raise urllib.error.HTTPError(endpoint, response.status, 'request rejected', response.headers, None)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            platform = record.get('platform', 'unknown')
            version = record.get('version', 'unknown')
            print(f'app review config hook: failed platform={platform} version={version}', file=sys.stderr)
            return 1
    print(f'app review config hook: sent {len(records)} store submission receipt(s)')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    return post_receipts(args.receipt)


if __name__ == '__main__':
    raise SystemExit(main())
