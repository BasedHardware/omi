"""Regression tests for #21848 — memory evidence encryption/rekey + guards.

Covers: evidence encrypted on standard->enhanced and decrypted on
enhanced->standard migration, decrypt-fail skips, evidence re-keying and
uid fixup in migrate_memories, refine_memory plaintext/orphan guards,
public-memory filtering, and not-found tolerant mutations.
"""

import contextlib

import database.memories as mem_db
import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def _bypass_write_fence(monkeypatch):
    monkeypatch.setattr(mem_db, 'external_write_fence', lambda *a, **k: contextlib.nullcontext())


def _snap(mid, data):
    s = MagicMock()
    s.exists = True
    s.id = mid
    s.to_dict.return_value = data
    s.reference = MagicMock()
    return s


def _fake_db(snaps):
    db = MagicMock()
    db.get_all = lambda refs: snaps
    db.batch = MagicMock()
    return db


# ---------- migrate_memories_level_batch ----------


def test_level_migration_encrypts_evidence_to_enhanced(monkeypatch):
    ev = [{'start': 0, 'end': 5}]
    snap = _snap('m1', {'content': 'hello', 'evidence': ev, 'data_protection_level': 'standard'})
    batch = MagicMock()
    fake = _fake_db([snap])
    fake.batch = lambda: batch
    monkeypatch.setattr(mem_db, '_get_db', lambda c=None: fake)
    monkeypatch.setattr(mem_db, '_typed_doc', lambda s: s.to_dict())
    monkeypatch.setattr(mem_db, '_prepare_memory_for_read', lambda d, u: dict(d))
    monkeypatch.setattr(mem_db.encryption, 'encrypt', lambda v, u: f'ENC[{v}]')

    mem_db.migrate_memories_level_batch('u', ['m1'], 'enhanced')
    args = batch.update.call_args[0]
    assert args[1]['content'].startswith('ENC[')
    assert args[1]['evidence'].startswith('ENC[')


def test_level_migration_decrypts_evidence_to_standard(monkeypatch):
    snap = _snap('m1', {'content': 'CIPHER', 'evidence': 'EVCIPHER', 'data_protection_level': 'enhanced'})
    batch = MagicMock()
    fake = _fake_db([snap])
    fake.batch = lambda: batch
    monkeypatch.setattr(mem_db, '_get_db', lambda c=None: fake)
    monkeypatch.setattr(mem_db, '_typed_doc', lambda s: s.to_dict())
    monkeypatch.setattr(
        mem_db, '_prepare_memory_for_read', lambda d, u: {**d, 'content': 'plain', 'evidence': 'EVCIPHER'}
    )
    monkeypatch.setattr(
        mem_db.encryption, 'decrypt', lambda v, u: '[{"start":0,"end":5}]' if v == 'EVCIPHER' else 'plain'
    )

    mem_db.migrate_memories_level_batch('u', ['m1'], 'standard')
    args = batch.update.call_args[0]
    assert args[1]['evidence'] == [{'start': 0, 'end': 5}]


def test_level_migration_skips_when_content_decrypt_fails(monkeypatch):
    snap = _snap('m1', {'content': 'CIPHER', 'evidence': [], 'data_protection_level': 'enhanced'})
    batch = MagicMock()
    fake = _fake_db([snap])
    fake.batch = lambda: batch
    monkeypatch.setattr(mem_db, '_get_db', lambda c=None: fake)
    monkeypatch.setattr(mem_db, '_typed_doc', lambda s: s.to_dict())
    monkeypatch.setattr(mem_db, '_prepare_memory_for_read', lambda d, u: dict(d))  # unchanged = failed

    mem_db.migrate_memories_level_batch('u', ['m1'], 'standard')
    batch.update.assert_not_called()


def test_level_migration_drops_unrecoverable_evidence(monkeypatch):
    snap = _snap('m1', {'content': 'CIPHER', 'evidence': 'BADCIPHER', 'data_protection_level': 'enhanced'})
    batch = MagicMock()
    fake = _fake_db([snap])
    fake.batch = lambda: batch
    monkeypatch.setattr(mem_db, '_get_db', lambda c=None: fake)
    monkeypatch.setattr(mem_db, '_typed_doc', lambda s: s.to_dict())
    monkeypatch.setattr(
        mem_db, '_prepare_memory_for_read', lambda d, u: {**d, 'content': 'plain', 'evidence': 'BADCIPHER'}
    )
    monkeypatch.setattr(mem_db.encryption, 'decrypt', lambda v, u: (_ for _ in ()).throw(Exception('bad')))

    mem_db.migrate_memories_level_batch('u', ['m1'], 'standard')
    args = batch.update.call_args[0]
    assert args[1]['evidence'] == []


# ---------- migrate_memories evidence re-key + uid ----------


