#!/usr/bin/env python3
"""Generate or verify the Firebase Firestore composite-index manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / 'backend'
sys.path.insert(0, str(BACKEND_ROOT))

from database.firestore_index_registry import firebase_index_manifest  # noqa: E402


def render_manifest() -> str:
    return json.dumps(firebase_index_manifest(), indent=2) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'firestore.indexes.json')
    parser.add_argument('--write', action='store_true', help='write the generated manifest')
    args = parser.parse_args()

    expected = render_manifest()
    path = args.manifest.resolve()
    actual = path.read_text(encoding='utf-8') if path.exists() else ''
    if args.write:
        path.write_text(expected, encoding='utf-8')
        return 0
    if actual != expected:
        print(f'ERROR: {path.relative_to(ROOT)} is not generated from firestore_index_registry.py', file=sys.stderr)
        print('Run: python3 backend/scripts/generate_firestore_indexes.py --write', file=sys.stderr)
        return 1
    print(f'{path.relative_to(ROOT)} matches the Firestore index registry')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
