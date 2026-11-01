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
from datetime import datetime, timezone
from typing import Any, Iterable

from prometheus_client import Counter as PromCounter

from config.dream_agent import KNOWN_KINDS
from config.dream_levers import telemetry_enabled

logger = logging.getLogger(__name__)
ERRORS = PromCounter('omi_dream_telemetry_error_total', 'Dream telemetry records that failed to emit', ['record'])

# Set by drain(); worker tasks inherit it, so every pass record names its sweep.
SWEEP_ID: ContextVar[str | None] = ContextVar('dream_sweep_id', default=None)

STATUSES = ('complete', 'failed', 'not_admitted', 'waiting', 'deadline')
# User-visible impact per applied edit kind (David 2026-10-30: weight by user impact).
# North star: value per reservation-hour. Merges and memory fixes change what users read;
# a dismissed junk person mostly tidies a list. Unlisted kinds count 1.
VALUE_WEIGHTS = {
    'merge_conversations': 5,
    'merge_people': 4,
    'merge_memories': 4,
    'resolve_required_memory': 4,
    'memory': 3,
    'retire_memory': 3,
    'supersede_memory': 3,
    'merge_tasks': 3,
    'close_task': 3,
    'retire_task': 2,
    'title': 2,
    'overview': 2,
    'entity_summary': 2,
    'set_language': 2,
    'vocabulary': 2,
    'spelling': 1,
    'dismiss_person': 1,
}


def value(outcomes: Iterable[Any] | None) -> int:
    """Impact-weighted count of applied edits."""
    return sum(
        VALUE_WEIGHTS.get(str(row.get('kind')), 1)
        for row in outcomes or []
        if isinstance(row, dict) and row.get('status') == 'applied'
    )


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
    try:
        instant = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return (instant.astimezone(timezone.utc) if instant.tzinfo else instant).isoformat()
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _kind(value: Any) -> str:
    return str(value) if value in KNOWN_KINDS else 'other'


OUTCOME_DECISIONS = frozenset({'undo', 'redo', 'accept', 'dismiss'})


def _age(applied_at: Any, now: datetime) -> str:
    if not isinstance(applied_at, datetime):
        return 'none'
    days = (now - applied_at).total_seconds() / 86400
    return 'lt1d' if days < 1 else 'lt7d' if days < 7 else 'lt30d' if days < 30 else 'gte30d'


def outcome_payload(kind: Any, decision: Any, *, applied_at: Any = None, now: datetime | None = None) -> dict[str, Any]:
    return {
        'event': 'dream_outcome',
        'kind': _kind(kind),
        'decision': decision if decision in OUTCOME_DECISIONS else 'other',
        'age': _age(applied_at, now or datetime.now(timezone.utc)),
    }


def record_outcome(kind: Any, decision: Any, *, applied_at: Any = None) -> None:
    """One owner decision on a Dream edit: Undo, Redo, or a Review accept/dismiss. Never raises."""
    try:
        payload = outcome_payload(kind, decision, applied_at=applied_at)
    except Exception as error:
        try:
            ERRORS.labels('outcome').inc()
            logger.warning('event=dream_telemetry_error record=outcome exc=%s', type(error).__name__)
        except Exception:
            pass
        return
    _emit('outcome', payload)


def change_kind(data: Any) -> str | None:
    """Policy kind of a journaled Dream change: its edit_kind, else its key segment.

    Accepted proposals are re-keyed ``agent:user:<uuid>`` and memory-target
    spelling keys use ``memory``; both keep the real kind in ``edit_kind``.
    """
    try:
        if not isinstance(data, dict) or dream_kind(data.get('edit_key')) is None:
            return None
        edit_kind = (data.get('change') or {}).get('edit_kind')
        return edit_kind if isinstance(edit_kind, str) and edit_kind else dream_kind(data.get('edit_key'))
    except Exception:
        return None


def dream_kind(edit_key: Any) -> str | None:
    """The kind of a Dream-authored edit key (``dream:<kind>:…``), else None."""
    if not isinstance(edit_key, str) or not edit_key.startswith(('dream:', 'agent:')):
        return None
    parts = edit_key.split(':')
    return parts[1] if len(parts) > 1 else None


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
        'verify_reasons': {_label(key): _int(count) for key, count in (report.get('verify_reasons') or {}).items()},
        'verifier_by_kind': {
            _kind(kind): {_label(decision): _int(count) for decision, count in row.items()}
            for kind, row in (report.get('verifier_by_kind') or {}).items()
            if isinstance(row, dict)
        },
        'staged': sum(len(rows) for rows in (report.get('proposed') or {}).values() if isinstance(rows, list)),
        'outcomes': _counts(row.get('status') for row in outcomes if isinstance(row, dict)),
        'applied': _counts(
            row.get('kind') if row.get('kind') in KNOWN_KINDS else 'other'
            for row in outcomes
            if isinstance(row, dict) and row.get('status') == 'applied'
        ),
        'value': value(outcomes),
        'wait_ms': _int(timing.get('wait_ms')),
        'waits': _int(timing.get('waits')),
        'wait_gateway_ms': _int(timing.get('wait_gateway_ms')),
        'wait_headroom_ms': _int(timing.get('wait_headroom_ms')),
        'wait_cause': _label(report.get('wait_cause')),
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


_JUDGE_KEYS = ('kind', 'stratum', 'verdict', 'grounded', 'owner_appropriate', 'useful')


def record_judgment(row: dict[str, Any]) -> None:
    """One content-free value-judge record (scores are -1 when unjudged)."""
    try:
        payload: dict[str, Any] = {'event': 'dream_judge'}
        for key in _JUDGE_KEYS:
            value = row.get(key)
            payload[key] = value if isinstance(value, int) and -1 <= value <= 2 else _label(value)
    except Exception:
        ERRORS.labels('judge').inc()
        return
    _emit('judge', payload)


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
        'waiting_causes': _counts(
            report.get('wait_cause') or 'drain' for report in reports if report.get('status') == 'waiting'
        ),
        'failure_types': _counts(report.get('error_type') for report in finals if report.get('status') == 'failed'),
        'applied': sum(
            1
            for report in finals
            for row in report.get('outcomes') or []
            if isinstance(row, dict) and row.get('status') == 'applied'
        ),
        'value': sum(value(report.get('outcomes')) for report in finals),
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
