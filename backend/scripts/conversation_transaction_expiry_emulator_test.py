#!/usr/bin/env python3
"""Firestore-emulator proof for the expired-transaction restart in ``run_transactional``.

Production incident: ``google.api_core.grpc_helpers`` raised
``Aborted: 409 The referenced transaction has expired or is no longer valid.`` when a
streaming read (``BatchGetDocuments``) referenced a transaction id Firestore had already
retired. The SDK's ``@firestore.transactional`` retries ``Aborted`` only around
``_commit``, so the read-path error escaped into the caller and tore down the live
listen session. The fix restarts that error on a brand-new transaction.

Emulator parity gap (verified against cloud-firestore-emulator v1.21.0): the emulator
reports a retired transaction id on ``:batchGet`` as ``400 INVALID_ARGUMENT
"Transaction is invalid or closed."``, not the production ``Aborted`` 409 envelope, so
the emulator alone cannot emit the incident's exact error. This harness therefore proves
the contract in two steps that keep every other layer real:

1. Native retired-id read: a real SDK-begun transaction id is genuinely retired through
   the emulator's REST ``:commit``, and the real streaming read
   (``doc_ref.get(transaction=...)``) surfaces the emulator-authenticated error instead
   of silently succeeding.
2. Production envelope restart: the exact production ``Aborted`` message is raised once
   at the transport seam the production remap feeds
   (``_wrapped_methods[batch_get_documents]``; the gapic retry predicate does not retry
   ``Aborted``, so it propagates exactly like the real transport error). Begin, the
   failing read, rollback, the fresh-transaction restart, the retrying read, and the
   commit all run against the real emulator through the real SDK, and the segments
   write is verified durable afterwards.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import uuid
import zlib
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PROJECT_ID = os.environ.setdefault('GOOGLE_CLOUD_PROJECT', os.environ.get('GCLOUD_PROJECT', 'demo-listen'))
os.environ.setdefault('GCLOUD_PROJECT', PROJECT_ID)
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_conversation_transaction_expiry_emulator_test_secret_32_bytes')

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.api_core.exceptions import Aborted, GoogleAPICallError
from google.cloud import firestore

from database import conversations as conversations_db

ABORTED_EXPIRED_MESSAGE = '409 The referenced transaction has expired or is no longer valid.'
SEGMENTS = [{'id': 'seg-1', 'text': 'emulator proof segment', 'start': 0.0, 'end': 1.0}]


def _conversation_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection('users').document(uid).collection('conversations').document(conversation_id)


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


def _assert_native_retired_id_read_fails(client: Any, uid: str, conversation_id: str) -> None:
    """A genuinely retired id must fail the real streaming read on the real emulator."""
    doc_ref = _conversation_ref(client, uid, conversation_id)
    transaction = client.transaction()
    transaction._begin()
    retired_id = transaction._id
    # Retire the id for real: commit it out-of-band through the emulator's REST API.
    # The emulator has now closed that id, exactly like the production expiry.
    _emulator_post(':commit', {'transaction': base64.b64encode(retired_id).decode(), 'writes': []})
    try:
        doc_ref.get(transaction=transaction)
    except GoogleAPICallError as error:
        if 'transaction' not in str(error).lower():
            raise AssertionError(f'emulator retired-id read failed for an unexpected reason: {error!r}') from error
    else:
        raise AssertionError('a streaming read on a genuinely retired transaction id did not fail')


def _assert_aborted_read_restart_writes_durable_segments(client: Any, uid: str, conversation_id: str) -> None:
    """The production Aborted envelope on the read must restart on a fresh transaction."""
    doc_ref = _conversation_ref(client, uid, conversation_id)
    transport = client._firestore_api._transport
    original_batch_get = transport._wrapped_methods[transport.batch_get_documents]
    seen_transaction_ids: list[bytes] = []
    injected = False

    def _production_envelope_batch_get(request: Any, **kwargs: Any) -> Any:
        nonlocal injected
        transaction_id = bytes(request.transaction or b'')
        if transaction_id:
            seen_transaction_ids.append(transaction_id)
        if transaction_id and not injected:
            injected = True
            # Exactly what google.api_core.grpc_helpers raised in production when the
            # retired id reached the streaming read. The gapic retry predicate does not
            # retry Aborted, so this propagates like the real transport error.
            raise Aborted(ABORTED_EXPIRED_MESSAGE)
        return original_batch_get(request, **kwargs)

    transport._wrapped_methods[transport.batch_get_documents] = _production_envelope_batch_get
    try:
        persisted = conversations_db.update_conversation_segments(
            uid,
            conversation_id,
            SEGMENTS,
            data_protection_level='standard',
            firestore_client=client,
        )
    finally:
        transport._wrapped_methods[transport.batch_get_documents] = original_batch_get

    if persisted is not True:
        raise AssertionError(f'the expired-transaction restart did not persist the segments write: {persisted}')
    if len(seen_transaction_ids) != 2:
        raise AssertionError(
            f'expected the restart to issue exactly two transactional reads, saw {len(seen_transaction_ids)}: '
            f'{seen_transaction_ids}'
        )
    if seen_transaction_ids[0] == seen_transaction_ids[1]:
        raise AssertionError('the restarted attempt reused the retired transaction id instead of a fresh one')

    snapshot = doc_ref.get()
    if not snapshot.exists:
        raise AssertionError('the restarted transaction did not leave a durable conversation document')
    stored = snapshot.to_dict() or {}
    if stored.get('has_content') is not True:
        raise AssertionError(
            f'the restarted transaction did not persist the durable content marker: {stored.get("has_content")}'
        )
    if stored.get('transcript_segments_compressed') is not True:
        raise AssertionError('the stored segments lost the compressed encoding marker')
    decoded = json.loads(zlib.decompress(stored['transcript_segments']).decode('utf-8'))
    if decoded != SEGMENTS:
        raise AssertionError(f'the durable segments round-trip mismatched: {decoded}')


def main() -> int:
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):
        raise RuntimeError('FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec')

    client: Any = firestore.Client(project=PROJECT_ID)
    uid = f'conversation-txn-expiry-emulator-{uuid.uuid4().hex}'
    conversation_id = f'expired-txn-{uuid.uuid4().hex}'
    _conversation_ref(client, uid, conversation_id).set(
        conversations_db.encode_conversation_for_write(
            uid,
            {
                'id': conversation_id,
                'status': 'in_progress',
                'discarded': False,
                'transcript_segments': [],
                'has_content': False,
                'data_protection_level': 'standard',
            },
        )
    )
    _assert_native_retired_id_read_fails(client, uid, conversation_id)
    _assert_aborted_read_restart_writes_durable_segments(client, uid, conversation_id)
    print('PASS: expired-transaction reads fail through the real stack and the Aborted 409 restarts durably')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
