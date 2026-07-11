from __future__ import annotations

import re
import uuid
from typing import List, Dict, Any, Union, Optional
import hashlib
import os
import asyncio

import pytz
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from database import (
    conversations as conversations_db,
    memories as memories_db,
    chat as chat_db,
    user_usage as user_usage_db,
    notifications as notification_db,
    daily_summaries as daily_summaries_db,
    llm_usage as llm_usage_db,
    users as users_db,
)
from database.sync_jobs import release_job_run_lock, try_acquire_job_run_lock
from services.users.data_export import iter_user_data_export
from services.users.account_deletion import background_wipe_user_data, start_account_deletion
from database.app_review_config import should_hide_subscription_ui
from database.webhook_health import record_dev_webhook_success
from database.conversations import get_in_progress_conversation, get_conversation
from database.redis_db import (
    cache_user_geolocation,
    get_cached_user_geolocation,
    set_user_webhook_db,
    get_user_webhook_db,
    disable_user_webhook_db,
    enable_user_webhook_db,
    user_webhook_status_db,
    set_user_preferred_app,
    set_user_data_protection_level,
    get_generic_cache,
    set_generic_cache,
    get_daily_summary_uid,
    store_daily_summary_to_uid,
    remove_daily_summary_to_uid,
)

from database.users import (
    claim_deletion_wipe_for_task,
    get_user_transcription_preferences,
    set_user_transcription_preferences,
)
from utils.stt.streaming import deepgram_nova3_multi_languages
from database.users import *
from models.conversation import Conversation
from models.geolocation import Geolocation
from utils.conversations.factory import deserialize_conversation, deserialize_conversations
from models.other import Person, CreatePerson
from models.shared import StatusResponse
from typing import Optional
from models.user_usage import UserUsageResponse, UsagePeriod
from datetime import datetime, time, timedelta

from models.users import (
    ChatUsageQuota,
    ChatQuotaUnit,
    WebhookType,
    UserSubscriptionResponse,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    PlanType,
    PricingOption,
    PhoneCallQuota,
    TrialMetadata,
)
from utils.phone_calls import get_quota_snapshot as get_phone_call_quota_snapshot
from utils.apps import get_available_app_by_id
from utils.subscription import (
    get_chat_quota_snapshot,
    get_paid_plan_definitions,
    get_plan_display_name,
    get_plan_limits,
    get_plan_features,
    get_monthly_usage_for_subscription,
    is_trial_paywalled,
    neo_grandfather_until,
    reconcile_basic_plan_with_stripe,
    filter_plans_for_user,
    has_ever_purchased,
    should_show_new_plans,
    adapt_plans_for_legacy_client,
    legacy_plan_features,
    clear_trial_paywall_cache,
    get_trial_metadata,
)
from database import user_usage as user_usage_db
from utils import stripe as stripe_utils
from utils.cloud_tasks import get_account_deletion_tasks_max_attempts, verify_cloud_tasks_oidc
from utils.executors import cleanup_executor, db_executor, run_blocking
from utils.log_sanitizer import sanitize
from utils.llm.followup import followup_question_prompt
from utils.notifications import send_notification, send_training_data_submitted_notification
from utils.llm.external_integrations import generate_comprehensive_daily_summary
from models.notification_message import NotificationMessage
from utils.other import endpoints as auth
from utils.other.storage import (
    delete_all_conversation_recordings,
    get_speech_sample_signed_urls,
    delete_user_person_speech_samples,
    delete_user_person_speech_sample,
)
from utils.webhooks import webhook_first_time_setup
from utils.byok import has_byok_keys, invalidate_byok_state_cache
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class MigrationRequest(BaseModel):
    type: str
    id: str
    target_level: str


class MigrationTargetRequest(BaseModel):
    target_level: str


class BatchMigrationRequest(BaseModel):
    requests: List[MigrationRequest]


class MigrationStatusResponse(BaseModel):
    status: str
    message: Optional[str] = None


class MigrationRequestsResponse(BaseModel):
    needs_migration: List[Dict[str, Any]] = Field(default_factory=list)


class UserStatusResponse(BaseModel):
    status: str
    message: Optional[str] = None


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(extra='allow')

    uid: str
    email: Optional[str] = None
    name: Optional[str] = None
    time_zone: Optional[str] = None
    created_at: Optional[datetime] = None
    motivation: Optional[str] = None
    use_case: Optional[str] = None
    job: Optional[str] = None
    company: Optional[str] = None
    data_protection_level: Optional[str] = None
    migration_status: Optional[Dict[str, Any]] = None


class UserWebhooksStatusResponse(BaseModel):
    audio_bytes: bool
    memory_created: bool
    realtime_transcript: bool
    day_summary: bool


class UserWebhookUrlResponse(BaseModel):
    url: Optional[str] = None


class UserDataExportResponse(BaseModel):
    profile: Dict[str, Any] = Field(default_factory=dict)
    conversations: List[Dict[str, Any]] = Field(default_factory=list)
    memories: List[Dict[str, Any]] = Field(default_factory=list)
    people: List[Dict[str, Any]] = Field(default_factory=list)
    action_items: List[Dict[str, Any]] = Field(default_factory=list)
    chat_messages: List[Dict[str, Any]] = Field(default_factory=list)


class StoreRecordingPermissionResponse(BaseModel):
    store_recording_permission: bool


class PrivateCloudSyncResponse(BaseModel):
    private_cloud_sync_enabled: bool


class OnboardingStateResponse(BaseModel):
    completed: bool = False
    acquisition_source: str = ''
    device_onboarding_completed: bool = False


class UserLanguageResponse(BaseModel):
    language: Optional[str] = None


class UserLanguageUpdateResponse(UserStatusResponse):
    single_language_mode: bool


class MemorySummaryRatingResponse(BaseModel):
    has_rating: bool
    rating: Optional[int] = None


class TrainingDataOptInResponse(BaseModel):
    opted_in: bool
    status: Optional[str] = None


class DailySummaryTestResponse(UserStatusResponse):
    summary_id: str
    conversations_count: int


class DailySummaryActionItem(BaseModel):
    description: Optional[str] = None
    priority: Optional[str] = None
    source_conversation_id: Optional[str] = None
    completed: Optional[bool] = None


class DailySummaryTopicHighlight(BaseModel):
    topic: Optional[str] = None
    emoji: Optional[str] = None
    summary: Optional[str] = None
    conversation_ids: Optional[List[str]] = None


class DailySummaryUnresolvedQuestion(BaseModel):
    question: Optional[str] = None
    conversation_id: Optional[str] = None


class DailySummaryDecisionMade(BaseModel):
    decision: Optional[str] = None
    conversation_id: Optional[str] = None


class DailySummaryKnowledgeNugget(BaseModel):
    insight: Optional[str] = None
    conversation_id: Optional[str] = None


class DailySummaryDayStats(BaseModel):
    total_conversations: Optional[int] = None
    total_duration_minutes: Optional[int] = None
    action_items_count: Optional[int] = None


