import threading
import uuid
from typing import List, Dict, Any, Union, Optional
import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import (
    conversations as conversations_db,
    memories as memories_db,
    chat as chat_db,
    user_usage as user_usage_db,
    notifications as notification_db,
    daily_summaries as daily_summaries_db,
)
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
)
from database.users import (
    get_user_transcription_preferences,
    set_user_transcription_preferences,
)
from database.users import *
from models.conversation import Geolocation, Conversation
from models.other import Person, CreatePerson
from typing import Optional
from models.user_usage import UserUsageResponse, UsagePeriod
from datetime import datetime

from models.users import WebhookType, UserSubscriptionResponse, SubscriptionPlan, PlanType, PricingOption
from utils.apps import get_available_app_by_id
from utils.subscription import (
    get_plan_limits,
    get_plan_features,
    get_monthly_usage_for_subscription,
    reconcile_basic_plan_with_stripe,
)
from utils import stripe as stripe_utils
from utils.llm.followup import followup_question_prompt
from utils.notifications import send_notification, send_training_data_submitted_notification
from utils.other import endpoints as auth
from utils.other.storage import (
    delete_all_conversation_recordings,
    get_speech_sample_signed_urls,
    delete_user_person_speech_samples,
    delete_user_person_speech_sample,
)
from utils.webhooks import webhook_first_time_setup

router = APIRouter()


class MigrationRequest(BaseModel):
    type: str
    id: str
    target_level: str


class MigrationTargetRequest(BaseModel):
    target_level: str


class BatchMigrationRequest(BaseModel):
    requests: List[MigrationRequest]


@router.get('/v1/users/profile', tags=['v1'])
def get_user_profile_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """Gets the full user profile, including data protection and migration status."""
    profile = get_user_profile(uid)
    if not profile:
        raise HTTPException(status_code=410, detail="User not found")
    return profile


