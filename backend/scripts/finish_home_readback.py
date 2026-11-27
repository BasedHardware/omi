"""Aggregate a read-only export of SCA-4489 Finish-to-Home observations.

A Finish is scored from its cut to the first committed write that left its window Home-eligible with a
summary (``eligible``). A Finish that found its window already on Home (``already_visible``) changes nothing and answers with that
card: when the event proves the card shows a summary it is ready at its cut and scores 0 s on the
``already_visible`` route; otherwise it is reported in ``already_visible_unproven`` and not scored. A Home response that carried the summary (``summary``) only validates that the
reader actually showed it; when the app fetches Home does not change the score.
"""

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
# A recording-level legacy proof follows its candidate (the finalization commit comes after the request). Only
# log-timestamp jitter can invert them; this bounds that allowance. Request-tied proofs need no timing.
LEGACY_PROOF_TOLERANCE = timedelta(seconds=5)


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
        if any(
            field in event and not KEY.fullmatch(event[field]) for field in ('finish', 'recording', 'card', 'request')
        ):
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
    legacy_candidates, legacy_proofs, request_proofs = defaultdict(list), defaultdict(list), set()
    eligible, fetched = defaultdict(list), defaultdict(list)
    routes, windows = defaultdict(list), defaultdict(list)
    visible = {}
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
            legacy_candidates[event['recording']].append(
                (
                    observed_at,
                    timestamp(event['cut_at']),
                    event['source'] if event['source'] in SOURCES else 'unknown',
                    event['basis'],
                    finish,
                    event.get('request'),
                )
            )
        elif stage == 'legacy_manual_end':
            if event.get('request'):
                request_proofs.add((event['recording'], event['request']))
            else:
                legacy_proofs[event['recording']].append(observed_at)
        elif stage == 'window':
            windows[event['recording']].append((observed_at, event['card']))
        elif stage == 'eligible':
            eligible[event['card']].append(observed_at)
        elif stage == 'summary':
            fetched[event['card']].append(observed_at)
        elif stage == 'route':
            routes[event['recording']].append((observed_at, event['route']))
        elif stage == 'already_visible':
            finish = event['finish']
            candidate = (observed_at, event['card'], event.get('summary') is True)
            if finish not in visible or candidate < visible[finish]:
                visible[finish] = candidate

    # An older client has no local cut token, and every headerless request on a recording logs a candidate
    # under the same recording key. A candidate is scored only where a deliberate Finish is established:
    # its own request id carries a proof (the request proved itself), or a recording-level proof follows the
    # recording's only candidate. Retries of a proven Finish keep the earliest proven cut. Every other
    # candidate is excluded and only reported; timing never picks between candidates.
    legacy_excluded = {'no_proof': 0, 'not_the_proven_request': 0, 'ambiguous': 0, 'retry': 0}
    for recording, candidates in legacy_candidates.items():
        candidates.sort(key=lambda candidate: candidate[:2])
        scored, reasons = _attribute(candidates, recording, request_proofs, legacy_proofs[recording])
        for candidate, reason in zip(candidates, reasons):
            observed_at, cut, source, basis, finish, _ = candidate
            if candidate is not scored:
                if start <= cut < end:
                    legacy_excluded[reason] += 1
                continue
            sample = (cut, observed_at, source, basis)
            if finish not in cuts or sample < cuts[finish]:
                cuts[finish] = sample
                bindings[finish] = (observed_at, recording)

    by_route_source = defaultdict(list)
    timing_basis = defaultdict(int)
    all_delays = []
    validation = {
        'eligible': 0,
        'fetched': 0,
        'eligible_card_not_fetched': 0,
        'other_linked_card_fetched': 0,
        'fetched_without_eligible': 0,
    }
    fetch_lags = []
    already_visible_unproven = 0
    for finish, (cut, _, source, basis) in cuts.items():
        if not start <= cut < end:
            continue
        already = visible.get(finish)
        if already is not None and not already[2]:
            # Found on Home, but the event does not prove a summary is showing: not a 0 s success, and no
            # eligibility write follows (the Finish changed nothing), so it is reported, not scored.
            already_visible_unproven += 1
            continue
        timing_basis[basis if basis in {'client_cut', 'server_cut'} else 'unknown'] += 1
        recording = bindings[finish][1] if finish in bindings else None
        linked = windows.get(recording, ())
        # The score is the first eligibility of any linked card; it never reads fetch timing. A Finish that
        # found its card already on Home showing a summary is ready at the cut: that card is its winner.
        if already is not None:
            linked = [(cut, already[1])]
            winner = (cut, already[1])
        else:
            winner = _first(eligible, linked, cut)
        first_ready = winner[0] if winner else None
        if winner is None:
            validation['fetched_without_eligible'] += _first(fetched, linked, cut) is not None
        else:
            # Validation follows the card that won: a fetch of another linked card does not show this one.
            ready_at, card = winner
            first_fetch = _first(fetched, [link for link in linked if link[1] == card], ready_at)
            validation['eligible'] += 1
            if first_fetch:
                validation['fetched'] += 1
                fetch_lags.append((first_fetch[0] - ready_at).total_seconds())
            else:
                validation['eligible_card_not_fetched'] += 1
                # A projection mismatch: Home returned a sibling card but suppressed the eligible one.
                validation['other_linked_card_fetched'] += _first(fetched, linked, ready_at) is not None
        route_signals = {route for t, route in routes.get(recording, ()) if cut <= t <= (first_ready or through)}
        if already is not None:
            route = 'already_visible'
        elif 'held' in route_signals:
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
        # Headerless candidates that are not a proven Finish: reported, never scored as cuts or misses.
        'legacy_excluded': legacy_excluded,
        # Finishes that found their card on Home without proof that it shows a summary: reported, not scored.
        'already_visible_unproven': already_visible_unproven,
        # Validation, not the score: did a Home response carry each eligible summary to the reader?
        'home_fetch_validation': {
            **validation,
            'fetch_after_eligible_p95_seconds': percentile(sorted(fetch_lags), len(fetch_lags)),
        },
    }


def _attribute(candidates, recording, request_proofs, recording_proofs):
    """``(scored candidate or None, exclusion reason per candidate)`` for one recording's legacy candidates."""
    tied = [candidate for candidate in candidates if (recording, candidate[5]) in request_proofs]
    if tied:
        # The proof names its request. Later proven requests on the recording are retries of that Finish and
        # never move its cut forward; unproven requests on the recording are not the Finish.
        scored = min(tied, key=lambda candidate: (candidate[1], candidate[0]))
        proven = {id(candidate) for candidate in tied}
        reasons = ['retry' if id(candidate) in proven else 'not_the_proven_request' for candidate in candidates]
        return scored, reasons
    if len(candidates) == 1 and any(proof >= candidates[0][0] - LEGACY_PROOF_TOLERANCE for proof in recording_proofs):
        return candidates[0], [None]
    if len(candidates) > 1 and recording_proofs:
        # A recording-level proof cannot say which of several requests was the Finish.
        return None, ['ambiguous'] * len(candidates)
    return None, ['no_proof'] * len(candidates)


def _first(observed, linked, after):
    """``(time, card)`` of the first observation of a card linked to this Finish, at or after ``after`` and the link."""
    return min(
        ((at, card) for linked_at, card in linked for at in observed.get(card, ()) if at >= max(after, linked_at)),
        default=None,
    )


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
