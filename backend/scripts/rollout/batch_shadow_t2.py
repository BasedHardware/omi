# LIFECYCLE: permanent
"""Read-only shadow T2 census; no serving-denominator substitution or writes.

The T2 ratio arm still requires >=3600 measured shadow speech seconds;
entry speech and normal-GPU success floors are separate qualification rules.
Paid recovery remains in combined loss, never in normal-GPU evidence. T1/T4 come from
the fresh serving observer, whose known hard harm is never erased. All reads
use numeric/state masks, one Firestore readTime and bounded pages. No owner,
job, transcript or artifact identifiers leave request memory.
"""

import argparse
from copy import deepcopy
import datetime as dt
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.rollout.batch_quality_gate import observer_record, observed_clock, epoch  # noqa: E402

MASK = (
    'shadow',
    'state',
    'outcome',
    'projection_status',
    'speech_seconds',
    'speech_loss_seconds',
    'vad',
    'settled_at',
    'created_at',
    'paid_providers',
)
STATES = frozenset({'recovered', 'empty', 'failed_held', 'error', 'paid_skipped'})


def value(raw):
    if 'arrayValue' in raw:
        return [value(item) for item in raw['arrayValue'].get('values', [])]
    for key in ('booleanValue', 'stringValue'):
        if key in raw:
            return raw[key]
    if 'integerValue' in raw:
        return int(raw['integerValue'])
    if 'doubleValue' in raw:
        return float(raw['doubleValue'])
    return None


def _measured_census(rows, overdue, since):
    """Only measured terminal units enter the speech denominator; drops do not."""
    speech = loss = maximum = 0.0
    unknown = 0
    dropped = 0
    recovered_speech_units = 0
    for row in rows:
        if row.get('shadow') is not True:
            unknown += 1
            continue
        if row.get('outcome') == 'dropped':
            dropped += 1
            continue
        created = row.get('created_at')
        if type(created) not in (int, float) or not math.isfinite(created) or created < 0:
            unknown += 1
            continue
        if created < since:
            continue  # Earlier-regime work settling now is not shadow25 evidence.
        if (
            row.get('outcome') == 'recovered'
            and row.get('projection_status') != 'planned'
            or row.get('outcome') == 'empty'
            and row.get('projection_status') != 'empty'
        ):
            unknown += 1
            continue  # Old inference-only outcomes cannot certify projection.
        measured, lost = row.get('speech_seconds'), row.get('speech_loss_seconds')
        if (
            row.get('outcome') not in STATES
            or row.get('vad') not in {'strict', 'worker'}
            or any(
                type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 7200.1 for n in (measured, lost)
            )
            or lost > measured
        ):
            unknown += 1
            continue
        # A malformed success/empty receipt cannot certify preserved speech.
        expected = 0 if row['outcome'] == 'recovered' else measured
        if lost != expected or row['outcome'] == 'empty' and measured > 0:
            unknown += 1
            continue
        speech += measured
        loss += lost
        maximum = max(maximum, lost)
        recovered_speech_units += row['outcome'] == 'recovered' and measured > 0
    pending = [row for row in overdue if row.get('state') != 'settled']
    unknown += len(pending)
    return {
        'terminal_unrecovered_vad_speech_seconds': loss,
        'terminal_unrecovered_speech_denominator_seconds': speech,
        'terminal_unrecovered_speech_max_unit_seconds': maximum,
        'measured_held_vad_speech_seconds': 0,
        'measured_held_vad_max_unit_seconds': 0,
        'terminal_unrecovered_speech_unknown_units': unknown,
        'held_vad_unknown_units': 0,
        'terminal_unrecovered_speech_vad_fallback_units': 0,
        'since_t0_failed_held_unknown_duration': 0,
        'since_t0_failed_held_vad_fallback_units': 0,
        'sampled_terminal_units': len(rows),
        'dropped_units': dropped,
        'overdue_units': len(pending),
        'recovered_speech_units': recovered_speech_units,
    }


def census(rows, overdue, since):
    """Combined loss remains authoritative; normal GPU proof is never paid recovery."""
    combined = _measured_census(rows, overdue, since)
    normal = [row for row in rows if row.get('paid_providers') == [] and row.get('vad') == 'worker']
    paid = [
        row
        for row in rows
        if isinstance(row.get('paid_providers'), list)
        and row['paid_providers']
        and all(
            isinstance(provider, str) and provider in {'modulate', 'soniox', 'deepgram'}
            for provider in row['paid_providers']
        )
    ]
    normal_census = _measured_census(normal, [], since)
    paid_census = _measured_census(paid, [], since)
    combined.update(
        normal_gpu_t2=normal_census,
        paid_recovery_t2=paid_census,
        normal_gpu_success_units=normal_census['recovered_speech_units'],
        normal_gpu_speech_seconds=normal_census['terminal_unrecovered_speech_denominator_seconds'],
        paid_recovery_speech_seconds=paid_census['terminal_unrecovered_speech_denominator_seconds'],
        normal_gpu_proof='worker_vad_and_explicit_empty_paid_providers',
    )
    return combined


