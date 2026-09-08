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
        # Delegate the full public fakeredis surface. A curated allowlist
        # drifts behind backend Redis usage (`mget`, `setex`, sets, hashes,
        # Lua script helpers, etc.) and can fall through to a real client.
        for attr in dir(fake):
            if attr.startswith("_"):
                continue
            value = getattr(fake, attr, None)
            if callable(value):
                setattr(self, attr, value)

    redis_pkg.Redis.__init__ = _fake_redis_init
    redis_pkg.StrictRedis.__init__ = _fake_redis_init

    def _fake_from_url(*args, **kwargs):
        return get_fake_redis()

    redis_pkg.Redis.from_url = staticmethod(_fake_from_url)
    redis_pkg.StrictRedis.from_url = staticmethod(_fake_from_url)
    redis_pkg.from_url = _fake_from_url
