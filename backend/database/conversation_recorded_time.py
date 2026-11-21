"""Recording read projection and the attach-before-create membership handshake."""

from datetime import datetime, timezone

from google.cloud import firestore

from config.recording_speakers import with_creation_scope_index
from database._client import run_transactional
from utils.conversations.recorded_time import SPAN_FIELDS, span_fields, write_span


def hydrate(data):
    """Derive legacy fields in memory; reads never write a backfill."""
    return {**data, **span_fields(data)}


def adopt_membership(transaction, user_ref, payload):
    member = user_ref.collection('episode_links').document(payload['id']).get(transaction=transaction).to_dict() or {}
    if member.get('episode_id'):
        payload['episode_id'] = member['episode_id']


def create_if_absent(uid, payload, *, firestore_client, stage_identity=None):
    from database import processing_backlog

    root = firestore_client.collection('users').document(uid)
    ref = root.collection('conversations').document(payload['id'])

    @firestore.transactional
    def create(transaction):
        if ref.get(transaction=transaction).exists:
            return False, False
        data = with_creation_scope_index(payload)
        # Adopt first: it only reads, and the identity staging below writes, so
        # keeping every read ahead of the first write keeps the transaction
        # order-valid.
        adopt_membership(transaction, root, data)
        if stage_identity is not None:
            # Screen/calendar evidence may name people before the conversation
            # row exists; stage those provisional identifiers in the same
            # transaction so the people write and the conversation create
            # commit together or not at all.
            stage_identity(transaction, data)
        changed = False
        if data.get('processing_deferred'):
            changed = processing_backlog.stage_transition(
                transaction, uid, data['id'], {}, data, firestore_client=firestore_client
            )
        transaction.create(ref, data)
        return True, changed

    return run_transactional(firestore_client, create)


def stamp_for_write(data):
    # Membership has one transactional writer; processing snapshots cannot replay it.
    data.pop('episode_id', None)
    # Full creates/processing writes recompute from their complete recording.
    # Partial writes carry the span computed by their transaction snapshot.
    complete = data.get('created_at') is not None
    recording = data.get('started_at') is not None and isinstance(data.get('transcript_segments'), list)
    if complete or (recording and not all(field in data for field in SPAN_FIELDS)):
        data.update(write_span(data, arrival_at=datetime.now(timezone.utc)))
