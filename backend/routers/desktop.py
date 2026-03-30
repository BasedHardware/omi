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
- Chat message count
- Screen activity sync
- Conversations from segments
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

import database.desktop as desktop_db
import database.screen_activity as screen_activity_db
from utils.other import endpoints as auth

router = APIRouter()


# ============================================================================
# REQUEST / RESPONSE MODELS
# ============================================================================

# --- Staged Tasks ---


class CreateStagedTaskRequest(BaseModel):
    description: str
    due_at: Optional[datetime] = None
    source: Optional[str] = None
    priority: Optional[str] = None
    metadata: Optional[str] = None
    category: Optional[str] = None
    relevance_score: Optional[int] = None


class BatchScoreEntry(BaseModel):
    id: str
    relevance_score: int


class BatchUpdateScoresRequest(BaseModel):
    scores: List[BatchScoreEntry]


# --- Focus Sessions ---


class CreateFocusSessionRequest(BaseModel):
    status: str  # "focused" or "distracted"
    app_or_site: str
    description: str
    message: Optional[str] = None
    duration_seconds: Optional[int] = None


# --- Advice ---


class CreateAdviceRequest(BaseModel):
    content: str
    category: Optional[str] = None
    reasoning: Optional[str] = None
    source_app: Optional[str] = None
    confidence: float = 0.5
    context_summary: Optional[str] = None
    current_activity: Optional[str] = None


class UpdateAdviceRequest(BaseModel):
    is_read: Optional[bool] = None
    is_dismissed: Optional[bool] = None


# --- Chat Sessions ---


class CreateChatSessionRequest(BaseModel):
    title: Optional[str] = None
    app_id: Optional[str] = None


class UpdateChatSessionRequest(BaseModel):
    title: Optional[str] = None
    starred: Optional[bool] = None


# --- Messages ---


class SaveMessageRequest(BaseModel):
    text: str
    sender: str  # "human" or "ai"
    app_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[str] = None


class RateMessageRequest(BaseModel):
    rating: Optional[int] = None  # 1, -1, or null


# --- Notification Settings ---


class UpdateNotificationSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    frequency: Optional[int] = None


# --- AI Profile ---


class UpdateAIUserProfileRequest(BaseModel):
    profile_text: Optional[str] = None
    generated_at: Optional[datetime] = None
    data_sources_used: Optional[int] = None


# --- LLM Usage ---


class RecordLlmUsageRequest(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    account: str = 'desktop_chat'


# --- Screen Activity ---


class ScreenActivityRow(BaseModel):
    id: int
    timestamp: str
    appName: Optional[str] = ''
    windowTitle: Optional[str] = ''
    ocrText: Optional[str] = ''


class ScreenActivitySyncRequest(BaseModel):
    rows: List[ScreenActivityRow]


# --- Conversations from segments ---


class TranscriptSegment(BaseModel):
    text: str
    speaker: str = 'SPEAKER_00'
    speaker_id: Optional[int] = None
    is_user: bool = False
    person_id: Optional[str] = None
    start: float = 0.0
    end: float = 0.0


class CreateConversationFromSegmentsRequest(BaseModel):
    transcript_segments: List[TranscriptSegment] = Field(max_length=500)
    source: Optional[str] = 'desktop'
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    language: Optional[str] = 'en'


# ============================================================================
# STAGED TASKS ENDPOINTS
# ============================================================================


@router.post('/v1/staged-tasks', tags=['desktop'])
def create_staged_task(
    request: CreateStagedTaskRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.create_staged_task(uid, request.model_dump())


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
    return desktop_db.create_focus_session(uid, request.model_dump())


@router.get('/v1/focus-sessions', tags=['desktop'])
def get_focus_sessions(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    date: Optional[str] = Query(None),
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
    date: Optional[str] = Query(None),
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
    return desktop_db.create_advice(uid, request.model_dump())


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
    if request.sender not in ('human', 'ai'):
        raise HTTPException(status_code=400, detail='Invalid sender')
    if not request.text.strip():
        raise HTTPException(status_code=400, detail='Empty message text')
    return desktop_db.save_desktop_message(uid, request.model_dump())


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
    uid: str = Depends(auth.get_current_user_uid),
):
    count = desktop_db.delete_desktop_messages(uid, app_id=app_id)
    return {'status': 'ok', 'deleted_count': count}


@router.patch('/v2/desktop/messages/{message_id}/rating', tags=['desktop'])
def rate_message(
    message_id: str,
    request: RateMessageRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if request.rating is not None and request.rating not in (1, -1):
        raise HTTPException(status_code=400, detail='Invalid rating value')
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
    if request.frequency is not None and not (0 <= request.frequency <= 5):
        raise HTTPException(status_code=400, detail='Frequency must be 0-5')
    return desktop_db.update_notification_settings(uid, enabled=request.enabled, frequency=request.frequency)


# ============================================================================
# ASSISTANT SETTINGS ENDPOINTS
# ============================================================================


@router.get('/v1/users/assistant-settings', tags=['desktop'])
def get_assistant_settings(uid: str = Depends(auth.get_current_user_uid)):
    return desktop_db.get_assistant_settings(uid)


@router.patch('/v1/users/assistant-settings', tags=['desktop'])
def update_assistant_settings(
    request: dict,
    uid: str = Depends(auth.get_current_user_uid),
):
    # Validate prompt lengths
    for section in ['focus', 'task', 'advice', 'memory']:
        section_data = request.get(section, {})
        if isinstance(section_data, dict):
            prompt = section_data.get('analysis_prompt')
            if prompt and len(prompt) > 10000:
                raise HTTPException(status_code=400, detail=f'{section} prompt exceeds 10000 characters')
    return desktop_db.update_assistant_settings(uid, request)


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
    return desktop_db.update_ai_user_profile(uid, request.model_dump(exclude_unset=True))


# ============================================================================
# DAILY SCORE / SCORES ENDPOINTS
# ============================================================================


@router.get('/v1/daily-score', tags=['desktop'])
def get_daily_score(
    date: Optional[str] = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    return desktop_db.get_daily_score(uid, date=date)


@router.get('/v1/scores', tags=['desktop'])
def get_scores(
    date: Optional[str] = Query(None),
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


# ============================================================================
# CHAT MESSAGE COUNT
# ============================================================================


@router.get('/v1/users/stats/chat-messages', tags=['desktop'])
def get_chat_message_count(uid: str = Depends(auth.get_current_user_uid)):
    count = desktop_db.get_chat_message_count(uid)
    return {'count': count}


# ============================================================================
# SCREEN ACTIVITY SYNC
# ============================================================================


@router.post('/v1/screen-activity/sync', tags=['desktop'])
def sync_screen_activity(
    request: ScreenActivitySyncRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    rows = [r.model_dump() for r in request.rows]
    written = screen_activity_db.upsert_screen_activity(uid, rows)
    return {'status': 'ok', 'written': written}


# NOTE: v2/messages (non-desktop-prefixed) and v1/conversations/from-segments
# remain on the Rust backend. v2/messages conflicts with chat.py's AI streaming
# endpoint, and from-segments requires the Rust LLM processing pipeline.
# These will be migrated in Phase 2 when the Python chat pipeline supports
# desktop persistence semantics.
