"""Aggregate-only enable gate; run from backend: python -m scripts.batch_pipeline_poll_state_census --project PROJECT."""

import argparse

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

# Full batch-job lifecycle inventory, including provider states; pinned by the complement test.
KNOWN_STATES = (
    'record_pending ready leased retry result_ready vendor_held committed dead quarantined '
    'privacy_blocked partial_retired provider_pending provider_running provider_superseded'
).split()


@firestore.transactional
def census(tx, client, collection):
    """Two COUNTs at one read-only snapshot; never fetch job documents."""
    pending = client.collection(collection).where(filter=FieldFilter('merge_pending', '==', True))
    total = pending.count().get(transaction=tx)[0][0].value
    known = pending.where(filter=FieldFilter('state', 'in', KNOWN_STATES)).count().get(transaction=tx)[0][0].value
    return int(total - known)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    client = firestore.Client(project=parser.parse_args().project)
    count = sum(
        census(client.transaction(read_only=True), client, f'batch_pipeline_{stage}_jobs') for stage in ('prod', 'dev')
    )
    print(f'{"FAIL" if count else "PASS"} ({count})')
    raise SystemExit(bool(count))
