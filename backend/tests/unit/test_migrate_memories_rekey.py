"""migrate_memories must re-key enhanced (encrypted) memories for the new owner.

Memories with data_protection_level='enhanced' are encrypted with a per-user key (utils.encryption
derives the key with the uid as the HKDF salt). On app-owner migration (POST /v1/apps/migrate-owner
-> migrate_memories(prev_uid, new_uid)) the memories were copied verbatim, so their content stayed
encrypted under prev_uid's key. The read path decrypts with new_uid and silently swallows the
failure, so the new owner just sees unreadable ciphertext: silent data loss. migrate_memories now
decrypts each enhanced memory with the previous user's key and re-encrypts with the new user's key
before copying, mirroring the decrypt-then-reencrypt pattern already used by migrate_memories_level_batch.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def _decorator_factory(*args, **kwargs):
    # The data-protection decorators are applied at import time as factories; a no-op keeps the
    # decorated CRUD functions intact without exercising real encryption on import.
    def _wrap(fn):
        return fn

    return _wrap


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


# Stub the heavy leaves database/memories.py imports so the real module loads.
for _p in ["google", "google.cloud", "database", "utils"]:
    _pkg(_p)
_mod("google.cloud.firestore", SERVER_TIMESTAMP=MagicMock())
_mod("google.cloud.firestore_v1", FieldFilter=MagicMock())
_mod("database._client", db=MagicMock())
_mod("database.users", get_user=MagicMock())
_mod(
    "database.helpers",
    set_data_protection_level=_decorator_factory,
    prepare_for_write=_decorator_factory,
    prepare_for_read=_decorator_factory,
)
_mod("utils.encryption", encrypt=FakeEnc.encrypt, decrypt=FakeEnc.decrypt)


def _load():
    spec = importlib.util.spec_from_file_location("database.memories", str(BACKEND_DIR / "database" / "memories.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["database.memories"] = mod
    spec.loader.exec_module(mod)
    return mod


memories = _load()


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


def test_enhanced_memory_is_rekeyed_for_new_owner():
    src = [{"id": "m1", "content": FakeEnc.encrypt("secret", "prevuid"), "data_protection_level": "enhanced"}]
    db, batch = _make_db(src)
    with patch.object(memories, "db", db), patch.object(memories, "encryption", FakeEnc):
        count = memories.migrate_memories("prevuid", "newuid")

    assert count == 1
    written = _written(batch)[0]
    # The content must now be encrypted under the NEW owner's key, not the previous owner's.
    assert written["content"] == FakeEnc.encrypt("secret", "newuid")
    assert written["content"] != FakeEnc.encrypt("secret", "prevuid")
    assert written["data_protection_level"] == "enhanced"
    # And it is actually decryptable by the new owner.
    assert FakeEnc.decrypt(written["content"], "newuid") == "secret"


def test_standard_memory_is_copied_unchanged():
    src = [{"id": "m2", "content": "plain text", "data_protection_level": "standard"}]
    db, batch = _make_db(src)
    with patch.object(memories, "db", db), patch.object(memories, "encryption", FakeEnc):
        memories.migrate_memories("prevuid", "newuid")

    written = _written(batch)[0]
    # Standard memories are not encrypted; they copy across verbatim.
    assert written["content"] == "plain text"


def test_undecryptable_content_is_copied_as_is_not_double_wrapped():
    # If the content cannot be decrypted with the source user's key (already-corrupted ciphertext),
    # it must be copied unchanged, NOT re-encrypted under the new key (which would mask the
    # corruption as a value the new owner can "decrypt").
    poisoned = FakeEnc.encrypt("secret", "someone-else")  # not decryptable with prevuid
    src = [{"id": "m1", "content": poisoned, "data_protection_level": "enhanced"}]
    db, batch = _make_db(src)
    with patch.object(memories, "db", db), patch.object(memories, "encryption", FakeEnc):
        memories.migrate_memories("prevuid", "newuid")

    written = _written(batch)[0]
    assert written["content"] == poisoned
    assert written["content"] != FakeEnc.encrypt(poisoned, "newuid")


def test_mixed_batch_rekeys_only_enhanced():
    src = [
        {"id": "m1", "content": FakeEnc.encrypt("alpha", "prevuid"), "data_protection_level": "enhanced"},
        {"id": "m2", "content": "beta", "data_protection_level": "standard"},
    ]
    db, batch = _make_db(src)
    with patch.object(memories, "db", db), patch.object(memories, "encryption", FakeEnc):
        count = memories.migrate_memories("prevuid", "newuid")

    assert count == 2
    written = _written(batch)
    assert FakeEnc.decrypt(written[0]["content"], "newuid") == "alpha"
    assert written[1]["content"] == "beta"
