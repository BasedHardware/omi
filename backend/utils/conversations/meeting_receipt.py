"""Durable meeting-treatment receipt without automatic Chat delivery.

The finalization job is authoritative. Conversation fields are a read projection
for API and post-processing consumers. Chat is reserved for user turns.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from database import conversation_finalization_jobs as jobs_db
from utils.conversations.meeting_treatment import meeting_treatment_verdict


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
