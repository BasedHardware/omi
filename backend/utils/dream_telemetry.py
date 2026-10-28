"""One structured record per Dream pass and per sweep; never raises into either.

Dream runs on Cloud Run, which Prometheus does not scrape, so these JSON log
lines are the source for log-based metrics and offline analysis. Every value is
a count, a duration, a uuid4 run/sweep id, or a label from an allowlist or a
bare identifier: no uid, ref, record text or exception message is ever logged.
"""

import json
import logging
import uuid
from collections import Counter
from contextvars import ContextVar
from typing import Any, Iterable

from prometheus_client import Counter as PromCounter

from config.dream_agent import KNOWN_KINDS
from config.dream_levers import telemetry_enabled

logger = logging.getLogger(__name__)
ERRORS = PromCounter('omi_dream_telemetry_error_total', 'Dream telemetry records that failed to emit', ['record'])

# Set by drain(); worker tasks inherit it, so every pass record names its sweep.
SWEEP_ID: ContextVar[str | None] = ContextVar('dream_sweep_id', default=None)

STATUSES = ('complete', 'failed', 'not_admitted', 'waiting', 'deadline')
_MAX_LABEL = 64


def _label(value: Any) -> str:
    """A short bare identifier passes; anything else is 'other' (or 'none' when empty)."""
    if value is None or value == '':
        return 'none'
    text = str(value)
    return text if len(text) <= _MAX_LABEL and text.isidentifier() else 'other'


def _uuid(value: Any) -> str:
    """Only a canonical uuid (minted by Dream, never derived from a uid) passes."""
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return 'none'


def _timestamp(value: Any) -> str | None:
    """An RFC 3339 instant from the Scheduler header, or None."""
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).isoformat()
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _counts(values: Iterable[Any]) -> dict[str, int]:
    return dict(sorted(Counter(_label(value) for value in values).items()))


def _emit(record: str, payload: dict[str, Any]) -> None:
    try:
        if not telemetry_enabled():
            return
        logger.info(json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str))
    except Exception as error:
        try:
            ERRORS.labels(record).inc()
            logger.warning('event=dream_telemetry_error record=%s exc=%s', record, type(error).__name__)
        except Exception:
            pass


def pass_payload(report: dict[str, Any]) -> dict[str, Any]:
    outcomes = report.get('outcomes') or []
    timing = report.get('timing') or {}
    feedback = report.get('defect_reports') or {}
    levers = report.get('levers') or {}
    status = report.get('status')
    return {
        'event': 'dream_pass',
        'sweep_id': _uuid(report.get('sweep_id') or SWEEP_ID.get()),
        'run_id': _uuid(report.get('run_id')),
        'trigger': _label(report.get('trigger')),
        'status': status if status in STATUSES else 'failed',
        'reason': _label(report.get('reason')),
        'error_type': _label(report.get('error_type')),
        'error_code': _label(report.get('error_code')),
        'stop_reason': _label(report.get('stop_reason')),
        'bucket': _label(report.get('size_bucket')),
        'material': _int(report.get('material')),
        'tokens': _int(report.get('tokens')),
        'weighted_tokens': _int(report.get('price_weighted_tokens')),
        'cached_tokens': _int(report.get('cached_tokens')),
        'uncached_tokens': _int(report.get('uncached_tokens')),
        'cache_unreported_tokens': _int(report.get('cache_unreported_tokens')),
        'first_prompt_tokens': _int(report.get('first_prompt_tokens')),
        'last_prompt_tokens': _int(report.get('last_prompt_tokens')),
        'completion_tokens': _int(report.get('completion_tokens')),
        'token_limit': _int(report.get('token_limit')),
        'turns': _int(report.get('turns')),
        'tool_calls': sum(_int(count) for count in (report.get('tool_counts') or {}).values()),
        'verifier_calls': _int(report.get('verifier_calls')),
        'staged': sum(len(rows) for rows in (report.get('proposed') or {}).values() if isinstance(rows, list)),
        'outcomes': _counts(row.get('status') for row in outcomes if isinstance(row, dict)),
        'applied': _counts(
            row.get('kind') if row.get('kind') in KNOWN_KINDS else 'other'
            for row in outcomes
            if isinstance(row, dict) and row.get('status') == 'applied'
        ),
        'wait_ms': _int(timing.get('wait_ms')),
        'waits': _int(timing.get('waits')),
        'seed_ms': _int(timing.get('seed_ms')),
        'model_ms': _int(timing.get('model_ms')),
        'verify_ms': _int(timing.get('verify_ms')),
        'total_ms': _int(timing.get('total_ms')),
        'levers': {
            _label(name): {
                _label(key): value if isinstance(value, (bool, int)) else _label(value) for key, value in row.items()
            }
            for name, row in levers.items()
            if isinstance(row, dict)
        },
        'defect_reports': {_label(key): _int(value) for key, value in feedback.items()},
        'cost_usd': round(float(report['cost_usd']), 4) if isinstance(report.get('cost_usd'), (int, float)) else None,
    }


def record_pass(report: dict[str, Any]) -> None:
    try:
        payload = pass_payload(report)
    except Exception as error:
        ERRORS.labels('pass').inc()
        logger.warning('event=dream_telemetry_error record=pass exc=%s', type(error).__name__)
        return
    _emit('pass', payload)


def sweep_payload(sweep: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, Any]:
    # Capacity waits retry the same owner; attempts and owners are counted separately.
    finals = sweep.get('finals')
    if not isinstance(finals, list):
        finals = reports
    return {
        'event': 'dream_sweep',
        'sweep_id': _uuid(sweep.get('sweep_id')),
        'retry_count': _int(sweep.get('retry_count')),
        'caller': sweep.get('caller') if sweep.get('caller') in {'scheduler', 'other', 'none'} else 'none',
        'scheduled_at': _timestamp(sweep.get('scheduled_at')),
        'due_owners': _int(sweep.get('due_owners')),
        'owners_started': _int(sweep.get('owners_started')),
        'owners_unreached': _int(sweep.get('owners_unreached')),
        'owners_inflight': _int(sweep.get('owners_inflight')),
        'attempts': len(reports),
        'final_status': _counts(report.get('status') for report in finals),
        'not_admitted': _counts(report.get('reason') for report in finals if report.get('status') == 'not_admitted'),
        'waiting_attempts': _counts(report.get('reason') for report in reports if report.get('status') == 'waiting'),
        'failure_types': _counts(report.get('error_type') for report in finals if report.get('status') == 'failed'),
        'applied': sum(
            1
            for report in finals
            for row in report.get('outcomes') or []
            if isinstance(row, dict) and row.get('status') == 'applied'
        ),
        'tokens': sum(_int(report.get('tokens')) for report in reports),
        'deadline': bool(sweep.get('deadline')),
        'capacity_closed': bool(sweep.get('capacity_closed')),
        'payoff_order': _label(sweep.get('payoff_order')),
        'reordered': _int(sweep.get('reordered')),
        'duration_ms': _int(sweep.get('duration_ms')),
    }


def record_sweep(sweep: dict[str, Any], reports: list[dict[str, Any]]) -> None:
    try:
        payload = sweep_payload(sweep, reports)
    except Exception as error:
        ERRORS.labels('sweep').inc()
        logger.warning('event=dream_telemetry_error record=sweep exc=%s', type(error).__name__)
        return
    _emit('sweep', payload)
