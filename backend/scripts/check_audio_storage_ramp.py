#!/usr/bin/env python3
"""Check aggregate operator evidence for one audio-storage ramp step.

No network calls or production writes. This validates a receipt, not the
truth of its measurements; the train owner supplies linked read-only evidence.
Missing telemetry is a refusal, never a measured zero. See the ramp runbook.
"""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SURFACES = {
    'gke/backend-listen',
    'gke/pusher',
    'cloud_run/backend',
    'cloud_run/backend-sync',
    'cloud_run/backend-sync-backfill',
    'cloud_run/backend-integration',
}
STEPS = {
    'stop-5': ('baseline', 0, 5, 0),
    'stop-25': ('stop-5', 12, 25, 0),
    'stop-100': ('stop-25', 4, 100, 0),
    'regional-5': ('stop-100', 1, 100, 5),
    'regional-100': ('regional-5', 12, 100, 100),
}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamps must be strings')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamps must include a timezone')
    return parsed


def check(step, receipt, now=None):
    """Return refusals; an empty list means the supplied evidence meets gates."""
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    def number(mapping, key):
        value = mapping[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{key} must be a finite nonnegative number')
        return value

    previous, hold, stop, regional = STEPS[step]
    require(receipt['previous_step'] == previous, f'previous_step must be {previous}')
    before, after = receipt['before'], receipt['after']
    start, end = timestamp(after['start']), timestamp(after['end'])
    applied = timestamp(receipt['applied_at'])
    prior_applied = timestamp(receipt['previous_applied_at'])
    now = now or datetime.now(timezone.utc)
    baseline_start, baseline_end = timestamp(before['start']), timestamp(before['end'])
    require(timestamp(before['end']) <= applied, 'baseline must precede apply')
    require((applied - baseline_end).total_seconds() <= 3600, 'baseline must end within 1h before apply')
    require((timestamp(before['end']) - timestamp(before['start'])).total_seconds() >= 3600, 'baseline needs >=1h')
    require(
        (baseline_start - timestamp(receipt['custody_roll_completed_at'])).total_seconds() >= 3600,
        'baseline must begin after custody roll DONE +1h',
    )
    accepted = receipt['accepted_baseline']
    require(
        accepted['start'] == before['start']
        and accepted['end'] == before['end']
        and accepted['evidence_ref'] == before['evidence_ref']
        and bool(before['evidence_ref']),
        'baseline window must match the accepted aggregate evidence',
    )
    require(start >= applied and (end - start).total_seconds() >= 3600, 'after needs a full >=1h new-state window')
    require(end <= now and (now - end).total_seconds() <= 3600, 'after evidence must end within the last hour')
    require((applied - prior_applied).total_seconds() >= hold * 3600, f'previous step needs >={hold}h soak')
    require(bool(receipt['lead_apply_ref']), 'lead apply ruling is required')
    require(bool(receipt['baseline_acceptance_ref']), 'lead acceptance of custody baseline is required')
    if previous != 'baseline':
        prior = receipt['previous_receipt']
        prior_end = timestamp(prior['after']['end'])
        require(not check(previous, prior, now=prior_end), 'previous step receipt must pass all gates')
        require(prior['applied_at'] == receipt['previous_applied_at'], 'previous apply identity differs from receipt')
        require(
            (prior_end - timestamp(prior['after']['start'])).total_seconds() >= hold * 3600,
            f'previous successful receipt must cover the full >={hold}h soak',
        )
        require(
            prior_end <= applied and (applied - prior_end).total_seconds() <= 3600,
            'previous successful receipt must end within 1h before apply',
        )
        require(baseline_start >= prior_applied, 'baseline must measure the previous step state')
    expected = {
        'AUDIO_ARCHIVE_STOP_PCM_ENABLED': 'true',
        'AUDIO_ARCHIVE_STOP_PCM_PERCENT': str(stop),
        'AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED': 'true' if regional else 'false',
        'AUDIO_ARCHIVE_REGIONAL_CACHE_PERCENT': str(regional),
        'BUCKET_AUDIO_DERIVED': 'omi-audio-derived-uc1' if regional else '',
        'AUDIO_DURABLE_OUTBOX_ENABLED': 'true',
        'AUDIO_ARCHIVE_READ_ENABLED': 'true',
    }
    serving = receipt['serving']
    require(set(serving) == SURFACES, 'all six serving surfaces are required')
    for surface in SURFACES:
        records = serving[surface]
        require(bool(records), f'{surface}: missing serving revisions/images')
        require(
            sum(number(record, 'share_percent') for record in records) == 100,
            f'{surface}: serving shares must sum to 100',
        )
        for record in records:
            require(
                bool(record['release_sha']) and bool(record['image_digest']), f'{surface}: release identity required'
            )
            require(record['ready'] is True, f'{surface}: serving artifact must be ready')
            for key, value in expected.items():
                require(record['effective_env'].get(key) == value, f'{surface}: {key} differs from step')
    for name in ('batch_stt', 'shadow_wer', 'speech_redrive', 'playback', 'audio_merge', 'decode_failed'):
        gate = receipt['quality'][name]
        require(
            gate['passed'] is True and bool(gate['evidence_ref']), f'{name}: measured parity/error evidence required'
        )
    for surface in ('listen', 'pusher'):
        custody = after['custody'][surface]
        require(number(custody, 'commits') > 0, f'{surface}: custody commits must be observed')
        if surface == 'listen':
            require(
                number(custody, 'failures') == 0 and number(custody, 'would_drop') == 0, 'listen: custody risk observed'
            )
        require(bool(custody['evidence_ref']), f'{surface}: custody evidence required')
    before_hours = (baseline_end - baseline_start).total_seconds() / 3600
    after_hours = (end - start).total_seconds() / 3600
    if before_hours <= 0 or after_hours <= 0:
        raise ValueError('observation windows must have positive duration')
    # Existing, recoverable pusher projection/queue pressure is compared to a
    # post-roll matched-hour baseline (lead 6418ac), never normalized to zero.
    # Separate commit/other failures so projection improvement cannot hide a
    # raw custody regression. Reset-aware counts become rates across long soaks.
    fields = ('projection_transient', 'queue_would_drop', 'commit_failures', 'other_failures', 'other_would_drop')
    for window in (before, after):
        custody = window['custody']['pusher']
        require(number(custody, 'commits') > 0, 'pusher: baseline and after commits must be observed')
        require(bool(custody['evidence_ref']), 'pusher: baseline and after evidence required')
        require(
            math.isclose(
                number(custody, 'failures'),
                sum(number(custody, key) for key in ('projection_transient', 'commit_failures', 'other_failures')),
                abs_tol=0.000001,
            ),
            'pusher: failure categories must account for all failures',
        )
        require(
            math.isclose(
                number(custody, 'would_drop'),
                number(custody, 'queue_would_drop') + number(custody, 'other_would_drop'),
                abs_tol=0.000001,
            ),
            'pusher: drop categories must account for all would_drop',
        )
    for field in fields:
        require(
            number(after['custody']['pusher'], field) / after_hours
            <= number(before['custody']['pusher'], field) / before_hours,
            f'pusher: {field}/hour rose above the matched baseline',
        )
    write_before = number(before, 'private_write_per_hour')
    write_after = number(after, 'private_write_per_hour')
    require(write_after < write_before, 'private WriteObject/h must fall in comparable windows')
    require(number(after, 'pcm_writes_avoided_per_hour') > 0, 'PCM avoidance counter must be active')
    require(bool(receipt['cohort_attribution_ref']), 'cohort/traffic-normalized attribution evidence required')
    if regional:
        require(
            number(after, 'regional_write_per_hour') > number(before, 'regional_write_per_hour'),
            'regional writes must rise',
        )
        require(
            receipt['iam']['passed'] is True and bool(receipt['iam']['evidence_ref']), 'writer IAM readback required'
        )
        require(
            receipt['dual_list']['passed'] is True and bool(receipt['dual_list']['evidence_ref']),
            'non-admitted dual-list guard required',
        )
    else:
        require(
            number(after, 'pcm_writes_avoided_per_hour') > number(before, 'pcm_writes_avoided_per_hour'),
            'PCM avoidance must increase',
        )
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=STEPS)
    parser.add_argument('receipt', type=Path, help='aggregate JSON receipt; no UIDs or audio payloads')
    args = parser.parse_args()
    try:
        errors = check(args.step, json.loads(args.receipt.read_text()))
    except (KeyError, ValueError, TypeError, OSError) as exc:
        print(f'REFUSE: missing or invalid evidence ({type(exc).__name__})')
        return 1
    for error in errors:
        print(f'REFUSE: {error}')
    if errors:
        return 1
    print(f'EVIDENCE PASS: {args.step}; lead still owns apply; billing savings require D+1 verification')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
