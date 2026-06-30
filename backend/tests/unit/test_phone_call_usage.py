import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_phone_call_usage(redis_client):
    redis_stub = types.ModuleType("database.redis_db")
    redis_stub.r = redis_client

    def try_catch_decorator(func):
        return func

    redis_stub.try_catch_decorator = try_catch_decorator
    previous = sys.modules.get("database.redis_db")
    sys.modules["database.redis_db"] = redis_stub
    try:
        spec = importlib.util.spec_from_file_location(
            "phone_call_usage_for_test", BACKEND_DIR / "database" / "phone_call_usage.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("database.redis_db", None)
        else:
            sys.modules["database.redis_db"] = previous


def test_reserve_current_month_slot_is_atomic_and_rolls_back_over_limit():
    redis_client = MagicMock()
    redis_client.incr.side_effect = [5, 6]
    module = _load_phone_call_usage(redis_client)

    reserved, used_before, _ = module.reserve_current_month_slot("uid1", monthly_limit=5)
    rejected, rejected_used_before, _ = module.reserve_current_month_slot("uid1", monthly_limit=5)

    assert reserved is True
    assert used_before == 4
    assert rejected is False
    assert rejected_used_before == 5
    redis_client.decr.assert_called_once()
