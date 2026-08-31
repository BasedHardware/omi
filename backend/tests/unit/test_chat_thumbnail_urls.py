"""Chat thumbnails: store the key, sign at read time (ADR-0087, BACKLOG L6).

The other five user-audio surfaces could switch to a signed URL outright because none of their URLs is
persisted. This one is different, and the difference is the whole design: what `upload_multi_chat_files`
returns is written into the chat message document (`fc.thumbnail` -> `chat_db.add_multi_files`) and
re-served on every later read. A signed URL stored there becomes a **deferred 403** the day it expires.

So the object KEY is persisted and the URL is minted where the record leaves the database — the shape
the codebase already uses for APP thumbnails (`models/app.py` keeps ids, `routers/conversations.py`
mints `thumbnail_urls`). The response of the upload route resolves too, so the client sees a URL there
exactly as it would on a later read.

The branch that matters most is the legacy one: every message written before this holds a full URL in
that field, and it must pass through untouched. Without it, this change would turn every image already
in a user's chat history into a broken link.
"""

from __future__ import annotations

import pytest

from tests.object_store_fakes import FakeObjectStore


class _RecordingStore(FakeObjectStore):
    def __init__(self):
        super().__init__()
        self.signed: list[tuple[str, str, int]] = []
        self.public: list[tuple[str, str]] = []

    def presign_get(self, bucket: str, key: str, *, expires_seconds: int) -> str:
        self.signed.append((bucket, key, expires_seconds))
        return f'https://signed.invalid/{bucket}/{key}'

    def public_url(self, bucket: str, key: str) -> str:
        self.public.append((bucket, key))
        return f'https://public.invalid/{bucket}/{key}'


@pytest.fixture
def store(monkeypatch):
    from utils.other import storage

    fake = _RecordingStore()
    monkeypatch.setattr(storage, '_object_store', lambda: fake)
    monkeypatch.setattr(storage, 'get_cached_signed_url', lambda key: None)
    monkeypatch.setattr(storage, 'cache_signed_url', lambda key, url, ttl: None)
    monkeypatch.setattr(storage, 'chat_files_bucket', 'chat-files', raising=False)
    return fake


# --- what gets stored ------------------------------------------------------------------------------


def test_the_upload_returns_keys_not_urls(store, tmp_path, monkeypatch):
    """What this returns is what lands in the message document, so it must be the durable identifier."""
    from utils.other import storage

    monkeypatch.chdir(tmp_path)
    (tmp_path / 'thumb.png').write_bytes(b'\x89PNG')

    keys = storage.upload_multi_chat_files(['thumb.png'], 'u1')

    assert keys == {'thumb.png': 'u1/thumb.png'}, 'a URL here would expire inside the stored document'
    assert store.signed == [] and store.public == [], 'nothing is minted at write time'


# --- what gets served ------------------------------------------------------------------------------


def test_a_stored_key_is_signed_on_the_way_out(store):
    from utils.other.storage import USER_AUDIO_URL_MINUTES, resolve_chat_thumbnail

    url = resolve_chat_thumbnail('u1/thumb.png')

    assert url == 'https://signed.invalid/chat-files/u1/thumb.png'
    assert store.signed == [('chat-files', 'u1/thumb.png', USER_AUDIO_URL_MINUTES * 60)]


def test_a_legacy_url_passes_through_untouched(store):
    """THE branch that decides whether this change is safe to ship. Every message written before this
    holds a full URL; signing it again would produce nonsense, and rejecting it would break the image."""
    from utils.other.storage import resolve_chat_thumbnail

    legacy = 'https://storage.googleapis.com/chat-files/u1/thumb.png'

    assert resolve_chat_thumbnail(legacy) == legacy
    assert store.signed == [], 'a stored URL must not be re-signed'


def test_an_empty_thumbnail_stays_empty(store):
    """A non-image file has no thumbnail, and must not acquire a URL pointing at nothing."""
    from utils.other.storage import resolve_chat_thumbnail

    assert resolve_chat_thumbnail('') == ''
    assert store.signed == []


def test_resolving_a_batch_touches_only_the_thumbnails(store):
    from utils.other.storage import resolve_chat_file_thumbnails

    records = [
        {'id': 'a', 'thumbnail': 'u1/a.png', 'openai_file_id': 'f-a'},
        {'id': 'b', 'thumbnail': '', 'openai_file_id': 'f-b'},
        {'id': 'c', 'thumbnail': 'https://legacy.invalid/x.png'},
    ]

    resolved = resolve_chat_file_thumbnails(records)

    assert resolved[0]['thumbnail'].startswith('https://signed.invalid/')
    assert resolved[1]['thumbnail'] == ''
    assert resolved[2]['thumbnail'] == 'https://legacy.invalid/x.png'
    assert resolved[0]['openai_file_id'] == 'f-a', 'nothing else on the record is touched'


# --- the wiring, so a read path cannot silently stop resolving --------------------------------------


def test_get_chat_files_signs_what_it_returns(monkeypatch, store):
    """BEHAVIOURAL, through a real database exit: seed a stored record carrying a key and check what the
    reader hands back. This is what the static check below cannot do, and it is the one exit that is not
    behind a decorator needing a live protection-level lookup."""
    from tests.store_fakes import install_fake_db_client

    fake_db = install_fake_db_client(monkeypatch)
    fake_db.set('users/u1/files/f1', {'id': 'f1', 'thumbnail': 'u1/thumb.png', 'mime_type': 'image/png'})

    import database.chat as chat_db

    (record,) = chat_db.get_chat_files('u1', ['f1'])

    assert record['thumbnail'] == 'https://signed.invalid/chat-files/u1/thumb.png'


def test_every_database_exit_resolves():
    """STATIC CHECK, labelled. The behaviour is covered above for one exit; this holds the WIRING on all
    three — a fourth read path added later without the call would serve raw keys, and the client would
    render a broken image rather than fail.

    It greps for the CALL, not the name: the first version matched the `from ... import` line too, so
    deleting the call while keeping the import passed. Caught by mutation.
    """
    import inspect

    from database import chat as chat_db

    for name in ('get_messages', 'get_chat_files', 'get_chat_files_desc'):
        source = inspect.getsource(getattr(chat_db, name))
        assert 'resolve_chat_file_thumbnails(' in source, f'{name} serves stored records without resolving'


def test_the_upload_routes_resolve_before_responding():
    """STATIC CHECK, labelled. The upload response must show a URL, like a later read would — otherwise
    a just-uploaded image is the one that does not render."""
    import inspect

    from routers import chat as chat_router

    source = inspect.getsource(chat_router)

    assert source.count('storage.resolve_chat_thumbnail(') == 2, 'both upload routes must resolve'
