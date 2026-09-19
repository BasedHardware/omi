"""Regression tests for idempotent app-install accounting."""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.redis_db as redis_db  # noqa: E402


def test_enable_app_reports_new_membership(monkeypatch):
    class FakeRedis:
        def sadd(self, key, app_id):
            assert key == "users/user-1/enabled_plugins"
            assert app_id == "app-1"
            return 1

    monkeypatch.setattr(redis_db, "r", FakeRedis())
    assert redis_db.enable_app("user-1", "app-1") is True


def test_enable_app_reports_existing_membership_without_incrementing(monkeypatch):
    class FakeRedis:
        def sadd(self, key, app_id):
            return 0

    monkeypatch.setattr(redis_db, "r", FakeRedis())
    assert redis_db.enable_app("user-1", "app-1") is False
