import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock, patch

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
]:
    _register(_name)

# Passthrough @tool decorator so the tool stays a plain callable.
sys.modules["langchain_core.tools"].tool = lambda func=None, **kw: (func if func is not None else (lambda f: f))
sys.modules["langchain_core.runnables"].RunnableConfig = dict


def _load_module_from_file(module_name: str, file_path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# Load integration_base first
_load_module_from_file(
    "utils.retrieval.tools.integration_base",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "integration_base.py",
)

apple_health_tools = _load_module_from_file(
    "utils.retrieval.tools.apple_health_tools",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "apple_health_tools.py",
)


def test_prepare_apple_health_access_sanitizes_connection_error():
    users_db = sys.modules["database.users"]
    users_db.get_integration = MagicMock(side_effect=RuntimeError("internal firestore credentials leak at /etc/secret"))

    config = {"configurable": {"user_id": "test_user_123"}}
    uid, integration, err = apple_health_tools.prepare_apple_health_access(config)

    assert uid == "test_user_123"
    assert integration is None
    assert err == "Error checking Apple Health connection."
    assert "internal firestore credentials leak" not in err


def test_get_apple_health_steps_tool_sanitizes_exceptions():
    config = {"configurable": {"user_id": "test_user_123"}}
    with patch.object(apple_health_tools, "prepare_apple_health_access", side_effect=RuntimeError("sensitive_db_stacktrace")):
        result = apple_health_tools.get_apple_health_steps_tool(config=config)
        assert result == "Error retrieving step data."
        assert "sensitive_db_stacktrace" not in result


def test_get_apple_health_sleep_tool_sanitizes_exceptions():
    config = {"configurable": {"user_id": "test_user_123"}}
    with patch.object(apple_health_tools, "prepare_apple_health_access", side_effect=RuntimeError("sensitive_token_leak")):
        result = apple_health_tools.get_apple_health_sleep_tool(config=config)
        assert result == "Error retrieving sleep data."
        assert "sensitive_token_leak" not in result


def test_get_apple_health_heart_rate_tool_sanitizes_exceptions():
    config = {"configurable": {"user_id": "test_user_123"}}
    with patch.object(apple_health_tools, "prepare_apple_health_access", side_effect=RuntimeError("private_key_leak")):
        result = apple_health_tools.get_apple_health_heart_rate_tool(config=config)
        assert result == "Error retrieving heart rate data."
        assert "private_key_leak" not in result


def test_get_apple_health_workouts_tool_sanitizes_exceptions():
    config = {"configurable": {"user_id": "test_user_123"}}
    with patch.object(apple_health_tools, "prepare_apple_health_access", side_effect=RuntimeError("sql_injection_path")):
        result = apple_health_tools.get_apple_health_workouts_tool(config=config)
        assert result == "Error retrieving workout data."
        assert "sql_injection_path" not in result


def test_get_apple_health_summary_tool_sanitizes_exceptions():
    config = {"configurable": {"user_id": "test_user_123"}}
    with patch.object(apple_health_tools, "prepare_apple_health_access", side_effect=RuntimeError("database_error_path")):
        result = apple_health_tools.get_apple_health_summary_tool(config=config)
        assert result == "Error retrieving health summary."
        assert "database_error_path" not in result


def test_internal_processing_exception_is_sanitized():
    config = {"configurable": {"user_id": "test_user_123"}}
    class ExplodingDict(dict):
        def get(self, key, default=None):
            if key == "steps":
                raise RuntimeError("database payload corrupted at memory offset 0xdeadbeef")
            return super().get(key, default)

    malformed_integration = {
        "connected": True,
        "health_data": ExplodingDict(),
    }
    with patch.object(apple_health_tools, "prepare_apple_health_access", return_value=("test_user_123", malformed_integration, None)):
        result = apple_health_tools.get_apple_health_steps_tool(config=config)
        assert result == "Error retrieving step data."
        assert "0xdeadbeef" not in result


if __name__ == "__main__":
    test_prepare_apple_health_access_sanitizes_connection_error()
    test_get_apple_health_steps_tool_sanitizes_exceptions()
    test_get_apple_health_sleep_tool_sanitizes_exceptions()
    test_get_apple_health_heart_rate_tool_sanitizes_exceptions()
    test_get_apple_health_workouts_tool_sanitizes_exceptions()
    test_get_apple_health_summary_tool_sanitizes_exceptions()
    test_internal_processing_exception_is_sanitized()
    print("All Apple Health sanitization unit tests passed successfully!")