@router.delete('/v1/users/delete-account', tags=['v1'])
def delete_account(uid: str = Depends(auth.get_current_user_uid)):
    try:
        delete_user_data(uid)
        # delete user from firebase auth
        auth.delete_account(uid)
        return {'status': 'ok', 'message': 'Account deleted successfully'}
    except Exception as e:
        print('delete_account', str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.patch('/v1/users/geolocation', tags=['v1'])
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

            cache_user_geolocation(uid, geolocation.dict())
        except Exception as e:
            print(f"Error processing geolocation update, caching new location anyway. Error: {e}")
            cache_user_geolocation(uid, geolocation.dict())
    else:
        # No previous location, so cache the new one
        cache_user_geolocation(uid, geolocation.dict())

    return {'status': 'ok'}


# ***********************************************
# ************* DEVELOPER WEBHOOKS **************
# ***********************************************


@router.post('/v1/users/developer/webhook/{wtype}', tags=['v1'])
def set_user_webhook_endpoint(wtype: WebhookType, data: dict, uid: str = Depends(auth.get_current_user_uid)):
    url = data['url']
    if url == '' or url == ',':
        disable_user_webhook_db(uid, wtype)
    set_user_webhook_db(uid, wtype, url)
    return {'status': 'ok'}


@router.get('/v1/users/developer/webhook/{wtype}', tags=['v1'])
def get_user_webhook_endpoint(wtype: WebhookType, uid: str = Depends(auth.get_current_user_uid)):
    return {'url': get_user_webhook_db(uid, wtype)}


@router.post('/v1/users/developer/webhook/{wtype}/disable', tags=['v1'])
def disable_user_webhook_endpoint(wtype: WebhookType, uid: str = Depends(auth.get_current_user_uid)):
    disable_user_webhook_db(uid, wtype)
    return {'status': 'ok'}


@router.post('/v1/users/developer/webhook/{wtype}/enable', tags=['v1'])
def enable_user_webhook_endpoint(wtype: WebhookType, uid: str = Depends(auth.get_current_user_uid)):
    enable_user_webhook_db(uid, wtype)
    return {'status': 'ok'}


@router.get('/v1/users/developer/webhooks/status', tags=['v1'])
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


@router.post('/v1/users/store-recording-permission', tags=['v1'])
def store_recording_permission(value: bool, uid: str = Depends(auth.get_current_user_uid)):
    set_user_store_recording_permission(uid, value)
    return {'status': 'ok'}


@router.get('/v1/users/store-recording-permission', tags=['v1'])
def get_store_recording_permission(uid: str = Depends(auth.get_current_user_uid)):
    return {'store_recording_permission': get_user_store_recording_permission(uid)}


@router.delete('/v1/users/store-recording-permission', tags=['v1'])
def delete_permission_and_recordings(uid: str = Depends(auth.get_current_user_uid)):
    set_user_store_recording_permission(uid, False)
    delete_all_conversation_recordings(uid)
    return {'status': 'ok'}


# *************************************************
# ************* PRIVATE CLOUD SYNC ****************
# *************************************************


@router.post('/v1/users/private-cloud-sync', tags=['v1'])
def set_private_cloud_sync(value: bool, uid: str = Depends(auth.get_current_user_uid)):
    set_user_private_cloud_sync_enabled(uid, value)
    return {'status': 'ok'}


@router.get('/v1/users/private-cloud-sync', tags=['v1'])
def get_private_cloud_sync(uid: str = Depends(auth.get_current_user_uid)):
    return {'private_cloud_sync_enabled': get_user_private_cloud_sync_enabled(uid)}


# ****************************************
# ************* PEOPLE CRUD **************
# ****************************************


# TODO: consider adding person photo.
@router.post('/v1/users/people', tags=['v1'], response_model=Person)
def create_new_person(data: CreatePerson, uid: str = Depends(auth.get_current_user_uid)):
    data = {
        'id': str(uuid.uuid4()),
        'name': data.name,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }
    result = create_person(uid, data)
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
    print('get_all_people', include_speech_samples)
    people = get_people(uid)
    if include_speech_samples:
        # Convert stored GCS paths to signed URLs for each person
        for person in people:
            stored_paths = person.get('speech_samples', [])
            person['speech_samples'] = get_speech_sample_signed_urls(stored_paths)
    return people


@router.patch('/v1/users/people/{person_id}/name', tags=['v1'])
def update_person_name(
    person_id: str,
    value: str,  # = Field(min_length=2, max_length=40),
    uid: str = Depends(auth.get_current_user_uid),
):
    update_person(uid, person_id, value)
    return {'status': 'ok'}


@router.delete('/v1/users/people/{person_id}', tags=['v1'], status_code=204)
def delete_person_endpoint(person_id: str, uid: str = Depends(auth.get_current_user_uid)):
    delete_person(uid, person_id)
    delete_user_person_speech_samples(uid, person_id)
    return {'status': 'ok'}


@router.delete('/v1/users/people/{person_id}/speech-samples/{sample_index}', tags=['v1'])
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


@router.delete('/v1/joan/{memory_id}/followup-question', tags=['v1'], status_code=204)
def delete_person_endpoint(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    if memory_id == '0':
        memory = get_in_progress_conversation(uid)
        if not memory:
            raise HTTPException(status_code=400, detail='No memory in progres')
    else:
        memory = get_conversation(uid, memory_id)
    memory = Conversation(**memory)
    return {'result': followup_question_prompt(memory.transcript_segments)}


# **************************************
# ************* Analytics **************
# **************************************


@router.post('/v1/users/analytics/memory_summary', tags=['v1'])
def set_memory_summary_rating(
    memory_id: str,
    value: int,  # 0, 1, -1 (shown)
    uid: str = Depends(auth.get_current_user_uid),
):
    set_conversation_summary_rating_score(uid, memory_id, value)
    return {'status': 'ok'}


@router.get('/v1/users/analytics/memory_summary', tags=['v1'])
def get_memory_summary_rating(
    memory_id: str,
    _: str = Depends(auth.get_current_user_uid),
):
    rating = get_conversation_summary_rating_score(memory_id)
    # TODO: later ask reason, a set of options, if user says good, whats the best, if bad, whats the worst
    if not rating:
        return {'has_rating': False}
    return {'has_rating': rating.get('value', -1) != -1, 'rating': rating.get('value', -1)}


@router.post('/v1/users/analytics/chat_message', tags=['v1'])
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
        print(f"⚠️  LangSmith feedback submission error (non-fatal): {e}")
    
    return {'status': 'ok'}


# ***************************************
# ************* Language ****************
# ***************************************


@router.get('/v1/users/language', tags=['v1'])
def get_user_language(uid: str = Depends(auth.get_current_user_uid)):
    """Get the user's preferred language."""
    language = get_user_language_preference(uid)
    if not language:
        return {'language': None}
    return {'language': language}


@router.patch('/v1/users/language', tags=['v1'])
def set_user_language(data: dict, uid: str = Depends(auth.get_current_user_uid)):
    """Set the user's preferred language (e.g., 'en', 'vi', etc.)."""
    language = data.get('language')
    if not language:
        raise HTTPException(status_code=400, detail="Language is required")
    set_user_language_preference(uid, language)
    return {'status': 'ok'}


# *************************************************
# ********** Transcription Preferences ************
# *************************************************


class TranscriptionPreferencesResponse(BaseModel):
    single_language_mode: bool = False
    vocabulary: List[str] = []


class TranscriptionPreferencesUpdate(BaseModel):
    single_language_mode: Optional[bool] = None
    vocabulary: Optional[List[str]] = None


@router.get('/v1/users/transcription-preferences', tags=['v1'], response_model=TranscriptionPreferencesResponse)
def get_transcription_preferences_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """Get user's transcription preferences (single language mode, vocabulary)."""
    prefs = get_user_transcription_preferences(uid)
    return prefs


@router.patch('/v1/users/transcription-preferences', tags=['v1'])
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


@router.post('/v1/users/migration/requests', tags=['v1'])
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


@router.get('/v1/users/migration/requests', tags=['v1'])
def get_migration_requests(target_level: str, uid: str = Depends(auth.get_current_user_uid)):
    """Checks which documents need to be migrated to the target level."""
    if target_level != 'enhanced':
        raise HTTPException(status_code=400, detail="Invalid target_level. Only migration to 'enhanced' is supported.")

    conversations_to_migrate = conversations_db.get_conversations_to_migrate(uid, target_level)
    memories_to_migrate = memories_db.get_memories_to_migrate(uid, target_level)
    chats_to_migrate = chat_db.get_chats_to_migrate(uid, target_level)
    needs_migration = conversations_to_migrate + memories_to_migrate + chats_to_migrate
    return {"needs_migration": needs_migration}


@router.post('/v1/users/migration/batch-requests', tags=['v1'])
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
            print(error_detail)
            errors.append(error_detail)

    if errors:
        raise HTTPException(status_code=500, detail={"message": "Some objects failed to migrate.", "errors": errors})

    return {'status': 'ok'}


@router.post('/v1/users/migration/requests/data-protection-level/finalize', tags=['v1'])
def finalize_migration_request(request: MigrationTargetRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Finalizes the migration by setting the user's global protection level."""
    if request.target_level != 'enhanced':
        raise HTTPException(status_code=400, detail="Invalid target_level. Only migration to 'enhanced' is supported.")

    finalize_migration(uid, request.target_level)
    set_user_data_protection_level(uid, request.target_level)
    return {'status': 'ok'}


@router.put('/v1/users/preferences/app', tags=['v1'])
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
        print(f"Failed to set preferred app in Redis for user {uid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to store app preference.")

    return {"status": "ok", "message": f"App {app_id_to_set} set as preferred app for user {uid}."}


# **************************************
# *********** Training Data ************
# **************************************


@router.get('/v1/users/training-data-opt-in', tags=['v1'])
def get_training_data_opt_in_status(uid: str = Depends(auth.get_current_user_uid)):
    """Get the user's training data opt-in status."""
    opt_in_data = get_user_training_data_opt_in(uid)
    if not opt_in_data:
        return {'opted_in': False, 'status': None}
    return {'opted_in': True, 'status': opt_in_data.get('status')}


@router.post('/v1/users/training-data-opt-in', tags=['v1'])
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


@router.get('/v1/users/me/subscription', tags=['v1'], response_model=UserSubscriptionResponse)
def get_user_subscription_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """Gets the user's subscription plan and usage."""
    marketplace_reviewers = os.getenv('MARKETPLACE_APP_REVIEWERS', '').split(',')
    if uid in marketplace_reviewers:
        unlimited_sub = Subscription(
            plan=PlanType.unlimited,
            status=SubscriptionStatus.active,
            limits=PlanLimits(
                transcription_seconds=None,
                words_transcribed=None,
                insights_gained=None,
                memories_created=None,
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
            memories_created_used=0,
            memories_created_limit=0,
            available_plans=[],
            show_subscription_ui=False,
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
            print(f"Error retrieving current price ID: {e}")

    # Populate dynamic fields for the response
    subscription.limits = get_plan_limits(subscription.plan)
    subscription.features = get_plan_features(subscription.plan)

    # Get current usage
    usage = get_monthly_usage_for_subscription(uid)

    # Calculate usage metrics
    transcription_seconds_used = usage.get('transcription_seconds', 0)
    words_transcribed_used = usage.get('words_transcribed', 0)
    insights_gained_used = usage.get('insights_gained', 0)
    memories_created_used = usage.get('memories_created', 0)

    # Get limits from subscription (0 means unlimited)
    transcription_seconds_limit = subscription.limits.transcription_seconds or 0
    words_transcribed_limit = subscription.limits.words_transcribed or 0
    insights_gained_limit = subscription.limits.insights_gained or 0
    memories_created_limit = subscription.limits.memories_created or 0

    # Build available plans for upgrading
    available_plans: List[SubscriptionPlan] = []
    monthly_price_id = os.getenv('STRIPE_UNLIMITED_MONTHLY_PRICE_ID')
    annual_price_id = os.getenv('STRIPE_UNLIMITED_ANNUAL_PRICE_ID')

    unlimited_plan_prices: List[PricingOption] = []
    if monthly_price_id:
        try:
            price_data = get_generic_cache(f'stripe_price:{monthly_price_id}')
            if not price_data:
                price = stripe_utils.stripe.Price.retrieve(monthly_price_id)
                price_data = price.to_dict_recursive()
                set_generic_cache(f'stripe_price:{monthly_price_id}', price_data, ttl=3600 * 24)  # 24 hours

            unlimited_plan_prices.append(
                PricingOption(
                    id=price_data['id'],
                    title="Monthly",
                    price_string=f"${price_data['unit_amount'] / 100:.2f}/{price_data['recurring']['interval']}",
                    description="Billed monthly. Cancel anytime.",
                )
            )
        except Exception as e:
            print(f"Error retrieving monthly price from Stripe: {e}")

    if annual_price_id:
        try:
            price_data = get_generic_cache(f'stripe_price:{annual_price_id}')
            if not price_data:
                price = stripe_utils.stripe.Price.retrieve(annual_price_id)
                price_data = price.to_dict_recursive()
                set_generic_cache(f'stripe_price:{annual_price_id}', price_data, ttl=3600 * 24)  # 24 hours

            unlimited_plan_prices.append(
                PricingOption(
                    id=price_data['id'],
                    title="Annual",
                    price_string=f"${price_data['unit_amount'] / 100:.2f}/{price_data['recurring']['interval']}",
                    description="Save 20% with annual billing.",
                )
            )
        except Exception as e:
            print(f"Error retrieving annual price from Stripe: {e}")

    if unlimited_plan_prices:
        available_plans.append(
            SubscriptionPlan(
                id="unlimited",
                title="Unlimited",
                features=[
                    "Unlimited listening time",
                    "Unlimited words transcribed",
                    "Unlimited insights",
                    "Unlimited memories",
                ],
                prices=unlimited_plan_prices,
            )
        )

    return UserSubscriptionResponse(
        subscription=subscription,
        transcription_seconds_used=transcription_seconds_used,
        transcription_seconds_limit=transcription_seconds_limit,
        words_transcribed_used=words_transcribed_used,
        words_transcribed_limit=words_transcribed_limit,
        insights_gained_used=insights_gained_used,
        insights_gained_limit=insights_gained_limit,
        memories_created_used=memories_created_used,
        memories_created_limit=memories_created_limit,
        available_plans=available_plans,
    )


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


@router.patch('/v1/users/daily-summary-settings', tags=['v1'])
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


@router.post('/v1/users/daily-summary-settings/test', tags=['v1'])
def test_daily_summary(request: TestDailySummaryRequest = None, uid: str = Depends(auth.get_current_user_uid)):
    """
    Test endpoint to manually trigger daily summary for the authenticated user.
    This bypasses the time check and sends a summary immediately.
    Optionally accepts a date parameter (YYYY-MM-DD) to generate summary for a specific date.
    """
    from datetime import datetime, time
    import pytz
    from utils.llm.external_integrations import generate_comprehensive_daily_summary
    from models.conversation import Conversation
    from utils.notifications import send_notification
    from models.notification_message import NotificationMessage

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
                # Use today
                now_in_user_tz = datetime.now(user_tz)
                date_str = now_in_user_tz.strftime('%Y-%m-%d')
                start_of_day = user_tz.localize(datetime.combine(now_in_user_tz.date(), time.min))
                end_of_day = now_in_user_tz

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
            date_str = now_utc.strftime('%Y-%m-%d')
            start_date_utc = datetime.combine(now_utc.date(), time.min).replace(tzinfo=pytz.utc)
            end_date_utc = now_utc

    # Get conversations for the date
    conversations_data = conversations_db.get_conversations(uid, start_date=start_date_utc, end_date=end_date_utc)

    if not conversations_data or len(conversations_data) == 0:
        raise HTTPException(status_code=400, detail=f'No conversations found for {date_str}')

    conversations = [Conversation(**convo_data) for convo_data in conversations_data]

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


@router.get('/v1/users/daily-summaries', tags=['v1'])
def get_daily_summaries(
    limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), uid: str = Depends(auth.get_current_user_uid)
):
    """
    Get list of daily summaries for the authenticated user.
    Returns summaries in reverse chronological order.
    """
    summaries = daily_summaries_db.get_daily_summaries(uid, limit=limit, offset=offset)
    return {'summaries': summaries}


@router.get('/v1/users/daily-summaries/{summary_id}', tags=['v1'])
def get_daily_summary(summary_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Get a single daily summary by ID.
    """
    summary = daily_summaries_db.get_daily_summary(uid, summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail='Daily summary not found')
    return summary


@router.delete('/v1/users/daily-summaries/{summary_id}', tags=['v1'])
def delete_daily_summary(summary_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Delete a daily summary by ID.
    """
    # Verify it exists first
    summary = daily_summaries_db.get_daily_summary(uid, summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail='Daily summary not found')

    daily_summaries_db.delete_daily_summary(uid, summary_id)
    return {'status': 'ok'}
