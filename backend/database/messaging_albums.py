"""Album admission and generation CAS, under the existing encrypted inbox transaction."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from database.firestore_transaction_retry import run_with_transaction_contention_retry
from utils import encryption
from utils.messaging.albums import merge_album, album_ready_at
from utils.messaging.identity import key


@dataclass
class AlbumBatch:
    root: Any
    tail: Any
    row: dict | None
    sequence: int
    total: int


def read_album(tx, identity, message):
    if not message.media_group_id:
        return None
    root = identity.collection('inbox').document(key(message.external_chat_id, 'album:' + message.media_group_id))
    root_row = root.get(transaction=tx).to_dict() or {}
    sequence = root_row.get('album_tail', 0)
    tail = (
        root
        if sequence == 0
        else identity.collection('inbox').document(
            key(message.external_chat_id, f'album:{message.media_group_id}:{sequence}')
        )
    )
    row = root_row if sequence == 0 else tail.get(transaction=tx).to_dict()
    mergeable = not row or (
        (row.get('status') == 'pending' or (row.get('status') == 'running' and row.get('album_appendable')))
        and not row.get('generation_started_at')
        and not row.get('fifo_settled_at')
    )
    if not mergeable:
        sequence += 1
        tail = identity.collection('inbox').document(
            key(message.external_chat_id, f'album:{message.media_group_id}:{sequence}')
        )
        row = None
    total = root_row.get('album_part_count', 0) + len(message.attachments)
    if total > 10:
        raise ValueError('Album contains too many attachments')
    return AlbumBatch(root, tail, row or None, sequence, total)


def append_album(tx, batch: AlbumBatch, part, payload, identity_id, now, channel, provider):
    # Called only after every admission read. Each provider part keeps a tombstone.
    prior = json.loads(encryption.decrypt(batch.row['payload'], identity_id)) if batch.row else None
    combined = merge_album(prior, payload)
    tx.create(part, {'status': 'done', 'created_at': now, 'done_at': now, 'channel': channel, 'provider': provider})
    tx.set(
        batch.tail,
        {
            'payload': encryption.encrypt(json.dumps(combined), identity_id),
            'status': batch.row['status'] if batch.row else 'pending',
            'created_at': batch.row['created_at'] if batch.row else now,
            'album_ready_at': album_ready_at(batch.row, now),
            'channel': channel,
            'provider': provider,
        },
        merge=True,
    )
    tx.set(batch.root, {'album_tail': batch.sequence, 'album_part_count': batch.total}, merge=True)
    return batch.tail.path


def seal_album(db, path, attachment_count, *, stale_seconds):
    """Seal only the exact prepared snapshot. Admission contends on this same row."""
    ref = db.document(path)

    @firestore.transactional
    def apply(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        now = datetime.now(timezone.utc)
        if (
            row.get('status') != 'running'
            or row.get('fifo_settled_at')
            or (now - (row.get('started_at') or row['created_at'])).total_seconds() >= stale_seconds
        ):
            raise PermissionError('Inbox turn expired')
        payload = json.loads(encryption.decrypt(row['payload'], ref.parent.parent.id))
        if len(payload['attachments']) != attachment_count:
            return payload
        tx.update(ref, {'generation_started_at': now})
        return None

    return run_with_transaction_contention_retry(db.transaction, apply, operation_name='messaging_album_seal')
