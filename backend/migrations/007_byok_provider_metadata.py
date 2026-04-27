"""
Migration 007: backfill `(provider, model, dim)` metadata on existing Pinecone vectors.

M2.5 prerequisite. Tags every legacy vector with the schema attribution that the
new write paths now stamp on every upsert. Idempotent — vectors that already have
`provider` set in metadata are skipped.

Per-namespace tags (legacy 3072-dim index only):
- ns1 conversations:    provider=openai, model=text-embedding-3-large, dim=3072
- ns2 (memories):       provider=openai, model=text-embedding-3-large, dim=3072
- ns3 (screen activity): provider=gemini, model=embedding-001,        dim=3072

Run:
    PINECONE_API_KEY=... PINECONE_INDEX_NAME=omi-prod \
    python backend/migrations/007_byok_provider_metadata.py

Estimate ~5 min for 30K vectors. Dry run first via `--dry-run` flag.
"""

import argparse
import os
import sys
from typing import Dict

from pinecone import Pinecone

LEGACY_TAGS: Dict[str, Dict[str, object]] = {
    'ns1': {'provider': 'openai', 'model': 'text-embedding-3-large', 'dim': 3072},
    'ns2': {'provider': 'openai', 'model': 'text-embedding-3-large', 'dim': 3072},
    'ns3': {'provider': 'gemini', 'model': 'embedding-001', 'dim': 3072},
}


def main(dry_run: bool = False) -> int:
    api_key = os.environ.get('PINECONE_API_KEY')
    index_name = os.environ.get('PINECONE_INDEX_NAME')
    if not api_key or not index_name:
        print('error: PINECONE_API_KEY and PINECONE_INDEX_NAME must be set', file=sys.stderr)
        return 2

    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)

    grand_tagged = 0
    grand_skipped = 0

    for namespace, tags in LEGACY_TAGS.items():
        print(f'== namespace={namespace} ==')
        cursor = None
        ns_tagged = 0
        ns_skipped = 0
        page_count = 0
        while True:
            page_count += 1
            page = index.list_paginated(namespace=namespace, pagination_token=cursor, limit=100)
            vector_ids = [v.id for v in page.vectors]
            if not vector_ids:
                break

            # Fetch metadata for the page so we can skip already-tagged vectors.
            fetched = index.fetch(ids=vector_ids, namespace=namespace)
            for vid in vector_ids:
                meta = (fetched.vectors.get(vid) or {}).metadata or {}
                if meta.get('provider'):
                    ns_skipped += 1
                    continue
                if dry_run:
                    print(f'  WOULD tag {vid} with {tags}')
                else:
                    index.update(id=vid, namespace=namespace, set_metadata=tags)
                ns_tagged += 1

            print(f'  page {page_count}: tagged={ns_tagged} skipped={ns_skipped}')
            if not page.pagination or not page.pagination.next:
                break
            cursor = page.pagination.next

        print(f'  done: tagged={ns_tagged} skipped={ns_skipped}')
        grand_tagged += ns_tagged
        grand_skipped += ns_skipped

    print(f'\nTotal: tagged={grand_tagged} skipped={grand_skipped} (dry_run={dry_run})')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Print what would be tagged without writing')
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
