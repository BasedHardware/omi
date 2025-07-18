from datetime import datetime, timezone

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter, transactional

from ._client import db, document_id_from_seed


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
                print(f"No more documents to delete in {collection_ref.path}")
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
