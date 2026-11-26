"""Generate synthetic wire fixtures on a local Firestore emulator.

Run from backend-go with the backend's Python environment installed.
./scripts/with-firestore.sh ../backend/.venv/bin/python internal/adapters/conversations/testdata/generate.py
"""

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

OWNER = 'conversation-fixture-owner'
KEY = 'conversation adapter synthetic fixture key'
HERE = Path(__file__).resolve().parent


def wire(value):
    if isinstance(value, datetime):
        return {'$timestamp': value.isoformat()}
    if isinstance(value, bytes):
        return {'$bytes': base64.b64encode(value).decode('ascii')}
    raise TypeError(type(value).__name__)


def main():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:', '[::1]:')):
        raise SystemExit('A loopback Firestore emulator is required')
    os.environ['ENCRYPTION_SECRET'] = KEY
    sys.path.insert(0, str(HERE.parents[4] / 'backend'))

    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from database import conversations, home_feed_writer
    from database.transcript_pointer import decode_stored_transcript
    from utils import encryption

    client = firestore.Client(project='demo-conversations-fixture', credentials=AnonymousCredentials())
    docs = client.collection('users').document(OWNER).collection('conversations')
    speech = [
        {'id': 's1', 'text': 'A synthetic café note.', 'start': 0.25, 'end': 2.5, 'is_user': True},
        {'id': 's2', 'text': '', 'start': 2.5, 'end': 3.25, 'is_user': False},
    ]
    started = datetime(2026, 1, 2, 3, 4, 5, 100000, tzinfo=timezone.utc)
    finished = datetime(2026, 1, 2, 3, 5, 6, 123456, tzinfo=timezone.utc)
    with patch.object(encryption, 'os', SimpleNamespace(urandom=lambda size: b'\x01' * size)):
        legacy = encryption.encrypt(json.dumps(speech), OWNER)
    with patch.object(encryption, 'os', SimpleNamespace(urandom=lambda size: b'\x02' * size)):
        enhanced = conversations._protect_json_value(speech, OWNER, 'enhanced')
    formats = {
        'standard_list': ('standard', speech, None),
        'standard_zlib': ('standard', conversations._protect_json_value(speech, OWNER, 'standard'), True),
        'enhanced_json': ('enhanced', legacy, False),
        'enhanced_zlib': ('enhanced', enhanced, True),
    }
    versions = iter(UUID(int=i) for i in range(1, 30))
    home_uuid = patch.object(home_feed_writer, 'uuid4', lambda: next(versions))
    with home_uuid:
        fixture = collect(docs, formats, speech, started, finished, conversations, decode_stored_transcript)
    (HERE / 'python_wire.json').write_text(
        json.dumps(fixture, default=wire, sort_keys=True, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )


def collect(docs, formats, speech, started, finished, conversations, decode_stored_transcript):
    rows = {}
    for name, (level, stored, compressed) in formats.items():
        row = {
            'id': name,
            'status': 'processing',
            'finalization_status': 'leased',
            'data_protection_level': level,
            'created_at': started,
            'started_at': started,
            'discarded': False,
            'structured': {'title': 'Pending', 'overview': 'Draft', 'emoji': '💬', 'sections': []},
            'transcript_segments': stored,
        }
        if compressed is not None:
            row['transcript_segments_compressed'] = compressed
        ref = docs.document(name)
        ref.set(row)
        rows[name] = ref.get().to_dict()
        assert decode_stored_transcript(
            OWNER, rows[name]['transcript_segments'], bool(compressed), require_decryption=True
        ) == speech

    # Exercise the persistence writer's field mask for the fields the Go port owns.
    result = {
        'status': 'completed',
        'finalization_status': 'completed',
        'discarded': True,
        'structured': {'title': 'Final title', 'overview': 'Final overview'},
        'finished_at': finished,
        'summary_covers_through': finished,
    }
    ref = docs.document('enhanced_zlib')
    ref.update(conversations._processing_result_update_fields(result))
    links = docs.parent.collection('episode_links')
    return {
        'rows': rows,
        'segments': speech,
        'finalized': ref.get().to_dict(),
        'dirty': links.document('enhanced_zlib').get().to_dict(),
        'control': links.document('home_feed_control').get().to_dict(),
    }


if __name__ == '__main__':
    main()
