#!/usr/bin/env python3
"""Retire only the two reviewed queues. Dry-run by default; never print identities.

Dry-run uses ro-prod's gcloud token. Execute uses explicitly configured ADC;
run only after the producer retirement is deployed. Siblings are not allowed.
"""

import argparse
from datetime import datetime, timezone
import json
import subprocess

CUTOFFS = {
    'projection_repairs': datetime(2026, 8, 28, tzinfo=timezone.utc),
    'chat_first_proactive_intents': datetime(2026, 10, 6, tzinfo=timezone.utc),
}


def retire(client, queue, *, execute=False, confirm_queue=None, max_deletes=1000, batch_size=400):
    if queue not in CUTOFFS or not 1 <= batch_size <= 400 or max_deletes < 1:
        raise ValueError('invalid queue or cap')
    if execute and confirm_queue != queue:
        raise ValueError('execute requires matching confirm-queue')
    query = client.collection_group(queue)
    total = int(query.count().get(timeout=60)[0][0].value)
    if execute:
        from google.cloud.firestore_v1 import FieldFilter

        # Check globally before writing: name-order pages alone cannot prove freshness.
        fresh = query.where(filter=FieldFilter('created_at', '>=', CUTOFFS[queue]))
        if int(fresh.count().get(timeout=60)[0][0].value):
            raise ValueError('post-retirement rows found; investigate producer before deleting')
    query = query.select(['created_at']).order_by('__name__')
    scanned = deleted = 0
    while scanned < max_deletes:
        page = list(query.limit(min(batch_size, max_deletes - scanned)).stream(timeout=60))
        if not page:
            break
        for doc in page:
            parts = doc.reference.path.split('/')
            if len(parts) != 4 or parts[0] != 'users' or parts[2] != queue:
                raise ValueError('unexpected collection-group ancestry; no writes for this page')
            created = doc.to_dict().get('created_at')
            if execute and (not isinstance(created, datetime) or created.tzinfo is None or created >= CUTOFFS[queue]):
                raise ValueError('missing or post-retirement timestamp; no writes for this page')
        if execute:
            batch = client.batch()
            for doc in page:
                batch.delete(doc.reference)
            batch.commit(timeout=60)
            deleted += len(page)
        scanned += len(page)
        query = query.start_after(page[-1])
    return {'queue': queue, 'total_count': total, 'scanned': scanned, 'deleted': deleted, 'cap': max_deletes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--queue', choices=CUTOFFS)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-queue', choices=CUTOFFS)
    parser.add_argument('--max-deletes', type=int)
    parser.add_argument('--batch-size', type=int, default=400)
    args = parser.parse_args(argv)
    if args.execute and (not args.queue or args.confirm_queue != args.queue or args.max_deletes is None):
        parser.error('--execute requires --queue, matching --confirm-queue and explicit --max-deletes')
    cap = args.max_deletes if args.max_deletes is not None else 1000
    if cap < 1 or not 1 <= args.batch_size <= 400:
        parser.error('positive max-deletes and batch-size between 1 and 400 required')
    from google.cloud import firestore

    if args.execute:
        client = firestore.Client(project=args.project)
    else:
        from google.oauth2.credentials import Credentials

        account = subprocess.check_output(['gcloud', 'config', 'get-value', 'account'], text=True).strip()
        if account != 'read-only-bot-account@based-hardware.iam.gserviceaccount.com':
            parser.error('source ~/.local/bin/gcp-agent-env.sh ro-prod first')
        token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], text=True).strip()
        client = firestore.Client(project=args.project, credentials=Credentials(token))
    print(
        json.dumps(
            {'mode': 'execute' if args.execute else 'dry-run', 'observed_at': datetime.now(timezone.utc).isoformat()}
        )
    )
    remaining = cap
    for queue in ([args.queue] if args.queue else CUTOFFS):
        if remaining:
            result = retire(
                client,
                queue,
                execute=args.execute,
                confirm_queue=args.confirm_queue,
                max_deletes=remaining,
                batch_size=args.batch_size,
            )
            remaining -= result['scanned']
        else:
            total = int(client.collection_group(queue).count().get(timeout=60)[0][0].value)
            result = {'queue': queue, 'total_count': total, 'scanned': 0, 'deleted': 0, 'cap': 0}
        print(json.dumps(result))


if __name__ == '__main__':
    main()
