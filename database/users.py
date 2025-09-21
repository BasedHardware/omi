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


def set_chat_message_rating_score(uid: str, message_id: str, value: int):
    doc_id = document_id_from_seed('chat_message' + message_id)
    db.collection('analytics').document(doc_id).set(
        {
            'id': doc_id,
            'message_id': message_id,
            'uid': uid,
            'value': value,
            'created_at': datetime.now(timezone.utc),
            'type': 'chat_message',
        }
    )


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