class DailySummaryLocationPin(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    conversation_id: Optional[str] = None
    time: Optional[str] = None


class DailySummaryResponse(BaseModel):
    model_config = ConfigDict(extra='allow')

    id: Optional[str] = None
    date: Optional[str] = None
    created_at: Optional[datetime] = None
    headline: Optional[str] = None
    overview: Optional[str] = None
    day_emoji: Optional[str] = None
    stats: Optional[DailySummaryDayStats] = None
    highlights: Optional[List[DailySummaryTopicHighlight]] = None
    action_items: Optional[List[DailySummaryActionItem]] = None
    unresolved_questions: Optional[List[DailySummaryUnresolvedQuestion]] = None
    decisions_made: Optional[List[DailySummaryDecisionMade]] = None
    knowledge_nuggets: Optional[List[DailySummaryKnowledgeNugget]] = None
    locations: Optional[List[DailySummaryLocationPin]] = None


class DailySummariesResponse(BaseModel):
    summaries: List[DailySummaryResponse] = Field(default_factory=list)


@router.get('/v1/users/profile', tags=['v1'], response_model=UserProfileResponse)
def get_user_profile_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """Gets the full user profile, including data protection and migration status."""
    profile = get_user_profile(uid)
    if not profile:
        raise HTTPException(status_code=410, detail="User not found")
    profile.setdefault('uid', uid)
    return profile


class DeleteAccountRequest(BaseModel):
    reason: Optional[str] = None
    reason_details: Optional[str] = None


@router.delete('/v1/users/delete-account', tags=['v1'], response_model=UserStatusResponse)
def delete_account(
    request: DeleteAccountRequest = DeleteAccountRequest(),
    uid: str = Depends(auth.get_current_user_uid),
):
    try:
        return start_account_deletion(uid, reason=request.reason, reason_details=request.reason_details)
    except Exception as e:
        logger.info(f'delete_account {sanitize(str(e))}')
        raise HTTPException(status_code=500, detail='Could not delete account. Please try again.')


# response_model omitted: include_in_schema=False Cloud Tasks handler; JSONResponse
# status codes drive queue retry/ack behavior.
@router.post('/v1/users/account-deletion-wipes/run', include_in_schema=False)
async def run_account_deletion_wipe(request: Request, task_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    try:
        payload = await request.json()
        uid = payload['uid']
        if not isinstance(uid, str) or not uid:
            raise ValueError('uid must be a non-empty string')
    except Exception as e:
        logger.error(f'account_deletion handler: invalid payload, dropping task: {sanitize(str(e))}')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

    lock_key = f'account-deletion:{uid}'
    lock_token = await run_blocking(db_executor, try_acquire_job_run_lock, lock_key)
    if not lock_token:
        logger.warning(f'account_deletion handler: run-lock held for {uid}, deferring')
        return JSONResponse(status_code=409, content={'status': 'locked'})

    release_lock = True
    try:
        claim_status = await run_blocking(db_executor, claim_deletion_wipe_for_task, uid)
        if claim_status == 'completed':
            return JSONResponse(status_code=200, content={'status': 'acked', 'job_status': 'completed'})
        if claim_status == 'running':
            return JSONResponse(status_code=409, content={'status': 'running'})
        if claim_status != 'claimed':
            logger.warning(f'account_deletion handler: non-actionable task for {uid}, claim_status={claim_status}')
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': claim_status})

        ok = await run_blocking(cleanup_executor, background_wipe_user_data, uid)
        if ok:
            return JSONResponse(status_code=200, content={'status': 'done'})

        max_attempts = get_account_deletion_tasks_max_attempts()
        if task_retry_count >= max_attempts - 1:
            logger.error(f'account_deletion handler: final attempt {task_retry_count + 1} failed for {uid}')
            return JSONResponse(status_code=200, content={'status': 'failed_final'})

        logger.warning(f'account_deletion handler: attempt {task_retry_count + 1} failed for {uid}, will retry')
        return JSONResponse(status_code=500, content={'status': 'retry'})
    except asyncio.CancelledError:
        release_lock = False
        logger.warning(f'account_deletion handler cancelled for {uid}; preserving run-lock until TTL')
        raise
    finally:
        if release_lock:
            await run_blocking(db_executor, release_job_run_lock, lock_key, lock_token)


@router.patch('/v1/users/geolocation', tags=['v1'], response_model=UserStatusResponse)
def set_user_geolocation(geolocation: Geolocation, uid: str = Depends(auth.get_current_user_uid)):
    last_location_data = get_cached_user_geolocation(uid)
    if last_location_data:
        try:
            last_location = Geolocation(**last_location_data)

            last_lat = round(last_location.latitude, 4)
            last_lon = round(last_location.longitude, 4)
            new_lat = round(geolocation.latitude, 4)
            new_lon = round(geolocation.longitude, 4)

            # Only update if location has changed up to 4 decimal places
            if last_lat == new_lat and last_lon == new_lon:
                return {'status': 'ok', 'message': 'Location not changed significantly.'}

            cache_user_geolocation(uid, geolocation.model_dump())
        except Exception as e:
            logger.error(f"Error processing geolocation update, caching new location anyway. Error: {e}")
            cache_user_geolocation(uid, geolocation.model_dump())
    else:
        # No previous location, so cache the new one
        cache_user_geolocation(uid, geolocation.model_dump())

    return {'status': 'ok'}


# ***********************************************
# ************* DEVELOPER WEBHOOKS **************
# ***********************************************


class SetUserWebhookUrlRequest(BaseModel):
    url: str


@router.post('/v1/users/developer/webhook/{wtype}', tags=['v1'], response_model=UserStatusResponse)
def set_user_webhook_endpoint(
    wtype: WebhookType, data: SetUserWebhookUrlRequest, uid: str = Depends(auth.get_current_user_uid)
):
    url = data.url
    if url == '' or url == ',':
        disable_user_webhook_db(uid, wtype)
    set_user_webhook_db(uid, wtype, url)
    return {'status': 'ok'}


@router.get('/v1/users/developer/webhook/{wtype}', tags=['v1'], response_model=UserWebhookUrlResponse)
def get_user_webhook_endpoint(wtype: WebhookType, uid: str = Depends(auth.get_current_user_uid)):
    return {'url': get_user_webhook_db(uid, wtype)}


@router.post('/v1/users/developer/webhook/{wtype}/disable', tags=['v1'], response_model=UserStatusResponse)
def disable_user_webhook_endpoint(wtype: WebhookType, uid: str = Depends(auth.get_current_user_uid)):
    disable_user_webhook_db(uid, wtype)
    return {'status': 'ok'}


@router.post('/v1/users/developer/webhook/{wtype}/enable', tags=['v1'], response_model=UserStatusResponse)
def enable_user_webhook_endpoint(wtype: WebhookType, uid: str = Depends(auth.get_current_user_uid)):
    enable_user_webhook_db(uid, wtype)
    record_dev_webhook_success(uid, wtype.value)
    return {'status': 'ok'}


@router.get('/v1/users/developer/webhooks/status', tags=['v1'], response_model=UserWebhooksStatusResponse)
def get_user_webhooks_status(uid: str = Depends(auth.get_current_user_uid)):
    # This only happens the first time because the user_webhook_status_db function will return None for existing users
    audio_bytes = user_webhook_status_db(uid, WebhookType.audio_bytes)
    if audio_bytes is None:
        audio_bytes = webhook_first_time_setup(uid, WebhookType.audio_bytes)
    memory_created = user_webhook_status_db(uid, WebhookType.memory_created)
    if memory_created is None:
        memory_created = webhook_first_time_setup(uid, WebhookType.memory_created)
    realtime_transcript = user_webhook_status_db(uid, WebhookType.realtime_transcript)
    if realtime_transcript is None:
        realtime_transcript = webhook_first_time_setup(uid, WebhookType.realtime_transcript)
    day_summary = user_webhook_status_db(uid, WebhookType.day_summary)
    if day_summary is None:
        day_summary = webhook_first_time_setup(uid, WebhookType.day_summary)
    return {
        'audio_bytes': audio_bytes,
        'memory_created': memory_created,
        'realtime_transcript': realtime_transcript,
        'day_summary': day_summary,
    }


# *************************************************
# ************* RECORDING PERMISSION **************
# *************************************************


@router.post('/v1/users/store-recording-permission', tags=['v1'], response_model=UserStatusResponse)
def store_recording_permission(value: bool, uid: str = Depends(auth.get_current_user_uid)):
    set_user_store_recording_permission(uid, value)
    return {'status': 'ok'}


@router.get('/v1/users/store-recording-permission', tags=['v1'], response_model=StoreRecordingPermissionResponse)
def get_store_recording_permission(uid: str = Depends(auth.get_current_user_uid)):
    return {'store_recording_permission': get_user_store_recording_permission(uid)}


@router.delete('/v1/users/store-recording-permission', tags=['v1'], response_model=UserStatusResponse)
def delete_permission_and_recordings(uid: str = Depends(auth.get_current_user_uid)):
    set_user_store_recording_permission(uid, False)
    delete_all_conversation_recordings(uid)
    return {'status': 'ok'}


# *************************************************
# ************* ONBOARDING STATE ******************
# *************************************************


@router.get('/v1/users/onboarding', tags=['v1'], response_model=OnboardingStateResponse)
def get_onboarding_state(uid: str = Depends(auth.get_current_user_uid)):
    """Get the user's onboarding state (completed status, acquisition source, etc.)."""
    state = get_user_onboarding_state(uid)
    return {
        'completed': state.get('completed', False),
        'acquisition_source': state.get('acquisition_source', ''),
        'device_onboarding_completed': state.get('device_onboarding_completed', False),
    }


class OnboardingStateUpdate(BaseModel):
    completed: Optional[bool] = None
    acquisition_source: Optional[str] = None
    device_onboarding_completed: Optional[bool] = None


@router.patch('/v1/users/onboarding', tags=['v1'], response_model=UserStatusResponse)
def update_onboarding_state(data: OnboardingStateUpdate, uid: str = Depends(auth.get_current_user_uid)):
    """Update the user's onboarding state."""
    current_state = get_user_onboarding_state(uid)
    if data.completed is not None:
        current_state['completed'] = data.completed
    if data.acquisition_source is not None:
        current_state['acquisition_source'] = data.acquisition_source
    if data.device_onboarding_completed is not None:
        current_state['device_onboarding_completed'] = data.device_onboarding_completed
    set_user_onboarding_state(uid, current_state)
    return {'status': 'ok'}


# *************************************************
# ************* PRIVATE CLOUD SYNC ****************
# *************************************************


@router.post('/v1/users/private-cloud-sync', tags=['v1'], response_model=UserStatusResponse)
def set_private_cloud_sync(value: bool, uid: str = Depends(auth.get_current_user_uid)):
    set_user_private_cloud_sync_enabled(uid, value)
    return {'status': 'ok'}


@router.get('/v1/users/private-cloud-sync', tags=['v1'], response_model=PrivateCloudSyncResponse)
def get_private_cloud_sync(uid: str = Depends(auth.get_current_user_uid)):
    return {'private_cloud_sync_enabled': get_user_private_cloud_sync_enabled(uid)}


# ****************************************
# ************* PEOPLE CRUD **************
# ****************************************


# TODO: consider adding person photo.
@router.post('/v1/users/people', tags=['v1'], response_model=Person)
def get_or_create_person(data: CreatePerson, uid: str = Depends(auth.get_current_user_uid)):
    """Create a new person or return existing one with same name (idempotent by name).

    This enables backward compatibility: old apps can call this API and get the
    same person that backend already created, preventing duplicates.
    """
    # Check if person with same name already exists
    existing_person = get_person_by_name(uid, data.name)
    if existing_person:
        return existing_person

    # Create new person
    person_data = {
        'id': str(uuid.uuid4()),
        'name': data.name,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }
    result = create_person(uid, person_data)
    return result


@router.get('/v1/users/people/{person_id}', tags=['v1'], response_model=Person)
def get_single_person(
    person_id: str, include_speech_samples: bool = False, uid: str = Depends(auth.get_current_user_uid)
):
    person = get_person(uid, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    if include_speech_samples:
        # Convert stored GCS paths to signed URLs
        stored_paths = person.get('speech_samples', [])
        person['speech_samples'] = get_speech_sample_signed_urls(stored_paths)
    return person


@router.get('/v1/users/people', tags=['v1'], response_model=List[Person])
def get_all_people(include_speech_samples: bool = True, uid: str = Depends(auth.get_current_user_uid)):
    logger.info(f'get_all_people {include_speech_samples}')
    people = get_people(uid)
    if include_speech_samples:
        # Convert GCS paths to signed URLs for each person
        for i, person in enumerate(people):
            stored_paths = person.get('speech_samples', [])
            people[i]['speech_samples'] = get_speech_sample_signed_urls(stored_paths)
    return people


@router.patch('/v1/users/people/{person_id}/name', tags=['v1'], response_model=UserStatusResponse)
def update_person_name(
    person_id: str,
    value: str,  # = Field(min_length=2, max_length=40),
    uid: str = Depends(auth.get_current_user_uid),
):
    if not update_person(uid, person_id, value):
        raise HTTPException(status_code=404, detail="Person not found")
    return {'status': 'ok'}


@router.delete('/v1/users/people/{person_id}', tags=['v1'], status_code=204)
def delete_person_endpoint(person_id: str, uid: str = Depends(auth.get_current_user_uid)):
    delete_person(uid, person_id)
    delete_user_person_speech_samples(uid, person_id)


@router.delete(
    '/v1/users/people/{person_id}/speech-samples/{sample_index}',
    tags=['v1'],
    response_model=UserStatusResponse,
)
def delete_person_speech_sample_endpoint(
    person_id: str,
    sample_index: int,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Delete a specific speech sample for a person by index."""
    person = get_person(uid, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    speech_samples = person.get('speech_samples', [])
    if sample_index < 0 or sample_index >= len(speech_samples):
        raise HTTPException(status_code=404, detail="Sample not found")

    path_to_delete = speech_samples[sample_index]

    # Extract filename from path for GCS deletion
    filename = path_to_delete.split('/')[-1]

    # Delete from GCS
    delete_user_person_speech_sample(uid, person_id, filename)

    # Remove from Firestore
    from database.users import remove_person_speech_sample

    remove_person_speech_sample(uid, person_id, path_to_delete)

    return {'status': 'ok'}


# **********************************************************
# ************* RANDOM JOAN SPECIFIC FEATURES **************
# **********************************************************


class FollowupQuestionResponse(BaseModel):
    """Response for the Joan follow-up question endpoint (a generated prompt)."""

    result: str = Field(description='Generated follow-up question prompt text.')


@router.delete('/v1/joan/{memory_id}/followup-question', tags=['v1'], response_model=FollowupQuestionResponse)
def delete_person_endpoint(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    if memory_id == '0':
        memory = get_in_progress_conversation(uid)
        if not memory:
            raise HTTPException(status_code=400, detail='No memory in progres')
    else:
        memory = get_conversation(uid, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail='Conversation not found')
    if memory.get('is_locked', False):
        raise HTTPException(status_code=402, detail='A paid plan is required to access this conversation.')
    memory = deserialize_conversation(memory)
    return {'result': followup_question_prompt(uid, memory.transcript_segments)}


# **************************************
# ************* Analytics **************
# **************************************


@router.post('/v1/users/analytics/memory_summary', tags=['v1'], response_model=UserStatusResponse)
def set_memory_summary_rating(
    memory_id: str,
    value: int,  # 0, 1, -1 (shown)
    uid: str = Depends(auth.get_current_user_uid),
):
    set_conversation_summary_rating_score(uid, memory_id, value)
    return {'status': 'ok'}


@router.get('/v1/users/analytics/memory_summary', tags=['v1'], response_model=MemorySummaryRatingResponse)
def get_memory_summary_rating(
    memory_id: str,
    _: str = Depends(auth.get_current_user_uid),
):
    rating = get_conversation_summary_rating_score(memory_id)
    # TODO: later ask reason, a set of options, if user says good, whats the best, if bad, whats the worst
    if not rating:
        return {'has_rating': False}
    return {'has_rating': rating.get('value', -1) != -1, 'rating': rating.get('value', -1)}


@router.post('/v1/users/analytics/chat_message', tags=['v1'], response_model=UserStatusResponse)
def set_chat_message_analytics(
    message_id: str,
    value: int,
    reason: str = None,  # Reason for thumbs down (e.g. 'too_verbose', 'incorrect_or_hallucination')
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Submit feedback rating for a chat message.

    Args:
        message_id: ID of the message being rated
        value: Rating value (1 = thumbs up, -1 = thumbs down, 0 = neutral/removed)
        reason: Optional reason for thumbs down. Valid values:
            - 'too_verbose': Response was too long or wordy
            - 'incorrect_or_hallucination': Response contained incorrect information
            - 'not_helpful_or_irrelevant': Response didn't address the question
            - 'didnt_follow_instructions': Response didn't follow user instructions
            - 'other': Other reason
    """
    # Always store feedback in Firestore analytics collection
    set_chat_message_rating_score(uid, message_id, value, reason)

    # Also update the rating directly on the message document for persistence
    rating_value = None if value == 0 else value
    chat_db.update_message_rating(uid, message_id, rating_value)

    # Try to submit feedback to LangSmith if the message has a run_id
    try:
        from utils.observability import submit_langsmith_feedback

        # Look up the message to get langsmith_run_id
        message_result = chat_db.get_message(uid, message_id)
        if message_result:
            message, _ = message_result
            langsmith_run_id = getattr(message, 'langsmith_run_id', None)
            if not langsmith_run_id and isinstance(message, dict):
                langsmith_run_id = message.get('langsmith_run_id')

            if langsmith_run_id:
                # Map value to score: 1 (thumbs up) -> 1.0, -1 (thumbs down) -> 0.0
                score = 1.0 if value == 1 else (0.0 if value == -1 else 0.5)

                # Build comment from reason if provided
                comment = reason if reason else None

                # Submit feedback to LangSmith (non-blocking, errors are logged)
                submit_langsmith_feedback(
                    run_id=langsmith_run_id,
                    score=score,
                    key="chat_message_rating",
                    comment=comment,
                )
    except Exception as e:
        # Don't fail the request if LangSmith feedback fails
        logger.error(f"⚠️  LangSmith feedback submission error (non-fatal): {e}")

    return {'status': 'ok'}


# ***************************************
# ************* Language ****************
# ***************************************


@router.get('/v1/users/language', tags=['v1'], response_model=UserLanguageResponse)
def get_user_language(uid: str = Depends(auth.get_current_user_uid)):
    """Get the user's preferred language."""
    language = get_user_language_preference(uid)
    if not language:
        return {'language': None}
    return {'language': language}


class SetUserLanguageRequest(BaseModel):
    language: str


@router.patch('/v1/users/language', tags=['v1'], response_model=UserLanguageUpdateResponse)
def set_user_language(data: SetUserLanguageRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Set the user's preferred language (e.g., 'en', 'vi', etc.)."""
    language = data.language
    if not language:
        raise HTTPException(status_code=400, detail="Language is required")
    set_user_language_preference(uid, language)
    single_language_mode = language not in deepgram_nova3_multi_languages
    set_user_transcription_preferences(uid, single_language_mode=single_language_mode)
    return {'status': 'ok', 'single_language_mode': single_language_mode}


# *************************************************
# ********** Transcription Preferences ************
# *************************************************


class TranscriptionPreferencesResponse(BaseModel):
    single_language_mode: bool = False
    vocabulary: List[str] = Field(default_factory=list)
    language: str = ''
    uses_custom_stt: bool = False
    custom_stt_since: Optional[datetime] = None


class TranscriptionPreferencesUpdate(BaseModel):
    single_language_mode: Optional[bool] = None
    vocabulary: Optional[List[str]] = None


@router.get('/v1/users/transcription-preferences', tags=['v1'], response_model=TranscriptionPreferencesResponse)
def get_transcription_preferences_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """Get user's transcription preferences (single language mode, vocabulary)."""
    prefs = get_user_transcription_preferences(uid)
    return prefs


@router.patch('/v1/users/transcription-preferences', tags=['v1'], response_model=UserStatusResponse)
def update_transcription_preferences_endpoint(
    data: TranscriptionPreferencesUpdate, uid: str = Depends(auth.get_current_user_uid)
):
    """
    Update user's transcription preferences.

    - single_language_mode: If True, uses exact language for higher accuracy but disables translation
    - vocabulary: List of custom keywords/terms (max 100) for better transcription accuracy
    """
    set_user_transcription_preferences(uid, single_language_mode=data.single_language_mode, vocabulary=data.vocabulary)
    return {'status': 'ok'}


# **************************************
# ********* Data Protection ************
# **************************************


@router.post('/v1/users/migration/requests', tags=['v1'], response_model=MigrationStatusResponse)
def handle_migration_requests(
    request: Union[MigrationRequest, MigrationTargetRequest], uid: str = Depends(auth.get_current_user_uid)
):
    """
    Handles data migration requests.
    - If 'id' and 'type' are present, it migrates a single object.
    - Otherwise, it initiates the data migration process for a 'target_level'.
    """
    if isinstance(request, MigrationRequest):
        # This is for migrating a single object
        if request.type == 'conversation':
            try:
                conversations_db.migrate_conversations_level_batch(uid, [request.id], request.target_level)
                return {'status': 'ok'}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to migrate conversation {request.id}: {e}")
        elif request.type == 'memory':
            try:
                memories_db.migrate_memories_level_batch(uid, [request.id], request.target_level)
                return {'status': 'ok'}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to migrate memory {request.id}: {e}")
        elif request.type == 'chat':
            try:
                chat_db.migrate_chats_level_batch(uid, [request.id], request.target_level)
                return {'status': 'ok'}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to migrate chat message {request.id}: {e}")
        else:
            raise HTTPException(status_code=400, detail=f"Unknown object type for migration: {request.type}")
    elif isinstance(request, MigrationTargetRequest):
        # This is for starting the migration process
        if request.target_level != 'enhanced':
            raise HTTPException(
                status_code=400, detail="Invalid target_level. Only migration to 'enhanced' is supported."
            )

        set_migration_status(uid, request.target_level)
        return {'status': 'ok', 'message': 'Migration status set.'}


@router.get('/v1/users/migration/requests', tags=['v1'], response_model=MigrationRequestsResponse)
def get_migration_requests(target_level: str, uid: str = Depends(auth.get_current_user_uid)):
    """Checks which documents need to be migrated to the target level."""
    if target_level != 'enhanced':
        raise HTTPException(status_code=400, detail="Invalid target_level. Only migration to 'enhanced' is supported.")

    conversations_to_migrate = conversations_db.get_conversations_to_migrate(uid, target_level)
    memories_to_migrate = memories_db.get_memories_to_migrate(uid, target_level)
    chats_to_migrate = chat_db.get_chats_to_migrate(uid, target_level)
    needs_migration = conversations_to_migrate + memories_to_migrate + chats_to_migrate
    return {"needs_migration": needs_migration}


@router.post('/v1/users/migration/batch-requests', tags=['v1'], response_model=MigrationStatusResponse)
def handle_batch_migration_requests(
    batch_request: BatchMigrationRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Migrates a batch of data objects to the target protection level."""
    errors = []

    # Group requests by type and target_level
    grouped_requests: Dict[tuple[str, str], List[str]] = {}
    for req in batch_request.requests:
        key = (req.type, req.target_level)
        if key not in grouped_requests:
            grouped_requests[key] = []
        grouped_requests[key].append(req.id)

    for (req_type, target_level), ids in grouped_requests.items():
        try:
            if req_type == 'conversation':
                conversations_db.migrate_conversations_level_batch(uid, ids, target_level)
            elif req_type == 'memory':
                memories_db.migrate_memories_level_batch(uid, ids, target_level)
            elif req_type == 'chat':
                chat_db.migrate_chats_level_batch(uid, ids, target_level)
            else:
                errors.append(f"Unknown object type for migration: {req_type}")
        except Exception as e:
            error_detail = f"Failed to migrate batch of type {req_type}: {e}"
            logger.info(error_detail)
            errors.append(error_detail)

    if errors:
        raise HTTPException(status_code=500, detail={"message": "Some objects failed to migrate.", "errors": errors})

    return {'status': 'ok'}


@router.post(
    '/v1/users/migration/requests/data-protection-level/finalize',
    tags=['v1'],
    response_model=MigrationStatusResponse,
)
def finalize_migration_request(request: MigrationTargetRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Finalizes the migration by setting the user's global protection level."""
    if request.target_level != 'enhanced':
        raise HTTPException(status_code=400, detail="Invalid target_level. Only migration to 'enhanced' is supported.")

    finalize_migration(uid, request.target_level)
    set_user_data_protection_level(uid, request.target_level)
    return {'status': 'ok'}


@router.put('/v1/users/preferences/app', tags=['v1'], response_model=UserStatusResponse)
def set_preferred_app_for_user(
    app_id: str = Query(..., description="The ID of the app to set as preferred"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Sets the user's preferred app for future processing."""

    app_id_to_set = app_id

    selected_app = get_available_app_by_id(app_id_to_set, uid)
    if not selected_app:
        raise HTTPException(status_code=410, detail=f"App with ID '{app_id_to_set}' not found or not accessible.")

    try:
        set_user_preferred_app(uid, app_id_to_set)
    except Exception as e:
        logger.error(f"Failed to set preferred app in Redis for user {uid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to store app preference.")

    return {"status": "ok", "message": f"App {app_id_to_set} set as preferred app for user {uid}."}


# **************************************
# *********** Training Data ************
# **************************************


@router.get('/v1/users/training-data-opt-in', tags=['v1'], response_model=TrainingDataOptInResponse)
def get_training_data_opt_in_status(uid: str = Depends(auth.get_current_user_uid)):
    """Get the user's training data opt-in status."""
    opt_in_data = get_user_training_data_opt_in(uid)
    if not opt_in_data:
        return {'opted_in': False, 'status': None}
    return {'opted_in': True, 'status': opt_in_data.get('status')}


@router.post('/v1/users/training-data-opt-in', tags=['v1'], response_model=UserStatusResponse)
def set_training_data_opt_in_status(uid: str = Depends(auth.get_current_user_uid)):
    """Opt-in for training data program. User's request will be reviewed."""
    set_user_training_data_opt_in(uid, 'pending_review')

    # Check if private cloud sync is enabled, if not, enable it
    if not get_user_private_cloud_sync_enabled(uid):
        set_user_private_cloud_sync_enabled(uid, True)

    # Send notification to user
    send_training_data_submitted_notification(uid)

    return {'status': 'ok', 'message': 'Your request has been submitted for review. We will let you know soon.'}


# **************************************
# ************* Usage ******************
# **************************************


@router.get('/v1/users/me/usage', tags=['v1'], response_model=UserUsageResponse)
def get_user_usage_stats_endpoint(
    uid: str = Depends(auth.get_current_user_uid),
    period: UsagePeriod = UsagePeriod.TODAY,
):
    """Gets daily and monthly usage stats for the authenticated user."""
    stats = user_usage_db.get_current_user_usage(uid, period.value)
    return stats


_SHA256_HEX_RE = re.compile(r'^[a-f0-9]{64}$')
_BYOK_REQUIRED_PROVIDERS = {'openai', 'anthropic', 'gemini', 'deepgram'}


class BYOKActivateRequest(BaseModel):
    fingerprints: Dict[str, str]


class BYOKActiveResponse(BaseModel):
    active: bool


@router.post('/v1/users/me/byok-active', tags=['v1'], response_model=BYOKActiveResponse)
def activate_byok_endpoint(data: BYOKActivateRequest, uid: str = Depends(auth.get_current_user_uid_no_byok_validation)):
    """Flip the user onto the BYOK free plan.

    The client sends SHA-256 fingerprints of the 4 provider keys so we can
    detect rotation without ever seeing the keys. The live keys themselves
    travel on every request as headers; they are never persisted.
    """
    missing = _BYOK_REQUIRED_PROVIDERS - set(data.fingerprints.keys())
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing fingerprints for providers: {sorted(missing)}",
        )
    for provider, fp in data.fingerprints.items():
        if provider not in _BYOK_REQUIRED_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
        if not _SHA256_HEX_RE.match(fp):
            raise HTTPException(
                status_code=400, detail=f"Invalid fingerprint for {provider}: expected lowercase hex SHA-256 (64 chars)"
            )
    users_db.set_byok_active(uid, data.fingerprints)
    invalidate_byok_state_cache(uid)
    clear_trial_paywall_cache(uid)
    return {"active": True}


@router.delete('/v1/users/me/byok-active', tags=['v1'], response_model=BYOKActiveResponse)
def deactivate_byok_endpoint(uid: str = Depends(auth.get_current_user_uid_no_byok_validation)):
    """Drop the user off the BYOK free plan (keys were cleared client-side)."""
    users_db.clear_byok_active(uid)
    invalidate_byok_state_cache(uid)
    clear_trial_paywall_cache(uid)
    return {"active": False}


def _byok_unlimited_subscription() -> Subscription:
    """BYOK free plan: unlimited limits, marked with the `byok` feature flag."""
    return Subscription(
        plan=PlanType.unlimited,
        status=SubscriptionStatus.active,
        features=["byok"],
        limits=PlanLimits(
            transcription_seconds=None,
            words_transcribed=None,
            insights_gained=None,
        ),
    )


@router.get('/v1/users/me/subscription', tags=['v1'], response_model=UserSubscriptionResponse)
def get_user_subscription_endpoint(
    # Keep reachable even when BYOK fingerprints drift — broken-BYOK users
    # must still see their plan so they can recover.
    uid: str = Depends(auth.get_current_user_uid_no_byok_validation),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_app_version: Optional[str] = Header(None, alias='X-App-Version'),
):
    """Gets the user's subscription plan and usage."""
    # BYOK free plan: user supplies their own OpenAI/Anthropic/Gemini/Deepgram keys.
    # Only return unlimited when the request actually carries BYOK headers (desktop).
    # Mobile (no BYOK headers) should see the real subscription even if BYOK is active.
    # Synthetic paid-tier quota for BYOK / marketplace-reviewer overrides so
    # these users aren't surprised by a disabled phone-call feature.
    unlimited_phone_quota = PhoneCallQuota(has_access=True, is_paid=True)

    if users_db.is_byok_active(uid) and has_byok_keys():
        return UserSubscriptionResponse(
            subscription=_byok_unlimited_subscription(),
            transcription_seconds_used=0,
            transcription_seconds_limit=0,
            words_transcribed_used=0,
            words_transcribed_limit=0,
            insights_gained_used=0,
            insights_gained_limit=0,
            available_plans=[],
            show_subscription_ui=False,
            phone_call_quota=unlimited_phone_quota,
        )

    marketplace_reviewers = os.getenv('MARKETPLACE_APP_REVIEWERS', '').split(',')
    if uid in marketplace_reviewers:
        unlimited_sub = Subscription(
            plan=PlanType.unlimited,
            status=SubscriptionStatus.active,
            limits=PlanLimits(
                transcription_seconds=None,
                words_transcribed=None,
                insights_gained=None,
            ),
        )
        return UserSubscriptionResponse(
            subscription=unlimited_sub,
            transcription_seconds_used=0,
            transcription_seconds_limit=0,
            words_transcribed_used=0,
            words_transcribed_limit=0,
            insights_gained_used=0,
            insights_gained_limit=0,
            available_plans=[],
            show_subscription_ui=False,
            phone_call_quota=unlimited_phone_quota,
        )
    # First, reconcile any "basic but actually unlimited" inconsistencies against Stripe once.
    raw_subscription = get_user_subscription(uid)
    reconcile_basic_plan_with_stripe(uid, raw_subscription)

    # Then re-evaluate using our normal "valid subscription" semantics.
    subscription = get_user_valid_subscription(uid)
    if not subscription:
        # Return default basic plan if no valid subscription
        subscription = get_default_basic_subscription()

    # Get current price ID from Stripe if subscription exists
    if subscription.stripe_subscription_id:
        try:
            stripe_sub = stripe_utils.stripe.Subscription.retrieve(subscription.stripe_subscription_id)
            stripe_sub_dict = stripe_sub.to_dict()
            if stripe_sub_dict and stripe_sub_dict.get('items', {}).get('data'):
                subscription.current_price_id = stripe_sub_dict['items']['data'][0]['price']['id']
        except Exception as e:
            logger.error(f"Error retrieving current price ID: {e}")

    # Populate dynamic fields for the response
    subscription.limits = get_plan_limits(subscription.plan)
    is_mobile = x_app_platform in ('ios', 'android')
    subscription.features = get_plan_features(subscription.plan, simplified=is_mobile)

    new_plans_enabled = should_show_new_plans(x_app_platform, x_app_version)

    # Backward-compat: old clients without the `operator` enum value would crash
    # on deserialization. Only send the real plan type to clients that understand it.
    if not new_plans_enabled and subscription.plan == PlanType.operator:
        subscription.plan = PlanType.unlimited

    # Get current usage
    usage = get_monthly_usage_for_subscription(uid)

    # Calculate usage metrics
    transcription_seconds_used = usage.get('transcription_seconds', 0)
    words_transcribed_used = usage.get('words_transcribed', 0)
    insights_gained_used = usage.get('insights_gained', 0)

    # Get limits from subscription (0 means unlimited)
    transcription_seconds_limit = subscription.limits.transcription_seconds or 0
    words_transcribed_limit = subscription.limits.words_transcribed or 0
    insights_gained_limit = subscription.limits.insights_gained or 0

    # Build available plans. Version-gated: new clients see Operator + Architect,
    # old clients get legacy plan names. Legacy plans filtered from purchase catalog.
    all_definitions = get_paid_plan_definitions()
    if not new_plans_enabled:
        all_definitions = adapt_plans_for_legacy_client(all_definitions)
    available_plans: List[SubscriptionPlan] = []
    ever_purchased = has_ever_purchased(uid, raw_subscription)
    definitions_for_user = filter_plans_for_user(
        all_definitions, subscription.plan, platform=x_app_platform, ever_purchased=ever_purchased
    )
    for definition in definitions_for_user:
        plan_prices: List[PricingOption] = []
        monthly_price_id = definition["monthly_price_id"]
        annual_price_id = definition["annual_price_id"]

        if monthly_price_id:
            try:
                price_data = get_generic_cache(f'stripe_price:{monthly_price_id}')
                if not price_data:
                    price = stripe_utils.stripe.Price.retrieve(monthly_price_id)
                    price_data = price.to_dict_recursive()
                    set_generic_cache(f'stripe_price:{monthly_price_id}', price_data, ttl=3600 * 24)

                plan_prices.append(
                    PricingOption(
                        id=price_data['id'],
                        title="Monthly",
                        price_string=f"${price_data['unit_amount'] / 100:.2f}/{price_data['recurring']['interval']}",
                        description="Billed monthly. Cancel anytime.",
                    )
                )
            except Exception as e:
                logger.error(
                    f"Error retrieving monthly price from Stripe for {definition['plan_id']} "
                    f"(price_id={monthly_price_id}): {sanitize(str(e))}"
                )

        if annual_price_id:
            try:
                price_data = get_generic_cache(f'stripe_price:{annual_price_id}')
                if not price_data:
                    price = stripe_utils.stripe.Price.retrieve(annual_price_id)
                    price_data = price.to_dict_recursive()
                    set_generic_cache(f'stripe_price:{annual_price_id}', price_data, ttl=3600 * 24)

                plan_prices.append(
                    PricingOption(
                        id=price_data['id'],
                        title="Annual",
                        price_string=f"${price_data['unit_amount'] / 100:.2f}/{price_data['recurring']['interval']}",
                        description=definition["annual_description"],
                    )
                )
            except Exception as e:
                logger.error(
                    f"Error retrieving annual price from Stripe for {definition['plan_id']} "
                    f"(price_id={annual_price_id}): {sanitize(str(e))}"
                )

        if plan_prices:
            features = (
                get_plan_features(definition["plan_type"], simplified=is_mobile)
                if new_plans_enabled
                else legacy_plan_features(definition["plan_type"])
            )
            available_plans.append(
                SubscriptionPlan(
                    id=definition["plan_id"],
                    title=definition["title"],
                    subtitle=definition.get("subtitle"),
                    description=definition.get("description"),
                    eyebrow=definition.get("eyebrow"),
                    features=features,
                    prices=plan_prices,
                    legacy=bool(definition.get("legacy")),
                )
            )

    show_subscription_ui = not should_hide_subscription_ui(uid, x_app_platform, x_app_version)

    # Phone-call feature access + monthly free-tier usage snapshot.
    phone_call_quota = PhoneCallQuota(**get_phone_call_quota_snapshot(uid).to_client_dict())

    # Chat quota — reuse the shared snapshot helper
    chat_snapshot = get_chat_quota_snapshot(uid, platform=x_app_platform)
    chat_percent = 0.0
    if chat_snapshot['limit'] is not None and chat_snapshot['limit'] > 0:
        chat_percent = min(100.0, round(100.0 * chat_snapshot['used'] / chat_snapshot['limit'], 2))
    chat_allowed = chat_snapshot['allowed']

    return UserSubscriptionResponse(
        subscription=subscription,
        transcription_seconds_used=transcription_seconds_used,
        transcription_seconds_limit=transcription_seconds_limit,
        words_transcribed_used=words_transcribed_used,
        words_transcribed_limit=words_transcribed_limit,
        insights_gained_used=insights_gained_used,
        insights_gained_limit=insights_gained_limit,
        available_plans=available_plans,
        show_subscription_ui=show_subscription_ui,
        chat_quota_used=round(chat_snapshot['used'], 4),
        chat_quota_unit=chat_snapshot['unit'],
        chat_quota_percent=chat_percent,
        chat_quota_allowed=chat_allowed,
        chat_quota_reset_at=chat_snapshot['reset_at'],
        phone_call_quota=phone_call_quota,
        desktop_grandfather_until=neo_grandfather_until(subscription),
    )


@router.get('/v1/users/me/usage-quota', tags=['users'], response_model=ChatUsageQuota)
def get_user_chat_usage_quota(
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    """Current-month chat usage for the user, plus their plan's cap.

    Used by the desktop app. Mobile uses the subscription endpoint instead.
    """
    # BYOK free plan: user brings their own keys, so there's no Omi-side cost
    # to meter. Only return unlimited when BYOK headers are on the request (desktop).
    # Mobile (no headers) should see real quota.
    if users_db.is_byok_active(uid) and has_byok_keys():
        return ChatUsageQuota(
            plan='Free (BYOK)',
            plan_type=PlanType.unlimited.value,
            unit=ChatQuotaUnit.questions,
            used=0.0,
            limit=None,
            percent=0.0,
            allowed=True,
            reset_at=None,
        )

    snapshot = get_chat_quota_snapshot(uid, platform=x_app_platform)
    plan = snapshot['plan']

    if snapshot['limit'] is not None and snapshot['limit'] > 0:
        percent = min(100.0, round(100.0 * snapshot['used'] / snapshot['limit'], 2))
    else:
        percent = 0.0

    return ChatUsageQuota(
        plan=get_plan_display_name(plan),
        plan_type=plan.value,
        unit=ChatQuotaUnit(snapshot['unit']),
        used=round(snapshot['used'], 4),
        limit=snapshot['limit'],
        percent=percent,
        allowed=snapshot['allowed'],
        reset_at=snapshot['reset_at'],
    )


class PaywallStatusResponse(BaseModel):
    paywalled: bool


@router.get('/v1/users/me/paywall', tags=['users'], response_model=PaywallStatusResponse)
def get_user_paywall_status(
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    platform: Optional[str] = Query(None),
):
    """Trial-paywall status for the calling user on the given platform.

    Used by the Rust desktop-backend middleware to decide whether to proxy
    paid LLM / TTS / Pinecone traffic. Mirrors the exact semantics of
    `is_trial_paywalled`: basic plan + no active BYOK + Firebase Auth
    account >3d old + platform in {macos, desktop}. Mobile platforms always
    return `paywalled=false`.

    Platform comes from `X-App-Platform` header (preferred) or `platform`
    query param (fallback). Unknown / missing platforms are never paywalled.
    """
    resolved_platform = x_app_platform or platform
    return PaywallStatusResponse(paywalled=is_trial_paywalled(uid, resolved_platform))


@router.get('/v1/users/me/trial', tags=['users'], response_model=TrialMetadata)
def get_user_trial_status(uid: str = Depends(auth.get_current_user_uid)):
    """Structured trial metadata for the calling user.

    Returns trial timing info (start, end, remaining seconds, expired flag)
    plus the list of features available during trial and the plan the user
    falls to after trial expiry. Used by desktop clients to render countdown
    banners and pre-expiry upgrade nudges.

    Paid-plan and BYOK users get `trial_expired=False` with zeroed timing
    (trial is irrelevant to them — they have full access).
    """
    return get_trial_metadata(uid)


# **************************************
# ****** Daily Summary Settings ********
# **************************************


class DailySummarySettingsResponse(BaseModel):
    enabled: bool
    hour: int  # Local hour (0-23) in user's timezone


class DailySummarySettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    hour: Optional[int] = None  # Local hour (0-23), e.g., 22 for 10 PM, 8 for 8 AM


@router.get('/v1/users/daily-summary-settings', tags=['v1'], response_model=DailySummarySettingsResponse)
def get_daily_summary_settings(uid: str = Depends(auth.get_current_user_uid)):
    """
    Get user's daily summary notification settings.

    Returns:
        - enabled: Whether daily summary notifications are enabled (default: True)
        - hour: Preferred hour in user's local timezone (0-23, default: 22 for 10 PM)
    """
    enabled = notification_db.get_daily_summary_enabled(uid)
    local_hour = notification_db.get_daily_summary_hour_local(uid)

    # Default to 22 (10 PM) local time if not set
    if local_hour is None:
        local_hour = notification_db.DEFAULT_DAILY_SUMMARY_HOUR_LOCAL

    return DailySummarySettingsResponse(enabled=enabled, hour=local_hour)


@router.patch('/v1/users/daily-summary-settings', tags=['v1'], response_model=UserStatusResponse)
def update_daily_summary_settings(data: DailySummarySettingsUpdate, uid: str = Depends(auth.get_current_user_uid)):
    """
    Update user's daily summary notification settings.

    Parameters:
        - enabled: Enable/disable daily summary notifications
        - hour: Preferred hour in local timezone (0-23).
                Examples: 22 (10 PM), 8 (8 AM), 18 (6 PM)

    Note: Hour is stored as local time. The system determines when to send
    based on the user's timezone and will send the summary at the correct local time
    """
    if data.enabled is not None:
        notification_db.set_daily_summary_enabled(uid, data.enabled)

    if data.hour is not None:
        if not (0 <= data.hour <= 23):
            raise HTTPException(status_code=400, detail="Hour must be between 0 and 23")

        try:
            notification_db.set_daily_summary_hour_local(uid, data.hour)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {'status': 'ok'}


class TestDailySummaryRequest(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD format, defaults to today


@router.post('/v1/users/daily-summary-settings/test', tags=['v1'], response_model=DailySummaryTestResponse)
def test_daily_summary(request: TestDailySummaryRequest = None, uid: str = Depends(auth.get_current_user_uid)):
    """
    Test endpoint to manually trigger daily summary for the authenticated user.
    This bypasses the time check and sends a summary immediately.
    Optionally accepts a date parameter (YYYY-MM-DD) to generate summary for a specific date.
    """
    time_zone_name = notification_db.get_user_time_zone(uid)
    tokens = notification_db.get_all_tokens(uid)

    if not tokens:
        raise HTTPException(status_code=400, detail='No notification tokens found for user')

    # Parse date or use today
    target_date = None
    if request and request.date:
        try:
            target_date = datetime.strptime(request.date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail='Invalid date format. Use YYYY-MM-DD')

    # Calculate date boundaries
    if time_zone_name:
        try:
            user_tz = pytz.timezone(time_zone_name)
            if target_date:
                # Use the specified date
                date_str = target_date.strftime('%Y-%m-%d')
                start_of_day = user_tz.localize(datetime.combine(target_date, time.min))
                end_of_day = user_tz.localize(datetime.combine(target_date, time.max))
            else:
                # Use local day boundaries (midnight-to-midnight)
                now_in_user_tz = datetime.now(user_tz)

                # Determine which calendar day to summarize
                if now_in_user_tz.hour < 12:
                    display_date = now_in_user_tz.date() - timedelta(days=1)
                else:
                    display_date = now_in_user_tz.date()
                date_str = display_date.strftime('%Y-%m-%d')
                start_of_day = user_tz.localize(datetime.combine(display_date, time.min))
                end_of_day = user_tz.localize(datetime.combine(display_date, time.max))

            start_date_utc = start_of_day.astimezone(pytz.utc)
            end_date_utc = end_of_day.astimezone(pytz.utc)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Timezone error: {str(e)}')
    else:
        now_utc = datetime.now(pytz.utc)
        if target_date:
            date_str = target_date.strftime('%Y-%m-%d')
            start_date_utc = datetime.combine(target_date, time.min).replace(tzinfo=pytz.utc)
            end_date_utc = datetime.combine(target_date, time.max).replace(tzinfo=pytz.utc)
        else:
            # Use UTC day boundaries
            if now_utc.hour < 12:
                display_date = now_utc.date() - timedelta(days=1)
            else:
                display_date = now_utc.date()
            date_str = display_date.strftime('%Y-%m-%d')
            start_date_utc = datetime.combine(display_date, time.min).replace(tzinfo=pytz.utc)
            end_date_utc = datetime.combine(display_date, time.max).replace(tzinfo=pytz.utc)

    # Get conversations for the date, excluding locked conversations
    conversations_data = conversations_db.get_conversations(
        uid, start_date=start_date_utc, end_date=end_date_utc, date_field='started_at'
    )
    if conversations_data:
        conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]

    if not conversations_data or len(conversations_data) == 0:
        raise HTTPException(status_code=400, detail=f'No conversations found for {date_str}')

    conversations = deserialize_conversations(conversations_data)

    # Generate summary (pass date range for fetching actual action items)
    summary_data = generate_comprehensive_daily_summary(uid, conversations, date_str, start_date_utc, end_date_utc)

    # Store in database
    summary_id = daily_summaries_db.create_daily_summary(uid, summary_data)

    # Send notification
    daily_summary_title = f"{summary_data.get('day_emoji', '📅')} {summary_data.get('headline', 'Your Daily Summary')}"
    summary_body = summary_data.get('overview', 'Tap to see your daily summary')
    if len(summary_body) > 150:
        summary_body = summary_body[:147] + "..."

    ai_message = NotificationMessage(
        text=summary_body,
        from_integration='false',
        type='day_summary',
        notification_type='daily_summary',
        navigate_to=f"/daily-summary/{summary_id}",
    )

    send_notification(
        uid, daily_summary_title, summary_body, NotificationMessage.get_message_as_dict(ai_message), tokens=tokens
    )

    return {
        'status': 'ok',
        'message': f'Daily summary generated for {date_str}',
        'summary_id': summary_id,
        'conversations_count': len(conversations),
    }


# Daily Summaries API


@router.get('/v1/users/daily-summaries', tags=['v1'], response_model=DailySummariesResponse)
def get_daily_summaries(
    limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), uid: str = Depends(auth.get_current_user_uid)
):
    """
    Get list of daily summaries for the authenticated user.
    Returns summaries in reverse chronological order.
    """
    summaries = daily_summaries_db.get_daily_summaries(uid, limit=limit, offset=offset)
    return {'summaries': summaries}


@router.get('/v1/users/daily-summaries/{summary_id}', tags=['v1'], response_model=DailySummaryResponse)
def get_daily_summary(summary_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Get a single daily summary by ID.
    """
    summary = daily_summaries_db.get_daily_summary(uid, summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail='Daily summary not found')
    return summary


@router.patch('/v1/users/daily-summaries/{summary_id}/visibility', tags=['v1'], response_model=UserStatusResponse)
def set_daily_summary_visibility(summary_id: str, value: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Set the visibility of a daily summary. Use value='shared' to make it shareable.
    """
    if value not in ('shared', 'private'):
        raise HTTPException(status_code=400, detail="Invalid visibility value. Must be 'shared' or 'private'")
    summary = daily_summaries_db.get_daily_summary(uid, summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail='Daily summary not found')
    daily_summaries_db.set_daily_summary_visibility(uid, summary_id, value)
    if value == 'private':
        remove_daily_summary_to_uid(summary_id)
    else:
        store_daily_summary_to_uid(summary_id, uid)
    return {'status': 'Ok'}


@router.delete('/v1/users/daily-summaries/{summary_id}', tags=['v1'], response_model=UserStatusResponse)
def delete_daily_summary(summary_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Delete a daily summary by ID.
    """
    summary = daily_summaries_db.get_daily_summary(uid, summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail='Daily summary not found')

    daily_summaries_db.delete_daily_summary(uid, summary_id)
    return {'status': 'ok'}


# Cooldown between user-initiated regenerations of the same summary. Cheap
# guard against double-taps wasting LLM tokens — not a security boundary.
_REGENERATE_COOLDOWN_SECONDS = 30


@router.post('/v1/users/daily-summaries/{summary_id}/regenerate', tags=['v1'], response_model=DailySummaryResponse)
def regenerate_daily_summary(summary_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Re-run summary generation for the date of an existing daily summary and
    overwrite the same doc in place. No push notification — the user is
    already looking at the page.
    """
    summary = daily_summaries_db.get_daily_summary(uid, summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail='Daily summary not found')

    date_str = summary.get('date')
    if not date_str:
        raise HTTPException(status_code=400, detail='Daily summary is missing its date')
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(status_code=400, detail='Daily summary has an invalid date')

    cooldown_key = f'daily_summary_regen:{uid}:{summary_id}'
    if get_generic_cache(cooldown_key):
        raise HTTPException(
            status_code=429,
            detail='Please wait a few seconds before regenerating this recap again.',
        )
    # Set the cooldown BEFORE the LLM call, not after. The check-then-set
    # window was wide enough that two concurrent requests could both pass
    # the guard and double-bill the LLM. This isn't atomic SETNX, but the
    # eager set closes the practical race for accidental double-taps.
    set_generic_cache(cooldown_key, {'at': datetime.utcnow().isoformat()}, ttl=_REGENERATE_COOLDOWN_SECONDS)

    # Resolve the user's local day boundaries the same way the scheduled job
    # does, so the regenerated payload uses the identical conversation set.
    time_zone_name = notification_db.get_user_time_zone(uid)
    if time_zone_name:
        try:
            user_tz = pytz.timezone(time_zone_name)
            start_of_day = user_tz.localize(datetime.combine(target_date, time.min))
            end_of_day = user_tz.localize(datetime.combine(target_date, time.max))
            start_date_utc = start_of_day.astimezone(pytz.utc)
            end_date_utc = end_of_day.astimezone(pytz.utc)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Timezone error: {str(e)}')
    else:
        start_date_utc = datetime.combine(target_date, time.min).replace(tzinfo=pytz.utc)
        end_date_utc = datetime.combine(target_date, time.max).replace(tzinfo=pytz.utc)

    conversations_data = conversations_db.get_conversations(
        uid, start_date=start_date_utc, end_date=end_date_utc, date_field='started_at'
    )
    if conversations_data:
        conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]
    if not conversations_data:
        raise HTTPException(status_code=400, detail=f'No conversations found for {date_str}')

    conversations = deserialize_conversations(conversations_data)

    summary_data = generate_comprehensive_daily_summary(uid, conversations, date_str, start_date_utc, end_date_utc)
    # Preserve fields readers care about that the generator silently resets:
    # - visibility: sharing state shouldn't toggle off on regenerate
    # - created_at: generator stamps a fresh utcnow(), but UI sorts/displays
    #   summaries by when they were first created, not last regenerated
    if 'visibility' in summary:
        summary_data['visibility'] = summary['visibility']
    if 'created_at' in summary:
        summary_data['created_at'] = summary['created_at']
    summary_data['regenerated_at'] = datetime.utcnow().isoformat()

    daily_summaries_db.update_daily_summary(uid, summary_id, summary_data)

    refreshed = daily_summaries_db.get_daily_summary(uid, summary_id)
    return refreshed or {**summary_data, 'id': summary_id}


@router.get('/v1/daily-summaries/{summary_id}/shared', tags=['v1'], response_model=DailySummaryResponse)
def get_shared_daily_summary(summary_id: str):
    """
    Public endpoint to retrieve a daily summary for sharing. No auth required.
    """
    uid = get_daily_summary_uid(summary_id)
    if not uid:
        raise HTTPException(status_code=404, detail='Daily summary not found')

    summary = daily_summaries_db.get_daily_summary(uid, summary_id)
    if not summary or summary.get('visibility') != 'shared':
        raise HTTPException(status_code=404, detail='Daily summary not found')

    _PUBLIC_FIELDS = {
        'id',
        'date',
        'headline',
        'overview',
        'day_emoji',
        'stats',
        'highlights',
        'action_items',
        'decisions_made',
        'knowledge_nuggets',
    }
    return {k: v for k, v in summary.items() if k in _PUBLIC_FIELDS}


# ***********************************
# *** Mentor Notification Settings ***
# ***********************************


class MentorNotificationSettingsResponse(BaseModel):
    frequency: int  # 0-5 where 0=disabled, 1=most selective, 5=most proactive


class MentorNotificationSettingsUpdate(BaseModel):
    frequency: int  # 0-5 where 0=disabled, 1=most selective, 5=most proactive


@router.get('/v1/users/mentor-notification-settings', tags=['v1'], response_model=MentorNotificationSettingsResponse)
def get_mentor_notification_settings(uid: str = Depends(auth.get_current_user_uid)):
    """
    Get user's mentor notification frequency preference.

    Returns:
        - frequency: Notification frequency (0-5)
          - 0 = disabled
          - 1 = ultra selective (least frequent)
          - 3 = balanced (default)
          - 5 = very proactive (most frequent)
    """
    frequency = notification_db.get_mentor_notification_frequency(uid)
    return MentorNotificationSettingsResponse(frequency=frequency)


@router.patch('/v1/users/mentor-notification-settings', tags=['v1'], response_model=UserStatusResponse)
def update_mentor_notification_settings(
    data: MentorNotificationSettingsUpdate, uid: str = Depends(auth.get_current_user_uid)
):
    """
    Update user's mentor notification frequency preference.

    Parameters:
        - frequency: Notification frequency (0-5)
          - 0 = disabled
          - 1 = ultra selective (least frequent)
          - 3 = balanced (default)
          - 5 = very proactive (most frequent)
    """
    try:
        notification_db.set_mentor_notification_frequency(uid, data.frequency)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {'status': 'ok'}


# LLM Usage Tracking Endpoints


class LlmUsageFeatureResponse(BaseModel):
    feature: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0


class LlmUsageResponse(BaseModel):
    summary: Dict[str, Any] = Field(default_factory=dict)
    top_features: List[LlmUsageFeatureResponse] = Field(default_factory=list)
    period_days: int


class LlmUsageRecordResponse(BaseModel):
    status: str


class LlmTotalCostResponse(BaseModel):
    total_cost_usd: float


@router.get('/v1/users/me/llm-usage', tags=['users'], response_model=LlmUsageResponse)
def get_llm_usage(
    days: int = Query(default=30, ge=1, le=365),
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Get LLM token usage summary for the current user.

    Returns usage breakdown by feature for the specified time period.
    """
    summary = llm_usage_db.get_usage_summary(uid, days=days)
    top_features = llm_usage_db.get_top_features(uid, days=days, limit=5)

    return {
        'summary': summary,
        'top_features': top_features,
        'period_days': days,
    }


@router.get('/v1/users/me/llm-usage/top-features', tags=['users'], response_model=List[LlmUsageFeatureResponse])
def get_llm_top_features(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=3, ge=1, le=10),
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Get top features by LLM token usage for the current user.

    Returns the top N features sorted by total token consumption.
    """
    return llm_usage_db.get_top_features(uid, days=days, limit=limit)


# response_model omitted: this streams a chunked JSON document via StreamingResponse (not a single JSON object);
# the responses= override documents the streamed shape in OpenAPI without enforcing response_model validation.
@router.get('/v1/users/export', tags=['v1'], responses={200: {'model': UserDataExportResponse}})
def export_all_user_data(uid: str = Depends(auth.get_current_user_uid)):
    """Export all user data for GDPR/CCPA compliance. Streams response to avoid timeouts."""
    return StreamingResponse(
        iter_user_data_export(uid),
        media_type='application/json',
        headers={'Content-Disposition': 'attachment; filename="omi-export.json"'},
    )


# ============================================================================
# Notification Settings
# ============================================================================


class UpdateNotificationSettingsRequest(BaseModel):
    enabled: bool | None = None
    frequency: int | None = Field(None, ge=0, le=5)


class NotificationSettingsResponse(BaseModel):
    enabled: bool
    frequency: int


@router.get('/v1/users/notification-settings', tags=['users'], response_model=NotificationSettingsResponse)
def get_notification_settings(uid: str = Depends(auth.get_current_user_uid)):
    return users_db.get_notification_settings(uid)


@router.patch('/v1/users/notification-settings', tags=['users'], response_model=NotificationSettingsResponse)
def update_notification_settings(
    request: UpdateNotificationSettingsRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return users_db.update_notification_settings(uid, enabled=request.enabled, frequency=request.frequency)


# ============================================================================
# Assistant Settings
# ============================================================================


class SharedAssistantSettings(BaseModel):
    cooldown_interval: int | None = None
    glow_overlay_enabled: bool | None = None
    analysis_delay: int | None = None
    screen_analysis_enabled: bool | None = None


class FocusAssistantSettings(BaseModel):
    enabled: bool | None = None
    analysis_prompt: str | None = Field(None, max_length=10000)
    cooldown_interval: int | None = None
    notifications_enabled: bool | None = None
    excluded_apps: list[str] | None = None


class TaskAssistantSettings(BaseModel):
    enabled: bool | None = None
    analysis_prompt: str | None = Field(None, max_length=10000)
    extraction_interval: float | None = None
    min_confidence: float | None = Field(None, ge=0.0, le=1.0)
    notifications_enabled: bool | None = None
    allowed_apps: list[str] | None = None
    browser_keywords: list[str] | None = None


class AdviceAssistantSettings(BaseModel):
    enabled: bool | None = None
    analysis_prompt: str | None = Field(None, max_length=10000)
    extraction_interval: float | None = None
    min_confidence: float | None = Field(None, ge=0.0, le=1.0)
    notifications_enabled: bool | None = None
    excluded_apps: list[str] | None = None


class MemoryAssistantSettings(BaseModel):
    enabled: bool | None = None
    analysis_prompt: str | None = Field(None, max_length=10000)
    extraction_interval: float | None = None
    min_confidence: float | None = Field(None, ge=0.0, le=1.0)
    notifications_enabled: bool | None = None
    excluded_apps: list[str] | None = None


class FloatingBarSettings(BaseModel):
    voice_answers_enabled: bool | None = None
    elevenlabs_voice_id: str | None = Field(None, max_length=200)


class UpdateAssistantSettingsRequest(BaseModel):
    shared: SharedAssistantSettings | None = None
    focus: FocusAssistantSettings | None = None
    task: TaskAssistantSettings | None = None
    advice: AdviceAssistantSettings | None = None
    memory: MemoryAssistantSettings | None = None
    floating_bar: FloatingBarSettings | None = None
    update_channel: str | None = Field(None, max_length=50)


class AssistantSettingsResponse(UpdateAssistantSettingsRequest):
    model_config = ConfigDict(extra='allow')


@router.get('/v1/users/assistant-settings', tags=['users'], response_model=AssistantSettingsResponse)
def get_assistant_settings(uid: str = Depends(auth.get_current_user_uid)):
    return users_db.get_assistant_settings(uid)


@router.patch('/v1/users/assistant-settings', tags=['users'], response_model=AssistantSettingsResponse)
def update_assistant_settings(
    request: UpdateAssistantSettingsRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    settings = request.model_dump(exclude_unset=True)
    return users_db.update_assistant_settings(uid, settings)


# ============================================================================
# AI User Profile
# ============================================================================


class UpdateAIUserProfileRequest(BaseModel):
    profile_text: str | None = Field(None, max_length=50000)
    generated_at: Optional[str] = None
    data_sources_used: int | None = Field(None, ge=0)


class AIUserProfileResponse(BaseModel):
    profile_text: str | None = None
    generated_at: Optional[str] = None
    data_sources_used: int | None = None


@router.get('/v1/users/ai-profile', tags=['users'], response_model=AIUserProfileResponse | None)
def get_ai_profile(uid: str = Depends(auth.get_current_user_uid)):
    return users_db.get_ai_user_profile(uid)


@router.patch('/v1/users/ai-profile', tags=['users'], response_model=AIUserProfileResponse)
def update_ai_profile(
    request: UpdateAIUserProfileRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return users_db.update_ai_user_profile(
        uid,
        profile_text=request.profile_text,
        generated_at=request.generated_at,
        data_sources_used=request.data_sources_used,
    )


# ============================================================================
# Bucket-based LLM Usage (extends existing /v1/users/me/llm-usage endpoints above)
# ============================================================================


class RecordLlmUsageBucketRequest(BaseModel):
    input_tokens: int = Field(0, ge=0)
    output_tokens: int = Field(0, ge=0)
    cache_read_tokens: int = Field(0, ge=0)
    cache_write_tokens: int = Field(0, ge=0)
    total_tokens: int = Field(0, ge=0)
    cost_usd: float = Field(0.0, ge=0.0)
    account: str = Field('omi', max_length=100)


@router.post('/v1/users/me/llm-usage', tags=['users'], response_model=LlmUsageRecordResponse)
def record_llm_usage_bucket(
    request: RecordLlmUsageBucketRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    llm_usage_db.record_llm_usage_bucket(
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


@router.get('/v1/users/me/llm-usage/total', tags=['users'], response_model=LlmTotalCostResponse)
def get_total_llm_cost(uid: str = Depends(auth.get_current_user_uid)):
    total = llm_usage_db.get_total_llm_cost(uid)
    return {'total_cost_usd': total}
