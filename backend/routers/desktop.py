"""
Desktop-specific API endpoints.

Migrated from the Rust desktop backend to unify the data source of truth
in the Python backend. These endpoints serve the macOS desktop app for:
- Staged tasks (AI task queue)
- Focus sessions (focus/distraction tracking)
- Advice (proactive coaching)
- Chat sessions v2 (multi-session chat)
- Desktop messages v2 (chat persistence)
- Notification settings
- Assistant settings (proactive assistants config)
- AI user profile
- Daily score / scores
- Desktop LLM usage tracking
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

import database.desktop as desktop_db
from utils.other import endpoints as auth

router = APIRouter()


# ============================================================================
# REQUEST / RESPONSE MODELS
# ============================================================================

# --- Staged Tasks ---


class CreateStagedTaskRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000)
    due_at: Optional[datetime] = None
    source: Optional[str] = None
    priority: Optional[str] = None
    metadata: Optional[str] = None
    category: Optional[str] = None
    relevance_score: Optional[int] = Field(None, ge=0, le=1000)


class BatchScoreEntry(BaseModel):
    id: str = Field(..., min_length=1)
    relevance_score: int = Field(..., ge=0, le=1000)


class BatchUpdateScoresRequest(BaseModel):
    scores: List[BatchScoreEntry] = Field(..., max_length=500)


# --- Focus Sessions ---


class CreateFocusSessionRequest(BaseModel):
    status: str = Field(..., pattern=r'^(focused|distracted)$')
    app_or_site: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1, max_length=5000)
    message: Optional[str] = Field(None, max_length=5000)
    duration_seconds: Optional[int] = Field(None, ge=0, le=86400)


# --- Advice ---


class CreateAdviceRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    category: Optional[str] = Field(None, max_length=100)
    reasoning: Optional[str] = Field(None, max_length=5000)
    source_app: Optional[str] = Field(None, max_length=200)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    context_summary: Optional[str] = Field(None, max_length=5000)
    current_activity: Optional[str] = Field(None, max_length=500)


class UpdateAdviceRequest(BaseModel):
    is_read: Optional[bool] = None
    is_dismissed: Optional[bool] = None


# --- Chat Sessions ---


class CreateChatSessionRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    app_id: Optional[str] = Field(None, max_length=200)


class UpdateChatSessionRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    starred: Optional[bool] = None


# --- Messages ---


class SaveMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100000)
    sender: str = Field(..., pattern=r'^(human|ai)$')
    app_id: Optional[str] = Field(None, max_length=200)
    session_id: Optional[str] = Field(None, max_length=200)
    metadata: Optional[str] = None


class RateMessageRequest(BaseModel):
    rating: Optional[int] = Field(None, ge=-1, le=1)


# --- Notification Settings ---


class UpdateNotificationSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    frequency: Optional[int] = Field(None, ge=0, le=5)


# --- Assistant Settings (matches Swift AssistantSettingsResponse schema) ---


class SharedAssistantSettings(BaseModel):
    cooldown_interval: Optional[int] = None
    glow_overlay_enabled: Optional[bool] = None
    analysis_delay: Optional[int] = None
    screen_analysis_enabled: Optional[bool] = None


class FocusAssistantSettings(BaseModel):
    enabled: Optional[bool] = None
    analysis_prompt: Optional[str] = Field(None, max_length=10000)
    cooldown_interval: Optional[int] = None
    notifications_enabled: Optional[bool] = None
    excluded_apps: Optional[List[str]] = None


class TaskAssistantSettings(BaseModel):
    enabled: Optional[bool] = None
    analysis_prompt: Optional[str] = Field(None, max_length=10000)
    extraction_interval: Optional[float] = None
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    notifications_enabled: Optional[bool] = None
    allowed_apps: Optional[List[str]] = None
    browser_keywords: Optional[List[str]] = None


class AdviceAssistantSettings(BaseModel):
    enabled: Optional[bool] = None
    analysis_prompt: Optional[str] = Field(None, max_length=10000)
    extraction_interval: Optional[float] = None
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    notifications_enabled: Optional[bool] = None
    excluded_apps: Optional[List[str]] = None


class MemoryAssistantSettings(BaseModel):
    enabled: Optional[bool] = None
    analysis_prompt: Optional[str] = Field(None, max_length=10000)
    extraction_interval: Optional[float] = None
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    notifications_enabled: Optional[bool] = None
    excluded_apps: Optional[List[str]] = None


class UpdateAssistantSettingsRequest(BaseModel):
    shared: Optional[SharedAssistantSettings] = None
    focus: Optional[FocusAssistantSettings] = None
    task: Optional[TaskAssistantSettings] = None
    advice: Optional[AdviceAssistantSettings] = None
    memory: Optional[MemoryAssistantSettings] = None
    update_channel: Optional[str] = Field(None, max_length=50)


# --- AI Profile ---


class UpdateAIUserProfileRequest(BaseModel):
    profile_text: Optional[str] = Field(None, max_length=50000)
    generated_at: Optional[datetime] = None
    data_sources_used: Optional[int] = Field(None, ge=0)


# --- LLM Usage ---


class RecordLlmUsageRequest(BaseModel):
    input_tokens: int = Field(0, ge=0)
    output_tokens: int = Field(0, ge=0)
    cache_read_tokens: int = Field(0, ge=0)
    cache_write_tokens: int = Field(0, ge=0)
    total_tokens: int = Field(0, ge=0)
    cost_usd: float = Field(0.0, ge=0.0)
    account: str = Field('desktop_chat', max_length=100)


# ============================================================================
# STAGED TASKS ENDPOINTS
# ============================================================================


@router.post('/v1/staged-tasks', tags=['desktop'])
def create_staged_task(
    request: CreateStagedTaskRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.create_staged_task(
        uid,
        description=request.description,
        due_at=request.due_at,
        source=request.source,
        priority=request.priority,
        metadata=request.metadata,
        category=request.category,
        relevance_score=request.relevance_score,
    )


@router.get('/v1/staged-tasks', tags=['desktop'])
def get_staged_tasks(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    uid: str = Depends(auth.get_current_user_uid),
):
    fetch_limit = limit + 1
    items = desktop_db.get_staged_tasks(uid, limit=fetch_limit, offset=offset)
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]
    return {'items': items, 'has_more': has_more}


@router.delete('/v1/staged-tasks/{task_id}', tags=['desktop'])
def delete_staged_task(
    task_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    desktop_db.delete_staged_task(uid, task_id)
    return {'status': 'ok'}


@router.patch('/v1/staged-tasks/batch-scores', tags=['desktop'])
def batch_update_staged_scores(
    request: BatchUpdateScoresRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    desktop_db.batch_update_staged_scores(uid, [s.model_dump() for s in request.scores])
    return {'status': 'ok'}


@router.post('/v1/staged-tasks/promote', tags=['desktop'])
def promote_staged_task(uid: str = Depends(auth.get_current_user_uid)):
    return desktop_db.promote_staged_task(uid)


@router.post('/v1/staged-tasks/migrate', tags=['desktop'])
def migrate_ai_tasks(uid: str = Depends(auth.get_current_user_uid)):
    return desktop_db.migrate_ai_tasks(uid)


@router.post('/v1/staged-tasks/migrate-conversation-items', tags=['desktop'])
def migrate_conversation_items(uid: str = Depends(auth.get_current_user_uid)):
    return desktop_db.migrate_conversation_items_to_staged(uid)


# ============================================================================
# FOCUS SESSIONS ENDPOINTS
# ============================================================================


@router.post('/v1/focus-sessions', tags=['desktop'])
def create_focus_session(
    request: CreateFocusSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.create_focus_session(
        uid,
        status=request.status,
        app_or_site=request.app_or_site,
        description=request.description,
        message=request.message,
        duration_seconds=request.duration_seconds,
    )


@router.get('/v1/focus-sessions', tags=['desktop'])
def get_focus_sessions(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.get_focus_sessions(uid, limit=limit, offset=offset, date=date)


@router.delete('/v1/focus-sessions/{session_id}', tags=['desktop'])
def delete_focus_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    desktop_db.delete_focus_session(uid, session_id)
    return {'status': 'ok'}


@router.get('/v1/focus-stats', tags=['desktop'])
def get_focus_stats(
    date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.get_focus_stats(uid, date=date)


# ============================================================================
# ADVICE ENDPOINTS
# ============================================================================


@router.post('/v1/advice', tags=['desktop'])
def create_advice(
    request: CreateAdviceRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.create_advice(
        uid,
        content=request.content,
        category=request.category or 'other',
        reasoning=request.reasoning,
        source_app=request.source_app,
        confidence=request.confidence,
        context_summary=request.context_summary,
        current_activity=request.current_activity,
    )


@router.get('/v1/advice', tags=['desktop'])
def get_advice(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    category: Optional[str] = Query(None),
    include_dismissed: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.get_advice(
        uid, limit=limit, offset=offset, category=category, include_dismissed=include_dismissed
    )


@router.patch('/v1/advice/{advice_id}', tags=['desktop'])
def update_advice(
    advice_id: str,
    request: UpdateAdviceRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    result = desktop_db.update_advice(uid, advice_id, is_read=request.is_read, is_dismissed=request.is_dismissed)
    if result is None:
        raise HTTPException(status_code=404, detail='Advice not found')
    return result


@router.delete('/v1/advice/{advice_id}', tags=['desktop'])
def delete_advice(
    advice_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    desktop_db.delete_advice(uid, advice_id)
    return {'status': 'ok'}


@router.post('/v1/advice/mark-all-read', tags=['desktop'])
def mark_all_advice_read(uid: str = Depends(auth.get_current_user_uid)):
    count = desktop_db.mark_all_advice_read(uid)
    return {'status': f'marked {count} as read'}


# ============================================================================
# CHAT SESSIONS v2 ENDPOINTS
# ============================================================================


@router.post('/v2/chat-sessions', tags=['desktop'])
def create_chat_session(
    request: CreateChatSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.create_chat_session(uid, title=request.title, app_id=request.app_id)


@router.get('/v2/chat-sessions', tags=['desktop'])
def get_chat_sessions(
    app_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    starred: Optional[bool] = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.get_chat_sessions(uid, app_id=app_id, limit=limit, offset=offset, starred=starred)


@router.get('/v2/chat-sessions/{session_id}', tags=['desktop'])
def get_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    result = desktop_db.get_chat_session(uid, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.patch('/v2/chat-sessions/{session_id}', tags=['desktop'])
def update_chat_session(
    session_id: str,
    request: UpdateChatSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    result = desktop_db.update_chat_session(uid, session_id, title=request.title, starred=request.starred)
    if result is None:
        raise HTTPException(status_code=404, detail='Chat session not found')
    return result


@router.delete('/v2/chat-sessions/{session_id}', tags=['desktop'])
def delete_chat_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    desktop_db.delete_chat_session(uid, session_id)
    return {'status': 'ok'}


# ============================================================================
# DESKTOP MESSAGES v2 ENDPOINTS
# Uses /v2/desktop/messages to avoid conflict with chat.py's /v2/messages
# (chat.py POST streams AI responses; desktop POST is persistence-only)
# ============================================================================


@router.post('/v2/desktop/messages', tags=['desktop'])
def save_message(
    request: SaveMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.save_desktop_message(
        uid,
        text=request.text,
        sender=request.sender,
        app_id=request.app_id,
        session_id=request.session_id,
        metadata=request.metadata,
    )


@router.get('/v2/desktop/messages', tags=['desktop'])
def get_messages(
    app_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.get_desktop_messages(uid, app_id=app_id, session_id=session_id, limit=limit, offset=offset)


@router.delete('/v2/desktop/messages', tags=['desktop'])
def delete_messages(
    app_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    count = desktop_db.delete_desktop_messages(uid, app_id=app_id, session_id=session_id)
    return {'status': 'ok', 'deleted_count': count}


@router.patch('/v2/desktop/messages/{message_id}/rating', tags=['desktop'])
def rate_message(
    message_id: str,
    request: RateMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if request.rating is not None and request.rating not in (1, -1):
        raise HTTPException(status_code=400, detail='Rating must be 1, -1, or null')
    if not desktop_db.rate_desktop_message(uid, message_id, request.rating):
        raise HTTPException(status_code=404, detail='Message not found')
    return {'status': 'ok'}


# ============================================================================
# NOTIFICATION SETTINGS ENDPOINTS
# ============================================================================


@router.get('/v1/users/notification-settings', tags=['desktop'])
def get_notification_settings(uid: str = Depends(auth.get_current_user_uid)):
    return desktop_db.get_notification_settings(uid)


@router.patch('/v1/users/notification-settings', tags=['desktop'])
def update_notification_settings(
    request: UpdateNotificationSettingsRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.update_notification_settings(uid, enabled=request.enabled, frequency=request.frequency)


# ============================================================================
# ASSISTANT SETTINGS ENDPOINTS
# ============================================================================


@router.get('/v1/users/assistant-settings', tags=['desktop'])
def get_assistant_settings(uid: str = Depends(auth.get_current_user_uid)):
    return desktop_db.get_assistant_settings(uid)


@router.patch('/v1/users/assistant-settings', tags=['desktop'])
def update_assistant_settings(
    request: UpdateAssistantSettingsRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    # model_dump(exclude_unset=True) ensures only fields the client sent are stored
    settings = request.model_dump(exclude_unset=True)
    return desktop_db.update_assistant_settings(uid, settings)


# ============================================================================
# AI USER PROFILE ENDPOINTS
# ============================================================================


@router.get('/v1/users/ai-profile', tags=['desktop'])
def get_ai_profile(uid: str = Depends(auth.get_current_user_uid)):
    return desktop_db.get_ai_user_profile(uid)


@router.patch('/v1/users/ai-profile', tags=['desktop'])
def update_ai_profile(
    request: UpdateAIUserProfileRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.update_ai_user_profile(
        uid,
        profile_text=request.profile_text,
        generated_at=request.generated_at,
        data_sources_used=request.data_sources_used,
    )


# ============================================================================
# DAILY SCORE / SCORES ENDPOINTS
# ============================================================================


@router.get('/v1/daily-score', tags=['desktop'])
def get_daily_score(
    date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.get_daily_score(uid, date=date)


@router.get('/v1/scores', tags=['desktop'])
def get_scores(
    date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.get_scores(uid, date=date)


# ============================================================================
# DESKTOP LLM USAGE ENDPOINTS
# ============================================================================


@router.post('/v1/users/me/llm-usage', tags=['desktop'])
def record_llm_usage(
    request: RecordLlmUsageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    desktop_db.record_desktop_llm_usage(
        uid,
        input_tokens=request.input_tokens,
        output_tokens=request.output_tokens,
        cache_read_tokens=request.cache_read_tokens,
        cache_write_tokens=request.cache_write_tokens,
        total_tokens=request.total_tokens,
        cost_usd=request.cost_usd,
        account=request.account,
    )
    return {'status': 'ok'}


@router.get('/v1/users/me/llm-usage/total', tags=['desktop'])
def get_total_llm_cost(uid: str = Depends(auth.get_current_user_uid)):
    total = desktop_db.get_total_desktop_llm_cost(uid)
    return {'total_cost_usd': total}


# NOTE: The following endpoints remain on the Rust backend:
# - v1/users/stats/chat-messages — queries PostHog (no Python PostHog client)
# - v1/screen-activity/sync — writes Pinecone embeddings (Rust has Pinecone client)
# - v2/messages (non-desktop-prefixed) — conflicts with chat.py's AI streaming
# - v1/conversations/from-segments — requires Rust LLM processing pipeline
# - v2/chat/initial-message, v2/chat/generate-title — AI generation
# - v2/agent/* — GCE VM management
# - v1/config/api-keys — API key distribution
# - Crisp messaging — external service integration
