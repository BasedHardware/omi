"""
Fake Redis using fakeredis.

Provides a hermetic in-memory Redis replacement that supports
the same API surface as redis.Redis — get, set, delete, expire,
JSON operations, etc.
"""

from typing import Optional

import fakeredis

# Module-level singleton
_fake_redis: Optional[fakeredis.FakeRedis] = None


def get_fake_redis() -> fakeredis.FakeRedis:
    """Return the shared FakeRedis instance."""
    if _fake_redis is None:
        raise RuntimeError("FakeRedis not initialized — call setup_fake_redis() first")
    return _fake_redis


def setup_fake_redis() -> fakeredis.FakeRedis:
    """Create and register the global FakeRedis singleton."""
    global _fake_redis
    _fake_redis = fakeredis.FakeRedis()
    return _fake_redis


def teardown_fake_redis():
    """Clear the singleton."""
    global _fake_redis
    _fake_redis = None


def patch_redis_client():
    """
    Monkeypatch redis.Redis so that the module-level ``r`` in database/redis_db
    returns our FakeRedis instance.

    Must be called BEFORE database.redis_db is imported.
    """
    import redis as redis_pkg

    original_init = redis_pkg.Redis.__init__

    def _fake_redis_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        fake = get_fake_redis()
        # Delegate all key methods to the fake
        for attr in (
            "get",
            "set",
            "delete",
            "exists",
            "expire",
            "ttl",
            "incr",
            "decr",
            "ping",
            "keys",
            "flushdb",
            "flushall",
            "pipeline",
            "evalscript",
            "eval",
        ):
            if hasattr(fake, attr):
                setattr(self, attr, getattr(fake, attr))

    redis_pkg.Redis.__init__ = _fake_redis_init
