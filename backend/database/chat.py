from google.cloud import firestore

from ._client import db


def add_message(uid: str, message_data: dict):
    user_ref = db.collection('users').document(uid)
    user_ref.collection('messages').add(message_data)
    return message_data


def get_messages(uid: str):
    user_ref = db.collection('users').document(uid)
    messages_ref = user_ref.collection('messages').order_by('created_at', direction=firestore.Query.DESCENDING)
    return [doc.to_dict() for doc in messages_ref.stream()]
