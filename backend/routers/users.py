import threading
import uuid
from typing import List, Dict, Any, Union
import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import (
    conversations as conversations_db,
    memories as memories_db,
    chat as chat_db,
    user_usage as user_usage_db,
)
from database.conversations import get_in_progress_conversation, get_conversation
from database.redis_db import (
    cache_user_geolocation,
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
from database.users import *
from models.conversation import Geolocation, Conversation
from models.other import Person, CreatePerson
from typing import Optional
from models.user_usage import UserUsageResponse, UsagePeriod
from datetime import datetime

from models.users import WebhookType, UserSubscriptionResponse, SubscriptionPlan, PlanType, PricingOption
from utils.apps import get_available_app_by_id
from utils.subscription import get_plan_limits, get_plan_features, get_monthly_usage_for_subscription
from utils import stripe as stripe_utils
from utils.llm.followup import followup_question_prompt
from utils.other import endpoints as auth
from utils.other.storage import (
    delete_all_conversation_recordings,
    get_user_person_speech_samples,
    delete_user_person_speech_samples,
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
        person['speech_samples'] = get_user_person_speech_samples(uid, person['id'])
    return person


@router.get('/v1/users/people', tags=['v1'], response_model=List[Person])
def get_all_people(include_speech_samples: bool = True, uid: str = Depends(auth.get_current_user_uid)):
    print('get_all_people', include_speech_samples)
    people = get_people(uid)
    if include_speech_samples:

        def single(person):
            person['speech_samples'] = get_user_person_speech_samples(uid, person['id'])

        threads = [threading.Thread(target=single, args=(person,)) for person in people]
        [t.start() for t in threads]
        [t.join() for t in threads]
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
    uid: str = Depends(auth.get_current_user_uid),
):
    set_chat_message_rating_score(uid, message_id, value)
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
    subscription = get_user_valid_subscription(uid)
    if not subscription:
        # Return default basic plan if no valid subscription
        subscription = get_default_basic_subscription()

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
