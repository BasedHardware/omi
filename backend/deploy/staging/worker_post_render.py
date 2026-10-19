#!/usr/bin/env python3
"""Helm post-renderer for the staging batch worker: add staging identity and fence env.

The shared worker chart (frozen for the prod track) has no extra-env hook. Staging needs the
worker's Firestore client on the `staging` database in based-hardware-dev, and the boot fence
needs the deployment identity. This reads rendered manifests on stdin, appends the env below to
every Deployment container named `worker`, and writes them to stdout. Values are fixed staging
identifiers, never secrets.
"""

from __future__ import annotations

import sys

import yaml

STAGING_ENV = {
    'OMI_DEPLOYMENT': 'staging',
    'GOOGLE_CLOUD_PROJECT': 'based-hardware-dev',
    'OMI_CUSTOMER_DATA_PROJECT': 'based-hardware-dev',
    'FIRESTORE_DATABASE_ID': 'staging',
    'FIREBASE_AUTH_PROJECT_ID': 'based-hardware-dev',
}


def patch(docs: list) -> list:
    patched = 0
    for doc in docs:
        if not isinstance(doc, dict) or doc.get('kind') != 'Deployment':
            continue
        for container in doc['spec']['template']['spec']['containers']:
            if container.get('name') != 'worker':
                continue
            env = container.setdefault('env', [])
            names = {entry['name'] for entry in env}
            clash = names & set(STAGING_ENV)
            if clash:
                raise SystemExit(f'worker already sets {sorted(clash)}; refusing to override')
            env.extend({'name': name, 'value': value} for name, value in STAGING_ENV.items())
            patched += 1
    if patched != 1:
        raise SystemExit(f'expected exactly one worker container, patched {patched}')
    return docs


def main() -> int:
    docs = [doc for doc in yaml.safe_load_all(sys.stdin) if doc is not None]
    yaml.safe_dump_all(patch(docs), sys.stdout, sort_keys=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
