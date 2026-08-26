"""Screen-frame egress (meeting-note screenshots) — contract §1, §6.

The one property that must not be broken: the client never decides what may
be stored. It uploads candidate bytes; this router canonicalises them,
judges those exact bytes, mints an internal approval, and only a holder of
that approval (utils/screen_frames/writer.py) may write to the screenshot
bucket. There is no client-supplied verdict anywhere in this router.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

import database.conversations as conversations_db
import database.redis_db as redis_db
import database.screen_frames as screen_frames_db
import database.users as users_db
from models.conversation_enums import ConversationStatus, ConversationVisibility
from models.screen_frame import (
    ConversationScreenFrameSet,
    ScreenFrameAdjudicationRequest,
    ScreenFrameAdjudicationResponse,
    ScreenFrameCandidateIn,
    ScreenFrameSettings,
    ScreenFrameSettingsUpdateRequest,
    ScreenFrameSharingUpdateRequest,
)
from utils.other import endpoints as auth
from utils.screen_frames import enforcement, store as screen_frame_store
from utils.screen_frames.availability import screen_frame_egress_enabled
from utils.screen_frames.pipeline import (
    ScreenFrameDigestMismatch,
    adjudicate_candidate,
    decode_and_verify_transport_digest,
)
from utils.screen_frames.policy import get_purpose_policy
from utils.screen_frames.writer import ScreenFrameWriteError

logger = logging.getLogger(__name__)

router = APIRouter()

# Defensive cap on a single candidate's decoded size. Not stated numerically
# in the contract (which only says "413 size/count" belongs in the error
# vocabulary); this is a conservative bound chosen to keep canonicalization
# cheap and flagged here as an assumption for review.
MAX_CANDIDATE_DECODED_BYTES = 20 * 1024 * 1024

CAPTURE_WINDOW_SLACK_SECONDS = 120
IDEMPOTENCY_TTL_SECONDS = 86400
EMPTY_FRAME_SET = ConversationScreenFrameSet(revision=0, banner=None, strip=[])


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _get_owned_conversation(uid: str, conversation_id: str) -> Dict[str, Any]:
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation is None or conversations_db.is_soft_deleted(conversation):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _require_adjudication_admission(uid: str, conversation: Dict[str, Any]) -> None:
    """Contract §6 admission checks that apply before any judging: existence
    and ownership are already established by the caller via
    _get_owned_conversation; this covers status + the account setting.
    """
    status = conversation.get('status')
    if status != ConversationStatus.completed.value and status != ConversationStatus.completed:
        raise HTTPException(status_code=409, detail={"code": "conversation_not_completed"})
    if not users_db.get_meeting_note_screenshots_enabled(uid):
        raise HTTPException(status_code=409, detail={"code": "meeting_note_screenshots_disabled"})


def _validate_capture_window(conversation: Dict[str, Any], candidates: List[ScreenFrameCandidateIn]) -> None:
    started_at = conversation.get('started_at')
    finished_at = conversation.get('finished_at')
    if started_at is None or finished_at is None:
        raise HTTPException(status_code=400, detail={"code": "conversation_window_unavailable"})
    started_at = _ensure_aware(started_at)
    finished_at = _ensure_aware(finished_at)
    lower = started_at - timedelta(seconds=CAPTURE_WINDOW_SLACK_SECONDS)
    upper = finished_at + timedelta(seconds=CAPTURE_WINDOW_SLACK_SECONDS)
    for candidate in candidates:
        captured_at = _ensure_aware(candidate.captured_at)
        if not (lower <= captured_at <= upper):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "captured_at_outside_conversation_window",
                    "client_frame_id": candidate.client_frame_id,
                },
            )


def _request_fingerprint(request: ScreenFrameAdjudicationRequest) -> str:
    payload = {
        "subject": request.subject.model_dump(mode="json"),
        "candidates": [
            {
                "client_frame_id": c.client_frame_id,
                "captured_at": c.captured_at.isoformat(),
                "mime_type": c.mime_type,
                "declared_width": c.declared_width,
                "declared_height": c.declared_height,
                "sha256_base64": c.sha256_base64,
            }
            for c in request.candidates
        ],
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.get(
    "/v1/screen-frame-egress/settings",
    response_model=ScreenFrameSettings,
    tags=["screen_frames"],
)
def get_screen_frame_settings(uid: str = Depends(auth.get_current_user_uid)):
    """Account-level, shared across every device (desktop, web, a
    reinstall) — this is the setting the adjudication route's admission
    check reads (contract §6). It protects the user from themselves, not
    third parties from the user (the privacy judge does that), so it lives
    as a plain user-profile field rather than a signed claim.
    """
    return ScreenFrameSettings(meeting_note_screenshots_enabled=users_db.get_meeting_note_screenshots_enabled(uid))


@router.patch(
    "/v1/screen-frame-egress/settings",
    response_model=ScreenFrameSettings,
    tags=["screen_frames"],
)
def update_screen_frame_settings(
    request: ScreenFrameSettingsUpdateRequest, uid: str = Depends(auth.get_current_user_uid)
):
    users_db.set_meeting_note_screenshots_enabled(uid, request.meeting_note_screenshots_enabled)
    return ScreenFrameSettings(meeting_note_screenshots_enabled=request.meeting_note_screenshots_enabled)


@router.post(
    "/v1/screen-frame-egress/adjudications",
    response_model=ScreenFrameAdjudicationResponse,
    tags=["screen_frames"],
)
def adjudicate_screen_frames(
    request: ScreenFrameAdjudicationRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "screenshots:adjudicate")),
):
    # Before anything else, and specifically before the judge: the judge is the
    # first step that sends screen bytes to Gemini, and it runs two stages ahead
    # of any bucket or signer check. 409 rather than 200-with-empty-set on
    # purpose — this must not stamp `screen_frames_adjudicated_at`, or a
    # conversation adjudicated while the feature was off would never be retried
    # once it is switched on. The client treats any 4xx as "render nothing, try
    # again next open", which is exactly right here.
    if not screen_frame_egress_enabled():
        raise HTTPException(status_code=409, detail={"code": "screen_frame_egress_unavailable"})

    policy = get_purpose_policy(request.purpose)
    if policy is None:
        raise HTTPException(status_code=400, detail={"code": "unknown_purpose"})

    if request.subject.kind != policy.subject_kind:
        raise HTTPException(status_code=400, detail={"code": "unsupported_subject_kind"})

    conversation = _get_owned_conversation(uid, request.subject.id)
    _require_adjudication_admission(uid, conversation)
    _validate_capture_window(conversation, request.candidates)

    for candidate in request.candidates:
        try:
            decoded_len = len(candidate.bytes_base64) * 3 // 4  # cheap upper-bound estimate pre-decode
        except Exception:
            decoded_len = 0
        if decoded_len > MAX_CANDIDATE_DECODED_BYTES:
            raise HTTPException(
                status_code=413, detail={"code": "candidate_too_large", "client_frame_id": candidate.client_frame_id}
            )

    # Step 1 (contract §4) for every candidate, up front: a digest mismatch
    # fails the whole request rather than silently dropping one frame — it
    # signals a transport bug or tampering, not a quality judgement.
    decoded_by_id: Dict[str, bytes] = {}
    for candidate in request.candidates:
        try:
            decoded_by_id[candidate.client_frame_id] = decode_and_verify_transport_digest(candidate)
        except ScreenFrameDigestMismatch as error:
            raise HTTPException(
                status_code=400,
                detail={"code": str(error), "client_frame_id": candidate.client_frame_id},
            ) from error

    fingerprint = _request_fingerprint(request)
    attempt_id = str(request.attempt_id)
    existing_fingerprint = redis_db.reserve_screen_frame_adjudication_attempt(
        uid, request.purpose, attempt_id, fingerprint, ttl=IDEMPOTENCY_TTL_SECONDS
    )
    if existing_fingerprint is not None:
        if existing_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail={"code": "attempt_id_reused_with_different_request"})
        stored = redis_db.get_screen_frame_adjudication_response(uid, request.purpose, attempt_id)
        if stored is not None:
            return ScreenFrameAdjudicationResponse.model_validate(stored)
        # Reserved but not yet finished (concurrent duplicate, or a crash
        # mid-request) — nothing safe to replay yet.
        raise HTTPException(status_code=503, detail={"code": "adjudication_in_progress_retry"})

    try:
        new_frames = []
        for candidate in request.candidates:
            outcome = adjudicate_candidate(
                uid=uid,
                purpose=request.purpose,
                subject_id=request.subject.id,
                policy=policy,
                candidate=candidate,
                raw_bytes=decoded_by_id[candidate.client_frame_id],
            )
            if outcome.written is not None:
                new_frames.append(outcome.written)
    except ScreenFrameWriteError as error:
        logger.error("screen_frame writer unavailable uid=%s error=%s", uid, error)
        raise HTTPException(status_code=503, detail={"code": "writer_unavailable"}) from error

    # Mark the attempt BEFORE building the response, and unconditionally — an all-rejected pass
    # is exactly the case this exists for. `revision` cannot record it, because nothing was
    # approved to bump it, so without this the client cannot tell that it already offered these
    # frames and had them refused, and re-uploads them on every reopen.
    screen_frames_db.mark_conversation_screen_frames_adjudicated(uid, request.subject.id)

    frame_set, committed = enforcement.enforce_and_persist(uid, request.subject.id, policy.max_persisted, new_frames)
    response = ScreenFrameAdjudicationResponse(
        attempt_id=request.attempt_id,
        outcome="committed" if committed else "no_approved_frames",
        frame_set=frame_set,
    )

    redis_db.store_screen_frame_adjudication_response(
        uid,
        request.purpose,
        attempt_id,
        fingerprint,
        json.loads(response.model_dump_json()),
        ttl=IDEMPOTENCY_TTL_SECONDS,
    )
    return response


@router.get(
    "/v1/conversations/{conversation_id}/screenshots",
    response_model=ConversationScreenFrameSet,
    tags=["screen_frames"],
)
def get_conversation_screenshots(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_owned_conversation(uid, conversation_id)
    # Contract §9: the account setting off means existing frames stay hidden. Enforced here
    # rather than in each client so every surface hides them the way the macOS gate already
    # does locally — without this, turning the setting off on desktop leaves the web banner
    # rendering the persisted set.
    if not users_db.get_meeting_note_screenshots_enabled(uid):
        return EMPTY_FRAME_SET
    return enforcement.build_frame_set_response(uid, conversation_id)


@router.delete(
    "/v1/conversations/{conversation_id}/screenshots/{frame_id}",
    response_model=ConversationScreenFrameSet,
    tags=["screen_frames"],
)
def delete_conversation_screenshot(conversation_id: str, frame_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_owned_conversation(uid, conversation_id)
    existed = screen_frame_store.delete_screen_frame(uid, conversation_id, frame_id)
    if not existed:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return enforcement.promote_banner_after_deletion(uid, conversation_id)


@router.delete(
    "/v1/conversations/{conversation_id}/screenshots",
    response_model=ConversationScreenFrameSet,
    tags=["screen_frames"],
)
def delete_all_conversation_screenshots(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_owned_conversation(uid, conversation_id)
    screen_frame_store.delete_conversation_screen_frames(uid, conversation_id)
    screen_frames_db.bump_conversation_screen_frames_revision(uid, conversation_id)
    return enforcement.build_frame_set_response(uid, conversation_id)


@router.patch(
    "/v1/conversations/{conversation_id}/screenshot-sharing",
    response_model=ConversationScreenFrameSet,
    tags=["screen_frames"],
)
def update_conversation_screenshot_sharing(
    conversation_id: str, request: ScreenFrameSharingUpdateRequest, uid: str = Depends(auth.get_current_user_uid)
):
    _get_owned_conversation(uid, conversation_id)
    screen_frames_db.set_conversation_screenshot_sharing_enabled(uid, conversation_id, request.enabled)
    return enforcement.build_frame_set_response(uid, conversation_id)


@router.get(
    "/v1/conversations/{conversation_id}/shared/screenshots",
    response_model=ConversationScreenFrameSet,
    tags=["screen_frames"],
)
def get_shared_conversation_screenshots(conversation_id: str):
    """Public, unauthenticated. Returns an empty set unless the conversation
    is currently shareable AND screenshot_sharing_enabled is true — never a
    404, so this route cannot be used to probe whether a conversation_id
    exists (contract §1/§9, and matches the existing
    GET /v1/conversations/{id}/shared 404-avoidance pattern for public
    conversation lookups... except this one specifically must not leak
    existence via status code, so it always returns 200).
    """
    uid = redis_db.get_conversation_uid(conversation_id)
    if not uid:
        return EMPTY_FRAME_SET

    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation is None or conversations_db.is_soft_deleted(conversation):
        return EMPTY_FRAME_SET

    visibility = conversation.get('visibility', ConversationVisibility.private)
    if not visibility or visibility == ConversationVisibility.private:
        return EMPTY_FRAME_SET

    if not screen_frames_db.get_conversation_screenshot_sharing_enabled(conversation):
        return EMPTY_FRAME_SET

    # The owner's account-level gate (contract §9): off hides existing frames here
    # too, not just on the owner's own devices. Still an empty set, never a 404.
    if not users_db.get_meeting_note_screenshots_enabled(uid):
        return EMPTY_FRAME_SET

    return enforcement.build_frame_set_response(uid, conversation_id)
