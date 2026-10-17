"""Unit tests for the #21852 chat-session cleanup fixes.

Covers: session-file cleanup on session delete, chat_context_generation
increment in cascaded deletes, thumbnail unlink on failed uploads,
file_ids clearing on surviving sessions, rating validation, reported-
message share guards, and the migrate_chats_level_batch decrypt guard.
"""

import database.chat as chat_db
import routers.chat as chat_router
import utils.other.chat_file as chat_file_mod
import pytest
from unittest.mock import MagicMock, patch

# ---------- database.chat.delete_chat_session ----------


class _FakeDoc:
    def __init__(self, id='m1'):
        self.id = id


class _FakeBatch:
    def __init__(self, updates):
        self._updates = updates
        self.deleted = []

    def update(self, ref, values):
        self._updates.append((ref, values))

    def delete(self, ref, **kwargs):
        self.deleted.append(ref)

    def commit(self):
        pass


class _FakeQuery:
    def __init__(self, docs):
        self._docs = docs
        self._calls = 0

    def limit(self, n):
        self._limit = n
        return self

    def stream(self):
        self._calls += 1
        if self._calls == 1:
            return iter(self._docs)
        return iter([])


class _FakeCollection:
    def __init__(self, query):
        self._query = query

    def where(self, **kwargs):
        return self._query

    def document(self, doc_id):
        return MagicMock()


class _FakeSessionRef:
    def get(self):
        m = MagicMock()
        m.exists = True
        return m

    def delete(self):
        pass


class _FakeUserRef:
    def __init__(self, query):
        self._query = query

    def collection(self, name):
        if name == 'messages':
            return _FakeCollection(self._query)
        return MagicMock(document=lambda _id: _FakeSessionRef())


def test_delete_chat_session_bumps_context_generation(monkeypatch):
    updates = []
    batches = []

    def fake_batch():
        b = _FakeBatch(updates)
        batches.append(b)
        return b

    fake_db = MagicMock()
    fake_db.batch = fake_batch
    fake_db.collection = lambda name: MagicMock(document=lambda uid: _FakeUserRef(_FakeQuery([_FakeDoc()])))
    monkeypatch.setattr(chat_db, 'db', fake_db)

    chat_db.delete_chat_session('u', 'sess', cascade_messages=True)
    assert updates, 'expected a user-doc update carrying chat_context_generation'
    assert any('chat_context_generation' in v for _, v in updates)


# ---------- migrate_chats_level_batch decrypt guard ----------


def _mk_snapshot(mid, data):
    snap = MagicMock()
    snap.exists = True
    snap.id = mid
    snap.to_dict.return_value = data
    snap.reference = MagicMock()
    return snap


def test_migrate_skips_row_when_decrypt_returns_ciphertext(monkeypatch):
    ciphertext = 'ENCRYPTED-BLOB'
    snap = _mk_snapshot('m1', {'text': ciphertext, 'data_protection_level': 'enhanced'})
    batch = MagicMock()
    fake_db = MagicMock()
    fake_db.batch = lambda: batch
    fake_db.get_all = lambda refs: [snap]
    fake_db.collection = lambda name: MagicMock(
        document=lambda uid: MagicMock(collection=lambda c: MagicMock(document=lambda m: MagicMock()))
    )
    monkeypatch.setattr(chat_db, 'db', fake_db)
    # decryption "fails" — returns ciphertext unchanged
    monkeypatch.setattr(chat_db, '_prepare_message_for_read', lambda d, uid: dict(d))
    monkeypatch.setattr(chat_db, 'typed_message_document', lambda s: s.to_dict())

    chat_db.migrate_chats_level_batch('u', ['m1'], 'standard')
    batch.update.assert_not_called()


def test_migrate_writes_when_decrypt_succeeds(monkeypatch):
    ciphertext = 'ENCRYPTED-BLOB'
    snap = _mk_snapshot('m1', {'text': ciphertext, 'data_protection_level': 'enhanced'})
    batch = MagicMock()
    fake_db = MagicMock()
    fake_db.batch = lambda: batch
    fake_db.get_all = lambda refs: [snap]
    monkeypatch.setattr(chat_db, 'db', fake_db)
    monkeypatch.setattr(chat_db, '_prepare_message_for_read', lambda d, uid: {**d, 'text': 'hello'})
    monkeypatch.setattr(chat_db, 'typed_message_document', lambda s: s.to_dict())

    chat_db.migrate_chats_level_batch('u', ['m1'], 'standard')
    batch.update.assert_called_once()
    args = batch.update.call_args[0]
    assert args[1]['data_protection_level'] == 'standard'
    assert args[1]['text'] == 'hello'


# ---------- FileChatTool.upload thumbnail cleanup ----------


