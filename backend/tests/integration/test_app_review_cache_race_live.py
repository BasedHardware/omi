"""Live integration test for the app review cache race (issue #15970).

Requires real Redis:
    cd backend && REDIS_DB_HOST=localhost REDIS_DB_PORT=16399 \
        python3 -m pytest tests/integration/test_app_review_cache_race_live.py -v -s

`set_app_review_cache` used to GET the whole reviews blob, edit it in Python,
then SET it back. Two reviewers racing on the same app clobbered each other:
whichever SET landed last won, silently dropping the other reviewer's entry
from the app's review list (Firestore still had it -- just not the cache
everything reads). Fixed by moving the read-modify-write into an atomic Lua
script.
"""

import os
import threading

import pytest

from database.redis_db import get_app_reviews, r, set_app_review_cache

APP_ID = "race-test-app-15970"


def _skip_if_no_redis():
    if not os.getenv("REDIS_DB_HOST"):
        pytest.skip("REDIS_DB_HOST not set")


@pytest.fixture(autouse=True)
def cleanup():
    r.delete(f"plugins:{APP_ID}:reviews")
    yield
    r.delete(f"plugins:{APP_ID}:reviews")


def test_concurrent_reviews_do_not_clobber_each_other():
    _skip_if_no_redis()
    n = 25
    barrier = threading.Barrier(n)

    def write(i):
        barrier.wait()  # maximize overlap between concurrent GET-modify-SET windows
        set_app_review_cache(APP_ID, f"user-{i}", {"score": i, "review": f"r{i}"})

    threads = [threading.Thread(target=write, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    reviews = get_app_reviews(APP_ID)
    assert len(reviews) == n, f"expected {n} reviews, found {len(reviews)} -- concurrent writes clobbered each other"
    for i in range(n):
        assert reviews[f"user-{i}"]["score"] == i


def test_legacy_unparseable_value_is_treated_as_empty_not_raised():
    _skip_if_no_redis()
    r.set(f"plugins:{APP_ID}:reviews", "{'uid-a': {'rating': 4}}")  # pre-JSON literal, invalid JSON/cjson

    set_app_review_cache(APP_ID, "uid-b", {"score": 5, "review": "new"})

    reviews = get_app_reviews(APP_ID)
    assert reviews == {"uid-b": {"score": 5, "review": "new"}}
