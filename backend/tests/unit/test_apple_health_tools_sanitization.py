import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent.parent


def _register(name: str):
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr = name.rsplit(".", 1)
        setattr(_register(parent_name), attr, mod)
    return mod


for _name in [
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "database",
    "database.users",
    "database.notifications",
    "utils",
    "utils.retrieval",
    "utils.retrieval.tools",
    "utils.retrieval.tools.integration_base",
]:
    _register(_name)

# Passthrough @tool decorator so tools remain plain callables
sys.modules["langchain_core.tools"].tool = lambda func=None, **kw: (func if func is not None else (lambda f: f))
sys.modules["langchain_core.runnables"].RunnableConfig = dict

# Stub integration_base helpers
integration_base = sys.modules["utils.retrieval.tools.integration_base"]
integration_base.resolve_config_uid = lambda c: (
    (c.get("configurable", {}).get("user_id"), None) if c else (None, "Config missing")
)
integration_base.get_integration_checked = lambda uid, name, display, not_conn, err_msg: (
    ({"health_data": {}}, None) if uid else (None, "User ID not found")
)

# Stub database modules
users_db = sys.modules["database.users"]
users_db.get_integration = MagicMock(return_value={"health_data": {}})

notification_db = sys.modules["database.notifications"]
notification_db.get_user_time_zone = MagicMock(return_value="UTC")


