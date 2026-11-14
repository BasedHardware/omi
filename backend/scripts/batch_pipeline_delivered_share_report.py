"""Read the per-route, per-language delivered share over a past window, or drill it.

Two modes, one definition. ``--project`` walks the same bounded job-metadata
page the live sampler uses, window by window, and derives delivery from the
result row for rows that predate the acknowledge stamp. ``--drill`` runs the
hermetic pipeline simulator twice (healthy, then a provider outage) and prints
the same table plus the alarm verdict, so the signal can be exercised without
production access.

Counts and metadata only: no transcript, audio, user id or email is printed.

Examples::

    python -m scripts.batch_pipeline_delivered_share_report --project based-hardware \\
        --from 2026-11-13T00:00Z --to 2026-11-14T00:00Z --step 900
    python -m scripts.batch_pipeline_delivered_share_report --drill
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from database.batch_pipeline_delivered_share import COHORT_SECONDS, PAGE_LIMIT, TARGET_SECONDS, delivered_share_page
from utils.batch_pipeline.delivered_share import (
    BASELINE_FACTOR,
    MIN_VOLUME,
    alarm_cells,
    cells,
    language_of,
    route_of,
    share,
)


def _epoch(text: str) -> float:
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.utcoffset() is None:
        raise ValueError('window timestamps must include a timezone')
    return value.timestamp()


def _windows(args):
    if args.step != COHORT_SECONDS:
        raise ValueError(f'--step must be {COHORT_SECONDS} seconds')
    if bool(args.baseline_start) != bool(args.baseline_end):
        raise ValueError('--baseline-from and --baseline-to must be supplied together')

    def window(start, end):
        start, end = _epoch(start), _epoch(end)
        if start >= end or start % COHORT_SECONDS or end % COHORT_SECONDS:
            raise ValueError('ranges must contain complete UTC quarter-hour cohorts, with --from before --to')
        return start, end

    target = window(args.start, args.end)
    baseline = window(args.baseline_start, args.baseline_end) if args.baseline_start else None
    return target, baseline


def _delivered_at(result: dict | None) -> float | None:
    """The first moment the transcript was visible, from the result receipt."""
    if not result or result.get('projection_state') != 'completed':
        return None
    receipt = result.get('projection') or {}
    at = receipt.get('persisted_at')
    if isinstance(at, (int, float)) and not isinstance(at, bool):
        return at
    parts = result.get('projection_parts') or {}
    times = [
        part.get('persisted_at')
        for part in parts.values()
        if isinstance(part.get('persisted_at'), (int, float)) and not isinstance(part.get('persisted_at'), bool)
    ]
    return max(times) if times else None


def _historical_rows(client, namespace: str, now: float):
    rows, truncated = delivered_share_page(client, namespace, now)
    # The live sampler includes the end boundary. Historical cohorts must be
    # half-open so an admission on a shared boundary is counted exactly once.
    end = now - TARGET_SECONDS
    rows = [row for row in rows if end - COHORT_SECONDS <= row['enqueued_at'] < end]
    missing = [row for row in rows if 'delivered_in_target' not in row]
    if missing:
        refs = [client.collection(f'{namespace}_results').document(row['segment_id']) for row in missing]
        snapshots = (
            client.get_all(
                refs,
                field_paths=('projection_state', 'projection.persisted_at', 'projection_part_count'),
                timeout=10,
                retry=None,
            )
            if refs
            else []
        )
        by_id = {snapshot.id: snapshot.to_dict() for snapshot in snapshots}
        # Part keys are numeric strings, not a single nested persisted_at field.
        # Discover only the count, then request explicit timestamp leaves for
        # legacy completed receipts without a summary timestamp. Never select
        # the receipt map: it also carries conversation and speaker identifiers.
        for segment_id, result in tuple(by_id.items()):
            if not result or result.get('projection_state') != 'completed' or _delivered_at(result) is not None:
                continue
            count = result.get('projection_part_count')
            if type(count) is not int or not 0 < count <= PAGE_LIMIT:
                raise ValueError('completed receipt has no timestamp or supported projection_part_count (1..5000)')
            fields = ('projection_state',) + tuple(f'projection_parts.`{index}`.persisted_at' for index in range(count))
            ref = client.collection(f'{namespace}_results').document(segment_id)
            snapshot = next(iter(client.get_all([ref], field_paths=fields, timeout=10, retry=None)), None)
            receipt = snapshot.to_dict() if snapshot else None
            parts = (receipt or {}).get('projection_parts') or {}
            if (
                not receipt
                or receipt.get('projection_state') != 'completed'
                or len(parts) != count
                or any(type(part.get('persisted_at')) not in (int, float) for part in parts.values())
            ):
                raise ValueError('legacy receipt has incomplete timestamp leaves; refusing a partial delivery count')
            by_id[segment_id] = receipt
        for row in missing:
            delivered = _delivered_at(by_id.get(row['segment_id']))
            admitted = row.get('enqueued_at')
            row['delivered_in_target'] = (
                delivered is not None
                and isinstance(admitted, (int, float))
                and 0 <= delivered - admitted <= TARGET_SECONDS
            )
    return rows, truncated


def _merge(target: dict, source: dict) -> None:
    for key, (admitted, delivered) in source.items():
        was_admitted, was_delivered = target.get(key, (0, 0))
        target[key] = (was_admitted + admitted, was_delivered + delivered)


def _print_table(title: str, counted: dict, baselines: dict | None = None) -> None:
    print(f'\n{title}')
    print(f'{"route":<10} {"language":<9} {"admitted":>9} {"delivered":>10} {"share":>7}  baseline')
    for (route, language), (admitted, delivered) in sorted(counted.items()):
        value = share(admitted, delivered)
        baseline = (baselines or {}).get((route, language))
        print(
            f'{route:<10} {language:<9} {admitted:>9} {delivered:>10} '
            f'{(f"{value:.3f}" if value is not None else "-"):>7}  '
            f'{(f"{baseline:.3f}" if baseline is not None else "-")}'
        )


def backfill(args) -> int:
    (start, end), baseline_window = _windows(args)
    from google.cloud import firestore

    client = firestore.Client(project=args.project)
    namespace = f'batch_pipeline_{args.stage}'
    counted: dict = {}
    truncated_windows = 0
    window = start
    while window < end:
        now = window + COHORT_SECONDS + TARGET_SECONDS
        rows, truncated = _historical_rows(client, namespace, now)
        truncated_windows += 1 if truncated else 0
        _merge(counted, cells(rows))
        window += COHORT_SECONDS
    _print_table(f'Delivered within {TARGET_SECONDS}s of admission, {args.start} to {args.end}', counted)
    if truncated_windows:
        print(f'\n{truncated_windows} window(s) hit the page cap; those shares cover the oldest rows only.')
    if baseline_window:
        baseline_counted: dict = {}
        window, baseline_end = baseline_window
        while window < baseline_end:
            now = window + COHORT_SECONDS + TARGET_SECONDS
            rows, _ = _historical_rows(client, namespace, now)
            _merge(baseline_counted, cells(rows))
            window += COHORT_SECONDS
        baselines = {
            key: share(admitted, delivered)
            for key, (admitted, delivered) in baseline_counted.items()
            if share(admitted, delivered) is not None
        }
        firing = alarm_cells(counted, baselines)
        print(
            f'\nAlarm (share < {BASELINE_FACTOR:.0%} of the baseline, at least {MIN_VOLUME} admitted): '
            f'{len(firing)} cell(s) firing'
        )
        for route, language, value, baseline in firing:
            print(f'  FIRING {route}/{language}: {value:.3f} vs baseline {baseline:.3f}')
    return 0


def drill(args) -> int:
    from dataclasses import replace

    from testing.pipeline_sim.sim import Simulation
    from testing.pipeline_sim.trace import GOLDEN_CONFIGS

    def run(**changes):
        base = GOLDEN_CONFIGS['provider_stt_ja']()
        # Enough admitted units for the real volume floor to be meaningful.
        workload = replace(base.workload, owners=12, uploads_per_owner_per_hour=8.0, arrival_seconds=1200.0)
        config = replace(base, workload=changes.pop('workload', workload), **changes)
        return Simulation(config).run()

    def rows(result):
        return [
            {
                'enqueued_at': record.accepted_at,
                'projection_binding': {'language': 'ja'},
                'policy': {'stt_route': 'provider'},
                'delivered_in_target': (
                    record.projected_at is not None
                    and record.accepted_at is not None
                    and 0 <= record.projected_at - record.accepted_at <= TARGET_SECONDS
                ),
            }
            for record in result.records
            if record.status == 'admitted' and record.accepted_at is not None
        ]

    healthy = cells(rows(run()))
    outage = cells(rows(run(vendor_routing_armed=True, vendor_outages=(('modulate', 0.0, 10**9),))))
    baselines = {key: share(admitted, delivered) for key, (admitted, delivered) in healthy.items()}
    _print_table('Drill baseline: healthy Japanese provider route', healthy)
    _print_table('Drill: Japanese provider route down for the whole run', outage, baselines)
    firing = alarm_cells(outage, baselines)
    print(f'\nAlarm verdict: {len(firing)} cell(s) firing')
    for route, language, value, baseline in firing:
        print(f'  FIRING {route}/{language}: {value:.3f} vs baseline {baseline:.3f}')
    return 0 if firing else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project', help='GCP project for the backfill read')
    parser.add_argument('--stage', default='prod', choices=('prod', 'dev'))
    parser.add_argument('--from', dest='start', help='window start, ISO-8601')
    parser.add_argument('--to', dest='end', help='window end, ISO-8601')
    parser.add_argument(
        '--step', type=int, default=COHORT_SECONDS, help='window size in seconds (only 900 is supported)'
    )
    parser.add_argument('--baseline-from', dest='baseline_start', help='baseline window start, ISO-8601')
    parser.add_argument('--baseline-to', dest='baseline_end', help='baseline window end, ISO-8601')
    parser.add_argument('--drill', action='store_true', help='run the hermetic simulator drill instead of a read')
    args = parser.parse_args()
    if args.drill:
        return drill(args)
    if not (args.project and args.start and args.end):
        parser.error('--project, --from and --to are required unless --drill is set')
    if bool(args.baseline_start) != bool(args.baseline_end):
        parser.error('--baseline-from and --baseline-to must be supplied together')
    try:
        _windows(args)
    except ValueError as error:
        parser.error(str(error))
    return backfill(args)


if __name__ == '__main__':
    raise SystemExit(main())
