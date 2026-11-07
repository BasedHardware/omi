#!/usr/bin/env python3
"""Episode log backfill. Dry-run by default. Production projects always refused.

Use --input for a synthetic/exported per-user JSON record list, or a dev
Firestore project. Never prints content, IDs, fingerprints or consumed IDs.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.cloud import firestore
from config import episode_log as config
from database import episode_log as store, episodes
from google.cloud.firestore_v1.field_path import FieldPath
from utils.episodes.log.backfill import convert, PAGE_SIZE
from utils.episodes.log.codec import loads

ALLOWED_PROJECTS = frozenset({'based-hardware-dev'})


def records(client, uid):
    root = store.root(client, uid)
    for namespace in ('episodes', 'episode_links', 'episode_segment_receipts'):
        anchor = None
        while True:
            query = root.collection(namespace).order_by(FieldPath.document_id()).limit(PAGE_SIZE)
            if anchor:
                query = query.start_after(anchor)
            page = list(query.stream())
            for doc in page:
                row = doc.to_dict() or {}
                if namespace == 'episodes':
                    row = episodes.unseal(uid, row)
                yield {'namespace': namespace, 'id': doc.id, 'data': row}
                if namespace == 'episode_segment_receipts':
                    for index in range(int(row.get('shards', 0))):
                        archive = doc.reference.collection('s').document(str(index)).get().to_dict() or {}
                        yield {'namespace': 'receipt_archive', 'id': doc.id, 'archive': index, 'data': archive}
            if len(page) < PAGE_SIZE:
                break
            anchor = page[-1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--project')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if not args.uid or '/' in args.uid:
        parser.error('Expected one user ID')
    if args.project == 'based-hardware' or (
        args.project and args.project not in ALLOWED_PROJECTS and not os.getenv('FIRESTORE_EMULATOR_HOST')
    ):
        parser.error('Production backfill is prohibited; use dev or the emulator')
    if args.apply and not args.project:
        parser.error('--apply requires an explicit dev/emulator project')
    client = firestore.Client(project=args.project) if args.project else None
    if client is not None and client.project not in ALLOWED_PROJECTS and not os.getenv('FIRESTORE_EMULATOR_HOST'):
        parser.error('Refusing production data plane')
    if args.apply and not config.enabled(args.uid):
        parser.error('EPISODES_LOG_ENABLED and cohort admission must be on for a backfill')
    source = loads(args.input.read_text()) if args.input else records(client, args.uid) if client else None
    if source is None:
        parser.error('Supply --input or an explicit --project')
    # A backfill is a baseline only. Do not overwrite a post-migration view with
    # stale exports: Fold._seed refuses an episode already known in the log.
    report = convert(args.uid, source, apply=args.apply, firestore_client=client)
    if args.apply:
        store.finish_backfill(args.uid, firestore_client=client)
    print(json.dumps(dict(report, dry_run=not args.apply), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
