"""Durable meeting-treatment receipt and Chat-intent projection.

The finalization job is authoritative. Conversation fields are a read projection
for API and post-processing consumers; the Chat intent is an idempotent derived
artifact keyed by ``capture:{conversation_id}``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from database import conversation_finalization_jobs as jobs_db
from database import conversations as conversations_db
from database.firestore_read_metrics import FirestoreReadSite
from utils.conversations.meeting_treatment import meeting_treatment_verdict
from utils.task_intelligence.proactive_engine import (
    persist_capture_arrival_intent,
    recommended_meeting_action_items,
)


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def is_desktop_meeting_role(conversation: Any) -> bool:
    source = _value(conversation, 'source')
    source_value = getattr(source, 'value', source)
    external_data = _value(conversation, 'external_data') or {}
    return (
        source_value == 'desktop'
        and isinstance(external_data, Mapping)
        and external_data.get('conversation_role') == 'meeting'
    )


def projected_meeting_treatment_eligible(conversation: Any) -> bool:
    """Read the durable conversation projection without recomputing policy."""
    return bool(_value(conversation, 'meeting_treatment_eligible', False))


def record_finalized_meeting_receipt(
    uid: str,
    conversation: Any,
    *,
    finalization_job_id: str | None = None,
    firestore_client: Any = None,
) -> dict[str, Any] | None:
    """Persist one auditable verdict for a finalized desktop meeting."""
    status = _value(conversation, 'status')
    status_value = getattr(status, 'value', status)
    if status_value != 'completed' or bool(_value(conversation, 'deferred', False)):
        return None
    if not is_desktop_meeting_role(conversation):
        return None
    conversation_id = _value(conversation, 'id')
    if not isinstance(conversation_id, str) or not conversation_id:
        return None
    verdict = meeting_treatment_verdict(conversation)
    return jobs_db.record_meeting_receipt(
        uid,
        conversation_id,
        finalization_job_id=finalization_job_id,
        eligible=verdict.eligible,
        reason=verdict.reason,
        duration_s=verdict.duration_s,
        dedup_speech_s=verdict.dedup_speech_s,
        firestore_client=firestore_client,
    )


def persist_receipt_intent(uid: str, conversation: Any, receipt: Mapping[str, Any]) -> str | None:
    """Create the stable conversationLink intent and attach it to its receipt."""
    if not bool(receipt.get('meeting_treatment_eligible')):
        return None
    job_id = receipt.get('job_id')
    conversation_id = _value(conversation, 'id')
    if not isinstance(job_id, str) or not isinstance(conversation_id, str):
        return None
    structured = _value(conversation, 'structured') or {}
    title = _value(structured, 'title', '') or ''
    overview = _value(structured, 'overview', '') or ''
    intent = persist_capture_arrival_intent(
        uid,
        conversation_id=conversation_id,
        summary=title or overview,
        is_desktop_meeting=True,
        recommended_action_items=recommended_meeting_action_items(structured),
    )
    if intent is None:
        return None
    if not jobs_db.mark_meeting_receipt_intent_persisted(job_id, intent.intent_id):
        return None
    return intent.intent_id


def record_and_persist_finalized_meeting_receipt(
    uid: str,
    conversation: Any,
    *,
    finalization_job_id: str | None = None,
    firestore_client: Any = None,
) -> dict[str, Any] | None:
    receipt = record_finalized_meeting_receipt(
        uid,
        conversation,
        finalization_job_id=finalization_job_id,
        firestore_client=firestore_client,
    )
    if receipt is not None and receipt.get('status') == 'recorded':
        persist_receipt_intent(uid, conversation, receipt)
    return receipt


def repair_meeting_receipt_intent(receipt: Mapping[str, Any]) -> bool:
    uid = receipt.get('uid')
    conversation_id = receipt.get('conversation_id')
    if not isinstance(uid, str) or not isinstance(conversation_id, str):
        return False
    conversation = conversations_db.get_conversation(
        uid, conversation_id, read_site=FirestoreReadSite.MEETING_RECEIPT_RECONCILER
    )
    if not conversation:
        return False
    return persist_receipt_intent(uid, conversation, receipt) is not None
