import hashlib
import json
import os
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.memories as memories_db  # noqa: E402


class _FakeEnc:
    @staticmethod
    def encrypt(text: str, uid: str) -> str:
        return f'{uid}::{text}'

    @staticmethod
    def decrypt(ciphertext: str, uid: str) -> str:
        prefix = f'{uid}::'
        if not isinstance(ciphertext, str) or not ciphertext.startswith(prefix):
            return ciphertext
        return ciphertext[len(prefix) :]


def test_migrate_memories_level_batch_encrypts_and_decrypts_evidence(monkeypatch):
    monkeypatch.setattr(memories_db, 'encryption', _FakeEnc)
    monkeypatch.setattr(memories_db, 'external_write_fence', lambda uid, **kwargs: nullcontext())
    monkeypatch.setattr(memories_db, 'verified_encrypted_read', lambda raw, dec: dec)

    evidence_list = [{'evidence_id': 'ev-1', 'source_id': 'conv-1'}]
    encrypted_evidence = _FakeEnc.encrypt(json.dumps(evidence_list), 'u1')

    doc_std = SimpleNamespace(
        id='m-std',
        exists=True,
        reference=SimpleNamespace(id='m-std'),
        to_dict=lambda: {
            'id': 'm-std',
            'data_protection_level': 'standard',
            'content': 'plain text',
            'evidence': evidence_list,
        },
    )
    doc_enh = SimpleNamespace(
        id='m-enh',
        exists=True,
        reference=SimpleNamespace(id='m-enh'),
        to_dict=lambda: {
            'id': 'm-enh',
            'data_protection_level': 'enhanced',
            'content': _FakeEnc.encrypt('secret text', 'u1'),
            'evidence': encrypted_evidence,
        },
    )

    updates = []

    class _Batch:
        def update(self, ref, data):
            updates.append((ref.id, data))

        def commit(self):
            pass

    def _make_client(docs):
        return SimpleNamespace(
            batch=lambda: _Batch(),
            get_all=lambda refs: docs,
            collection=lambda name: SimpleNamespace(
                document=lambda uid: SimpleNamespace(
                    collection=lambda coll: SimpleNamespace(document=lambda doc_id: SimpleNamespace(id=doc_id))
                )
            ),
        )

    memories_db.migrate_memories_level_batch('u1', ['m-std'], 'enhanced', firestore_client=_make_client([doc_std]))
    assert updates[0] == (
        'm-std',
        {
            'data_protection_level': 'enhanced',
            'content': _FakeEnc.encrypt('plain text', 'u1'),
            'evidence': encrypted_evidence,
        },
    )

    updates.clear()
    memories_db.migrate_memories_level_batch('u1', ['m-enh'], 'standard', firestore_client=_make_client([doc_enh]))
    assert updates[0] == (
        'm-enh',
        {
            'data_protection_level': 'standard',
            'content': 'secret text',
            'evidence': evidence_list,
        },
    )


def test_migrate_memories_rekeys_encrypted_evidence_and_updates_uid(monkeypatch):
    monkeypatch.setattr(memories_db, 'encryption', _FakeEnc)
    monkeypatch.setattr(memories_db, 'external_write_fence', lambda uid, **kwargs: nullcontext())

    evidence_json = json.dumps([{'evidence_id': 'ev-1', 'source_id': 'conv-1'}])
    poisoned_evidence = _FakeEnc.encrypt(evidence_json, 'other-uid')
    source_docs = [
        SimpleNamespace(
            to_dict=lambda: {
                'id': 'm1',
                'uid': 'prevuid',
                'data_protection_level': 'enhanced',
                'content': _FakeEnc.encrypt('secret', 'prevuid'),
                'evidence': _FakeEnc.encrypt(evidence_json, 'prevuid'),
            }
        ),
        SimpleNamespace(
            to_dict=lambda: {
                'id': 'm2',
                'uid': 'prevuid',
                'data_protection_level': 'enhanced',
                'content': _FakeEnc.encrypt('secret-2', 'prevuid'),
                'evidence': poisoned_evidence,
            }
        ),
    ]

    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value.stream.return_value = source_docs
    batch = MagicMock()
    db.batch.return_value = batch

    count = memories_db.migrate_memories('prevuid', 'newuid', firestore_client=db)
    assert count == 2

    written = [call.args[1] for call in batch.set.call_args_list]
    assert written[0]['uid'] == 'newuid'
    assert written[0]['content'] == _FakeEnc.encrypt('secret', 'newuid')
    assert written[0]['evidence'] == _FakeEnc.encrypt(evidence_json, 'newuid')
    assert written[1]['uid'] == 'newuid'
    assert written[1]['evidence'] == poisoned_evidence


