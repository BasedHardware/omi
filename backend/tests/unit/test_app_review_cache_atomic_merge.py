"""Two people reviewing the same app must not erase each other.

Every review for an app lives under one key, `plugins:{app_id}:reviews`, that every reviewer
writes. `set_app_review_cache` read that key, edited the dict in Python and wrote it back, so
a review that landed between the read and the write was lost.

It does not come back. The key has no TTL and nothing repopulates it from Firestore, while
`get_app_reviews` reads it for the app listing, so the lost review stays missing from the
review list, the rating average and the rating count. The same gap also empties
`get_specific_user_review`, which `POST /v1/apps/review` reads to carry the developer's
reply forward, so the next edit of that review silently drops the reply.

The merge now runs inside Redis. These tests pin the client-side contract: one atomic
command, never a read-modify-write.
"""

import json
import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

import pytest

from database import redis_db

KEY = 'plugins:app-1:reviews'


class _FakeRedis:
    """Records every command. `eval` applies the merge the way Redis runs a script: atomically."""

    def __init__(self, initial=None, lua_can_parse=True):
        self.store = dict(initial or {})
        self.calls = []
        self.lua_can_parse = lua_can_parse

    def get(self, key):
        self.calls.append(('get', key))
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.calls.append(('set', key))
        self.store[key] = value

    def eval(self, script, numkeys, *args):
        self.calls.append(('eval', args[0]))
        if not self.lua_can_parse:
            return 0
        key, uid, payload = args[0], args[1], args[2]
        raw = self.store.get(key)
        reviews = json.loads(raw) if raw else {}
        reviews[uid] = json.loads(payload)
        self.store[key] = json.dumps(reviews)
        return 1


@pytest.fixture
def fake(monkeypatch):
    def _install(**kwargs):
        f = _FakeRedis(**kwargs)
        monkeypatch.setattr(redis_db, 'r', f)
        return f

    return _install


def test_a_review_is_written_in_one_atomic_command(fake):
    f = fake()

    redis_db.set_app_review_cache('app-1', 'uid-a', {'score': 5})

    assert [c[0] for c in f.calls] == ['eval'], "a separate get and set can lose a concurrent review"


def test_a_concurrent_review_is_not_lost(fake):
    f = fake(initial={KEY: json.dumps({'uid-a': {'score': 5}})})

    redis_db.set_app_review_cache('app-1', 'uid-b', {'score': 3})

    stored = json.loads(f.store[KEY])
    assert stored == {'uid-a': {'score': 5}, 'uid-b': {'score': 3}}


def test_the_writer_does_not_read_the_key_into_python_first(fake):
    f = fake(initial={KEY: json.dumps({'uid-a': {'score': 5}})})

    redis_db.set_app_review_cache('app-1', 'uid-b', {'score': 3})

    assert ('get', KEY) not in f.calls


def test_a_legacy_value_still_merges_instead_of_clobbering(fake):
    legacy = b"{'uid-a': {'score': 5}}"
    f = fake(initial={KEY: legacy}, lua_can_parse=False)

    redis_db.set_app_review_cache('app-1', 'uid-b', {'score': 3})

    stored = json.loads(f.store[KEY])
    assert stored == {'uid-a': {'score': 5}, 'uid-b': {'score': 3}}
    assert [c[0] for c in f.calls] == ['eval', 'get', 'set']


def test_the_first_review_for_an_app_creates_the_entry(fake):
    f = fake()

    redis_db.set_app_review_cache('app-1', 'uid-a', {'score': 4})

    assert json.loads(f.store[KEY]) == {'uid-a': {'score': 4}}
