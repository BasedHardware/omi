"""Fleet-gate-shaped outcome sample and verdict for one simulation run.

Thresholds and aggregate definitions mirror the workspace gate
``data/run-2026-10-13-two-lane-nemotron/ops/fleet_gate.sh`` (omi-workspace repo,
constants near lines 45-61; ``terminal_speech_aggregates``,
``quarantine_projection_aggregates``, ``first_summary_aggregates`` and
``verdict``). That file is read for definitions only and is never imported:
an external adapter can feed ``sample`` (JSON) to the real gate's ``verdict``.

Every job row the gate would see is scored at the simulation's end time
(``now``), so right-censored work counts at its observed age, as in the gate.
Rows the privacy purge would erase (owner or target fenced) are excluded from
the gate cohort and reported separately under ``sim``.
"""

from __future__ import annotations

import math
from typing import Any

# fleet_gate.sh constants (definitions mirrored, not imported).
RECOVERY_SLA_SECONDS = 900
OBLIGATION_AGE_LIMIT_SECONDS = 15 * 60
QUARANTINE_PROJECTION_P95_LIMIT_SECONDS = 5 * 60
QUARANTINE_PROJECTION_LOW_SAMPLE_SLOW_SECONDS = 10 * 60
QUARANTINE_PROJECTION_LOW_SAMPLE_SLOW_COUNT = 2
QUARANTINE_PROJECTION_HARD_SLOW_SECONDS = 15 * 60
QUARANTINE_PROJECTION_P95_MIN_SAMPLE = 20
PROJECTION_STALL_SECONDS = 20 * 60
TERMINAL_UNRECOVERED_SPEECH_LIMIT = 0.002
FIRST_SUMMARY_DEADLINE_SECONDS = 120
FIRST_SUMMARY_MAX_OVERDUE_SECONDS = 60
FIRST_SUMMARY_MIN_RATE_SAMPLE = 20
FIRST_SUMMARY_MAX_BREACH_RATE = 0.05
ERROR_STATES = frozenset(('error', 'failed'))


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile, the same rule the gate uses for its p95."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _job_rows(result) -> tuple[list[dict], list[dict]]:
    """Gate-visible job rows (+ purge-excluded rows) for either simulated path."""
    if result.store is not None:
        rows, excluded = [], []
        for record in result.records:
            if record.status != 'admitted':
                continue
            for sid in record.segment_ids:
                if ('jobs', sid) not in result.store.rows:
                    excluded.append({'_document_id': sid, 'state': 'purged'})
                    continue
                row = dict(result.store.rows[('jobs', sid)])
                row['_document_id'] = sid
                (excluded if record.excluded or row.get('state') == 'privacy_blocked' else rows).append(row)
        return rows, excluded
    # Legacy path: one synthetic row per segment (no quarantine/recovery states exist there).
    rows = []
    for record in result.records:
        if record.status != 'admitted':
            continue
        for segment in record.spec.segments:
            failed = record.projected_at is not None and segment.kind == 'speech' and record.failed_segments > 0
            rows.append(
                {
                    '_document_id': f'{record.job_id}:{segment.index}',
                    'enqueued_at': record.accepted_at,
                    'duration_seconds': segment.duration,
                    'state': 'committed' if record.projected_at is not None else 'running',
                    'client_status': 'completed' if record.projected_at is not None else 'processing',
                    'result': {'outcome': 'no_recoverable_speech' if failed else 'success'},
                    '_projected_speech': segment.duration if record.projected_at is not None else None,
                }
            )
    return rows, []