def test_refine_memory_encrypts_enhanced_content_and_skips_missing_doc(monkeypatch):
    monkeypatch.setattr(memories_db, 'encryption', _FakeEnc)

    missing_ref = MagicMock()
    missing_ref.get.return_value = SimpleNamespace(exists=False, to_dict=lambda: None)
    missing_db = MagicMock()
    missing_db.collection.return_value.document.return_value.collection.return_value.document.return_value = missing_ref
    append_mock = MagicMock()
    monkeypatch.setattr(memories_db.memory_ledger, 'append_commit', append_mock)

    assert memories_db.refine_memory('u1', 'm-missing', {'content': {'to': 'new'}}, firestore_client=missing_db) is None
    append_mock.assert_not_called()

    existing_doc = {
        'id': 'm1',
        'data_protection_level': 'enhanced',
        'content': _FakeEnc.encrypt('old', 'u1'),
        'arguments': {'slot': 'a'},
    }
    mem_ref = MagicMock()
    mem_ref.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: dict(existing_doc))
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value.document.return_value = mem_ref

    tx_updates = []

    class _Tx:
        def update(self, ref, payload):
            tx_updates.append(payload)

    captured_mutations = []

    def _fake_append(uid, parent, mutations, **kwargs):
        captured_mutations.extend(mutations)
        kwargs['projection_writer'](_Tx())
        return {'commit': {'commit_id': 'c1'}}

    monkeypatch.setattr(memories_db.memory_ledger, 'append_commit', _fake_append)

    memories_db.refine_memory(
        'u1',
        'm1',
        {'content': {'to': 'refined secret'}, 'slot': {'to': 'b'}},
        firestore_client=db,
    )

    expected_cipher = _FakeEnc.encrypt('refined secret', 'u1')
    expected_sha = hashlib.sha256(b'refined secret').hexdigest()
    assert len(tx_updates) == 1
    assert tx_updates[0]['content'] == expected_cipher
    assert tx_updates[0]['arguments'] == {'slot': 'b'}
    assert captured_mutations[0]['arg_changes']['content'] == {
        'to': expected_cipher,
        'to_sha256': expected_sha,
    }


def test_get_user_public_memories_filters_rejected_invalidated_tombstoned_and_locked():
    docs = [
        SimpleNamespace(to_dict=lambda d=d: d)
        for d in [
            {'id': 'pub-valid', 'content': 'ok', 'visibility': 'public'},
            {'id': 'pub-default', 'content': 'ok2'},
            {'id': 'priv', 'content': 'secret', 'visibility': 'private'},
            {'id': 'pub-rejected', 'content': 'no', 'visibility': 'public', 'user_review': False},
            {
                'id': 'pub-invalidated',
                'content': 'old',
                'visibility': 'public',
                'invalid_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
            },
            {
                'id': 'pub-tombstoned',
                'content': None,
                'visibility': 'public',
                'redaction_status': 'payload_tombstoned',
            },
            {'id': 'pub-locked', 'content': 'locked', 'visibility': 'public', 'is_locked': True},
        ]
    ]
    query = MagicMock()
    query.order_by.return_value = query
    query.limit.return_value = query
    query.offset.return_value = query
    query.stream.return_value = docs

    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value = query

    result = memories_db.get_user_public_memories('u1', limit=20, offset=0, firestore_client=db)
    assert [m['id'] for m in result] == ['pub-valid', 'pub-default']


def test_legacy_memory_update_helpers_tolerate_missing_documents():
    mem_ref = MagicMock()
    mem_ref.update.side_effect = memories_db.FirestoreNotFound('missing')
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value.document.return_value = mem_ref

    assert memories_db.review_memory('u1', 'm1', True, firestore_client=db) is None
    assert memories_db.change_memory_visibility('u1', 'm1', 'private', firestore_client=db) is None
    assert memories_db.update_memory_fields('u1', 'm1', {'headline': 'h'}, firestore_client=db) is None


