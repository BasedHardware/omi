"""Scheduled push coordinator for EXP-005; default dark and aggregate-only receipts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config.first_value_recovery import recovery_enabled
from database import first_value_recovery as recovery
from utils.notification_dispatch import NotificationIntent, NotificationKind, dispatch_notification
from utils.product_telemetry import emit_product_event

logger = logging.getLogger(__name__)

CAPTURE_TITLE = 'Reconnect your Omi pendant'
CAPTURE_BODY = 'Open Omi to check your pendant connection and make your first capture.'
RESULT_TITLE = 'Your Omi result is ready'
RESULT_BODY = 'Open Omi to read your result.'
CAPTURE_DATA = {'push_type': 'capture_recovery', 'action': 'repair_device'}
# The generic route is a released-client fallback. New clients resolve the exact
# ready-result route after authentication without carrying an object id in FCM.
RESULT_DATA = {
    'notification_type': 'first_value_ready_result',
    'action': 'open_ready_result',
    'navigate_to': '/conversations',
}


@dataclass
class DispatchSummary:
    considered: int = 0
    claimed: int = 0
    delivered: int = 0
    suppressed: int = 0
    failed: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def note(self, reason: str) -> None:
        self.reasons[reason] = self.reasons.get(reason, 0) + 1


def _event(uid: str, variant: str, kind: str, stage: str, outcome: str, channel: str = 'push') -> None:
    emit_product_event(
        uid=uid,
        event='First Value Recovery Delivery' if stage == 'delivery' else 'First Value Recovery Eligibility',
        properties={
            'experiment_id': recovery.EXPERIMENT_ID,
            'variant': variant,
            'kind': kind,
            'channel': channel,
            'outcome': outcome,
        },
    )


def _intent(uid: str, kind: str) -> NotificationIntent:
    capture = kind == recovery.CAPTURE
    return NotificationIntent(
        user_id=uid,
        title=CAPTURE_TITLE if capture else RESULT_TITLE,
        body=CAPTURE_BODY if capture else RESULT_BODY,
        source='first_value_recovery',
        kind=NotificationKind.CAPTURE_RECOVERY if capture else NotificationKind.FIRST_VALUE_RESULT,
        data=CAPTURE_DATA if capture else RESULT_DATA,
    )


def run_first_value_recovery_dispatch(
    *,
    now: datetime,
    firestore_client: Any = None,
    limit: int = recovery.MAX_PUSH_PROBES_PER_RUN,
) -> DispatchSummary:
    """The kill switch precedes selection and is rechecked immediately before FCM."""

    summary = DispatchSummary()
    if not recovery_enabled():
        return summary
    candidates = recovery.due_push_starts(now=now, firestore_client=firestore_client, limit=limit)
    if len(candidates) >= limit:
        summary.note('bounded_backlog')
    for candidate in candidates:
        summary.considered += 1
        uid = str(candidate.get('uid') or '')
        start_id = str(candidate['start_id'])
        try:
            start = recovery.probe_start(uid, start_id, candidate, now=now, firestore_client=firestore_client)
            claimed_result = False
            for kind in recovery.iter_candidate_kinds(start, now=now):
                access = recovery.push_access(uid, now=now, firestore_client=firestore_client)
                if not access['notifications_authorized']:
                    summary.suppressed += 1
                    summary.note('notification_permission')
                    _event(uid, str(start.get('variant')), kind, 'eligibility', 'notification_permission')
                    continue
                if kind == recovery.CAPTURE and not access['recent_pendant']:
                    summary.suppressed += 1
                    summary.note('recent_pendant_required')
                    _event(uid, str(start.get('variant')), kind, 'eligibility', 'recent_pendant_required')
                    continue
                claim = recovery.claim_prompt(
                    uid, start_id, start, kind, 'push', now=now, firestore_client=firestore_client
                )
                if claim is None:
                    summary.suppressed += 1
                    summary.note('claim_suppressed')
                    continue
                summary.claimed += 1
                claimed_result = claimed_result or kind == recovery.RESULT
                # A disable/cohort-zero flip after the query or claim still wins.
                if not recovery_enabled():
                    summary.suppressed += 1
                    summary.note('killed_before_dispatch')
                    return summary
                outcome = dispatch_notification(_intent(uid, kind))
                delivered = bool(outcome.delivered and outcome.delivered > 0)
                outcome_name = 'accepted' if delivered else 'undeliverable'
                recovery.mark_delivery(uid, start_id, kind, outcome_name, now=now, firestore_client=firestore_client)
                _event(uid, str(start.get('variant')), kind, 'delivery', outcome_name)
                if delivered:
                    summary.delivered += 1
                else:
                    summary.failed += 1
            next_probe = None
            expires_at = start.get('expires_at')
            if (
                not claimed_result
                and start.get('result_opened_at') is None
                and isinstance(expires_at, datetime)
                and now + recovery.PROBE_INTERVAL < expires_at
            ):
                next_probe = now + recovery.PROBE_INTERVAL
            recovery.set_next_push_probe(uid, start_id, next_probe, firestore_client=firestore_client)
        except Exception as error:
            summary.failed += 1
            summary.note(f'error_{type(error).__name__}')
            # One malformed/failing start never exposes its identity in logs or
            # retries as an unbounded queue. Its next due probe is preserved.
            logger.warning('first-value recovery probe failed error_type=%s', type(error).__name__)
    logger.info(
        'first_value_recovery considered=%d claimed=%d delivered=%d suppressed=%d failed=%d reasons=%s',
        summary.considered,
        summary.claimed,
        summary.delivered,
        summary.suppressed,
        summary.failed,
        sorted(summary.reasons.items()),
    )
    return summary
