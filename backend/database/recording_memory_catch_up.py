"""Durable claims and revision fences for recording memory catch-up."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.transcript_publication import pre_chat_memory_catch_up_enabled
from database import recording_transcript_publication as publication
from database._client import run_transactional
from database.legal_holds import assert_no_destructive_operation_transaction

LEASE_SECONDS = 20
MAX_RECORDINGS_PER_CHAT = 4


class RecordingMemoryChanged(RuntimeError):
    pass


def _conversations(client, uid):
    return client.collection('users').document(uid).collection('conversations')


def pending_recordings(client, uid, *, destination=None):
    field, value = (
        (f'{publication.FIELD}.conversation_id', destination)
        if destination is not None
        else (publication.MEMORY_PENDING, True)
    )
    query = _conversations(client, uid).where(filter=FieldFilter(field, '==', value))
    return [doc.id for doc in query.select([]).limit(MAX_RECORDINGS_PER_CHAT).stream()]


def _eligible(row):
    from database.conversations import is_visible_conversation

    return bool(
        row
        and row.get('status') != 'in_progress'
        and is_visible_conversation(row, presentation=True, include_recordings=True)
    )


def _transcript_version(row):
    return (
        row['id'],
        row['sync_content_revision'],
        row['transcript_segments'],
        row.get('transcript_segments_compressed'),
    )


@dataclass(frozen=True)
class RecordingMemoryClaim:
    client: object
    uid: str
    recording_id: str
    token: str
    row: dict

    def prepare_commit(self, transaction):
        """Enroll the publication in the memory transaction's read set."""
        if not pre_chat_memory_catch_up_enabled():
            raise RecordingMemoryChanged('recording catch-up disabled')
        current = publication.read_snapshot(self.client, self.uid, self.recording_id, transaction=transaction)
        if not _eligible(current) or _transcript_version(current) != _transcript_version(self.row):
            raise RecordingMemoryChanged('recording publication changed during catch-up')
        lease = current.get(publication.MEMORY_LEASE) or {}
        expires = lease.get('expires_at')
        if (
            lease.get('token') != self.token
            or not isinstance(expires, datetime)
            or expires <= datetime.now(timezone.utc)
        ):
            raise RecordingMemoryChanged('recording memory claim expired or moved')
        rows = _conversations(self.client, self.uid)
        source = rows.document(self.recording_id)
        target = rows.document(self.row['id'])

        def finish():
            changes = {
                publication.MEMORY_REVISION: self.row['sync_content_revision'],
                publication.MEMORY_LEASE: firestore.DELETE_FIELD,
            }
            if source == target:
                changes[publication.MEMORY_PENDING] = False
            else:
                transaction.update(source, {publication.MEMORY_PENDING: False})
            transaction.update(target, changes)

        return finish

    def complete_empty(self):
        @firestore.transactional
        def complete(transaction):
            assert_no_destructive_operation_transaction(transaction, self.client, uid=self.uid)
            self.prepare_commit(transaction)()

        run_transactional(self.client, complete)

    def release(self):
        target = _conversations(self.client, self.uid).document(self.row['id'])

        @firestore.transactional
        def release(transaction):
            data = target.get(transaction=transaction, field_paths=[publication.MEMORY_LEASE]).to_dict() or {}
            if (data.get(publication.MEMORY_LEASE) or {}).get('token') == self.token:
                transaction.update(target, {publication.MEMORY_LEASE: firestore.DELETE_FIELD})

        run_transactional(self.client, release)


def claim_recording(client, uid, recording_id):
    rows = _conversations(client, uid)
    source = rows.document(recording_id)
    token = uuid4().hex

    @firestore.transactional
    def claim(transaction):
        row = publication.read_snapshot(client, uid, recording_id, transaction=transaction)
        if not row:
            return None, False, None
        cid = row['id']
        pending = source.get(transaction=transaction, field_paths=[publication.MEMORY_PENDING]).to_dict() or {}
        if not pending.get(publication.MEMORY_PENDING):
            return cid, False, None
        if not _eligible(row):
            return cid, False, None
        assert_no_destructive_operation_transaction(transaction, client, uid=uid)
        revision = row['sync_content_revision']
        if row.get(publication.MEMORY_REVISION) == revision:
            transaction.update(source, {publication.MEMORY_PENDING: False})
            return cid, False, None
        now = datetime.now(timezone.utc)
        lease = row.get(publication.MEMORY_LEASE) or {}
        if lease.get('revision') == revision and lease.get('expires_at', now) > now:
            return cid, True, None
        transaction.update(
            rows.document(cid),
            {
                publication.MEMORY_LEASE: {
                    'token': token,
                    'revision': revision,
                    'expires_at': now + timedelta(seconds=LEASE_SECONDS),
                }
            },
        )
        return cid, False, RecordingMemoryClaim(client, uid, recording_id, token, row)

    return run_transactional(client, claim)
