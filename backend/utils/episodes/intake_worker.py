"""Pass a versioned episode intake acknowledgement to workerd."""

import os
from urllib.parse import urlsplit


def notify_workerd(uid: str, conversation_id: str, revision: object) -> None:
    origin = os.getenv('SYNC_EPISODE_INTAKE_ORIGIN', '').rstrip('/')
    audience = os.getenv('WORKER_EPISODE_INTAKE_AUDIENCE', '')
    if not origin or not audience or type(revision) is not int or revision <= 0:
        return

    url = urlsplit(origin)
    if url.scheme != 'https' or not url.hostname:
        return
    if url.username or url.password or url.path or url.query or url.fragment:
        return

    import httpx

    from database._client import get_firestore_client
    from utils.sync.worker_client import identity_token

    ref = get_firestore_client().collection('users').document(uid).collection('conversations').document(conversation_id)
    snapshot = ref.get(field_paths=['sync_content_revision'], timeout=2, retry=None)
    row = snapshot.to_dict() or {}
    if row.get('sync_content_revision') != revision or snapshot.update_time is None:
        return
    response = httpx.post(
        f'{origin}/internal/finalization/episode-intake',
        json={'owner': uid, 'conversation': conversation_id, 'written': snapshot.update_time.isoformat()},
        headers={'Authorization': f'Bearer {identity_token(audience)}'},
        follow_redirects=False,
        timeout=5.0,
    )
    if response.status_code not in {200, 204, 409}:
        response.raise_for_status()