def test_migrate_memories_rekeys_evidence_and_uid(monkeypatch):
    memory = {
        'id': 'm1',
        'content': 'CIPHER',
        'evidence': 'EVCIPHER',
        'data_protection_level': 'enhanced',
        'uid': 'old',
    }
    query = MagicMock()
    query.stream.return_value = [MagicMock(to_dict=lambda: dict(memory))]
    prev_ref = MagicMock()
    prev_ref.collection.return_value = query
    fake = MagicMock()
    fake.collection.side_effect = lambda name: MagicMock(
        document=lambda uid: (
            prev_ref if uid == 'old' else MagicMock(collection=lambda c: MagicMock(document=lambda i: MagicMock()))
        )
    )
    fake.batch.return_value = MagicMock()
    monkeypatch.setattr(mem_db, '_get_db', lambda c=None: fake)
    monkeypatch.setattr(mem_db, '_typed_doc', lambda s: s.to_dict())

    def dec(v, uid):
        return {'CIPHER': 'plain', 'EVCIPHER': 'evjson'}[v] if uid == 'old' else v

    monkeypatch.setattr(mem_db.encryption, 'decrypt', dec)
    monkeypatch.setattr(mem_db.encryption, 'encrypt', lambda v, u: f'{u}:{v}')

    n = mem_db.migrate_memories('old', 'new')
    assert n == 1
    set_calls = fake.batch.return_value.set.call_args_list
    doc = set_calls[0][0][1]
    assert doc['content'] == 'new:plain'
    assert doc['evidence'] == 'new:evjson'
    assert doc['uid'] == 'new'


# ---------- refine_memory guards ----------


def test_refine_memory_no_orphan_ledger_when_missing(monkeypatch):
    memory_ref = MagicMock()
    memory_ref.get.return_value.exists = False
    fake = MagicMock()
    fake.collection.return_value = MagicMock(
        document=lambda u: MagicMock(collection=lambda c: MagicMock(document=lambda i: memory_ref))
    )
    monkeypatch.setattr(mem_db, '_get_db', lambda c=None: fake)
    append = MagicMock()
    monkeypatch.setattr(mem_db.memory_ledger, 'append_commit', append)

    out = mem_db.refine_memory('u', 'm1', {'content': {'to': 'x'}})
    assert out is None
    append.assert_not_called()


def test_refine_memory_encrypts_content_on_enhanced(monkeypatch):
    written = {}
    snap = _snap('m1', {'data_protection_level': 'enhanced', 'arguments': {}, 'content': 'ENCOLD'})

    memory_ref = MagicMock()
    memory_ref.get.return_value = snap
    fake = MagicMock()
    fake.collection.return_value = MagicMock(
        document=lambda u: MagicMock(collection=lambda c: MagicMock(document=lambda i: memory_ref))
    )
    monkeypatch.setattr(mem_db, '_get_db', lambda c=None: fake)
    monkeypatch.setattr(mem_db, '_typed_doc', lambda s: s.to_dict())
    monkeypatch.setattr(
        mem_db, 'projection_update_for_refine', lambda ex, ch, t: {'content': ch['content']['to'], 'arguments': {}}
    )
    monkeypatch.setattr(mem_db.encryption, 'encrypt', lambda v, u: f'ENC[{v}]')
    monkeypatch.setattr(mem_db.encryption, 'decrypt', lambda v, u: v)

    def fake_append(uid, none, ops, commit_time=None, projection_writer=None, use_current_head=None):
        txn = MagicMock()
        txn.update = lambda ref, payload: written.update(payload)
        projection_writer(txn)
        return {}

    monkeypatch.setattr(mem_db.memory_ledger, 'append_commit', fake_append)
    mem_db.refine_memory('u', 'm1', {'content': {'to': 'plaintext'}})
    assert written['content'] == 'ENC[plaintext]'


# ---------- public memory filtering ----------


def test_public_memories_filter_rejected_invalid_tombstone_locked(monkeypatch):
    docs = [
        _snap('a', {'visibility': 'public'}),
        _snap('b', {'visibility': 'public', 'user_review': False}),
        _snap('c', {'visibility': 'public', 'invalid_at': 't'}),
        _snap('d', {'visibility': 'public', 'redaction_status': 'payload_tombstoned'}),
        _snap('e', {'visibility': 'public', 'is_locked': True}),
        _snap('f', {'visibility': 'private'}),
        _snap('g', {'scoring': 1}),  # missing visibility counts as public
    ]
    ref = MagicMock()
    ref.order_by.return_value = ref
    ref.limit.return_value = ref
    ref.offset.return_value = ref
    ref.stream.return_value = docs
    fake = MagicMock()
    fake.collection.return_value = MagicMock(document=lambda u: MagicMock(collection=lambda c: ref))
    monkeypatch.setattr(mem_db, '_get_db', lambda c=None: fake)
    monkeypatch.setattr(mem_db, '_typed_doc', lambda s: s.to_dict())

    out = mem_db.get_user_public_memories('u')
    ids = {m.get('id') or i for i, m in enumerate(out)}
    assert len(out) == 2  # 'a' and 'g' only


# ---------- not-found tolerant mutations ----------


def test_review_memory_tolerates_missing_doc(monkeypatch):
    from google.api_core.exceptions import NotFound

    memory_ref = MagicMock()
    memory_ref.update.side_effect = NotFound('gone')
    fake = MagicMock()
    fake.collection.return_value = MagicMock(
        document=lambda u: MagicMock(collection=lambda c: MagicMock(document=lambda i: memory_ref))
    )
    monkeypatch.setattr(mem_db, '_get_db', lambda c=None: fake)
    mem_db.review_memory('u', 'm1', True)  # must not raise


def test_change_visibility_tolerates_missing_doc(monkeypatch):
    from google.api_core.exceptions import NotFound

    memory_ref = MagicMock()
    memory_ref.update.side_effect = NotFound('gone')
    fake = MagicMock()
    fake.collection.return_value = MagicMock(
        document=lambda u: MagicMock(collection=lambda c: MagicMock(document=lambda i: memory_ref))
    )
    monkeypatch.setattr(mem_db, '_get_db', lambda c=None: fake)
    mem_db.change_memory_visibility('u', 'm1', 'private')
