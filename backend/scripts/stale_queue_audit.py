#!/usr/bin/env python3
"""Read-only queue repair planning. Fetch metadata only; emit no identities.

Uses the active gcloud account's token explicitly rather than interactive ADC.
There is deliberately no write mode: age alone is not a terminalization policy.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import subprocess

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from google.oauth2.credentials import Credentials

QUEUES = {
    'projection_repairs': ('status', ('queued', 'failed', 'dead_letter')),
    'candidate_integration_outbox': ('status', ('pending', 'failed', 'processing', 'dead_letter')),
    'chat_first_proactive_intents': ('delivery_state', ('ready', 'pending_kernel_receipt', 'dead_letter')),
}
FIELDS = ('status', 'delivery_state', 'created_at', 'attempt_count', 'source', 'available_at', 'claimed_at')


def summarize(rows: list[dict], now: datetime) -> dict:
    dates = [row['created_at'] for row in rows if isinstance(row.get('created_at'), datetime)]
    return {
        'sample_count': len(rows),
        'sample_oldest_days': round(max(((now - date).total_seconds() / 86400 for date in dates), default=0), 3),
        'sample_attempt_counts': dict(Counter(str(row.get('attempt_count', 'missing')) for row in rows)),
        'sample_sources': dict(Counter(row.get('source', 'missing') for row in rows)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--sample-limit', type=int, default=200)
    args = parser.parse_args()
    if not 1 <= args.sample_limit <= 2000:
        parser.error('sample-limit must be between 1 and 2000')
    account = subprocess.check_output(['gcloud', 'config', 'get-value', 'account'], text=True).strip()
    if account != 'read-only-bot-account@based-hardware.iam.gserviceaccount.com':
        parser.error('source ~/.local/bin/gcp-agent-env.sh ro-prod first')
    token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], text=True).strip()
    client = firestore.Client(project=args.project, credentials=Credentials(token))
    now = datetime.now(timezone.utc)
    print(json.dumps({'mode': 'dry-run', 'observed_at': now.isoformat(), 'writes': 0}))
    for queue, (field, states) in QUEUES.items():
        for state in states:
            query = client.collection_group(queue).where(filter=FieldFilter(field, '==', state))
            count = int(query.count().get(timeout=30)[0][0].value)
            rows = [snapshot.to_dict() for snapshot in query.select(FIELDS).limit(args.sample_limit).stream(timeout=30)]
            print(json.dumps({'queue': queue, 'state': state, 'total_count': count, **summarize(rows, now)}))


if __name__ == '__main__':
    main()
