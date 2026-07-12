#!/usr/bin/env python3
"""Emit reviewed Firestore config docs for limited memory `/v3` rollout.

Dry-run only: this script prints the exact document paths/payloads that an admin
or deployment pipeline may apply. It intentionally performs no cloud writes.
"""

from __future__ import annotations
from typing import Any, Dict

import argparse
import json
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.memory.v3.limited_rollout_config import build_limited_rollout_config_bundle


def build_report(*, uid: str, account_generation: int) -> Dict[str, Any]:
    bundle = build_limited_rollout_config_bundle(uid=uid, account_generation=account_generation)
    return {
        'artifact': 'v3_limited_rollout_config',
        'status': 'SAFE_INERT_TEMPLATE',
        'read_only': True,
        'writes_executed': bundle.writes_executed,
        'apply_by_default': bundle.apply_by_default,
        'uid': uid,
        'document_count': len(bundle.documents),
        'documents': bundle.documents,
        'operator_notes': [
            'Script emits inert config only; it does not write Firestore.',
            'Deploy firestore.indexes.json and wait for READY before any separately approved activation.',
            'This script cannot open the global gate, assert write convergence, create memory_state/head, or grant reads.',
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--uid', required=True)
    parser.add_argument('--account-generation', required=True, type=int)
    args = parser.parse_args()
    print(
        json.dumps(
            build_report(uid=args.uid, account_generation=args.account_generation),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == '__main__':
    main()
