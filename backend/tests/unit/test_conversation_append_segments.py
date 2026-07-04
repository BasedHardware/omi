import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Same heavy-import isolation the connector tests use, so importing the conversations
# database module doesn't construct real Firestore/LLM clients at import time.
from tests.unit.memory_import_isolation import (  # noqa: E402
    ensure_utils_memory_packages_importable,
    install_canonical_write_runtime_stubs,
    install_database_client_stub,
    install_ws_i_heavy_import_stubs,
)

import types  # noqa: E402

ensure_utils_memory_packages_importable(str(BACKEND_DIR))
install_database_client_stub()
install_canonical_write_runtime_stubs()
install_ws_i_heavy_import_stubs()

# database/conversations.py pulls a few heavy leaf modules (Hume SDK, GCS storage) that
# aren't needed for the pure append logic under test and aren't importable in isolation.
# Stub just those leaves so the REAL conversations module imports cleanly.
for _name in ("utils.other", "utils.other.hume", "utils.other.storage"):
    sys.modules.setdefault(_name, types.ModuleType(_name))
sys.modules["utils.other.storage"].list_audio_chunks = lambda *a, **k: []
sys.modules["utils.other"].hume = sys.modules["utils.other.hume"]
sys.modules["utils.other"].storage = sys.modules["utils.other.storage"]

# The heavy-import isolation above stubs database.conversations itself with a mock (so
# unrelated tests never pull its transitive imports). This test needs the REAL module,
# so evict that one stub and import it fresh.
sys.modules.pop("database.conversations", None)
import database.conversations as cdb  # noqa: E402

assert type(cdb).__name__ == "module", "expected the real conversations module, got a stub"


def _fake_db_with_snapshot(snapshot):
    """A stand-in for the Firestore client whose document chain resolves to a doc_ref
    returning `snapshot` from .get(transaction=...)."""
    doc_ref = MagicMock(name='doc_ref')
    doc_ref.get.return_value = snapshot
    db = MagicMock(name='db')
    db.transaction.return_value = MagicMock(name='transaction')
    db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref
    return db, doc_ref


def _passthrough_transactional(fn):
    # Replace @firestore.transactional so calling _append(transaction) runs the body
    # directly (no real commit/retry machinery) in the unit test.
    return fn


def test_append_concatenates_existing_and_new_inside_transaction():
    """The core data-loss fix: append re-reads the existing segments inside the
    transaction and CONCATENATES the new ones (never overwrites), and writes via
    transaction.update — so two concurrent appends can't clobber each other."""
    stored = {
        'data_protection_level': 'standard',
        # Standard level, uncompressed → _prepare_conversation_for_read returns the
        # list as-is (no zlib needed in the test).
        'transcript_segments': [{'text': 'existing', 'person_id': 'pA'}],
    }
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = stored
    db, doc_ref = _fake_db_with_snapshot(snapshot)

    new_segments = [{'text': 'appended', 'person_id': 'pB'}]

    with patch.object(cdb, 'db', db), patch.object(
        cdb.firestore, 'transactional', _passthrough_transactional
    ), patch.object(
        # Identity write-prep so we can inspect the raw payload (skip compression/encryption).
        cdb,
        '_prepare_conversation_for_write',
        lambda payload, uid, level: payload,
    ):
        ok = cdb.append_transcript_segments('uid', 'conv1', new_segments)

    assert ok is True
    txn = db.transaction.return_value
    assert txn.update.call_count == 1
    written_ref, payload = txn.update.call_args.args
    assert written_ref is doc_ref
    # Existing segment is preserved and the new one is appended — not overwritten.
    assert payload['transcript_segments'] == [
        {'text': 'existing', 'person_id': 'pA'},
        {'text': 'appended', 'person_id': 'pB'},
    ]
    # person_ids index reflects both speakers.
    assert payload['person_ids'] == ['pA', 'pB']


def test_append_returns_false_when_conversation_deleted():
    """If the conversation was deleted mid-ingest (snapshot missing) the append is a
    no-op that reports False, so the caller never treats it as stored."""
    snapshot = MagicMock()
    snapshot.exists = False
    db, _doc_ref = _fake_db_with_snapshot(snapshot)

    with patch.object(cdb, 'db', db), patch.object(cdb.firestore, 'transactional', _passthrough_transactional):
        ok = cdb.append_transcript_segments('uid', 'conv1', [{'text': 'x', 'person_id': 'pB'}])

    assert ok is False
    assert db.transaction.return_value.update.call_count == 0


def test_append_only_extends_finished_at():
    """finished_at is monotonic: a smaller incoming value never shrinks the stored one,
    so a reordered/late append can't roll the conversation's end time backwards."""
    from datetime import datetime, timezone

    later = datetime(2026, 1, 2, tzinfo=timezone.utc)
    earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stored = {
        'data_protection_level': 'standard',
        'transcript_segments': [{'text': 'existing', 'person_id': 'pA'}],
        'finished_at': later,
    }
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = stored
    db, _doc_ref = _fake_db_with_snapshot(snapshot)

    with patch.object(cdb, 'db', db), patch.object(
        cdb.firestore, 'transactional', _passthrough_transactional
    ), patch.object(cdb, '_prepare_conversation_for_write', lambda payload, uid, level: payload):
        cdb.append_transcript_segments('uid', 'conv1', [{'text': 'x', 'person_id': 'pB'}], finished_at=earlier)

    _ref, payload = db.transaction.return_value.update.call_args.args
    # earlier < stored later → finished_at must NOT be written (no shrink).
    assert 'finished_at' not in payload


def test_append_tolerates_unreadable_existing_segments():
    """If the existing segments blob is corrupt/undecompressible (left as raw bytes by
    the read path), the append must not crash the transaction or fold garbage into the
    write — it stores the new segments and moves on rather than looping forever."""
    stored = {
        'data_protection_level': 'standard',
        # Simulate an undecompressible blob: read path leaves it as raw bytes, not a list.
        'transcript_segments': b'\x00\x01corrupt',
        'transcript_segments_compressed': True,
    }
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = stored
    db, _doc_ref = _fake_db_with_snapshot(snapshot)

    new_segments = [{'text': 'appended', 'person_id': 'pB'}]

    with patch.object(cdb, 'db', db), patch.object(
        cdb.firestore, 'transactional', _passthrough_transactional
    ), patch.object(cdb, '_prepare_conversation_for_write', lambda payload, uid, level: payload):
        ok = cdb.append_transcript_segments('uid', 'conv1', new_segments)

    assert ok is True
    _ref, payload = db.transaction.return_value.update.call_args.args
    # Garbage existing bytes are dropped; only the clean new segment is written.
    assert payload['transcript_segments'] == [{'text': 'appended', 'person_id': 'pB'}]
    assert payload['person_ids'] == ['pB']
