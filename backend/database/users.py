from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter, transactional

from ._client import db, document_id_from_seed
from models.users import Subscription, PlanLimits, PlanType, SubscriptionStatus
from utils.subscription import get_default_basic_subscription


def is_exists_user(uid: str):
    user_ref = db.collection('users').document(uid)
    if not user_ref.get().exists:
        return False
    return True


def get_user_profile(uid: str) -> dict:
    """Gets the full user profile document."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if user_doc.exists:
        return user_doc.to_dict()
    return {}


def get_user_store_recording_permission(uid: str):
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('store_recording_permission', False)


def set_user_store_recording_permission(uid: str, value: bool):
    user_ref = db.collection('users').document(uid)
    user_ref.update({'store_recording_permission': value})


def get_user_private_cloud_sync_enabled(uid: str) -> bool:
    """Check if user has private cloud sync enabled."""
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('private_cloud_sync_enabled', True)


def set_user_private_cloud_sync_enabled(uid: str, value: bool):
    """Enable or disable private cloud sync for a user."""
    user_ref = db.collection('users').document(uid)
    user_ref.update({'private_cloud_sync_enabled': value})


def create_person(uid: str, data: dict):
    people_ref = db.collection('users').document(uid).collection('people')
    people_ref.document(data['id']).set(data)
    return data


def get_person(uid: str, person_id: str):
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_data = person_ref.get().to_dict()
    return person_data


def get_people(uid: str):
    people_ref = db.collection('users').document(uid).collection('people')
    people = people_ref.stream()
    return [person.to_dict() for person in people]


def get_person_by_name(uid: str, name: str):
    people_ref = db.collection('users').document(uid).collection('people')
    query = people_ref.where(filter=FieldFilter('name', '==', name)).limit(1)
    docs = list(query.stream())
    if docs:
        return docs[0].to_dict()
    return None


def get_people_by_ids(uid: str, person_ids: list[str]):
    if not person_ids:
        return []
    people_ref = db.collection('users').document(uid).collection('people')
    # Firestore 'in' query supports up to 30 items.
    all_people = []
    for i in range(0, len(person_ids), 30):
        chunk_ids = person_ids[i : i + 30]
        people_query = people_ref.where("id", 'in', chunk_ids)
        people = people_query.stream()
        all_people.extend([person.to_dict() for person in people])
    return all_people


def update_person(uid: str, person_id: str, name: str):
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_ref.update({'name': name})


def delete_person(uid: str, person_id: str):
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_ref.delete()


def add_person_speech_sample(uid: str, person_id: str, sample_path: str, max_samples: int = 5) -> bool:
    """
    Append speech sample path to person's speech_samples list.
    Limits to max_samples to prevent unlimited growth.

    Args:
        uid: User ID
        person_id: Person ID
        sample_path: GCS path to the speech sample
        max_samples: Maximum number of samples to keep (default 5)

    Returns:
        True if sample was added, False if limit reached
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return False

    person_data = person_doc.to_dict()
    current_samples = person_data.get('speech_samples', [])

    # Check if we've hit the limit
    if len(current_samples) >= max_samples:
        return False

    person_ref.update(
        {
            'speech_samples': firestore.ArrayUnion([sample_path]),
            'updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def get_person_speech_samples_count(uid: str, person_id: str) -> int:
    """Get the count of speech samples for a person."""
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return 0

    person_data = person_doc.to_dict()
    return len(person_data.get('speech_samples', []))


def remove_person_speech_sample(uid: str, person_id: str, sample_path: str) -> bool:
    """
    Remove a speech sample path from person's speech_samples list.

    Args:
        uid: User ID
        person_id: Person ID
        sample_path: GCS path to remove

    Returns:
        True if removed, False if person not found
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return False

    person_ref.update({
        'speech_samples': firestore.ArrayRemove([sample_path]),
        'updated_at': datetime.now(timezone.utc),
    })
    return True


def set_person_speaker_embedding(uid: str, person_id: str, embedding: list) -> bool:
    """
    Store speaker embedding for a person.

    Args:
        uid: User ID
        person_id: Person ID
        embedding: List of floats representing the speaker embedding

    Returns:
        True if stored successfully, False if person not found
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return False

    person_ref.update(
        {
            'speaker_embedding': embedding,
            'updated_at': datetime.now(timezone.utc),
        }
    )
    return True


def get_person_speaker_embedding(uid: str, person_id: str) -> Optional[list]:
    """
    Get speaker embedding for a person.

    Args:
        uid: User ID
        person_id: Person ID

    Returns:
        List of floats representing the embedding, or None if not found
    """
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_doc = person_ref.get()

    if not person_doc.exists:
        return None

    person_data = person_doc.to_dict()
    return person_data.get('speaker_embedding')


def delete_user_data(uid: str):
    user_ref = db.collection('users').document(uid)
    if not user_ref.get().exists:
        return {'status': 'error', 'message': 'User not found'}

    subcollections_to_delete = ['conversations', 'messages', 'chat_sessions', 'people', 'memories', 'files']
    batch_size = 450

    for cname in subcollections_to_delete:
        print(f"Deleting subcollection: {cname} for user {uid}")
        collection_ref = user_ref.collection(cname)

        while True:
            docs_query = collection_ref.limit(batch_size)
            docs = list(docs_query.stream())

            if not docs:
                # docs might not exists, try using {parent path / id}
                print(f"No more documents to delete in {collection_ref.parent.path}/{collection_ref.id}")
                break

            batch = db.batch()
            for doc in docs:
                print(f"Deleting document: {doc.reference.path}")
                batch.delete(doc.reference)
            batch.commit()

            if len(docs) < batch_size:
                print(f"Processed all documents in {collection_ref.path}")
                break

    # delete the user document itself
    print(f"Deleting user document: {uid}")
    user_ref.delete()
    return {'status': 'ok', 'message': 'Account deleted successfully'}


# **************************************
# ************* Analytics **************
# **************************************


def set_conversation_summary_rating_score(uid: str, conversation_id: str, value: int):
    doc_id = document_id_from_seed('memory_summary' + conversation_id)
    db.collection('analytics').document(doc_id).set(
        {
            'id': doc_id,
            'memory_id': conversation_id,
            'uid': uid,
            'value': value,
            'created_at': datetime.now(timezone.utc),
            'type': 'memory_summary',
        }
    )


def get_conversation_summary_rating_score(conversation_id: str):
    doc_id = document_id_from_seed('memory_summary' + conversation_id)
    doc_ref = db.collection('analytics').document(doc_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return None


def get_all_ratings(rating_type: str = 'memory_summary'):
    ratings = db.collection('analytics').where('type', '==', rating_type).stream()
    return [rating.to_dict() for rating in ratings]


def set_chat_message_rating_score(uid: str, message_id: str, value: int, reason: str = None):
    """
    Store chat message rating/feedback.
    
    Args:
        uid: User ID
        message_id: Message ID being rated
        value: Rating value (1 = thumbs up, -1 = thumbs down, 0 = neutral/removed)
        reason: Optional reason for thumbs down (e.g. 'too_verbose', 'incorrect_or_hallucination', 
                'not_helpful_or_irrelevant', 'didnt_follow_instructions', 'other')
    """
    doc_id = document_id_from_seed('chat_message' + message_id)
    data = {
        'id': doc_id,
        'message_id': message_id,
        'uid': uid,
        'value': value,
        'created_at': datetime.now(timezone.utc),
        'type': 'chat_message',
    }
    if reason:
        data['reason'] = reason
    db.collection('analytics').document(doc_id).set(data)


# **************************************
# ************** Payments **************
# **************************************


def get_stripe_connect_account_id(uid: str):
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('stripe_account_id', None)


def set_stripe_connect_account_id(uid: str, account_id: str):
    user_ref = db.collection('users').document(uid)
    user_ref.update({'stripe_account_id': account_id})


def set_paypal_payment_details(uid: str, data: dict):
    user_ref = db.collection('users').document(uid)
    user_ref.update({'paypal_details': data})


def get_paypal_payment_details(uid: str):
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('paypal_details', None)


def set_default_payment_method(uid: str, payment_method_id: str):
    user_ref = db.collection('users').document(uid)
    user_ref.update({'default_payment_method': payment_method_id})


def get_default_payment_method(uid: str):
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('default_payment_method', None)


def get_stripe_customer_id(uid: str) -> Optional[str]:
    """Get the Stripe customer ID for a user."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        return user_data.get('stripe_customer_id')
    return None


def set_stripe_customer_id(uid: str, customer_id: str):
    user_ref = db.collection('users').document(uid)
    user_ref.update({'stripe_customer_id': customer_id})


def get_user_by_stripe_customer_id(customer_id: str):
    users_ref = db.collection('users')
    query = users_ref.where(filter=FieldFilter('stripe_customer_id', '==', customer_id)).limit(1)
    docs = list(query.stream())
    if docs:
        user_dict = docs[0].to_dict()
        user_dict['uid'] = docs[0].id
        return user_dict
    return None


def update_user_subscription(uid: str, subscription_data: dict):
    """Updates the user's subscription information, removing dynamic fields before storing."""
    subscription_data_to_store = subscription_data.copy()
    subscription_data_to_store.pop('features', None)
    subscription_data_to_store.pop('limits', None)

    user_ref = db.collection('users').document(uid)
    user_ref.update({'subscription': subscription_data_to_store})


# **************************************
# ********* Data Protection ************
# **************************************


def get_data_protection_level(uid: str) -> str:
    """
    Get the user's data protection level.

    Args:
        uid: User ID

    Returns:
        'enhanced' or 'e2ee'. Defaults to 'enhanced'.
    """
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        return user_data.get('data_protection_level', 'enhanced')

    return 'enhanced'


def set_data_protection_level(uid: str, level: str) -> None:
    """
    Set the user's data protection level.

    Args:
        uid: User ID
        level: 'enhanced', or 'e2ee'
    """
    if level not in ['enhanced', 'e2ee']:
        raise ValueError("Invalid data protection level. Only 'enhanced' or 'e2ee' are supported.")
    user_ref = db.collection('users').document(uid)
    user_ref.set({'data_protection_level': level}, merge=True)


def set_migration_status(uid: str, target_level: str):
    """Sets the migration status on the user's profile."""
    user_ref = db.collection('users').document(uid)
    migration_status = {'target_level': target_level, 'status': 'in_progress', 'started_at': datetime.now(timezone.utc)}
    user_ref.set({'migration_status': migration_status}, merge=True)


def finalize_migration(uid: str, target_level: str):
    """Atomically sets the new protection level and removes the migration status field."""
    user_ref = db.collection('users').document(uid)
    user_ref.update({'data_protection_level': target_level, 'migration_status': firestore.DELETE_FIELD})


# **************************************
# ************* Language ***************
# **************************************


def get_user_language_preference(uid: str) -> str:
    """
    Get the user's preferred language.

    Args:
        uid: User ID

    Returns:
        Language code (e.g., 'en', 'vi') or empty string if not set
    """
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        return user_data.get('language', '')

    return ''  # Return empty string if not set


def set_user_language_preference(uid: str, language: str) -> None:
    """
    Set the user's preferred language.

    Args:
        uid: User ID
        language: Language code (e.g., 'en', 'vi')
    """
    user_ref = db.collection('users').document(uid)
    user_ref.set({'language': language}, merge=True)


def get_user_subscription(uid: str) -> Subscription:
    """Gets the user's subscription, creating a default free one if it doesn't exist."""
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get(['subscription'])
    if user_doc.exists:
        user_data = user_doc.to_dict()
        if 'subscription' in user_data:
            sub_data = user_data['subscription']
            # Handle migration for old 'free' plan identifier
            if sub_data.get('plan') == 'free':
                sub_data['plan'] = PlanType.basic.value
                update_user_subscription(uid, sub_data)
            return Subscription(**sub_data)

    # If subscription doesn't exist for the user, create and return a default free plan.
    default_subscription = get_default_basic_subscription()
    # Strip dynamic fields before storing
    sub_to_store = default_subscription.dict()
    sub_to_store.pop('features', None)
    sub_to_store.pop('limits', None)
    user_ref.set({'subscription': sub_to_store}, merge=True)
    return default_subscription


def get_user_training_data_opt_in(uid: str) -> Optional[dict]:
    """Get user's training data opt-in status."""
    user_ref = db.collection('users').document(uid)
    user_data = user_ref.get().to_dict()
    return user_data.get('training_data_opt_in', None)


def set_user_training_data_opt_in(uid: str, status: str):
    """Set user's training data opt-in status. Status can be: pending_review, approved, rejected"""
    user_ref = db.collection('users').document(uid)
    user_ref.update(
        {
            'training_data_opt_in': {
                'status': status,
                'requested_at': datetime.now(timezone.utc),
            }
        }
    )


def get_user_valid_subscription(uid: str) -> Optional[Subscription]:
    """
    Gets the user's subscription if it is currently valid for use.

    A subscription is considered valid if:
    - It's a basic (free) plan with 'active' status.
    - It's a paid plan with a 'current_period_end' that has not passed yet.
      This allows users to use the service until the end of the billing period
      they paid for, even after cancelling.

    Returns the Subscription object if valid, otherwise None.
    """
    subscription = get_user_subscription(uid)

    # Basic (free) plans are only valid if their status is active.
    if subscription.plan == PlanType.basic:
        return subscription if subscription.status == SubscriptionStatus.active else None

    # For paid plans (e.g., unlimited), validity is determined by the period end.
    if subscription.current_period_end:
        period_end_dt = datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
        if period_end_dt >= datetime.now(timezone.utc):
            return subscription

    # Fallback to default basic subscription
    return get_default_basic_subscription()


# **************************************
# ******** Task Integrations ***********
# **************************************


def get_task_integrations(uid: str) -> dict:
    """
    Get all task integration connections for a user.

    Args:
        uid: User ID

    Returns:
        Dictionary with app_key as keys and connection details as values
    """
    user_ref = db.collection('users').document(uid)
    integrations_ref = user_ref.collection('task_integrations')

    integrations = {}
    for doc in integrations_ref.stream():
        integrations[doc.id] = doc.to_dict()

    return integrations


def get_task_integration(uid: str, app_key: str) -> Optional[dict]:
    """
    Get a specific task integration connection.

    Args:
        uid: User ID
        app_key: Task integration app key (e.g., 'asana', 'todoist')

    Returns:
        Connection details or None if not found
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('task_integrations').document(app_key)
    doc = integration_ref.get()

    if doc.exists:
        return doc.to_dict()
    return None


def set_task_integration(uid: str, app_key: str, data: dict) -> None:
    """
    Save or update a task integration connection.

    Args:
        uid: User ID
        app_key: Task integration app key (e.g., 'asana', 'todoist')
        data: Connection details to save
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('task_integrations').document(app_key)

    # Add timestamp
    data['updated_at'] = datetime.now(timezone.utc)
    if not integration_ref.get().exists:
        data['created_at'] = datetime.now(timezone.utc)

    integration_ref.set(data, merge=True)


def delete_task_integration(uid: str, app_key: str) -> bool:
    """
    Delete a task integration connection.
    Also clears default_task_integration if it matches the deleted app.

    Args:
        uid: User ID
        app_key: Task integration app key

    Returns:
        True if deleted, False if not found
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('task_integrations').document(app_key)

    if not integration_ref.get().exists:
        return False

    # Check if this is the default integration
    user_doc = user_ref.get()
    is_default = False
    if user_doc.exists:
        user_data = user_doc.to_dict()
        is_default = user_data.get('default_task_integration') == app_key

    # Delete integration
    integration_ref.delete()

    # Clear default if needed
    if is_default:
        user_ref.update({'default_task_integration': firestore.DELETE_FIELD})

    return True


def get_default_task_integration(uid: str) -> Optional[str]:
    """
    Get the user's default task integration app.

    Args:
        uid: User ID

    Returns:
        App key of default integration or None
    """
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        return user_data.get('default_task_integration')

    return None


def set_default_task_integration(uid: str, app_key: str) -> None:
    """
    Set the user's default task integration app.

    Args:
        uid: User ID
        app_key: Task integration app key to set as default
    """
    user_ref = db.collection('users').document(uid)
    user_ref.set({'default_task_integration': app_key}, merge=True)


# **************************************
# ******** Integrations ********
# **************************************


def get_integration(uid: str, app_key: str) -> Optional[dict]:
    """
    Get a specific integration connection.

    Args:
        uid: User ID
        app_key: Integration app key (e.g., 'google_calendar', 'whoop')

    Returns:
        Connection details or None if not found
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('integrations').document(app_key)
    doc = integration_ref.get()

    if doc.exists:
        return doc.to_dict()
    return None


def set_integration(uid: str, app_key: str, data: dict) -> None:
    """
    Save or update an integration connection.

    Args:
        uid: User ID
        app_key: Integration app key (e.g., 'google_calendar', 'whoop')
        data: Connection details to save
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('integrations').document(app_key)

    # Add timestamp
    data['updated_at'] = datetime.now(timezone.utc)
    if not integration_ref.get().exists:
        data['created_at'] = datetime.now(timezone.utc)

    integration_ref.set(data, merge=True)


def delete_integration(uid: str, app_key: str) -> bool:
    """
    Delete an integration connection.

    Args:
        uid: User ID
        app_key: Integration app key

    Returns:
        True if deleted, False if not found
    """
    user_ref = db.collection('users').document(uid)
    integration_ref = user_ref.collection('integrations').document(app_key)

    if not integration_ref.get().exists:
        return False

    integration_ref.delete()
    return True


# Legacy function names for backward compatibility
def get_calendar_integration(uid: str, app_key: str) -> Optional[dict]:
    """Legacy function name - use get_integration instead."""
    return get_integration(uid, app_key)


def set_calendar_integration(uid: str, app_key: str, data: dict) -> None:
    """Legacy function name - use set_integration instead."""
    return set_integration(uid, app_key, data)


def delete_calendar_integration(uid: str, app_key: str) -> bool:
    """Legacy function name - use delete_integration instead."""
    return delete_integration(uid, app_key)


# **************************************
# ***** Transcription Preferences ******
# **************************************


def get_user_transcription_preferences(uid: str) -> dict:
    """
    Get the user's transcription preferences.

    Returns:
        dict with 'single_language_mode' (bool) and 'vocabulary' (List[str])
    """
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        prefs = user_data.get('transcription_preferences', {})
        return {
            'single_language_mode': prefs.get('single_language_mode', False),
            'vocabulary': prefs.get('vocabulary', []),
        }

    return {'single_language_mode': False, 'vocabulary': []}


def set_user_transcription_preferences(uid: str, single_language_mode: bool = None, vocabulary: list = None) -> None:
    """
    Set the user's transcription preferences.

    Args:
        uid: User ID
        single_language_mode: If True, use exact language instead of multi-language detection
        vocabulary: List of custom keywords/terms for better transcription accuracy
    """
    user_ref = db.collection('users').document(uid)
    update_data = {}

    if single_language_mode is not None:
        update_data['transcription_preferences.single_language_mode'] = single_language_mode

    if vocabulary is not None:
        # Limit vocabulary to 100 terms max
        update_data['transcription_preferences.vocabulary'] = vocabulary[:100]

    if update_data:
        user_ref.update(update_data)