def test_upload_unlinks_thumbnail_when_create_raises(tmp_path, monkeypatch):
    thumb = tmp_path / 'thumb.png'
    thumb.write_bytes(b'x')
    src = tmp_path / 'img.png'
    src.write_bytes(b'\x89PNG\r\n\x1a\n')

    monkeypatch.setattr(chat_file_mod.File, 'is_image', lambda self: True)
    monkeypatch.setattr(
        chat_file_mod.File, 'generate_thumbnail', lambda self, **k: setattr(self, 'thumbnail_path', thumb)
    )
    monkeypatch.setattr(chat_file_mod.File, 'get_mime_type', lambda self: 'image/png')
    monkeypatch.setattr(chat_file_mod.openai.files, 'create', lambda **k: (_ for _ in ()).throw(Exception('down')))

    with pytest.raises(Exception):
        chat_file_mod.FileChatTool.upload(src)
    assert not thumb.exists()


# ---------- FileChatTool.cleanup clears file_ids ----------


def test_cleanup_clears_session_file_ids(monkeypatch):
    tool = object.__new__(chat_file_mod.FileChatTool)
    tool.uid = 'u'
    tool.chat_session_id = 'sess'
    tool.chat_session = MagicMock(file_ids=['f1'])

    updated = {}
    session_ref = MagicMock()
    session_ref.get.return_value.exists = True
    session_ref.update.side_effect = lambda v: updated.update(v)
    fake_db = MagicMock()
    fake_db.collection = lambda n: MagicMock(
        document=lambda u: MagicMock(collection=lambda c: MagicMock(document=lambda s: session_ref))
    )
    monkeypatch.setattr(chat_file_mod.chat_db, 'db', fake_db)
    monkeypatch.setattr(chat_file_mod.chat_db, 'get_chat_files', lambda u, ids: [{'openai_file_id': 'o1'}])
    monkeypatch.setattr(chat_file_mod.chat_db, 'delete_multi_files', lambda u, f: None)
    monkeypatch.setattr(chat_file_mod.openai.files, 'delete', lambda *a, **k: None)

    tool.cleanup()
    assert updated == {'file_ids': []}


# ---------- share endpoints ----------


class _ShareReq:
    def __init__(self, ids):
        self.message_ids = ids


def _msg(mid, reported=False):
    m = MagicMock()
    m.id = mid
    m.reported = reported
    return m


def test_share_dedupes_and_rejects_reported(monkeypatch):
    calls = []

    def get_message(uid, mid):
        calls.append(mid)
        return (_msg(mid, reported=(mid == 'bad')), None)

    monkeypatch.setattr(chat_router.chat_db, 'get_message', get_message)
    monkeypatch.setattr(chat_router, 'get_user_display_name', lambda u: 'x')
    monkeypatch.setattr(chat_router, 'store_chat_share', lambda *a, **k: {'ok': True})
    monkeypatch.setattr(chat_router.share_links, 'build_share_url', lambda p: p)

    # dedupe: 'a' twice → single fetch each
    res = chat_router.share_chat_messages(_ShareReq(['a', 'a', 'b']), uid='u')
    assert calls.count('a') == 1
    # reported → 400
    import fastapi

    with pytest.raises(fastapi.HTTPException) as exc:
        chat_router.share_chat_messages(_ShareReq(['ok', 'bad']), uid='u')
    assert exc.value.status_code == 400


def test_shared_get_filters_post_share_reports(monkeypatch):
    monkeypatch.setattr(
        chat_router, 'get_chat_share', lambda t: {'uid': 'u', 'message_ids': ['m1', 'm2'], 'display_name': 'd'}
    )

    def get_message(uid, mid):
        return (_msg(mid, reported=(mid == 'm2')), None)

    monkeypatch.setattr(chat_router.chat_db, 'get_message', get_message)
    out = chat_router.get_shared_chat_messages('tok')
    assert out['count'] == 1
    assert out['messages'][0]['id'] == 'm1'


# ---------- rating ----------


def test_rate_message_rejects_invalid_rating(monkeypatch):
    import fastapi

    req = MagicMock()
    req.rating = 5
    monkeypatch.setattr(chat_router.chat_db, 'update_message_rating', lambda *a: {'x': 1})
    with pytest.raises(fastapi.HTTPException) as exc:
        chat_router.rate_message('m1', req, None, None, None, uid='u')
    assert exc.value.status_code == 422


def test_rate_message_404s_when_snapshot_none(monkeypatch):
    import fastapi

    req = MagicMock()
    req.rating = 1
    req.reason = None
    req.comment = None
    monkeypatch.setattr(chat_router.chat_db, 'update_message_rating', lambda *a: None)
    with pytest.raises(fastapi.HTTPException) as exc:
        chat_router.rate_message('m1', req, None, None, None, uid='u')
    assert exc.value.status_code == 404
