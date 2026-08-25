from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional

from models.memory_evidence import SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem

DEFAULT_SHORT_TERM_TTL_DAYS = 30
SHORT_TERM_LIFECYCLE_POLICY_VERSION = 'short_term_lifecycle.v1'


class ShortTermLifecycleOutcome(str, Enum):
    remain_short_term = 'remain_short_term'
    promote_to_long_term = 'promote_to_long_term'
    archive = 'archive'
    reject_or_hide = 'reject_or_hide'
    source_tombstoned = 'source_tombstoned'


class ShortTermDisposition(str, Enum):
    promote_to_long_term = 'promote_to_long_term'
    archive = 'archive'
    reject_or_hide = 'reject_or_hide'


@dataclass(frozen=True)
class ShortTermLifecycleDecision:
    outcome: ShortTermLifecycleOutcome
    default_access_allowed: bool
    requires_lifecycle_decision: bool
    audit_metadata: Dict[str, Any]


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('lifecycle timestamps must be timezone-aware')
    return value.astimezone(timezone.utc)


def default_short_term_expiry(captured_at: datetime) -> datetime:
    return _coerce_aware_utc(captured_at) + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS)


def _coerce_disposition(disposition: Optional[ShortTermDisposition | str]) -> Optional[ShortTermDisposition]:
    if disposition is None:
        return None
    return disposition if isinstance(disposition, ShortTermDisposition) else ShortTermDisposition(disposition)


def _audit_metadata(
    item: MemoryItem,
    *,
    now: datetime,
    decision_reason: str,
    expiry_at: datetime,
    disposition: Optional[ShortTermDisposition],
) -> Dict[str, Any]:
    return {
        'policy_version': SHORT_TERM_LIFECYCLE_POLICY_VERSION,
        'memory_id': item.memory_id,
        'uid': item.uid,
        'tier': item.tier.value,
        'status': item.status.value,
        'processing_state': item.processing_state.value,
        'source_state': item.source_state.value,
        'captured_at': _coerce_aware_utc(item.captured_at).isoformat(),
        'expires_at': expiry_at.isoformat(),
        'evaluated_at': now.isoformat(),
        'disposition': disposition.value if disposition else None,
        'decision_reason': decision_reason,
    }


def _decision(
    item: MemoryItem,
    *,
    now: datetime,
    expiry_at: datetime,
    outcome: ShortTermLifecycleOutcome,
    default_access_allowed: bool,
    requires_lifecycle_decision: bool,
    decision_reason: str,
    disposition: Optional[ShortTermDisposition] = None,
) -> ShortTermLifecycleDecision:
    return ShortTermLifecycleDecision(
        outcome=outcome,
        default_access_allowed=default_access_allowed,
        requires_lifecycle_decision=requires_lifecycle_decision,
        audit_metadata=_audit_metadata(
            item,
            now=now,
            decision_reason=decision_reason,
            expiry_at=expiry_at,
            disposition=disposition,
        ),
    )


def evaluate_short_term_lifecycle(
    item: MemoryItem,
    *,
    now: Optional[datetime] = None,
    disposition: Optional[ShortTermDisposition | str] = None,
) -> ShortTermLifecycleDecision:
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))
    if item.tier != MemoryTier.short_term:
        raise ValueError('short-term lifecycle policy only evaluates short_term memory items')

    expiry_at = _coerce_aware_utc(item.expires_at or default_short_term_expiry(item.captured_at))
    resolved_disposition = _coerce_disposition(disposition)

    if item.source_state in {SourceState.tombstoned, SourceState.purged}:
        return _decision(
            item,
            now=current_time,
            expiry_at=expiry_at,
            outcome=ShortTermLifecycleOutcome.source_tombstoned,
            default_access_allowed=False,
            requires_lifecycle_decision=False,
            decision_reason='source_tombstoned',
            disposition=resolved_disposition,
        )

    if item.status != MemoryItemStatus.active:
        return _decision(
            item,
            now=current_time,
            expiry_at=expiry_at,
            outcome=ShortTermLifecycleOutcome.reject_or_hide,
            default_access_allowed=False,
            requires_lifecycle_decision=False,
            decision_reason='short_term_not_active',
            disposition=resolved_disposition,
        )

    if item.processing_state == ProcessingState.processed:
        if resolved_disposition is not None:
            outcome = ShortTermLifecycleOutcome(resolved_disposition.value)
            return _decision(
                item,
                now=current_time,
                expiry_at=expiry_at,
                outcome=outcome,
                default_access_allowed=False,
                requires_lifecycle_decision=False,
                decision_reason=f'l2_processed_{resolved_disposition.value}',
                disposition=resolved_disposition,
            )
        return _decision(
            item,
            now=current_time,
            expiry_at=expiry_at,
            outcome=ShortTermLifecycleOutcome.remain_short_term,
            default_access_allowed=False,
            requires_lifecycle_decision=True,
            decision_reason='short_term_l2_processed_requires_explicit_lifecycle_disposition',
            disposition=resolved_disposition,
        )

    if expiry_at <= current_time:
        return _decision(
            item,
            now=current_time,
            expiry_at=expiry_at,
            outcome=ShortTermLifecycleOutcome.remain_short_term,
            default_access_allowed=False,
            requires_lifecycle_decision=True,
            decision_reason='short_term_expired_requires_lifecycle_decision',
            disposition=resolved_disposition,
        )

    return _decision(
        item,
        now=current_time,
        expiry_at=expiry_at,
        outcome=ShortTermLifecycleOutcome.remain_short_term,
        default_access_allowed=True,
        requires_lifecycle_decision=False,
        decision_reason='short_term_fresh',
        disposition=resolved_disposition,
    )
