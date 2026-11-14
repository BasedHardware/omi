#!/usr/bin/env python3
"""Count the stored fresh-delivery cohort at an explicit sample time; no documents are read."""

import argparse
import json
import math
import os
import sys

from google.cloud import firestore


def count_cohort(client, stage, sample_time):
    # Deliberately independent of the serving helper for acceptance comparisons.
    # Capture age and fresh_first describe a different cohort.
    window_start, window_end = sample_time - 1200, sample_time - 600
    query = (
        client.collection(f'batch_pipeline_{stage}_results')
        .where('fresh_capture', '==', True)
        .where('committed_at', '>=', window_start)
        .where('committed_at', '<=', window_end)
    )
    total = int(query.count().get(timeout=10, retry=None)[0][0].value)
    pending = int(query.where('projection_state', '==', 'pending').count().get(timeout=10, retry=None)[0][0].value)
    return {
        'sample_time': sample_time,
        'window_start': window_start,
        'window_end': window_end,
        'total': total,
        'pending': pending,
        'ratio': pending / total if total else None,
    }


def main(argv=None, *, client_factory=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', choices=('based-hardware', 'based-hardware-dev'), required=True)
    parser.add_argument('--stage', choices=('prod', 'dev'), required=True)
    parser.add_argument('--sample-time', type=float, required=True, help='Guard window anchor, Unix seconds')
    args = parser.parse_args(argv)
    if not math.isfinite(args.sample_time) or args.sample_time <= 1200:
        parser.error('--sample-time must be finite Unix seconds greater than 1200')
    if (args.stage == 'prod') != (args.project == 'based-hardware'):
        parser.error('stage must match project')
    tier = 'ro-prod' if args.stage == 'prod' else 'ro-dev'
    if os.getenv('GCP_AGENT_TIER') != tier:
        print(f'Select {tier} before counting.', file=sys.stderr)
        return 2
    try:
        if client_factory is None:
            client_factory = firestore.Client
        result = count_cohort(client_factory(project=args.project), args.stage, args.sample_time)
    except Exception as error:
        # No SDK messages, document identifiers or customer content in output.
        print(json.dumps({'ratio': None, 'error_type': type(error).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
