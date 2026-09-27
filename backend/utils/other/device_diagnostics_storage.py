"""Private, bounded support bundles in the already bound private cloud bucket."""

from __future__ import annotations

import json
import secrets
from typing import Any

from utils.other import storage


def save_bundle(uid: str, bundle: bytes) -> str:
    ticket = secrets.token_hex(6).upper()
    bucket = storage._get_storage_client().bucket(storage.private_cloud_sync_bucket)
    path = f'diagnostics/{uid}/{ticket}.json'
    # The ticket lookup is private too. Neither object is served as a public URL.
    with storage.owner_storage_write_gate(uid, bucket):
        bucket.blob(path).upload_from_string(bundle, content_type='application/json')
        bucket.blob(f'diagnostics/tickets/{ticket}.json').upload_from_string(
            json.dumps({'uid': uid, 'path': path}), content_type='application/json'
        )
    return ticket


def read_bundle(ticket: str) -> dict[str, Any] | None:
    bucket = storage._get_storage_client().bucket(storage.private_cloud_sync_bucket)
    lookup = bucket.blob(f'diagnostics/tickets/{ticket}.json')
    if not lookup.exists():
        return None
    reference = json.loads(lookup.download_as_bytes())
    uid = reference['uid']
    path = reference['path']
    if not path.startswith(f'diagnostics/{uid}/') or not path.endswith(f'/{ticket}.json'):
        return None
    blob = bucket.blob(path)
    if not blob.exists():
        return None
    return json.loads(blob.download_as_bytes())
