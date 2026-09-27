"""Authenticated mobile summary and recording quality feedback."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from database import conversations as conversations_db
from database import feedback as feedback_db
from database import recording_sessions as recording_sessions_db
from models.feedback import (
    FeedbackSurface,
    FeedbackTargetKind,
    MobileFeedbackKind,
    MobileFeedbackReceipt,
    MobileFeedbackRequest,
)
from utils.other import endpoints as auth
from utils.product_metrics import sanitize_app_build
from utils.product_telemetry import emit_product_event

router = APIRouter(tags=['mobile-feedback'])


def _provenance_from_conversation(conversation: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Copy only fields the backend already owns; leave unknowns absent."""
    if not isinstance(conversation, dict):
        return {}
    fields = {
        'backend_release': ('backend_release', 'processing_backend_release'),
        'model_name': ('model_name', 'summary_model', 'transcription_model'),
        'model_version': ('model_version', 'summary_model_version', 'transcription_model_version'),
        'prompt_name': ('prompt_name', 'summary_prompt_name'),
        'prompt_commit': ('prompt_commit', 'summary_prompt_commit'),
        'trace_id': ('trace_id', 'summary_trace_id'),
    }
    result: dict[str, Any] = {}
    for output, candidates in fields.items():
        for candidate in candidates:
            value = conversation.get(candidate)
            if value:
                result[output] = value
                break
    return result


def _header_or_payload(header: str | None, payload: str | None, *, max_length: int) -> str | None:
    value = (payload or header or '').strip()
    return value[:max_length] if value else None


@router.post('/v1/mobile/feedback', response_model=MobileFeedbackReceipt, status_code=201)
def submit_mobile_feedback(
    payload: MobileFeedbackRequest,
    x_app_platform: str | None = Header(None, alias='X-App-Platform'),
    x_app_version: str | None = Header(None, alias='X-App-Version'),
    x_app_build: str | None = Header(None, alias='X-App-Build'),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'memories:modify')),
) -> MobileFeedbackReceipt:
    """Persist one explicit mobile feedback action.

    Summary targets are authenticated conversation ids. Recording targets are
    authenticated recording-session ids whose user-scoped binding is read
    before the write. The idempotency key is scoped to the authenticated UID,
    so a retry is safe while a reused key with a different payload is rejected.
    """
    related_conversation_id: str | None = None
    resolved_target_kind = FeedbackTargetKind.conversation
    provenance: dict[str, Any] = {}
    if payload.kind is MobileFeedbackKind.summary_helpfulness or payload.target_kind == 'conversation':
        conversation = conversations_db.get_conversation(uid, payload.target_id)
        if not conversation:
            raise HTTPException(status_code=404, detail='Conversation not found')
        related_conversation_id = payload.target_id
        provenance = _provenance_from_conversation(conversation)
        resolved_target_kind = FeedbackTargetKind.conversation
    else:
        try:
            binding = recording_sessions_db.get_recording_session(uid, payload.target_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail='Recording ownership is temporarily unavailable') from exc
        if binding:
            related_conversation_id = binding['conversation_id']
            conversation = conversations_db.get_conversation(uid, related_conversation_id)
            if conversation:
                provenance = _provenance_from_conversation(conversation)
            resolved_target_kind = FeedbackTargetKind.recording
        elif payload.target_kind is None:
            # Older mobile builds only had the conversation id available on
            # the detail page. Preserve their authenticated ownership path
            # while new callers can make this coordinate explicit with
            # target_kind=conversation.
            conversation = conversations_db.get_conversation(uid, payload.target_id)
            if not conversation:
                raise HTTPException(status_code=404, detail='Recording not found')
            related_conversation_id = payload.target_id
            provenance = _provenance_from_conversation(conversation)
            resolved_target_kind = FeedbackTargetKind.conversation
        else:
            raise HTTPException(status_code=404, detail='Recording not found')

    app_version = _header_or_payload(x_app_version, payload.app_version, max_length=64)
    app_build = sanitize_app_build(payload.app_build, x_app_build, payload.app_version, x_app_version)
    platform = _header_or_payload(x_app_platform, payload.platform, max_length=32)
    if platform:
        platform = platform.lower()
    merged_provenance = {
        **provenance,
    }
    try:
        event_id, created = feedback_db.record_feedback_event_idempotent(
            uid,
            (
                FeedbackSurface.conversation_summary
                if payload.kind is MobileFeedbackKind.summary_helpfulness
                else FeedbackSurface.recording_quality
            ),
            resolved_target_kind,
            payload.target_id,
            payload.value,
            feedback_id=payload.feedback_id,
            reason=payload.reason.value if payload.reason else None,
            comment=payload.comment,
            platform=platform,
            app_version=app_version,
            feedback_kind=payload.kind,
            app_build=app_build if app_build != 'unknown' else None,
            client_app_namespace=payload.client_app_namespace,
            client_app_profile=payload.client_app_profile,
            backend_release=merged_provenance.get('backend_release'),
            model_name=merged_provenance.get('model_name'),
            model_version=merged_provenance.get('model_version'),
            prompt_name=merged_provenance.get('prompt_name'),
            prompt_commit=merged_provenance.get('prompt_commit'),
            trace_id=merged_provenance.get('trace_id'),
            correlation_id=payload.correlation_id,
            related_conversation_id=related_conversation_id,
        )
    except feedback_db.FeedbackIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail='feedback_id was already used for a different event') from exc
    except feedback_db.FeedbackPersistenceError as exc:
        raise HTTPException(status_code=503, detail='Feedback could not be durably stored; retry safely') from exc

    if created:
        emit_product_event(
            uid=uid,
            event='Product Feedback Submitted',
            properties={
                'feedback_id': payload.feedback_id,
                'event_id': event_id,
                'kind': payload.kind.value,
                'value': payload.value,
                'reason': payload.reason.value if payload.reason else None,
                'platform': platform,
                'app_version': app_version,
                'app_build': app_build,
                'client_app_namespace': payload.client_app_namespace,
                'client_app_profile': payload.client_app_profile,
                'backend_release': merged_provenance.get('backend_release'),
                'model_name': merged_provenance.get('model_name'),
                'model_version': merged_provenance.get('model_version'),
                'prompt_name': merged_provenance.get('prompt_name'),
                'prompt_commit': merged_provenance.get('prompt_commit'),
                'trace_id': merged_provenance.get('trace_id'),
                'correlation_id': payload.correlation_id,
            },
        )
    return MobileFeedbackReceipt(feedback_id=payload.feedback_id, event_id=event_id, created=created)
