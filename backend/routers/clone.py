import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

import utils.other.endpoints as auth
from models.clone import (
    CloneAskRequest,
    CloneAskResponse,
    CloneBenchmarkRequest,
    CloneBenchmarkResult,
    CloneReplyRequest,
    CloneReplyResponse,
)
from utils.llm.clone_benchmark import benchmark_clone
from utils.llm.on_behalf import answer_personal_question, draft_on_behalf_reply
from utils.subscription import enforce_chat_quota

# The AI clone endpoints live in their own router (not chat.py) so the on-behalf
# LLM + deep-memory import chain is not pulled into the hot chat path.
router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/v1/clone/reply', tags=['clone'], response_model=CloneReplyResponse)
def clone_reply(
    data: CloneReplyRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "chat:reply_draft")),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    """Draft a reply on the user's behalf for a chat-app contact (the AI clone).

    Grounds the reply in the user's persona, memories, and the contact thread, and
    returns a send decision (review-first by default; auto-send only when every
    guardrail in the send policy passes).
    """
    enforce_chat_quota(uid, platform=x_app_platform)
    try:
        return draft_on_behalf_reply(uid, data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error('clone_reply_failed uid=%s error=%s', uid, e)
        raise HTTPException(status_code=500, detail='Failed to draft reply')


@router.post('/v1/clone/benchmark', tags=['clone'], response_model=CloneBenchmarkResult)
def clone_benchmark(
    data: CloneBenchmarkRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "chat:clone_benchmark")),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    """Benchmark the clone against the user's own past replies (Nik's method).

    For each (incoming, actual_reply) pair, drafts a reply and judges whether it is a
    good stand-in, returning a match rate the user can trust before enabling auto-send.
    A single sample draws several LLM calls, so this has its own tighter rate bucket.
    """
    enforce_chat_quota(uid, platform=x_app_platform)
    try:
        return benchmark_clone(uid, data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error('clone_benchmark_failed uid=%s error=%s', uid, e)
        raise HTTPException(status_code=500, detail='Failed to run clone benchmark')


@router.post('/v1/clone/ask', tags=['clone'], response_model=CloneAskResponse)
def clone_ask(
    data: CloneAskRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "chat:reply_draft")),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    """Answer a personal question about/as the user, grounded in their memory bank + persona
    (the clone's "what do you know about me?")."""
    enforce_chat_quota(uid, platform=x_app_platform)
    try:
        return answer_personal_question(uid, data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error('clone_ask_failed uid=%s error=%s', uid, e)
        raise HTTPException(status_code=500, detail='Failed to answer question')