def _obligations(rows: list[dict], now: float) -> dict[str, Any]:
    out = {
        'admissions': len(rows),
        'completed': sum(row.get('client_status') == 'completed' for row in rows),
        'errors': 0,
        'unrecovered_quarantines': 0,
        'unrecovered_quarantines_over_sla': 0,
        'recovery_obligations_over_15m': 0,
        'projection_obligations_over_15m': 0,
        'oldest_recovery_obligation_seconds': 0.0,
        'oldest_projection_obligation_seconds': 0.0,
        'oldest_unprojected_seconds': 0.0,
        'stuck_jobs_over_30m': 0,
        'held_recovery_units': 0,
    }
    for row in rows:
        state, status = row.get('state', ''), row.get('client_status', '')
        if state in ERROR_STATES or status in ERROR_STATES:
            out['errors'] += 1
        if state == 'quarantined':
            age = max(0.0, now - row['quarantined_at'])
            out['unrecovered_quarantines'] += 1
            out['oldest_recovery_obligation_seconds'] = max(out['oldest_recovery_obligation_seconds'], age)
            out['recovery_obligations_over_15m'] += age > OBLIGATION_AGE_LIMIT_SECONDS
            out['unrecovered_quarantines_over_sla'] += age >= RECOVERY_SLA_SECONDS
            out['held_recovery_units'] += row.get('recovery_state') in ('held', 'failed_held', 'result_held')
        if status != 'completed':
            age = max(0.0, now - row['enqueued_at'])
            out['oldest_unprojected_seconds'] = max(out['oldest_unprojected_seconds'], age)
            out['stuck_jobs_over_30m'] += age > 1800
            if state != 'quarantined':
                start = row['enqueued_at']
                settled = (row.get('recovery') or {}).get('settled_at')
                if row.get('recovery_state') == 'recovered' and isinstance(settled, (int, float)):
                    start = settled
                age = max(0.0, now - start)
                out['oldest_projection_obligation_seconds'] = max(out['oldest_projection_obligation_seconds'], age)
                out['projection_obligations_over_15m'] += age > OBLIGATION_AGE_LIMIT_SECONDS
    for key in (
        'oldest_recovery_obligation_seconds',
        'oldest_projection_obligation_seconds',
        'oldest_unprojected_seconds',
    ):
        out[key] = round(out[key], 1)
    return out


def _terminal_speech(rows: list[dict], result) -> dict[str, Any]:
    terminal = projected = 0.0
    success_units = 0
    for row in rows:
        outcome = (row.get('result') or {}).get('outcome')
        if outcome == 'no_recoverable_speech':
            terminal += float(row['duration_seconds'])
            continue
        if outcome != 'success':
            continue
        if '_projected_speech' in row:
            speech = row['_projected_speech']
        else:
            speech = ((result.store.rows.get(('results', row['_document_id'])) or {}).get('projection') or {}).get(
                'speech_seconds'
            )
        if speech is None:
            continue
        success_units += 1
        projected += float(speech)
    denominator = terminal + projected
    fraction = terminal / denominator if denominator > 0 else None
    return {
        'terminal_unrecovered_candidate_seconds': round(terminal, 3),
        'projected_speech_seconds': round(projected, 3),
        'projected_success_units': success_units,
        'terminal_unrecovered_speech_denominator_seconds': round(denominator, 3),
        'terminal_unrecovered_speech_fraction': round(fraction, 6) if fraction is not None else None,
        'terminal_unrecovered_speech_unknown_units': 0,
        'terminal_unrecovered_speech_status': 'N/A' if denominator == 0 else 'MEASURED',
    }


