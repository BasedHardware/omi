#!/usr/bin/env python3
"""Bounded owner-only legacy queue observation. Dry-run by default; prints counts.

Run through an agent GCP tier. --apply is for the quality lead after inspecting
the dry-run; the implementation lane must never invoke it. No IDs, titles or
transcripts are printed. No recording, job, status or custody state is changed.
"""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import subprocess
import sys

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database.transcription_wait_repair import observe_legacy_queue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--days', type=int, default=5, choices=range(1, 8))
    parser.add_argument('--limit', type=int, default=500, choices=range(1, 1001))
    parser.add_argument('--max-updates', type=int, default=20, choices=range(1, 21))
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error('--apply and --dry-run are mutually exclusive')
    spec = importlib.util.spec_from_file_location(
        'owner_guard', Path.home() / '.claude/skills/fetch-owner-audio/guard.py'
    )
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    uid = guard.owner_uid('/Volumes/Ephemeral/owner-lab/spkfix-1104/uid.txt')
    client = firestore.Client(project='based-hardware')
    # date -u owns operator timestamps, including the one written by --apply.
    now = int(subprocess.check_output(['date', '-u', '+%s'], text=True).strip())
    since = datetime.fromtimestamp(now, timezone.utc) - timedelta(days=args.days)
    rows = list(
        client.collection('users')
        .document(uid)
        .collection('conversations')
        .where(filter=FieldFilter('started_at', '>=', since))
        .order_by('started_at')
        .limit(args.limit + 1)
        .select(
            [
                'status',
                'home_transcription_deadline_at',
                'episode_transcription_deadline_at',
                'record_projection_revision',
                'record_admitted_at',
                'home_transcription_queue_observed_at',
            ]
        )
        .stream(timeout=40, retry=None)
    )
    if len(rows) > args.limit:
        raise SystemExit(
            'Scope exceeds --limit; no observations applied. Narrow --days or raise --limit (maximum 1000).'
        )
    outcomes = Counter()
    eligible = []
    for doc in rows:
        row = doc.to_dict() or {}
        if row.get('status') != 'completed' or row.get('record_projection_revision'):
            continue
        if not (row.get('home_transcription_deadline_at') or row.get('episode_transcription_deadline_at')):
            continue
        if row.get('record_admitted_at') is not None or row.get('home_transcription_queue_observed_at') is not None:
            outcomes['already_stamped'] += 1
            continue
        jobs = list(
            client.collection('batch_pipeline_prod_jobs')
            .where(filter=FieldFilter('conversation_id', '==', doc.id))
            .limit(33)
            .select(['owner_id'])
            .stream(timeout=20, retry=None)
        )
        if len(jobs) > 32:
            outcomes['job_limit'] += 1
            continue
        # A global conversation-id collision may not authorize another account.
        if any((job.to_dict() or {}).get('owner_id') != uid for job in jobs):
            outcomes['owner_mismatch'] += 1
            continue
        refs = [job.reference for job in jobs]
        outcome = observe_legacy_queue(client, uid, doc.id, refs, now, apply=False)
        outcomes[outcome] += 1
        if outcome == 'eligible':
            eligible.append((doc.id, refs))
    if args.apply:
        if len(eligible) > args.max_updates:
            raise SystemExit('Eligible scope exceeds --max-updates; no observations applied. Narrow --days.')
        outcomes.pop('eligible', None)
        for cid, refs in eligible:
            outcomes[observe_legacy_queue(client, uid, cid, refs, now, apply=True)] += 1
    print(subprocess.check_output(['date', '-u', '+%Y-%m-%dT%H:%M:%SZ'], text=True).strip())
    print('apply' if args.apply else 'dry-run', dict(sorted(outcomes.items())))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Firestore exception messages may contain document paths. No UID may
        # escape this owner-only tool, including in a traceback on failure.
        raise SystemExit(f'Failed: {type(error).__name__}; no identifiers logged') from None
