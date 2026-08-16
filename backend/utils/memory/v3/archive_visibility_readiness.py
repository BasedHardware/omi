"""Canonical module for ``utils.memory.v3.archive_visibility_readiness`` (WS-G8b)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List

VISIBLE = 'visible'
NOT_VISIBLE = 'not_visible'
BLOCKED = 'BLOCKED'

_ALLOWED_VISIBILITIES = {'short_term', 'long_term', 'archived_evidence'}
_ALLOWED_LIFECYCLES = {'working', 'active', 'context_only', 'review', 'superseded', 'rejected', 'hidden', None, ''}
_ALLOWED_SOURCE_FRESHNESS = {'fresh', 'stable', 'historical', 'stale'}
_SENSITIVE_KEYS = {
    'content',
    'text',
    'quote',
    'evidence',
    'source_refs',
    'evidence_quotes',
    'cursor',
    'next_cursor',
    'page_token',
    'api_key',
    'token',
    'secret',
}


def _sanitized_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'memory_layer': decision.get('memory_layer') or 'unknown',
        'visibility': decision.get('visibility') or 'unknown',
        'source_freshness': decision.get('source_freshness') or 'unknown',
        'default_visible': bool(decision.get('default_visible')),
        'opt_in_visible': bool(decision.get('opt_in_visible')),
        'reason': decision.get('reason') or 'missing_reason',
        'agent_use': decision.get('agent_use') or 'not_available',
    }


def _drop_sensitive_fields(record: Dict[str, Any]) -> Dict[str, Any]:
    return {key: deepcopy(value) for key, value in record.items() if key not in _SENSITIVE_KEYS}


def decide_default_visibility(
    record: Dict[str, Any],
    *,
    include_archive: bool = False,
    include_historical: bool = False,
    server_archive_capability: bool = False,
    server_historical_capability: bool = False,
) -> Dict[str, Any]:
    """Pure readiness-only default visibility decision for future GET /v3/memories.

    The contract is intentionally fail-closed. It does not call production services,
    import routers, mutate persistence, emit telemetry, or wire runtime behavior.
    """

    safe_record = _drop_sensitive_fields(dict(record))
    visibility = safe_record.get('visibility')
    lifecycle = safe_record.get('lifecycle_status') or safe_record.get('status')
    source_freshness = safe_record.get('source_freshness')
    memory_layer = safe_record.get('memory_layer')

    decision = {
        **safe_record,
        'default_visible': False,
        'opt_in_visible': False,
        'agent_use': 'not_default_visible',
        'reason': 'fail_closed',
    }

    if visibility not in _ALLOWED_VISIBILITIES:
        decision['reason'] = 'unknown_visibility_fail_closed'
        return decision
    if lifecycle not in _ALLOWED_LIFECYCLES:
        decision['reason'] = 'unknown_lifecycle_fail_closed'
        return decision
    if source_freshness not in _ALLOWED_SOURCE_FRESHNESS:
        decision['reason'] = 'unknown_source_freshness_fail_closed'
        return decision

    if lifecycle in {'hidden', 'rejected'}:
        decision['reason'] = 'hidden_or_rejected_fail_closed'
        return decision

    if visibility == 'archived_evidence' or memory_layer == 'l1_archive':
        if include_archive and include_historical:
            if server_archive_capability and server_historical_capability:
                decision['opt_in_visible'] = True
                decision['agent_use'] = 'archived_evidence_not_stable_profile'
                decision['reason'] = 'archive_visible_only_by_explicit_opt_in'
            else:
                decision['reason'] = 'archive_requires_server_capability'
        else:
            decision['reason'] = 'archive_requires_explicit_opt_in'
        return decision

    if visibility == 'short_term':
        if lifecycle != 'working':
            decision['reason'] = 'short_term_requires_approved_working_lifecycle'
            return decision
        if source_freshness == 'stale':
            if include_historical:
                decision['opt_in_visible'] = True
                decision['agent_use'] = 'historical_short_term_context_not_default_visible'
                decision['reason'] = 'stale_short_term_visible_only_by_explicit_opt_in'
            else:
                decision['reason'] = 'stale_short_term_requires_explicit_opt_in'
            return decision
        if source_freshness != 'fresh':
            decision['reason'] = 'short_term_requires_fresh_source'
            return decision
        if safe_record.get('source_backed_projection') is not True:
            decision['reason'] = 'short_term_requires_source_backed_projection'
            return decision
        decision['default_visible'] = True
        decision['agent_use'] = 'fresh_short_term_source_backed_context'
        decision['reason'] = 'fresh_short_term_source_backed_default_visible'
        return decision

    if visibility == 'long_term':
        if lifecycle == 'active' and source_freshness == 'stable':
            decision['default_visible'] = True
            decision['agent_use'] = 'stable_profile_fact'
            decision['reason'] = 'active_long_term_default_visible'
            return decision
        if lifecycle in {'review', 'context_only', 'superseded'}:
            decision['reason'] = 'non_active_long_term_not_default_visible'
            return decision
        decision['reason'] = 'long_term_requires_active_stable_source'
        return decision

    return decision


def _sample_records() -> List[Dict[str, Any]]:
    return [
        {
            'memory_id': 'sample_archive',
            'memory_layer': 'l1_archive',
            'archive_class': 'general',
            'visibility': 'archived_evidence',
            'source_freshness': 'historical',
            'source_backed_projection': True,
        },
        {
            'memory_id': 'sample_stale_short',
            'memory_layer': 'working',
            'lifecycle_status': 'working',
            'visibility': 'short_term',
            'source_freshness': 'stale',
            'source_backed_projection': True,
        },
        {
            'memory_id': 'sample_fresh_short',
            'memory_layer': 'working',
            'lifecycle_status': 'working',
            'visibility': 'short_term',
            'source_freshness': 'fresh',
            'source_backed_projection': True,
        },
        {
            'memory_id': 'sample_long_term',
            'memory_layer': 'durable',
            'lifecycle_status': 'active',
            'visibility': 'long_term',
            'source_freshness': 'stable',
            'source_backed_projection': True,
        },
    ]


def evaluate_archive_short_term_visibility_readiness(
    *, sample_records: Iterable[Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    records = list(sample_records) if sample_records is not None else _sample_records()
    decisions = [decide_default_visibility(record) for record in records]
    sanitized_decisions = [_sanitized_decision(decision) for decision in decisions]
    reason_counts: Dict[str, int] = {}
    for decision in sanitized_decisions:
        reason = decision['reason']
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    default_visible_count = sum(1 for decision in sanitized_decisions if decision['default_visible'])
    opt_in_visible_count = sum(1 for decision in sanitized_decisions if decision['opt_in_visible'])

    return {
        'script': 'p1_3_v3_archive_short_term_visibility_readiness',
        'status': BLOCKED,
        'proof_status': BLOCKED,
        'approval': False,
        'read_only': True,
        'route_wiring': False,
        'runtime_behavior_changed': False,
        'production_call_count': 0,
        'firestore_read_count': 0,
        'firestore_write_count': 0,
        'network_call_count': 0,
        'telemetry_sink_call_count': 0,
        'provider_or_vector_call_count': 0,
        'legacy_fallback_or_merge': False,
        'case_count': len(sanitized_decisions),
        'default_visible_count': default_visible_count,
        'blocked_or_opt_in_required_count': len(sanitized_decisions) - default_visible_count,
        'opt_in_visible_count': opt_in_visible_count,
        'reason_counts': reason_counts,
        'decisions': sanitized_decisions,
        'contract': {
            'archive_default_visible': False,
            'stale_short_term_default_visible': False,
            'archive_requires_explicit_opt_in': True,
            'historical_context_requires_explicit_opt_in': True,
            'fresh_short_term_source_backed_projection_default_visible': True,
            'long_term_active_stable_synthesis_allowed': True,
            'unknown_visibility_lifecycle_or_freshness_fail_closed': True,
            'memory_failure_legacy_fallback_or_merge_allowed': False,
        },
        'summary': {
            'status': BLOCKED,
            'case_count': len(sanitized_decisions),
            'default_visible_count': default_visible_count,
            'blocked_or_opt_in_required_count': len(sanitized_decisions) - default_visible_count,
            'archive_opt_in_required_count': reason_counts.get('archive_requires_explicit_opt_in', 0),
            'server_capability_required_count': reason_counts.get('archive_requires_server_capability', 0),
        },
        'remaining_blocker': 'future GET /v3/memories route wiring and real service runtime evidence are intentionally absent',
    }


# Neutral symbol aliases (memory names remain valid via shim)