def serving_clock(history, since, through):
    """Actual T1/T4 clean reads and no serving T2 harm, never a CLI clock."""
    start = last = None
    samples = gap = 0
    for row in history:
        try:
            stamp = epoch(row['observed_through'])
        except (KeyError, ValueError, TypeError, AttributeError):
            start = last = None
            samples = gap = 0
            continue
        if stamp < epoch(since) or stamp > epoch(through):
            continue
        hard = row.get('hard3') or {}
        if hard.get('T1') != 'CLEAN' or hard.get('T4') != 'CLEAN' or hard.get('T2') == 'TRIP':
            start = last = None
            samples = gap = 0
            continue
        if last is None or not 0 <= stamp - last <= 300:
            start, samples, gap = row['observed_through'], 0, 0
        if last is None or stamp != last:
            samples += 1
        if last is not None and stamp >= last and stamp - last <= 300:
            gap = max(gap, stamp - last)
        last = stamp
    return dict(
        observation_started_at=start, observed_samples=samples, max_sample_gap_seconds=gap, last_observed_at=last
    )


def combine(base, counts, read_time, since, now, prior=None, history=()):
    """Replace only low-evidence serving T2; retain any observed serving harm."""
    raw = dict(counts, rows_read_at=read_time)
    shadow = observer_record(raw, now)
    out = deepcopy(base)
    out.update(
        at=now,
        observation_since=since,
        t2_evidence_scope='shadow25',
        t2_speech_denominator_seconds=shadow['t2_speech_denominator_seconds'],
        shadow_t2=counts,
    )
    out['hard3'] = {k: base.get('hard3', {}).get(k, 'UNKNOWN') for k in ('T1', 'T2', 'T4')}
    out['reasons'] = list(base.get('reasons') or [])
    out['alerts'] = list(base.get('alerts') or [])
    if out['hard3']['T2'] != 'TRIP':
        out['hard3']['T2'] = shadow['hard3']['T2']
    out['reasons'] = sorted(set(out['reasons']) | {r for r in shadow['reasons'] if r.startswith('T2_')})
    if any(r.startswith('T2_') for r in shadow['reasons']):
        out['hard3']['T2'] = 'TRIP'
    try:
        # Neither a stale source nor a later post-read wall clock fills a gap.
        through = min(epoch(base['observed_through']), epoch(read_time))
        fresh = 0 <= epoch(now) - through <= 300
        out['observed_through'] = dt.datetime.fromtimestamp(through, dt.timezone.utc).isoformat()
    except (KeyError, ValueError, TypeError, AttributeError):
        fresh = False
        out['observed_through'] = read_time
    if not fresh:
        out['hard3'] = {k: v if v == 'TRIP' else 'UNKNOWN' for k, v in out['hard3'].items()}
    out['verdict'] = 'TRIP' if out['reasons'] or 'TRIP' in out['hard3'].values() else 'CLEAN'
    out = observed_clock(out, prior)
    # Lead44cf37: the 30m clock is actual serving T1/T4 continuity, while T2
    # qualifies from a complete shadow census >=3600s. Reconstruct that clock
    # from receipts, rather than inventing an extra30m wait after the floor.
    clock = serving_clock(history, since, out['observed_through'])
    if (
        clock['observation_started_at'] is not None
        and clock['last_observed_at'] is not None
        and 0 <= epoch(now) - clock['last_observed_at'] <= 300
    ):
        out.update({k: v for k, v in clock.items() if k != 'last_observed_at'})
        out['observation_clock_scope'] = 'serving_T1_T4_clean_and_no_serving_T2_harm'
    else:
        out['hard3'] = {k: v if v == 'TRIP' else 'UNKNOWN' for k, v in out['hard3'].items()}
    return out