def _quarantine_projection(rows: list[dict], result) -> dict[str, Any]:
    now = result.ended_at
    latencies, censored = [], 0
    for row in rows:
        quarantined_at = row.get('quarantined_at') or 0
        if not quarantined_at:
            continue
        binding = row.get('projection_binding') or {}
        ledger = result.store.rows.get(('content', f"{row['owner_id']}/{binding.get('content_id')}"), {})
        if ledger.get('status') == 'completed':
            latencies.append(ledger['updated_at'] - quarantined_at)
        else:
            latencies.append(max(0.0, now - quarantined_at))
            censored += 1
    p95 = percentile(latencies, 0.95)
    over_600 = sum(value > QUARANTINE_PROJECTION_LOW_SAMPLE_SLOW_SECONDS for value in latencies)
    if not latencies:
        status = 'NO_QUARANTINES'
    elif len(latencies) >= QUARANTINE_PROJECTION_P95_MIN_SAMPLE and p95 > QUARANTINE_PROJECTION_P95_LIMIT_SECONDS:
        status = 'FAIL'
    elif (
        len(latencies) < QUARANTINE_PROJECTION_P95_MIN_SAMPLE
        and over_600 >= QUARANTINE_PROJECTION_LOW_SAMPLE_SLOW_COUNT
    ):
        status = 'FAIL'
    else:
        status = 'PASS'
    return {
        'quarantine_projection_cohort_count': len(latencies),
        'quarantine_projection_censored_count': censored,
        'quarantine_projection_unmeasured_count': 0,
        'quarantine_projection_p95_seconds': round(p95, 1) if p95 is not None else None,
        'quarantine_projection_over_600_count': over_600,
        'quarantine_projection_over_900_count': sum(
            value > QUARANTINE_PROJECTION_HARD_SLOW_SECONDS for value in latencies
        ),
        'quarantine_projection_max_seconds': round(max(latencies), 1) if latencies else None,
        'quarantine_projection_p95_status': status,
        # Low-sample caveat: below the gate's 20-sample floor p95 is not judged; n is reported.
        'quarantine_projection_low_sample': 0 < len(latencies) < QUARANTINE_PROJECTION_P95_MIN_SAMPLE,
    }


def _first_summary(result) -> dict[str, Any]:
    now = result.ended_at
    checked = breaches = 0
    maximum = 0.0
    for record in result.records:
        if (
            record.summary_pending_at is None
            or record.excluded
            or (record.first_summary_policy and not record.first_summary_policy.first_summary_enabled)
        ):
            continue
        checked += 1
        due = record.summary_pending_at + (
            record.first_summary_policy.first_summary_deadline_seconds
            if record.first_summary_policy
            else FIRST_SUMMARY_DEADLINE_SECONDS
        )
        end = record.summary_completed_at if record.summary_completed_at is not None else now
        overdue = max(0.0, end - due)
        if overdue > 0:
            breaches += 1
            maximum = max(maximum, overdue)
    rate = breaches / checked if checked else None
    if maximum > FIRST_SUMMARY_MAX_OVERDUE_SECONDS:
        status = 'FAIL'
    elif checked < FIRST_SUMMARY_MIN_RATE_SAMPLE:
        status = 'PENDING'
    elif rate > FIRST_SUMMARY_MAX_BREACH_RATE:
        status = 'FAIL'
    else:
        status = 'PASS'
    return {
        'first_summary_checked_conversations': checked,
        'first_summary_deadline_breaches': breaches,
        'first_summary_unknown_count': 0,
        'first_summary_max_overdue_seconds': round(maximum, 1),
        'first_summary_overdue_over_60_seconds': maximum > FIRST_SUMMARY_MAX_OVERDUE_SECONDS,
        'first_summary_breach_rate': round(rate, 4) if rate is not None else None,
        'first_summary_status': status,
    }