def _load_module_from_file(module_name: str, file_path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


apple_health_tools = _load_module_from_file(
    "utils.retrieval.tools.apple_health_tools",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "apple_health_tools.py",
)


def test_get_apple_health_steps_tool_sanitizes_exception():
    bad_integration = MagicMock()
    bad_integration.get.side_effect = RuntimeError("sensitive_firestore_internal_ip_10.0.0.1_token_xyz")
    original_prepare = apple_health_tools.prepare_apple_health_access
    apple_health_tools.prepare_apple_health_access = MagicMock(return_value=("user_123", bad_integration, None))

    try:
        res = apple_health_tools.get_apple_health_steps_tool(config={"configurable": {"user_id": "user_123"}})
        assert res == "Error retrieving step data."
        assert "sensitive_firestore_internal_ip_10.0.0.1_token_xyz" not in res
    finally:
        apple_health_tools.prepare_apple_health_access = original_prepare


def test_get_apple_health_steps_tool_sanitizes_prepare_access_exception():
    original_prepare = apple_health_tools.prepare_apple_health_access
    apple_health_tools.prepare_apple_health_access = MagicMock(
        side_effect=RuntimeError("connection_timeout_leak_secret")
    )

    try:
        res = apple_health_tools.get_apple_health_steps_tool(config={"configurable": {"user_id": "user_123"}})
        assert res == "Error retrieving step data."
        assert "connection_timeout_leak_secret" not in res
    finally:
        apple_health_tools.prepare_apple_health_access = original_prepare


def test_get_apple_health_sleep_tool_sanitizes_exception():
    bad_integration = MagicMock()
    bad_integration.get.side_effect = RuntimeError("database_query_error_table_users_leak")
    original_prepare = apple_health_tools.prepare_apple_health_access
    apple_health_tools.prepare_apple_health_access = MagicMock(return_value=("user_123", bad_integration, None))

    try:
        res = apple_health_tools.get_apple_health_sleep_tool(config={"configurable": {"user_id": "user_123"}})
        assert res == "Error retrieving sleep data."
        assert "database_query_error_table_users_leak" not in res
    finally:
        apple_health_tools.prepare_apple_health_access = original_prepare


def test_get_apple_health_heart_rate_tool_sanitizes_exception():
    bad_integration = MagicMock()
    bad_integration.get.side_effect = RuntimeError("redis_cluster_down_auth_token_98765")
    original_prepare = apple_health_tools.prepare_apple_health_access
    apple_health_tools.prepare_apple_health_access = MagicMock(return_value=("user_123", bad_integration, None))

    try:
        res = apple_health_tools.get_apple_health_heart_rate_tool(config={"configurable": {"user_id": "user_123"}})
        assert res == "Error retrieving heart rate data."
        assert "redis_cluster_down_auth_token_98765" not in res
    finally:
        apple_health_tools.prepare_apple_health_access = original_prepare


def test_get_apple_health_workouts_tool_sanitizes_exception():
    bad_integration = MagicMock()
    bad_integration.get.side_effect = RuntimeError("unhandled_json_decode_exception_memory_dump")
    original_prepare = apple_health_tools.prepare_apple_health_access
    apple_health_tools.prepare_apple_health_access = MagicMock(return_value=("user_123", bad_integration, None))

    try:
        res = apple_health_tools.get_apple_health_workouts_tool(config={"configurable": {"user_id": "user_123"}})
        assert res == "Error retrieving workout data."
        assert "unhandled_json_decode_exception_memory_dump" not in res
    finally:
        apple_health_tools.prepare_apple_health_access = original_prepare


def test_get_apple_health_summary_tool_sanitizes_exception():
    bad_integration = MagicMock()
    bad_integration.get.side_effect = RuntimeError("summary_aggregation_oom_traceback_frame")
    original_prepare = apple_health_tools.prepare_apple_health_access
    apple_health_tools.prepare_apple_health_access = MagicMock(return_value=("user_123", bad_integration, None))

    try:
        res = apple_health_tools.get_apple_health_summary_tool(config={"configurable": {"user_id": "user_123"}})
        assert res == "Error retrieving health summary."
        assert "summary_aggregation_oom_traceback_frame" not in res
    finally:
        apple_health_tools.prepare_apple_health_access = original_prepare


def test_get_apple_health_data_helper_sanitizes_exception():
    original_get = users_db.get_integration
    users_db.get_integration = MagicMock(side_effect=RuntimeError("firestore_unavailable"))

    try:
        res = apple_health_tools.get_apple_health_data("user_123")
        assert res is None
    finally:
        users_db.get_integration = original_get


def test_prepare_apple_health_access_missing_uid():
    uid, integration, err = apple_health_tools.prepare_apple_health_access({})
    assert err is not None
    assert uid is None
    assert integration is None


def test_all_tools_successful_execution():
    healthy_integration = {
        "health_data": {
            "period_days": 7,
            "steps": {"total": 35000, "average_per_day": 5000, "daily": [{"date": "2026-09-22", "steps": 5000}]},
            "sleep": {"total_sleep_hours": 49.0, "daily": [{"date": "2026-09-22", "sleepHours": 7.0}]},
            "heart_rate": {"average": 68.0, "minimum": 52.0, "maximum": 135.0},
            "workouts": [
                {"type": "Running", "durationMinutes": 30.0, "caloriesBurned": 300, "startDate": 1727000000000}
            ],
            "active_energy": {
                "total": 3500,
                "average_per_day": 500,
                "daily": [{"date": "2026-09-22", "calories": 500}],
            },
        },
        "last_synced": "2026-09-22T20:00:00Z",
    }
    original_prepare = apple_health_tools.prepare_apple_health_access
    apple_health_tools.prepare_apple_health_access = MagicMock(return_value=("user_123", healthy_integration, None))

    try:
        config = {"configurable": {"user_id": "user_123"}}
        steps_res = apple_health_tools.get_apple_health_steps_tool(config=config)
        assert "Apple Health Step Data" in steps_res
        assert "35,000" in steps_res

        sleep_res = apple_health_tools.get_apple_health_sleep_tool(config=config)
        assert "Apple Health Sleep Data" in sleep_res
        assert "49.0 hours" in sleep_res

        hr_res = apple_health_tools.get_apple_health_heart_rate_tool(config=config)
        assert "Apple Health Heart Rate Data" in hr_res
        assert "68 bpm" in hr_res

        workout_res = apple_health_tools.get_apple_health_workouts_tool(config=config)
        assert "Apple Health Workouts" in workout_res
        assert "Running" in workout_res

        summary_res = apple_health_tools.get_apple_health_summary_tool(config=config)
        assert "Apple Health Summary" in summary_res
        assert "STEPS" in summary_res
        assert "SLEEP" in summary_res
        assert "HEART RATE" in summary_res
    finally:
        apple_health_tools.prepare_apple_health_access = original_prepare


if __name__ == "__main__":
    test_get_apple_health_steps_tool_sanitizes_exception()
    test_get_apple_health_steps_tool_sanitizes_prepare_access_exception()
    test_get_apple_health_sleep_tool_sanitizes_exception()
    test_get_apple_health_heart_rate_tool_sanitizes_exception()
    test_get_apple_health_workouts_tool_sanitizes_exception()
    test_get_apple_health_summary_tool_sanitizes_exception()
    test_get_apple_health_data_helper_sanitizes_exception()
    test_prepare_apple_health_access_missing_uid()
    test_all_tools_successful_execution()
    print("All apple health tools sanitization unit tests passed successfully!")
