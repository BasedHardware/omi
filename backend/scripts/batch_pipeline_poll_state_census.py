"""Aggregate-only enable gate; run from backend: python -m scripts.batch_pipeline_poll_state_census --project PROJECT."""

import argparse

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from config.batch_census import JOB_STATES

# Full batch-job lifecycle inventory, including provider states; generated from
# the census registry and pinned by the complement test. This complement counts
# only jobs with merge_pending == True, so record_recovery_waiting (written with
# merge_pending: False) is measured by the registry's own census leg, not here.
KNOWN_STATES = list(JOB_STATES)


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
