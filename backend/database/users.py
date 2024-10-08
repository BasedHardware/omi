from google.cloud.firestore_v1 import FieldFilter

from ._client import db


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
