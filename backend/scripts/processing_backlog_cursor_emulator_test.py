#!/usr/bin/env python3
"""Loopback-only proof that malformed backlog cursors rewind instead of stalling.

The production ``InvalidArgument`` deferrals (event=processing_backlog, #23827)
have no traceback. This script reproduces the server-side rejection class
against the loopback Firestore emulator — a stored cursor whose ``id`` is empty
builds a document name with a trailing slash, which Firestore rejects with
InvalidArgument on every visit — and proves the validated worker page rewinds
to newest instead of rebuilding the rejected query.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('PROVIDER_MODE', 'offline')
os.environ.setdefault('MEMORY_ENABLED', 'on')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_emulator_proof_key_32_bytes_ok')
os.environ.setdefault('GOOGLE_AUTH_DISABLE_GCE_CHECK', 'true')

from google.api_core import exceptions as gexc
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from utils import processing_backlog_worker as worker


def main():
    if not os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        raise RuntimeError('requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-held-audio', credentials=AnonymousCredentials())
    uid = f'cursor-proof-{uuid4().hex}'
    audio = client.collection('users').document(uid).collection('stt_cap_holds')
    for index in range(worker.PAGE + 2):
        audio.document(f'hold-{index:02d}').set({'state': 'held', 'listed_at': 1000 - index, 'seconds': 60})
    with patch.object(worker.cap_hold, 'holds', lambda owner: audio):
        # Mechanism: the unvalidated cursor shape the server rejects every visit.
        rejected = audio.order_by('listed_at', direction=firestore.Query.DESCENDING).order_by(
            '__name__', direction=firestore.Query.DESCENDING
        )
        try:
            list(rejected.start_after({'listed_at': 1000, '__name__': audio.document('')}).limit(worker.PAGE).stream())
        except gexc.InvalidArgument:
            pass
        else:
            raise AssertionError('empty cursor id did not reproduce InvalidArgument')
        # Repair: the worker page rewinds to newest instead of stalling.
        for poisoned in ({'at': None, 'id': ''}, {'at': 1, 'id': ''}, 'legacy-cursor'):
            rows = worker._page(uid, 'audio', poisoned)
            assert [snap.id for _, snap in rows] == [f'hold-{index:02d}' for index in range(worker.PAGE)], poisoned
        # Drain: paging with validated cursors still reaches every sibling.
        seen, cursor = [], None
        for _ in range(5):
            page = worker._page(uid, 'audio', cursor)
            if not page:
                break
            seen.extend(snap.id for _, snap in page)
            last = worker._candidate(*page[-1])
            cursor = {'at': last['at'], 'id': last['id']}
        else:
            raise AssertionError('cursor failed to terminate')
        assert len(set(seen)) == worker.PAGE + 2
    client.close()
    print('PASS: InvalidArgument mechanism reproduced; malformed cursors rewind and drain without stalling')


if __name__ == '__main__':
    main()