@pytest.mark.asyncio
async def test_memories_router_public_create_updates_persona_and_mutations_map_value_error():
    from pathlib import Path
    from types import ModuleType
    from testing.import_isolation import load_module_fresh, stub_modules
    from models.memories import Memory, MemoryCategory, MemoryDB

    def make_module(name: str, **attrs):
        mod = ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        return mod

    submitted_personas = []
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    created_mem = MemoryDB(
        id='m-pub',
        uid='u1',
        content='Public fact',
        category=MemoryCategory.manual,
        visibility='public',
        created_at=now,
        updated_at=now,
    )

    class _FakeService:
        def __init__(self, db_client=None):
            pass

        def create_external_memory(self, *args, **kwargs):
            return created_mem

        def review(self, uid, memory_id, value):
            raise ValueError('Memory not found')

        def update_visibility(self, uid, memory_id, value):
            raise ValueError('Memory not found')

        def update_baseline(self, uid, memory_id, value):
            raise ValueError('Memory not found')

    async def _fake_run_blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    auth_mod = make_module(
        'utils.other.endpoints',
        get_current_user_uid=lambda: 'u1',
        with_rate_limit=lambda fn, *a, **kw: fn,
    )
    executors_mod = make_module(
        'utils.executors',
        db_executor=None,
        llm_executor=None,
        postprocess_executor=None,
        run_blocking=_fake_run_blocking,
        submit_with_context=lambda executor, fn, *args: submitted_personas.append((fn, args)),
    )
    apps_mod = make_module('utils.apps', update_personas_async=MagicMock())
    mem_service_mod = make_module(
        'utils.memory.memory_service',
        MEMORY_LIST_SCAN_BUDGET_DETAIL='budget',
        MemoryBackingStoreUnavailable=type('MemoryBackingStoreUnavailable', (Exception,), {}),
        MemoryPayload=dict,
        MemoryService=_FakeService,
        fetch_memory_dict=lambda uid, memory_id, db_client=None: {'id': memory_id},
    )

    with stub_modules(
        {
            'utils.other.endpoints': auth_mod,
            'utils.executors': executors_mod,
            'utils.apps': apps_mod,
            'utils.memory.memory_service': mem_service_mod,
            'utils.memory.canonical_memory_adapter': make_module(
                'utils.memory.canonical_memory_adapter',
                mint_direct_user_write_authority=lambda: 'auth',
            ),
            'database.memory_imports': make_module('database.memory_imports', ingest_memory_import_batch=MagicMock()),
            'database.review_queue': make_module('database.review_queue'),
            'utils.feedback': make_module('utils.feedback', record_memory_feedback=lambda *a, **kw: None),
            'utils.product_metrics': make_module('utils.product_metrics', record_product_event=lambda *a, **kw: None),
        }
    ):
        router_path = Path(__file__).resolve().parents[2] / 'routers' / 'memories.py'
        memories_router = load_module_fresh('routers.memories', router_path)

        fake_req = SimpleNamespace(headers={})

        async def _empty_json():
            return {}

        fake_req.json = _empty_json

        res = await memories_router.create_memory(
            fake_req,
            Memory(content='Public fact', visibility='public', category=MemoryCategory.manual),
            uid='u1',
        )
        assert res.id == 'm-pub'
        assert len(submitted_personas) == 1
        assert submitted_personas[0] == (apps_mod.update_personas_async, ('u1',))

        with pytest.raises(HTTPException) as exc_review:
            memories_router.review_memory('m-1', True, uid='u1')
        assert exc_review.value.status_code == 404

        with pytest.raises(HTTPException) as exc_vis:
            memories_router.update_memory_visibility(
                'm-1',
                request=memories_router.MemoryValueRequest(value='public'),
                uid='u1',
            )
        assert exc_vis.value.status_code == 404

        with pytest.raises(HTTPException) as exc_base:
            memories_router.update_memory_baseline('m-1', True, uid='u1')
        assert exc_base.value.status_code == 404