def query_pages(call, collection, field, since, until, *, read_time=None, max_rows=10000):
    rows, cursor = [], None
    while True:
        query = {
            'from': [{'collectionId': collection}],
            'select': {'fields': [{'fieldPath': f} for f in MASK]},
            'where': {
                'compositeFilter': {
                    'op': 'AND',
                    'filters': [
                        {
                            'fieldFilter': {
                                'field': {'fieldPath': field},
                                'op': 'GREATER_THAN_OR_EQUAL',
                                'value': {'doubleValue': since},
                            }
                        },
                        {
                            'fieldFilter': {
                                'field': {'fieldPath': field},
                                'op': 'LESS_THAN_OR_EQUAL',
                                'value': {'doubleValue': until},
                            }
                        },
                    ],
                }
            },
            'orderBy': [
                {'field': {'fieldPath': field}, 'direction': 'ASCENDING'},
                {'field': {'fieldPath': '__name__'}, 'direction': 'ASCENDING'},
            ],
            'limit': 500,
        }
        if cursor:
            query['startAt'] = {'values': cursor, 'before': False}
        request = {'structuredQuery': query}
        if read_time:
            request['readTime'] = read_time
        response = call(request)
        times = [r['readTime'] for r in response if r.get('readTime')]
        if not times:
            raise ValueError('server_read_time_required')
        read_time = read_time or min(times, key=epoch)
        page = [r['document'] for r in response if 'document' in r]
        for document in page:
            rows.append({k: value(v) for k, v in document.get('fields', {}).items()})
        if len(rows) >= max_rows:
            raise ValueError('shadow_census_page_budget')
        if len(page) < 500:
            return rows, read_time
        last = page[-1]
        cursor = [last['fields'][field], {'referenceValue': last['name']}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-observer', type=Path, required=True)
    parser.add_argument('--since', required=True, help='actual shadow25 activation time')
    parser.add_argument(
        '--out', type=Path, required=True, help='new output directory, never the serving observer output'
    )
    args = parser.parse_args()
    if os.environ.get('GCP_AGENT_TIER') != 'ro-prod':
        parser.error('ro-prod required')
    if args.out.resolve() == args.source_observer.resolve().parent:
        parser.error('separate_output_required')
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        since = epoch(args.since)
        if not 0 <= since <= epoch(now):
            raise ValueError('actual_shadow_start_required')
        token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], text=True, timeout=30).strip()
        url = (
            'https://firestore.googleapis.com/v1/projects/based-hardware/databases/'
            + quote('(default)', safe='')
            + '/documents:runQuery'
        )

        def call(body):
            request = Request(
                url,
                data=json.dumps(body).encode(),
                headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
            )
            with urlopen(request, timeout=40) as response:
                return json.load(response)

        clock_response = call(
            {
                'structuredQuery': {
                    'from': [{'collectionId': 'batch_pipeline_prod_shadow_jobs'}],
                    'select': {'fields': [{'fieldPath': 'state'}]},
                    'limit': 1,
                }
            }
        )
        times = [r['readTime'] for r in clock_response if r.get('readTime')]
        if not times:
            raise ValueError('server_read_time_required')
        read_time = min(times, key=epoch)
        rows, _ = query_pages(
            call, 'batch_pipeline_prod_shadow_jobs', 'settled_at', since, epoch(read_time), read_time=read_time
        )
        # Only old unfinished attempts make completeness unknown; fresh flights
        # are normal in-flight work, not fabricated loss. One snapshot for both.
        overdue = []
        if epoch(read_time) - 900 >= since:
            overdue, _ = query_pages(
                call,
                'batch_pipeline_prod_shadow_jobs',
                'created_at',
                since,
                epoch(read_time) - 900,
                read_time=read_time,
            )
        base = json.loads(args.source_observer.read_text())
        history = [
            json.loads(line)
            for line in args.source_observer.with_name('watch-samples.jsonl').read_text().splitlines()
            if line.strip()
        ]
        try:
            prior = json.loads((args.out / 'watch-latest.json').read_text())
        except (OSError, ValueError):
            prior = {}
        row = combine(
            base,
            census(rows, overdue, since),
            read_time,
            args.since,
            dt.datetime.now(dt.timezone.utc).isoformat(),
            prior,
            history,
        )
    except Exception as error:
        row = {
            'at': now,
            'verdict': 'BLIND',
            'reasons': ['shadow_sample_unavailable'],
            'alerts': [],
            'hard3': dict(T1='UNKNOWN', T2='UNKNOWN', T4='UNKNOWN'),
            'read_error_class': type(error).__name__,
            'observation_since': args.since,
        }
    args.out.mkdir(parents=True, exist_ok=True)
    temporary = args.out / 'watch-latest.tmp'
    temporary.write_text(json.dumps(row, sort_keys=True) + '\n')
    temporary.replace(args.out / 'watch-latest.json')
    with (args.out / 'watch-samples.jsonl').open('a') as stream:
        stream.write(json.dumps(row, sort_keys=True) + '\n')
    print(json.dumps(row, sort_keys=True))
    return 0 if row['verdict'] == 'CLEAN' and set(row['hard3'].values()) == {'CLEAN'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
