"""Aggregate a read-only export of SCA-4489 Finish-to-Home observations."""

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
import re
import sys

MARKER = 'event=v3_finish_home_sli '
KEY = re.compile(r'[0-9a-f]{32}')
SOURCES = {'app', 'pendant', 'unknown'}
DEADLINE = timedelta(seconds=60)


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('timestamps must include a timezone')
    return result.astimezone(timezone.utc)


def observations(entries, through):
    for entry in entries:
        payload = entry.get('textPayload') or (entry.get('jsonPayload') or {}).get('message') or ''
        _, marker, body = payload.partition(MARKER)
        if not marker:
            continue
        event = json.loads(body)
        if any(field in event and not KEY.fullmatch(event[field]) for field in ('finish', 'recording', 'card')):
            raise ValueError('unexpected identifier in Finish event')
        event['observed_at'] = timestamp(entry['timestamp'])
        if event['observed_at'] <= through:
            yield event


def percentile(values, population):
    rank = math.ceil(0.95 * population)
    return values[rank - 1] if 0 < rank <= len(values) else None


def counts(samples, censor_seconds):
    total = len(samples)
    matched = sorted(delay for delay, exact in samples if delay is not None and exact)
    within = sum(delay <= DEADLINE.total_seconds() for delay in matched)
    unmatched = sum(delay is None for delay, _ in samples)
    uncertain = [(delay, exact) for delay, exact in samples if not exact]
    certified_late = sum(delay is not None and delay > DEADLINE.total_seconds() for delay, _ in uncertain)
    timing_unknown = len(samples) - unmatched - len(matched) - certified_late

    p95 = percentile(matched, total)
    missing = unmatched or uncertain
    # A server-receipt clock is a lower bound. Conservatively withhold an
    # exact percentile when any such sample could change the rank.
    if p95 is not None and (
        (missing and p95 > censor_seconds) or any(delay is not None and delay < p95 for delay, _ in uncertain)
    ):
        p95 = None
    rank = math.ceil(0.95 * total)
    return {
        'finishes': total,
        'within_60s': within,
        'late': len(matched) - within + certified_late,
        'unmatched': unmatched,
        'timing_unknown': timing_unknown,
        'matched_client_cut_p95_seconds': percentile(matched, len(matched)),
        'p95_seconds': p95,
        'p95_at_or_below_60s': (
            True if total and within >= rank else False if total and within + timing_unknown < rank else None
        ),
    }


def readback(events, start, through):
    end = start + timedelta(hours=24)
    if through < end + DEADLINE:
        raise ValueError('the last Finish in the cohort needs a full 60 seconds')
    censor_seconds = (through - end).total_seconds()
    cuts, bindings = {}, {}
    legacy_candidates, legacy_proofs = {}, set()
    summaries, routes, windows = defaultdict(list), defaultdict(list), defaultdict(list)
    for event in events:
        stage = event['stage']
        observed_at = event['observed_at']
        if stage == 'cut':
            cut = timestamp(event['cut_at'])
            source = event['source'] if event['source'] in SOURCES else 'unknown'
            finish = event['finish']
            candidate = (cut, observed_at, source, event['basis'])
            if finish not in cuts or candidate < cuts[finish]:
                cuts[finish] = candidate
        elif stage == 'binding':
            finish = event['finish']
            candidate = (observed_at, event['recording'])
            if finish not in bindings or candidate < bindings[finish]:
                bindings[finish] = candidate
        elif stage == 'legacy_candidate':
            finish = event['finish']
            candidate = (
                timestamp(event['cut_at']),
                observed_at,
                event['source'] if event['source'] in SOURCES else 'unknown',
                event['basis'],
                event['recording'],
            )
            if finish not in legacy_candidates or candidate < legacy_candidates[finish]:
                legacy_candidates[finish] = candidate
        elif stage == 'legacy_manual_end':
            legacy_proofs.add(event['recording'])
        elif stage == 'window':
            windows[event['recording']].append((observed_at, event['card']))
        elif stage == 'summary':
            summaries[event['card']].append(observed_at)
        elif stage == 'route':
            routes[event['recording']].append((observed_at, event['route']))

    # An older client has no local cut token. Its candidate becomes eligible
    # only when a committed server manual-end marker names the same recording.
    for finish, (cut, observed_at, source, basis, recording) in legacy_candidates.items():
        if recording not in legacy_proofs:
            continue
        candidate = (cut, observed_at, source, basis)
        if finish not in cuts or candidate < cuts[finish]:
            cuts[finish] = candidate
        if finish not in bindings or (observed_at, recording) < bindings[finish]:
            bindings[finish] = (observed_at, recording)

    by_route_source = defaultdict(list)
    timing_basis = defaultdict(int)
    all_delays = []
    for finish, (cut, _, source, basis) in cuts.items():
        if not start <= cut < end:
            continue
        timing_basis[basis if basis in {'client_cut', 'server_cut'} else 'unknown'] += 1
        recording = bindings[finish][1] if finish in bindings else None
        first_ready = min(
            (
                ready
                for linked_at, card in windows.get(recording, ())
                for ready in summaries.get(card, ())
                if ready >= max(cut, linked_at)
            ),
            default=None,
        )
        route_signals = {route for t, route in routes.get(recording, ()) if cut <= t <= (first_ready or through)}
        if 'held' in route_signals:
            route = 'held'
        elif 'fast' in route_signals:
            route = 'fast'
        elif 'batch' in route_signals:
            route = 'batch'
        else:
            route = 'unknown'
        delay = (first_ready - cut).total_seconds() if first_ready else None
        sample = (delay, basis == 'client_cut')
        by_route_source[route, source].append(sample)
        all_delays.append(sample)

    return {
        'cohort_start': start.isoformat(),
        'cohort_end': end.isoformat(),
        'observed_through': through.isoformat(),
        'totals': counts(all_delays, censor_seconds),
        'timing_basis': dict(sorted(timing_basis.items())),
        'by_route_source': [
            {'route': route, 'source': source, **counts(delays, censor_seconds)}
            for (route, source), delays in sorted(by_route_source.items())
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort-start', required=True, type=timestamp)
    parser.add_argument('--observed-through', required=True, type=timestamp)
    parser.add_argument('--export-limit', type=int, default=25000)
    args = parser.parse_args()
    rows = json.load(sys.stdin)
    if len(rows) >= args.export_limit:
        parser.error('export reached its row cap; export smaller disjoint time ranges and combine them')
    print(
        json.dumps(
            readback(observations(rows, args.observed_through), args.cohort_start, args.observed_through), indent=2
        )
    )


if __name__ == '__main__':
    main()
