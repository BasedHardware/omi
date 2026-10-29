# LIFECYCLE: permanent
"""David 2026-10-29: only custody, lost speech and language trip.

Pure policy, shared by the proposed observer adapter, controller and entry
checklist. This module cannot read production, execute a command, or change a
marker. Soft evidence is retained as alerts, never promoted by a prefix match.
"""

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import re

HARD = frozenset(
    {
        'T1_custody_missing_or_mismatch',
        'T2_lost_unit_over120s',
        'T2_lost_speech_over0_2pct',
        'T4_unsafe_parakeet_route',
        'T4_completed_without_route_proof',
    }
)
# Missing observations of the hard three cannot prove a clean gate. They do
# not authorize rollback. Unknown capture duration is not measured lost speech.
HARD_UNKNOWN = frozenset(
    {
        'custody_unknown',
        'speech_unknown',
        'routes',
        'custody',
        'vad',
        'stale_census',
        'sample_unavailable',
        'observer_unavailable',
    }
)
POLICY = 'hard3-1029'


def observer_record(sample, at, alerts=()):
    """Reduce actual aggregate evidence, without reading a manual T2 marker.

    The collector supplies the complete observation window. Thresholds match
    the existing hard-three observer, including measured held speech. A missing
    field is UNKNOWN; a partial sample never becomes clean through defaults.
    """
    reasons, hard3 = [], {}

    def number(node, key):
        value = node.get(key) if isinstance(node, dict) else None
        return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None

    unavailable = sample.get('unavailable', [])
    custody = sample.get('custody') or {}
    missing, unknown = number(custody, 'missing'), number(custody, 'unknown')
    if missing is not None and missing > 0:
        reasons.append('T1_custody_missing_or_mismatch')
    hard3['T1'] = (
        'TRIP'
        if missing is not None and missing > 0
        else 'CLEAN' if missing == 0 and unknown == 0 and 'custody' not in unavailable else 'UNKNOWN'
    )

    keys = (
        'terminal_unrecovered_vad_speech_seconds',
        'terminal_unrecovered_speech_denominator_seconds',
        'terminal_unrecovered_speech_max_unit_seconds',
        'measured_held_vad_speech_seconds',
        'measured_held_vad_max_unit_seconds',
        'terminal_unrecovered_speech_unknown_units',
        'held_vad_unknown_units',
        'terminal_unrecovered_speech_vad_fallback_units',
        'since_t0_failed_held_unknown_duration',
        'since_t0_failed_held_vad_fallback_units',
    )
    values = {key: number(sample, key) for key in keys}
    complete = all(value is not None for value in values.values())
    t2_reasons = []
    # Known harm still trips when another part of the sample is unknown.
    terminal_measured = values['terminal_unrecovered_speech_vad_fallback_units'] == 0
    maxima = [
        values[k]
        for k in ('terminal_unrecovered_speech_max_unit_seconds', 'measured_held_vad_max_unit_seconds')
        if values[k] is not None and (k != 'terminal_unrecovered_speech_max_unit_seconds' or terminal_measured)
    ]
    if maxima and max(maxima) >= 120:
        t2_reasons.append('T2_lost_unit_over120s')
    ratio_keys = keys[:2] + ('measured_held_vad_speech_seconds',)
    if terminal_measured and all(values[k] is not None for k in ratio_keys):
        held = values['measured_held_vad_speech_seconds']
        lost = values['terminal_unrecovered_vad_speech_seconds'] + held
        denominator = values['terminal_unrecovered_speech_denominator_seconds'] + held
        if not math.isfinite(lost) or not math.isfinite(denominator):
            complete = False
        elif denominator >= 3600 and lost / denominator > 0.002:
            t2_reasons.append('T2_lost_speech_over0_2pct')
    reasons.extend(t2_reasons)
    hard3['T2'] = (
        'TRIP'
        if t2_reasons
        else (
            'CLEAN'
            if complete
            and values['terminal_unrecovered_speech_unknown_units'] == 0
            and values['held_vad_unknown_units'] == 0
            and values['terminal_unrecovered_speech_vad_fallback_units'] == 0
            and values['since_t0_failed_held_unknown_duration'] == 0
            and values['since_t0_failed_held_vad_fallback_units'] == 0
            and 'vad' not in unavailable
            else 'UNKNOWN'
        )
    )

    unsafe = number(sample, 'language_route_unsafe_parakeet_units')
    no_proof = number(sample, 'language_route_missing_completed_units')
    if unsafe is not None and unsafe > 0:
        reasons.append('T4_unsafe_parakeet_route')
    if no_proof is not None and no_proof > 0 and 'routes' not in unavailable:
        reasons.append('T4_completed_without_route_proof')
    hard3['T4'] = (
        'TRIP'
        if unsafe is not None and unsafe > 0 or no_proof is not None and no_proof > 0 and 'routes' not in unavailable
        else 'CLEAN' if unsafe == 0 and no_proof == 0 and 'routes' not in unavailable else 'UNKNOWN'
    )
    # Read freshness protects the hard measurements, not worker/manifest pins.
    try:
        fresh = 0 <= epoch(at) - epoch(sample['rows_read_at']) <= 300
    except (KeyError, TypeError, ValueError, AttributeError):
        fresh = False
    if not fresh:
        hard3 = {key: value if value == 'TRIP' else 'UNKNOWN' for key, value in hard3.items()}
    return dict(
        at=at,
        verdict='TRIP' if reasons else 'CLEAN',
        reasons=sorted(reasons),
        alerts=sorted(set(alerts)),
        hard3=hard3,
        policy=POLICY,
    )


