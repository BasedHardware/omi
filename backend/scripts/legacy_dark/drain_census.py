#!/usr/bin/env python3
"""Legacy-sync drain census: the aggregate counts that gate ``dark`` (contract (h)).

Read-only. Prints counts and a verdict, never a document, uid, task name or
label value beyond the queue names. Run on a read tier:

    source ~/.local/bin/gcp-agent-env.sh ro-prod      # or ro-dev for staging
    cd backend && .venv/bin/python -m scripts.legacy_dark.drain_census --env prod
    .venv/bin/python -m scripts.legacy_dark.drain_census --env staging --confirm

``--confirm`` takes a second census after 10 minutes and prints the ``dark``
entry verdict (two zero reads >= 10 minutes apart). Any unavailable read
counts as non-zero: the census fails closed.

Exit codes: 0 zero (or READY with --confirm), 1 non-zero / NOT_READY,
2 usage or credential error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from utils.sync.legacy_dark import (
    DARK_CONFIRMATION_SECONDS,
    LEGACY_QUEUES,
    DrainCensus,
    dark_entry_verdict,
)

ENVIRONMENTS = {
    # env: (project, firestore database, cloud tasks location)
    'prod': ('based-hardware', '(default)', 'us-central1'),
    'staging': ('based-hardware-dev', 'staging', 'us-central1'),
}
MONITORING = 'https://monitoring.googleapis.com'
ADMISSIONS_WINDOW = '30m'


def _count(query: Any) -> int:
    return int(query.count().get()[0][0].value)


def _safe(read: Callable[[], int], errors: dict[str, str], name: str) -> Optional[int]:
    try:
        return read()
    except Exception as error:  # fail closed: unavailable is non-zero
        errors[name] = type(error).__name__
        return None


def _session():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    return AuthorizedSession(credentials)


def _queue_depths(session: Any, project: str, env: str, errors: dict[str, str]) -> dict[str, Optional[int]]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=10)
    params = {
        'filter': 'metric.type="cloudtasks.googleapis.com/queue/depth" AND resource.type="cloud_tasks_queue"',
        'interval.startTime': start.isoformat().replace('+00:00', 'Z'),
        'interval.endTime': end.isoformat().replace('+00:00', 'Z'),
        'view': 'FULL',
    }
    depths: dict[str, Optional[int]] = {queue: None for queue in LEGACY_QUEUES}
    # Staging shares based-hardware-dev with dev, whose queues carry no prefix:
    # only the env's own queue ids count (dev's ``sync-jobs`` is not staging's).
    queue_ids = {(queue if env == 'prod' else f'staging-{queue}'): queue for queue in LEGACY_QUEUES}
    try:
        response = session.get(f'{MONITORING}/v3/projects/{project}/timeSeries', params=params, timeout=30)
        response.raise_for_status()
        for series in response.json().get('timeSeries', []):
            queue = queue_ids.get(series.get('resource', {}).get('labels', {}).get('queue_id'))
            if queue is not None and series.get('points'):
                value = series['points'][0].get('value', {})
                depths[queue] = int(value.get('int64Value', value.get('doubleValue', 0)))
    except Exception as error:
        errors['queue_depth'] = type(error).__name__
        return depths
    for queue, value in depths.items():
        if value is None:
            # A queue with no points in 10 minutes either does not exist or is
            # idle and unreported; both are reported, neither is assumed zero.
            errors[f'queue_depth:{queue}'] = 'no_points'
    return depths


def _prom_scalar(session: Any, project: str, promql: str) -> Optional[float]:
    url = f'{MONITORING}/v1/projects/{project}/location/global/prometheus/api/v1/query'
    response = session.get(url, params={'query': promql}, timeout=30)
    response.raise_for_status()
    result = response.json().get('data', {}).get('result', [])
    if not result:
        return None
    return float(result[0]['value'][1])


def _legacy_admissions(session: Any, project: str, errors: dict[str, str]) -> Optional[int]:
    try:
        deployed = _prom_scalar(session, project, 'count(omi_legacy_sync_mode)')
        if not deployed:
            errors['legacy_admissions'] = 'mode_gauge_absent'
            return None
        value = _prom_scalar(session, project, f'sum(increase(omi_legacy_sync_admissions_total[{ADMISSIONS_WINDOW}]))')
        # The mode gauge proves the code is serving; a counter with no series
        # has never been incremented.
        return 0 if value is None else int(round(value))
    except Exception as error:
        errors['legacy_admissions'] = type(error).__name__
        return None


def take_census(env: str, *, with_ledger: bool = False) -> tuple[DrainCensus, dict[str, str]]:
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter

    project, database, _location = ENVIRONMENTS[env]
    errors: dict[str, str] = {}
    client = firestore.Client(project=project, database=database)
    ledger = client.collection_group('sync_content_ledger')

    def where(query: Any, field: str, op: str, value: Any) -> Any:
        return query.where(filter=FieldFilter(field, op, value))

    def legacy_status(status: str) -> int:
        total = _count(where(ledger, 'status', '==', status))
        batch = _count(where(where(ledger, 'status', '==', status), 'dispatch_protocol', '==', 'batch_v1'))
        return total - batch

    observed_at = time.time()
    session = _session()
    depths = _queue_depths(session, project, env, errors)
    census = DrainCensus(
        observed_at=observed_at,
        sync_backfill_pending=_safe(lambda: _count(client.collection('sync_backfill_pending')), errors, 'pending'),
        sequencer_active_owners=_safe(
            lambda: _count(where(client.collection('sync_backfill_sequencer'), 'active_job_id', '>', '')),
            errors,
            'sequencer_active_owners',
        ),
        redrive_required=_safe(lambda: _count(client.collection('sync_redrive_required')), errors, 'redrive_required'),
        cap_holds_awaiting_legacy=_safe(
            lambda: _count(client.collection_group('stt_cap_holds')), errors, 'cap_holds_awaiting_legacy'
        ),
        queue_depth_sync_jobs=depths['sync-jobs'],
        queue_depth_sync_jobs_fresh=depths['sync-jobs-fresh'],
        queue_depth_sync_backfill=depths['sync-backfill'],
        queue_depth_sync_backfill_fresh=depths['sync-backfill-fresh'],
        legacy_admissions_window=_legacy_admissions(session, project, errors),
    )
    if with_ledger:
        info: dict[str, str] = {}
        census = replace(
            census,
            ledger_processing_legacy=_safe(lambda: legacy_status('processing'), info, 'ledger_processing_legacy'),
            ledger_retryable_legacy=_safe(lambda: legacy_status('retryable'), info, 'ledger_retryable_legacy'),
        )
        errors.update({f'informational:{key}': value for key, value in info.items()})
    return census, errors


def _render(env: str, census: DrainCensus, errors: dict[str, str]) -> dict[str, Any]:
    blockers = census.nonzero()
    return {
        'env': env,
        'tier': os.environ.get('GCP_AGENT_TIER', 'unknown'),
        'observed_at': datetime.fromtimestamp(census.observed_at, timezone.utc).isoformat(),
        'counts': {name: getattr(census, name) for name in census.__dataclass_fields__ if name != 'observed_at'},
        'unavailable': errors,
        'verdict': 'ZERO' if not blockers else 'NONZERO',
        'note': 'queue depth counts all tasks; sync-jobs also carries sr- enrichment until C3 moves it',
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env', choices=sorted(ENVIRONMENTS), required=True)
    parser.add_argument(
        '--with-ledger', action='store_true', help='informational ledger counts (needs a collection-group index)'
    )
    parser.add_argument('--confirm', action='store_true', help='second read after 10 minutes; print dark verdict')
    args = parser.parse_args(argv)
    if os.environ.get('GCP_AGENT_TIER') not in {'ro-prod', 'ro-dev', 'dev-operator', 'prod-operator'}:
        print(json.dumps({'error': 'source gcp-agent-env.sh with an agent tier first'}))
        return 2
    first, first_errors = take_census(args.env, with_ledger=args.with_ledger)
    print(json.dumps(_render(args.env, first, first_errors), sort_keys=True))
    if not args.confirm:
        return 0 if not first.nonzero() else 1
    time.sleep(DARK_CONFIRMATION_SECONDS)
    second, second_errors = take_census(args.env, with_ledger=args.with_ledger)
    print(json.dumps(_render(args.env, second, second_errors), sort_keys=True))
    verdict = dark_entry_verdict(first, second)
    print(json.dumps({'dark_entry': 'READY' if verdict.ready else 'NOT_READY', 'blockers': list(verdict.blockers)}))
    return 0 if verdict.ready else 1


if __name__ == '__main__':
    sys.exit(main())