def verdict(sample: dict[str, Any], *, final: bool = True) -> tuple[str, int] | None:
    """The subset of fleet_gate.verdict the simulation can measure, in the gate's order.

    Like the gate, an intermediate poll returns None while work is incomplete;
    only the final sample turns incompleteness into ``timeout_incomplete``.
    """
    if sample['errors']:
        return 'GATE_FAIL projection_error', 1
    if sample['unrecovered_quarantines_over_sla']:
        return 'GATE_FAIL unrecovered_quarantine', 1
    if (
        sample['admissions'] > 0
        and sample['terminal_unrecovered_speech_status'] == 'N/A'
        and sample['projected_success_units'] == 0
        and sample['hold_elapsed_seconds'] > PROJECTION_STALL_SECONDS
    ):
        return 'GATE_FAIL projection_stalled', 1
    if sample['oldest_unprojected_seconds'] > 1800:
        return 'GATE_FAIL stuck_job_over_30m', 1
    if sample['recovery_obligations_over_15m'] or sample['projection_obligations_over_15m']:
        return 'GATE_FAIL obligation_over_15m', 1
    if sample['quarantine_projection_over_900_count']:
        return 'GATE_FAIL obligation_over_15m', 1
    fraction = sample['terminal_unrecovered_speech_fraction']
    if fraction is not None and fraction > TERMINAL_UNRECOVERED_SPEECH_LIMIT:
        return 'GATE_FAIL terminal_unrecovered_speech_over_0_2pct', 1
    count, p95 = sample['quarantine_projection_cohort_count'], sample['quarantine_projection_p95_seconds']
    if p95 is not None and (
        (count >= QUARANTINE_PROJECTION_P95_MIN_SAMPLE and p95 > QUARANTINE_PROJECTION_P95_LIMIT_SECONDS)
        or (
            count < QUARANTINE_PROJECTION_P95_MIN_SAMPLE
            and sample['quarantine_projection_over_600_count'] >= QUARANTINE_PROJECTION_LOW_SAMPLE_SLOW_COUNT
        )
    ):
        return 'GATE_FAIL quarantine_projection_p95_over_5m', 1
    checked = sample['first_summary_checked_conversations']
    if sample['first_summary_overdue_over_60_seconds']:
        return 'GATE_FAIL first_summary_deadline', 1
    if checked >= FIRST_SUMMARY_MIN_RATE_SAMPLE and sample['first_summary_deadline_breaches'] / checked > (
        FIRST_SUMMARY_MAX_BREACH_RATE
    ):
        return 'GATE_FAIL first_summary_deadline', 1
    if sample['completed'] < sample['admissions'] or sample['admissions'] == 0:
        if not final:
            return None
        return ('GATE_NO_WORK', 2) if sample['admissions'] == 0 else ('GATE_FAIL timeout_incomplete', 1)
    return 'GATE_PASS', 0


