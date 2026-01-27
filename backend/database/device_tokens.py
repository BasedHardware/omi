import secrets
from datetime import datetime, timedelta
from typing import Optional
from google.cloud import firestore

db = firestore.Client()

TOKEN_EXPIRY_DAYS = 30


def create_device_sync_token(uid: str, device_id: str) -> str:
    token = secrets.token_urlsafe(32)
    doc_ref = db.collection("device_sync_tokens").document(token)
    doc_ref.set({
        "uid": uid,
        "device_id": device_id,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=TOKEN_EXPIRY_DAYS),
    })
    return token


def validate_device_sync_token(token: str, device_id: str) -> Optional[dict]:
    doc = db.collection("device_sync_tokens").document(token).get()
    if not doc.exists:
        return None
    
    data = doc.to_dict()
    if data.get("device_id") != device_id:
        return None
    
    expires_at = data.get("expires_at")
    if expires_at and expires_at.replace(tzinfo=None) < datetime.utcnow():
        return None
    
    return data


def revoke_device_sync_token(uid: str, device_id: str) -> int:
    query = db.collection("device_sync_tokens").where("uid", "==", uid).where("device_id", "==", device_id)
    docs = query.stream()
    count = 0
    for doc in docs:
        doc.reference.delete()
        count += 1
    return count


def revoke_all_user_device_tokens(uid: str) -> int:
    query = db.collection("device_sync_tokens").where("uid", "==", uid)
    docs = query.stream()
    count = 0
    for doc in docs:
        doc.reference.delete()
        count += 1
    return count


def get_user_device_tokens(uid: str) -> list[dict]:
    query = db.collection("device_sync_tokens").where("uid", "==", uid)
    docs = query.stream()
    tokens = []
    for doc in docs:
        data = doc.to_dict()
        data["token_id"] = doc.id[:8] + "..."
        tokens.append(data)
    return tokens
