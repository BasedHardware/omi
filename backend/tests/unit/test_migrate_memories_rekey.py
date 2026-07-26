"""migrate_memories must re-key enhanced (encrypted) memories for the new owner.

Memories with data_protection_level='enhanced' are encrypted with a per-user key (utils.encryption
derives the key with the uid as the HKDF salt). On app-owner migration (POST /v1/apps/migrate-owner
-> migrate_memories(prev_uid, new_uid)) the memories were copied verbatim, so their content stayed
encrypted under prev_uid's key. The read path decrypts with new_uid and silently swallows the
failure, so the new owner just sees unreadable ciphertext: silent data loss. migrate_memories now
decrypts each enhanced memory with the previous user's key and re-encrypts with the new user's key
before copying, mirroring the decrypt-then-reencrypt pattern already used by migrate_memories_level_batch.
"""

import os
from unittest.mock import MagicMock

import pytest

# database.memories -> utils.encryption reads ENCRYPTION_SECRET at import time, so a valid key must be
# present before the module is imported below. setdefault leaves any caller-provided value untouched.
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Import the real module. Its top level is referentially transparent (get_firestore_client is lazy),
# so no client is constructed and no network is touched on import. Fakes are injected per-test via
# the firestore_client parameter and monkeypatch on the module's encryption singleton.
from database import memories  # noqa: E402


class FakeEnc:
    """Per-user keyed stand-in for utils.encryption: content encrypted for one uid is unreadable to another."""

    @staticmethod
    def encrypt(content, uid):
        return f"{uid}::{content}"

    @staticmethod
    def decrypt(ciphertext, uid):
        # Mirror production utils.encryption.decrypt: on failure (wrong key / corrupt data) it does
        # NOT raise, it returns the input ciphertext unchanged. The migration must detect that.
        prefix = f"{uid}::"
        if not isinstance(ciphertext, str) or not ciphertext.startswith(prefix):
            return ciphertext
        return ciphertext[len(prefix) :]


@pytest.fixture
def enc(monkeypatch):
    """Inject the per-user keyed fake encryption onto the module's lazy singleton (no sys.modules mutation)."""
    monkeypatch.setattr(memories, "encryption", FakeEnc)
    return FakeEnc


def _doc(data):
    snap = MagicMock()
    snap.to_dict.return_value = data
    return snap


def _make_db(source_dicts):
    db = MagicMock()
    memories_ref = db.collection.return_value.document.return_value.collection.return_value
    memories_ref.stream.return_value = [_doc(d) for d in source_dicts]
    batch = MagicMock()
    db.batch.return_value = batch
    return db, batch


def _written(batch):
    # The second positional arg of each batch.set(ref, memory) call.
    return [call.args[1] for call in batch.set.call_args_list]


def test_enhanced_memory_is_rekeyed_for_new_owner(enc):
    src = [{"id": "m1", "content": enc.encrypt("secret", "prevuid"), "data_protection_level": "enhanced"}]
    db, batch = _make_db(src)
    count = memories.migrate_memories("prevuid", "newuid", firestore_client=db)

    assert count == 1
    written = _written(batch)[0]
    # The content must now be encrypted under the NEW owner's key, not the previous owner's.
    assert written["content"] == enc.encrypt("secret", "newuid")
    assert written["content"] != enc.encrypt("secret", "prevuid")
    assert written["data_protection_level"] == "enhanced"
    # And it is actually decryptable by the new owner.
    assert enc.decrypt(written["content"], "newuid") == "secret"


def test_standard_memory_is_copied_unchanged(enc):
    src = [{"id": "m2", "content": "plain text", "data_protection_level": "standard"}]
    db, batch = _make_db(src)
    memories.migrate_memories("prevuid", "newuid", firestore_client=db)

    written = _written(batch)[0]
    # Standard memories are not encrypted; they copy across verbatim.
    assert written["content"] == "plain text"


def test_undecryptable_content_is_copied_as_is_not_double_wrapped(enc):
    # If the content cannot be decrypted with the source user's key (already-corrupted ciphertext),
    # it must be copied unchanged, NOT re-encrypted under the new key (which would mask the
    # corruption as a value the new owner can "decrypt").
    poisoned = enc.encrypt("secret", "someone-else")  # not decryptable with prevuid
    src = [{"id": "m1", "content": poisoned, "data_protection_level": "enhanced"}]
    db, batch = _make_db(src)
    memories.migrate_memories("prevuid", "newuid", firestore_client=db)

    written = _written(batch)[0]
    assert written["content"] == poisoned
    assert written["content"] != enc.encrypt(poisoned, "newuid")


def test_mixed_batch_rekeys_only_enhanced(enc):
    src = [
        {"id": "m1", "content": enc.encrypt("alpha", "prevuid"), "data_protection_level": "enhanced"},
        {"id": "m2", "content": "beta", "data_protection_level": "standard"},
    ]
    db, batch = _make_db(src)
    count = memories.migrate_memories("prevuid", "newuid", firestore_client=db)

    assert count == 2
    written = _written(batch)
    assert enc.decrypt(written[0]["content"], "newuid") == "alpha"
    assert written[1]["content"] == "beta"
