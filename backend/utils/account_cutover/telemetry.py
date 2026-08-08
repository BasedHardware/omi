"""Privacy-safe telemetry for account cutover decisions.

Never logs raw user content, prompts, transcripts, or PII beyond uid-free
enums and generations.
"""

from __future__ import annotations

import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)

ACCOUNT_CUTOVER_TRANSITIONS_TOTAL = Counter(
    'omi_account_cutover_transitions_total',
    'Whole-account cutover state transitions',
    ['from_state', 'to_state', 'reason'],
)

ACCOUNT_CUTOVER_ACCESS_TOTAL = Counter(
    'omi_account_cutover_access_total',
    'Account cutover product-traffic access decisions',
    ['state', 'decision', 'client_action'],
)


def _safe(value: str, *, default: str = 'other', max_len: int = 64) -> str:
    text = (value or default).strip().lower() or default
    cleaned = ''.join(ch if ch.isalnum() or ch in '._:-' else '_' for ch in text)
    return cleaned[:max_len] or default


def record_cutover_transition(*, from_state: str, to_state: str, reason: str) -> None:
    from_label = _safe(from_state)
    to_label = _safe(to_state)
    reason_label = _safe(reason)
    try:
        ACCOUNT_CUTOVER_TRANSITIONS_TOTAL.labels(
            from_state=from_label,
            to_state=to_label,
            reason=reason_label,
        ).inc()
    except Exception:  # noqa: BLE001 — telemetry must never fail the path
        logger.debug('account cutover transition metric failed', exc_info=True)
    logger.info(
        'account_cutover_transition from_state=%s to_state=%s reason=%s',
        from_label,
        to_label,
        reason_label,
    )


def record_cutover_access_decision(*, state: str, decision: str, client_action: str) -> None:
    state_label = _safe(state)
    decision_label = _safe(decision)
    action_label = _safe(client_action)
    try:
        ACCOUNT_CUTOVER_ACCESS_TOTAL.labels(
            state=state_label,
            decision=decision_label,
            client_action=action_label,
        ).inc()
    except Exception:  # noqa: BLE001
        logger.debug('account cutover access metric failed', exc_info=True)
    logger.info(
        'account_cutover_access state=%s decision=%s client_action=%s',
        state_label,
        decision_label,
        action_label,
    )


__all__ = [
    'ACCOUNT_CUTOVER_ACCESS_TOTAL',
    'ACCOUNT_CUTOVER_TRANSITIONS_TOTAL',
    'record_cutover_access_decision',
    'record_cutover_transition',
]
