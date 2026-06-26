from __future__ import annotations

import logging
import threading

from database import users as users_db
from database.action_items import get_action_item_ids
from database.conversations import get_conversation_ids
from database.memories import get_memory_ids
from database.screen_activity import get_screen_activity_ids
from database.vector_db import (
    delete_action_item_vectors_batch,
    delete_conversation_vectors_batch,
    delete_memory_vectors_batch,
    delete_screen_activity_vectors,
    delete_transcript_chunk_vectors_batch,
)
from utils import stripe as stripe_utils
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.other.storage import delete_all_conversation_recordings
from utils.twilio_service import delete_user_caller_ids

logger = logging.getLogger(__name__)


def purge_derived_user_data(uid: str):
    """Best-effort purge of a user's derived data outside Firestore."""
    try:
        conversation_ids = get_conversation_ids(uid)
        if conversation_ids:
            delete_conversation_vectors_batch(uid, conversation_ids)
    except Exception as e:
        logger.error(f'delete_account purge conversation vectors failed for {uid}: {sanitize(str(e))}')

    try:
        conversation_ids = get_conversation_ids(uid)
        if conversation_ids:
            delete_transcript_chunk_vectors_batch(uid, conversation_ids)
    except Exception as e:
        logger.error(f'delete_account purge transcript chunk vectors failed for {uid}: {sanitize(str(e))}')

    try:
        memory_ids = get_memory_ids(uid)
        if memory_ids:
            delete_memory_vectors_batch(uid, memory_ids)
    except Exception as e:
        logger.error(f'delete_account purge memory vectors failed for {uid}: {sanitize(str(e))}')

    try:
        action_item_ids = get_action_item_ids(uid)
        if action_item_ids:
            delete_action_item_vectors_batch(uid, action_item_ids)
    except Exception as e:
        logger.error(f'delete_account purge action item vectors failed for {uid}: {sanitize(str(e))}')

    try:
        screen_activity_ids = get_screen_activity_ids(uid)
        if screen_activity_ids:
            delete_screen_activity_vectors(uid, screen_activity_ids)
    except Exception as e:
        logger.error(f'delete_account purge screen activity vectors failed for {uid}: {sanitize(str(e))}')

    try:
        delete_all_conversation_recordings(uid)
    except Exception as e:
        logger.error(f'delete_account purge recordings failed for {uid}: {sanitize(str(e))}')


def background_wipe_user_data(uid: str):
    try:
        # Twilio caller IDs first, while the phone_numbers subcollection still carries twilio_sid metadata.
        delete_user_caller_ids(uid)
        purge_derived_user_data(uid)
        users_db.delete_user_data(uid)
        logger.info(f'delete_account background wipe complete for {uid}')
    except Exception as e:
        logger.error(f'delete_account background wipe failed for {uid}: {sanitize(str(e))}')


def start_account_deletion(uid: str, reason: str | None = None, reason_details: str | None = None) -> dict[str, str]:
    if reason or reason_details:
        try:
            users_db.set_user_deletion_feedback(uid, reason, reason_details)
        except Exception as e:
            logger.info(f'delete_account feedback store failed: {sanitize(str(e))}')

    try:
        sub = users_db.get_user_subscription(uid)
        if sub and sub.stripe_subscription_id:
            canceled = stripe_utils.cancel_subscription(sub.stripe_subscription_id)
            if not canceled:
                logger.error(f'delete_account stripe cancel returned None for {uid}')
    except Exception as e:
        logger.error(f'delete_account subscription lookup failed for {uid}: {sanitize(str(e))}')

    try:
        auth.delete_account(uid)
    except Exception as e:
        err = str(e).upper()
        if 'USER_NOT_FOUND' in err or 'NO USER RECORD' in err:
            logger.info(f'delete_account firebase user already gone for {uid}')
        else:
            raise

    threading.Thread(target=background_wipe_user_data, args=(uid,), daemon=True).start()

    return {'status': 'ok', 'message': 'Account deletion started'}
