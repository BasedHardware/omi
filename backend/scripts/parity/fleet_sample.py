"""Adapt the workspace fleet gate's JSON sample into parity rows 3 and 4.

The fleet gate (``data/run-2026-10-13-two-lane-nemotron/ops/fleet_gate.sh``,
``--env staging`` for staging) prints one JSON sample per poll, then a final
``GATE_*`` line. Both surfaces read the same sample shape, so rows 3 and 4 are
computed from the same aggregates the ramp controller's gate already trusts.

Only aggregate fields are read; the gate never prints identifiers.
"""

from __future__ import annotations

import json
import math
from typing import Any, Iterable, Mapping

# Fleet-gate tokens that contract (g) treats as data loss (ROLLBACK_ZERO).
DATA_LOSS_GATE_TOKENS = (
    'terminal_unrecovered_speech_',
    'stuck_job_over_30m',
    'obligation_over_15m',
    'projection_error',
    'projection_stalled',
)
CONTRACT_DISPATCH_LIMIT_SECONDS = 121.0


def is_data_loss_token(reason: str | None) -> bool:
    if not reason:
        return False
    return any(reason == token or (token.endswith('_') and reason.startswith(token)) for token in DATA_LOSS_GATE_TOKENS)


def parse_gate_output(lines: Iterable[str]) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Return ``(last_sample, status, reason)`` from fleet-gate stdout.

    ``status`` is PASS/FAIL/NO_WORK/PENDING from the last ``GATE_*`` line, or
    None when the gate has not finished.
    """
    sample, status, reason = None, None, None
    for raw in lines:
        line = raw.strip()
        if line.startswith('{'):
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                sample = parsed
        elif line.startswith('GATE_'):
            head, _, tail = line.partition(' ')
            status, reason = head[len('GATE_') :], (tail.strip() or None)
    return sample, status, reason


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _int(value: Any) -> int:
    out = _num(value)
    return int(out) if out is not None and out >= 0 else 0


def row3_aggregates(sample: Mapping[str, Any], legacy: Mapping[str, Any] | None) -> dict[str, Any]:
    """Row 3 inputs. Breaches use the contract's strict 121s, not the gate's 125s tolerance.

    The gate counts dispatches over 120s + 5s tolerance; any measured dispatch
    above 121s (seen through ``first_summary_dispatch_max_seconds``) is at least
    one contract breach even when the gate's own count is zero.
    """
    breaches = _int(sample.get('first_summary_dispatch_breaches'))
    max_dispatch = _num(sample.get('first_summary_dispatch_max_seconds'))
    if max_dispatch is not None and max_dispatch > CONTRACT_DISPATCH_LIMIT_SECONDS:
        breaches = max(breaches, 1)
    return {
        'first_summary_dispatch_measured_count': _int(sample.get('first_summary_dispatch_measured_count')),
        'first_summary_dispatch_breaches_over_121s': breaches,
        'first_summary_dispatch_max_seconds': max_dispatch,
        'first_summary_completion_p95_seconds': _num(sample.get('first_summary_completion_latency_p95_seconds')),
        # The gate measures conversation close -> summary present; that is the
        # batch side's accept -> summary for a finished recording.
        'accept_to_summary_p95_seconds': _num(sample.get('first_summary_close_to_summary_p95_seconds')),
        'legacy_accept_to_summary_p95_seconds': _num((legacy or {}).get('accept_to_summary_p95_seconds')),
    }


def row4_aggregates(sample: Mapping[str, Any], census: Mapping[str, Any] | None) -> dict[str, Any]:
    stuck = _int(sample.get('since_t0_stuck_jobs_over_30m', sample.get('stuck_jobs_over_30m')))
    oldest = _num(sample.get('since_t0_oldest_unprojected_seconds', sample.get('oldest_unprojected_seconds')))
    if oldest is not None and oldest > 1800:
        stuck = max(stuck, 1)
    obligations = (
        _int(sample.get('since_t0_recovery_obligations_over_15m', sample.get('recovery_obligations_over_15m')))
        + _int(sample.get('since_t0_projection_obligations_over_15m', sample.get('projection_obligations_over_15m')))
        + _int(sample.get('quarantine_projection_over_900_count'))
    )
    status = sample.get('terminal_unrecovered_speech_status')
    fraction = _num(sample.get('terminal_unrecovered_speech_fraction')) if status == 'MEASURED' else None
    census = census or {}
    return {
        'admitted_units': _int(sample.get('admissions')),
        'stuck_jobs_over_30m': stuck,
        'obligations_over_15m': obligations,
        'terminal_unrecovered_speech_fraction': fraction,
        'conversation_count_batch': census.get('conversation_count_batch'),
        'conversation_count_legacy': census.get('conversation_count_legacy'),
        'duration_seconds_batch': census.get('duration_seconds_batch'),
        'duration_seconds_legacy': census.get('duration_seconds_legacy'),
        'systematic_difference': census.get('systematic_difference'),
    }
