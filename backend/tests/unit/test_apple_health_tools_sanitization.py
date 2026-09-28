import os
from unittest.mock import patch

import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "0123456789abcdef0123456789abcdef")

from utils.retrieval.tools import apple_health_tools


class CorruptHealthData:
    def __bool__(self):
        return True

    def get(self, *args, **kwargs):
        raise KeyError("KeyError: 'secret_token_key' in /internal/path/to/db")


@pytest.fixture
def mock_corrupt_apple_health():
    corrupt_integration = {"health_data": CorruptHealthData()}
    with patch.object(
        apple_health_tools,
        "prepare_apple_health_access",
        return_value=("uid_123", corrupt_integration, None),
    ):
        yield


def test_get_apple_health_steps_tool_sanitized(mock_corrupt_apple_health, caplog):
    with caplog.at_level("ERROR"):
        res = apple_health_tools.get_apple_health_steps_tool.func()

    assert "secret_token_key" not in res
    assert "/internal/path/to/db" not in res
    assert (
        res
        == "An error occurred while retrieving Apple Health step data. Please try again later."
    )
    assert "secret_token_key" in caplog.text


def test_get_apple_health_sleep_tool_sanitized(mock_corrupt_apple_health, caplog):
    with caplog.at_level("ERROR"):
        res = apple_health_tools.get_apple_health_sleep_tool.func()

    assert "secret_token_key" not in res
    assert "/internal/path/to/db" not in res
    assert (
        res
        == "An error occurred while retrieving Apple Health sleep data. Please try again later."
    )
    assert "secret_token_key" in caplog.text


def test_get_apple_health_heart_rate_tool_sanitized(mock_corrupt_apple_health, caplog):
    with caplog.at_level("ERROR"):
        res = apple_health_tools.get_apple_health_heart_rate_tool.func()

    assert "secret_token_key" not in res
    assert "/internal/path/to/db" not in res
    assert (
        res
        == "An error occurred while retrieving Apple Health heart rate data. Please try again later."
    )
    assert "secret_token_key" in caplog.text


def test_get_apple_health_workouts_tool_sanitized(mock_corrupt_apple_health, caplog):
    with caplog.at_level("ERROR"):
        res = apple_health_tools.get_apple_health_workouts_tool.func()

    assert "secret_token_key" not in res
    assert "/internal/path/to/db" not in res
    assert (
        res
        == "An error occurred while retrieving Apple Health workout data. Please try again later."
    )
    assert "secret_token_key" in caplog.text


def test_get_apple_health_workout_tool_alias_sanitized(
    mock_corrupt_apple_health, caplog
):
    with caplog.at_level("ERROR"):
        res = apple_health_tools.get_apple_health_workout_tool.func()

    assert "secret_token_key" not in res
    assert "/internal/path/to/db" not in res
    assert (
        res
        == "An error occurred while retrieving Apple Health workout data. Please try again later."
    )
    assert "secret_token_key" in caplog.text


def test_get_apple_health_summary_tool_sanitized(mock_corrupt_apple_health, caplog):
    with caplog.at_level("ERROR"):
        res = apple_health_tools.get_apple_health_summary_tool.func()

    assert "secret_token_key" not in res
    assert "/internal/path/to/db" not in res
    assert (
        res
        == "An error occurred while retrieving Apple Health summary data. Please try again later."
    )
    assert "secret_token_key" in caplog.text