def epoch(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone_required')
    return parsed.timestamp()


def classify(verdict, reasons):
    """Keep mixed hard+soft trips hard; retain every soft signal for paging."""
    reasons = set(reasons)
    hard = sorted(reasons & HARD)
    unknown = sorted(reasons & HARD_UNKNOWN)
    alerts = sorted(reasons - HARD - HARD_UNKNOWN)
    if hard:
        return dict(verdict='TRIP', reasons=hard, alerts=alerts + unknown)
    if unknown:
        return dict(verdict='BLIND', reasons=unknown, alerts=alerts)
    # An unexplained non-clean verdict is missing safety evidence, rather than
    # an invented clean observation. Known soft reasons may be alert-only.
    if not reasons and verdict not in ('CLEAN', 'ALERT'):
        return dict(verdict='BLIND', reasons=['observer_unavailable'], alerts=[])
    return dict(verdict='CLEAN', reasons=[], alerts=alerts)


def observation(latest, now, max_age=300):
    if not isinstance(latest, dict):
        return classify('BLIND', ['observer_unavailable'])
    try:
        age = now - epoch(latest['at'])
        if not 0 <= age <= max_age:
            raise ValueError('stale')
        if not isinstance(latest['reasons'], list) or not all(isinstance(r, str) for r in latest['reasons']):
            raise ValueError('reasons')
        result = classify(latest['verdict'], latest['reasons'])
    except (KeyError, TypeError, ValueError, AttributeError):
        return classify('BLIND', ['observer_unavailable'])
    alerts = latest.get('alerts', [])
    if not isinstance(alerts, list) or not all(isinstance(r, str) for r in alerts):
        alerts = ['malformed_soft_alerts']
    result['alerts'] = sorted(set(result['alerts'] + alerts))
    # Adapter declarations cannot turn an old, partially observed safety read
    # into a clean gate. The observer must explicitly supply each hard result.
    safety = latest.get('hard3')
    if not isinstance(safety, dict) or set(safety) != {'T1', 'T2', 'T4'}:
        safety = {}
    if result['verdict'] != 'TRIP' and any(safety.get(k) != 'CLEAN' for k in ('T1', 'T2', 'T4')):
        result['verdict'] = 'BLIND'
        result['reasons'] = sorted(set(result['reasons'] + ['hard3_evidence_incomplete']))
    return result


def entry_check(packet, now):
    """The single gate: 24h errclass + serving-SHA replay + hard three clean.

    Receipts are produced by their owning lanes; this checks their contract,
    not their scientific validity. No manifest, latch id, or hand-armed marker
    participates. APPROVE ENTRY remains a separate lead-only operation.
    """
    errors = []
    if not isinstance(packet, dict):
        return dict(policy=POLICY, verdict='WAIT', errors=['packet_invalid'], alerts=[])
    sha = packet.get('serving_sha')
    if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{40}', sha):
        errors.append('serving_sha_required')
    err = packet.get('errclass') or {}
    replay = packet.get('replay') or {}
    for name, receipt in (('errclass', err), ('replay', replay)):
        if not isinstance(receipt, dict):
            errors.append(name + '_receipt_invalid')
            continue
        try:
            if not 0 <= now - epoch(receipt['at']) <= 900:
                raise ValueError('stale')
        except (KeyError, TypeError, ValueError, AttributeError):
            errors.append(name + '_receipt_stale_or_missing')
        if receipt.get('serving_sha') != sha:
            errors.append(name + '_not_serving_sha')
        if receipt.get('complete') is not True or not receipt.get('evidence_ref'):
            errors.append(name + '_evidence_incomplete')
    if isinstance(err, dict):
        hours = err.get('baseline_hours')
        if type(hours) not in (int, float) or not math.isfinite(hours) or hours < 24:
            errors.append('errclass_24h_baseline_required')
        if err.get('includes_zero_percent_traffic') is not True:
            errors.append('errclass_zero_percent_coverage_required')
        if type(err.get('untriaged_new_classes')) is not int or err['untriaged_new_classes'] != 0:
            errors.append('errclass_untriaged_new_classes')
    if isinstance(replay, dict) and replay.get('verdict') != 'PASS':
        errors.append('replay_not_green')
    guard = observation(packet.get('observer'), now)
    if guard['verdict'] != 'CLEAN':
        errors.extend('hard3:' + reason for reason in guard['reasons'])
    try:
        if not 1800 <= now - epoch(packet['observer']['observation_since']):
            raise ValueError('lookback')
    except (KeyError, TypeError, ValueError, AttributeError):
        errors.append('hard3_full_30m_lookback_required')
    return dict(
        policy=POLICY,
        verdict='READY_FOR_LEAD_ENTRY' if not errors else 'WAIT',
        errors=sorted(set(errors)),
        alerts=guard['alerts'],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('packet', type=Path)
    parser.add_argument('--sample', action='store_true', help='reduce a raw observer aggregate; no production read')
    parser.add_argument('--now', help='UTC ISO timestamp; offline replay only')
    args = parser.parse_args()
    now = epoch(args.now) if args.now else dt.datetime.now(dt.timezone.utc).timestamp()
    packet = json.loads(args.packet.read_text())
    if args.sample:
        print(
            json.dumps(
                observer_record(packet, dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat()), sort_keys=True
            )
        )
        return 0
    result = entry_check(packet, now)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['verdict'] == 'READY_FOR_LEAD_ENTRY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
