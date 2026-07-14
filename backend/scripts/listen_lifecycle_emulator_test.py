#!/usr/bin/env python3
"""Firestore-emulator contention contract for the #9687 listen lifecycle."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PROJECT_ID = os.environ.setdefault('GOOGLE_CLOUD_PROJECT', os.environ.get('GCLOUD_PROJECT', 'demo-listen'))
os.environ.setdefault('GCLOUD_PROJECT', PROJECT_ID)
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_listen_lifecycle_emulator_test_secret_32_bytes')

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore

from database import conversations as conversations_db
from database import recording_sessions as recording_sessions_db
from models.conversation_photo import ConversationPhoto
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.live_content import retry_fenced_live_content_once


def _conversation_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection('users').document(uid).collection('conversations').document(conversation_id)


def _document_name(uid: str, conversation_id: str) -> str:
    return f'projects/{PROJECT_ID}/databases/(default)/documents/users/{uid}/conversations/{conversation_id}'


def _emulator_post(endpoint: str, payload: dict[str, Any]) -> Any:
    host = os.environ['FIRESTORE_EMULATOR_HOST']
    request = Request(
        f'http://{host}/v1/projects/{PROJECT_ID}/databases/(default)/documents{endpoint}',
        data=json.dumps(payload).encode(),
        headers={'authorization': 'Bearer owner', 'content-type': 'application/json'},
        method='POST',
    )
    with urlopen(request, timeout=10) as response:  # nosec B310 - local emulator URL from its test-only env.
        body = response.read().decode()
    return json.loads(body) if body else {}


def _hold_cleanup_parent_lock(uid: str, conversation_id: str) -> str:
    transaction_body = _emulator_post(':beginTransaction', {'options': {'readWrite': {}}})
    transaction = transaction_body.get('transaction') if isinstance(transaction_body, dict) else None
    if not isinstance(transaction, str) or not transaction:
        raise AssertionError(f'Firestore emulator did not return a transaction ID: {transaction_body}')
    read_body = _emulator_post(
        ':batchGet',
        {'documents': [_document_name(uid, conversation_id)], 'transaction': transaction},
    )
    rows = read_body if isinstance(read_body, list) else []
    if not any(isinstance(row, dict) and row.get('found') for row in rows):
        raise AssertionError(f'cleanup transaction did not read its conversation parent: {read_body}')
    return transaction


def _commit_cleanup_parent_delete(uid: str, conversation_id: str, transaction: str) -> None:
    _emulator_post(
        ':commit',
        {'writes': [{'delete': _document_name(uid, conversation_id)}], 'transaction': transaction},
    )


def _seed_empty_live_conversation(client: Any, uid: str, conversation_id: str) -> Any:
    """Write an empty in-progress conversation the way production writes it.

    Segments are stored compressed, so a raw empty list is a document state
    production never produces — seeding one hides encoding-aware guard bugs.
    """
    conversation_ref = _conversation_ref(client, uid, conversation_id)
    conversation_ref.set(
        conversations_db._prepare_conversation_for_write(
            {
                'id': conversation_id,
                'status': 'in_progress',
                'discarded': False,
                'transcript_segments': [],
                'has_content': False,
                'data_protection_level': 'standard',
            },
            uid,
            'standard',
        )
    )
    return conversation_ref


def _seed_live_generation(client: Any, uid: str, conversation_id: str, recording_session_id: str) -> Any:
    conversation_ref = _seed_empty_live_conversation(client, uid, conversation_id)
    recording_sessions_db.create_or_get_recording_session(
        uid,
        recording_session_id,
        conversation_id,
        firestore_client=client,
    )
    return conversation_ref


def _assert_cleanup_lock_fences_late_segment_write(client: Any, uid: str) -> None:
    """Exercise the server-mode ordering: cleanup lock → late writer → delete."""
    conversation_id = f'locked-cleanup-{uuid.uuid4().hex}'
    recording_session_id = f'session-{uuid.uuid4().hex}'
    _seed_live_generation(client, uid, conversation_id, recording_session_id)
    cleanup_transaction = _hold_cleanup_parent_lock(uid, conversation_id)
    write_result: dict[str, bool] = {}
    writer_done = threading.Event()

    def write_late_segment() -> None:
        write_result['persisted'] = conversations_db.update_conversation_segments(
            uid,
            conversation_id,
            [{'id': 'blocked-segment', 'text': 'blocked behind cleanup lock'}],
            firestore_client=client,
        )
        writer_done.set()

    writer = threading.Thread(target=write_late_segment, name='listen-lifecycle-emulator-writer')
    writer.start()
    if writer_done.wait(timeout=0.25):
        raise AssertionError('late content write did not block behind the cleanup parent lock')
    _commit_cleanup_parent_delete(uid, conversation_id, cleanup_transaction)
    writer.join(timeout=5)
    if writer.is_alive():
        raise AssertionError('late content write did not finish after cleanup released the parent lock')
    if write_result.get('persisted') is not False:
        raise AssertionError(f'late content write was not fenced after cleanup won: {write_result}')

    discarded = recording_sessions_db.record_lifecycle_event(
        uid,
        recording_session_id,
        conversation_id,
        'discarded',
        firestore_client=client,
    )
    if not discarded['accepted'] or discarded['lifecycle_phase'] != 'discarded':
        raise AssertionError('cleanup-first ordering did not terminalize the old recording generation')


def _assert_live_content_prevents_cleanup(
    client: Any,
    uid: str,
    conversation_id: str,
    recording_session_id: str,
    content_write: Callable[[], bool],
) -> Any:
    """A production content transaction commits its marker before cleanup reads."""
    if not content_write():
        raise AssertionError('content writer unexpectedly lost a live parent')

    deleted = recording_sessions_db.tombstone_and_delete_empty_conversation(
        uid,
        conversation_id,
        recording_session_id,
        firestore_client=client,
    )
    if deleted:
        raise AssertionError('cleanup ignored durable content committed by the late writer')

    conversation_ref = _conversation_ref(client, uid, conversation_id)
    snapshot = conversation_ref.get()
    if not snapshot.exists:
        raise AssertionError('cleanup deleted a conversation after its content transaction committed')
    conversation = snapshot.to_dict() or {}
    if conversation.get('has_content') is not True:
        raise AssertionError('content write did not persist the durable has_content marker')
    session = recording_sessions_db.get_recording_session(uid, recording_session_id, firestore_client=client)
    if session is None or session['lifecycle_phase'] != 'in_progress':
        raise AssertionError('cleanup terminalized the recording session after content committed')
    return conversation_ref


def _assert_cleanup_fences_then_rolls_over(
    client: Any,
    uid: str,
    *,
    content_kind: str,
    content_write: Callable[[str], bool],
    content_present: Callable[[Any], bool],
) -> None:
    """Cleanup-first ordering must move late buffered content to a fresh generation.

    Firestore's server transaction mode serializes a read/write cleanup before
    a concurrent SDK writer. The writer therefore observes the deleted parent;
    production's bounded rollover helper must replay that buffer to a new
    recording generation instead of recreating the terminal parent.
    """
    old_conversation_id = f'{content_kind}-cleanup-first-{uuid.uuid4().hex}'
    old_recording_session_id = f'session-{uuid.uuid4().hex}'
    _seed_live_generation(client, uid, old_conversation_id, old_recording_session_id)

    if not recording_sessions_db.tombstone_and_delete_empty_conversation(
        uid,
        old_conversation_id,
        old_recording_session_id,
        firestore_client=client,
    ):
        raise AssertionError('empty cleanup did not win the required cleanup-first ordering')
    if content_write(old_conversation_id):
        raise AssertionError('late content recreated a terminal conversation instead of being fenced')

    old_session = recording_sessions_db.get_recording_session(
        uid,
        old_recording_session_id,
        firestore_client=client,
    )
    if old_session is None or old_session['lifecycle_phase'] != 'discarded':
        raise AssertionError('cleanup-first ordering did not terminalize the old recording generation')

    fresh_conversation_id = f'{content_kind}-fresh-{uuid.uuid4().hex}'
    fresh_recording_session_id = f'session-{uuid.uuid4().hex}'

    async def rollover() -> None:
        _seed_live_generation(client, uid, fresh_conversation_id, fresh_recording_session_id)

    def write_current() -> str | None:
        return 'old-generation' if content_write(old_conversation_id) else None

    def write_fresh() -> str | None:
        return 'fresh-generation' if content_write(fresh_conversation_id) else None

    result, rolled_over = asyncio.run(
        retry_fenced_live_content_once(
            write_current=write_current,
            rollover=rollover,
            write_fresh=write_fresh,
        )
    )
    if (result, rolled_over) != ('fresh-generation', True):
        raise AssertionError(
            f'late {content_kind} content did not roll over into a fresh generation: {result=}, {rolled_over=}'
        )

    fresh_ref = _conversation_ref(client, uid, fresh_conversation_id)
    if not content_present(fresh_ref):
        raise AssertionError(f'late {content_kind} content did not persist in the fresh conversation')


def _assert_segment_content_contract(client: Any, uid: str) -> None:
    conversation_id = f'segment-{uuid.uuid4().hex}'
    recording_session_id = f'session-{uuid.uuid4().hex}'
    started_at = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    _seed_live_generation(client, uid, conversation_id, recording_session_id)

    conversation_ref = _assert_live_content_prevents_cleanup(
        client,
        uid,
        conversation_id,
        recording_session_id,
        lambda: conversations_db.update_conversation_segments(
            uid,
            conversation_id,
            [{'id': 'late-segment', 'text': 'persisted after cleanup read'}],
            started_at=started_at,
            firestore_client=client,
        ),
    )
    conversation = conversation_ref.get().to_dict() or {}
    if not conversation.get('transcript_segments'):
        raise AssertionError('late transcript segments were not preserved')
    if conversation.get('started_at') != started_at:
        raise AssertionError('first-segment started_at did not commit atomically with content')

    def write_segments(target_conversation_id: str) -> bool:
        return conversations_db.update_conversation_segments(
            uid,
            target_conversation_id,
            [{'id': 'fenced-segment', 'text': 'replayed after cleanup'}],
            started_at=started_at,
            firestore_client=client,
        )

    _assert_cleanup_fences_then_rolls_over(
        client,
        uid,
        content_kind='segment',
        content_write=write_segments,
        content_present=lambda ref: (
            bool((ref.get().to_dict() or {}).get('transcript_segments'))
            and (ref.get().to_dict() or {}).get('started_at') == started_at
        ),
    )
    _assert_cleanup_lock_fences_late_segment_write(client, uid)


def _assert_photo_content_contract(client: Any, uid: str) -> None:
    conversation_id = f'photo-{uuid.uuid4().hex}'
    recording_session_id = f'session-{uuid.uuid4().hex}'
    _seed_live_generation(client, uid, conversation_id, recording_session_id)

    def write_photo(target_conversation_id: str) -> bool:
        return conversations_db.store_conversation_photos(
            uid,
            target_conversation_id,
            [ConversationPhoto(id='late-photo', base64='aGVsbG8=', description='late screenshot')],
            firestore_client=client,
        )

    conversation_ref = _assert_live_content_prevents_cleanup(
        client,
        uid,
        conversation_id,
        recording_session_id,
        lambda: write_photo(conversation_id),
    )
    if len(list(conversation_ref.collection('photos').stream())) != 1:
        raise AssertionError('late photo subdocument was not preserved')

    _assert_cleanup_fences_then_rolls_over(
        client,
        uid,
        content_kind='photo',
        content_write=write_photo,
        content_present=lambda ref: len(list(ref.collection('photos').stream())) == 1,
    )


def _assert_photo_only_finalization_is_admitted(client: Any, uid: str) -> None:
    conversation_id = f'photo-finalization-{uuid.uuid4().hex}'
    _seed_empty_live_conversation(client, uid, conversation_id)
    if not conversations_db.store_conversation_photos(
        uid,
        conversation_id,
        [ConversationPhoto(id='only-photo', base64='aGVsbG8=', description='photo-only listen conversation')],
        firestore_client=client,
    ):
        raise AssertionError('photo-only writer unexpectedly lost its conversation parent')

    intent = lifecycle_service.request_finalization(
        uid,
        conversation_id,
        has_byok_keys=False,
        firestore_client=client,
    )
    if intent['status'] != 'queued' or not intent['job_id']:
        raise AssertionError(f'photo-only conversation was not admitted to durable finalization: {intent}')


def _assert_legacy_photo_only_finalization_is_admitted(client: Any, uid: str) -> None:
    """Pre-marker photo children must still admit a durable finalization job."""
    conversation_id = f'legacy-photo-finalization-{uuid.uuid4().hex}'
    conversation_ref = _seed_empty_live_conversation(client, uid, conversation_id)
    conversation_ref.collection('photos').document('legacy-only-photo').set(
        {'id': 'legacy-only-photo', 'description': 'pre-marker photo-only listen conversation'}
    )

    intent = lifecycle_service.request_finalization(
        uid,
        conversation_id,
        has_byok_keys=False,
        firestore_client=client,
    )
    if intent['status'] != 'queued' or not intent['job_id']:
        raise AssertionError(f'legacy photo-only conversation was not admitted to durable finalization: {intent}')


def main() -> int:
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):
        raise RuntimeError('FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec')

    client: Any = firestore.Client(project=PROJECT_ID)
    uid = f'listen-lifecycle-emulator-{uuid.uuid4().hex}'
    _assert_segment_content_contract(client, uid)
    _assert_photo_content_contract(client, uid)
    _assert_photo_only_finalization_is_admitted(client, uid)
    _assert_legacy_photo_only_finalization_is_admitted(client, uid)
    print('PASS: Firestore emulator fenced cleanup races and preserved listen content through fresh-generation replay')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
