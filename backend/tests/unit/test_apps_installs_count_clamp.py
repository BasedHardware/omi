"""Regression: get_apps_installs_count must never return a negative install count.

The install counter is a plain Redis INCR/DECR with no floor, so drift (a disable with no matching
enable, or a DECR on an evicted key) can leave a negative value like b'-1'. A negative count later
reaches math.log(1 + installs) in utils.apps.compute_app_score, which raises ValueError: math domain
error and 500s the entire marketplace catalog sort. Clamp at the read boundary. No live services.
"""

import os
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.redis_db as redis_db  # noqa: E402


def test_get_apps_installs_count_clamps_negative_and_none(monkeypatch):
    fake = MagicMock()
    fake.mget.return_value = [b"-1", b"3", None, b"0", b"-42"]
    monkeypatch.setattr(redis_db, "r", fake)

    result = redis_db.get_apps_installs_count(["a", "b", "c", "d", "e"])

    assert result == {"a": 0, "b": 3, "c": 0, "d": 0, "e": 0}  # negatives floored to 0


def test_get_apps_installs_count_empty_ids():
    assert redis_db.get_apps_installs_count([]) == {}
