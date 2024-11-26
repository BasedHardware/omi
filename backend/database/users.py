from datetime import datetime, timezone

from google.cloud.firestore_v1 import FieldFilter

from ._client import db, document_id_from_seed


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
    people_ref = (
        db.collection('users').document(uid).collection('people')
        .where(filter=FieldFilter('deleted', '==', False))
    )
    people = people_ref.stream()
    return [person.to_dict() for person in people]


def update_person(uid: str, person_id: str, name: str):
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_ref.update({'name': name})


def delete_person(uid: str, person_id: str):
    person_ref = db.collection('users').document(uid).collection('people').document(person_id)
    person_ref.update({'deleted': True})


def delete_user_data(uid: str):
    # TODO: why dont we delete the whole document ref here?
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('memories')
    # delete all memories
    batch = db.batch()
    for doc in memories_ref.stream():
        batch.delete(doc.reference)
    batch.commit()
    # delete chat messages
    messages_ref = user_ref.collection('messages')
    batch = db.batch()
    for doc in messages_ref.stream():
        batch.delete(doc.reference)
    batch.commit()
    # delete facts
    batch = db.batch()
    facts_ref = user_ref.collection('facts')
    for doc in facts_ref.stream():
        batch.delete(doc.reference)
    batch.commit()
    # delete processing memories
    processing_memories_ref = user_ref.collection('processing_memories')
    batch = db.batch()
    for doc in processing_memories_ref.stream():
        batch.delete(doc.reference)
    batch.commit()
    # delete user
    user_ref.delete()
    return {'status': 'ok', 'message': 'Account deleted successfully'}


# **************************************
# ************* Analytics **************
# **************************************

def set_memory_summary_rating_score(uid: str, memory_id: str, value: int):
    doc_id = document_id_from_seed('memory_summary' + memory_id)
    db.collection('analytics').document(doc_id).set({
        'id': doc_id,
        'memory_id': memory_id,
        'uid': uid,
        'value': value,
        'created_at': datetime.now(timezone.utc),
        'type': 'memory_summary',
    })


def get_memory_summary_rating_score(memory_id: str):
    doc_id = document_id_from_seed('memory_summary' + memory_id)
    doc_ref = db.collection('analytics').document(doc_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return None


def get_all_ratings():
    ratings = db.collection('analytics').where('type', '==', 'memory_summary').stream()
    return [rating.to_dict() for rating in ratings]


def set_chat_message_rating_score(uid: str, message_id: str, value: int):
    doc_id = document_id_from_seed('chat_message' + message_id)
    db.collection('analytics').document(doc_id).set({
        'id': doc_id,
        'message_id': message_id,
        'uid': uid,
        'value': value,
        'created_at': datetime.now(timezone.utc),
        'type': 'chat_message',
    })