def score(result, *, final: bool = True) -> dict[str, Any]:
    now = result.ended_at
    rows, excluded = _job_rows(result)
    sample: dict[str, Any] = {}
    sample.update(_obligations(rows, now))
    sample.update(_terminal_speech(rows, result))
    if result.store is not None:
        sample.update(_quarantine_projection(rows, result))
    else:
        sample.update(_quarantine_projection([], result))
    sample.update(_first_summary(result))
    sample['recovery_vendor_spend_per_worn_hour_usd'] = None  # no price model; see sim.paid_fallback_calls
    sample['http_5xx'] = {'comparison_ready': False, 'regression': False}
    sample['hold_complete'] = True
    sample['hold_elapsed_seconds'] = round(now - result.clock.start, 1)

    admitted = [r for r in result.records if r.status == 'admitted' and not r.excluded]
    latencies = [r.projected_at - r.accepted_at for r in admitted if r.projected_at is not None]
    paid_by_kind: dict[str, int] = {}
    for owner, calls in result.modulate.calls_by_owner.items():
        kind = result.workload.owners.get(owner, 'unknown')
        paid_by_kind[kind] = paid_by_kind.get(kind, 0) + calls
    excluded_segments = {sid for r in result.records if r.excluded for sid in r.segment_ids}
    status_counts: dict[str, int] = {}
    for record in result.records:
        status_counts[record.status] = status_counts.get(record.status, 0) + 1
    excluded_counts: dict[str, int] = {}
    for record in result.records:
        if record.excluded:
            excluded_counts[record.excluded] = excluded_counts.get(record.excluded, 0) + 1
    sample['sim'] = {
        'scenario': result.config.name,
        'seed': result.config.seed,
        'path': result.config.path,
        'virtual_seconds': round(now - result.clock.start, 1),
        'uploads': len(result.records),
        'upload_status': dict(sorted(status_counts.items())),
        'excluded_uploads': dict(sorted(excluded_counts.items())),
        'excluded_job_rows': len(excluded),
        'completion_rate': round(len(latencies) / len(admitted), 4) if admitted else None,
        'accept_to_projection_p50_seconds': _round(percentile(latencies, 0.5)),
        'accept_to_projection_p95_seconds': _round(percentile(latencies, 0.95)),
        'accept_to_projection_max_seconds': _round(max(latencies) if latencies else None),
        'paid_fallback_calls': result.modulate.calls,
        'paid_fallback_audio_seconds': round(result.modulate.audio_seconds, 1),
        'paid_fallback_calls_by_owner_kind': dict(sorted(paid_by_kind.items())),
        'paid_fallback_calls_on_excluded_segments': sum(
            result.modulate.calls_by_segment[sid] for sid in excluded_segments
        ),
        'max_paid_calls_per_segment': max(result.modulate.calls_by_segment.values(), default=0),
        'stt': {
            'requests': result.stt.stats.requests,
            'empty': result.stt.stats.empty,
            'errors': result.stt.stats.errors,
            'timeouts': result.stt.stats.timeouts,
            'peak_replicas': result.stt.stats.peak_replicas,
            'max_queue_depth': result.stt.stats.max_queue_depth,
        },
        'executors': {
            name: {
                'workers': executor.workers,
                'max_queue': executor.max_queue,
                'p95_wait_seconds': {
                    label: _round(percentile(waits, 0.95)) for label, waits in sorted(executor.waits.items())
                },
            }
            for name, executor in result.executors.items()
        },
        'drain': result.revision.report.counts(),
        'lost_fire_and_forget_units': len(result.revision.report.lost),
        'summaries_never_completed': sum(
            1
            for r in result.records
            if r.summary_pending_at is not None and r.summary_completed_at is None and not r.excluded
        ),
        'counters': result.counters,
    }
    if result.sequencer is not None:
        sample['sim']['sequencer'] = {
            'per_owner_concurrency': result.sequencer.k,
            'max_active_per_owner': result.sequencer.stats.max_active_per_owner,
            'max_pending_per_owner': result.sequencer.stats.max_pending_per_owner,
        }
    if result.store is not None:
        states: dict[str, int] = {}
        recovery: dict[str, int] = {}
        for row in result.store.jobs():
            states[row.get('state')] = states.get(row.get('state'), 0) + 1
            if row.get('recovery_state'):
                recovery[row['recovery_state']] = recovery.get(row['recovery_state'], 0) + 1
        sample['sim']['job_states'] = dict(sorted(states.items()))
        sample['sim']['recovery_states'] = dict(sorted(recovery.items()))
    fenced_paid = 0
    for record in result.records:
        if record.fenced_at is None:
            continue
        for sid in record.segment_ids:
            fenced_paid += sum(at >= record.fenced_at for at in result.modulate.call_times.get(sid, ()))
    sample['sim']['paid_fallback_calls_after_privacy_fence'] = fenced_paid
    outcome = verdict(sample, final=final)
    message, code = outcome if outcome is not None else ('GATE_PENDING', 3)
    failed_polls = [poll for poll in getattr(result, 'polls', ()) if poll[2] == 1]
    sample['sim']['gate_polls'] = len(getattr(result, 'polls', ()))
    if final and failed_polls:
        # The real gate exits at its first failing poll; report that, plus the end state.
        sample['sim']['end_state_verdict'] = message
        sample['sim']['first_failing_poll_seconds'] = failed_polls[0][0]
        message, code = failed_polls[0][1], 1
    sample['verdict'] = message
    sample['verdict_code'] = code
    return sample


def _round(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None
