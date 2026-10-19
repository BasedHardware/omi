"""Tests for turn-local, labelled calendar spans (issue #4643)."""

import asyncio
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class _AutoMockModule(ModuleType):
    """Module stub that returns a MagicMock for any missing attribute."""

    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _register(name):
    mod = sys.modules.get(name)
    if not isinstance(mod, _AutoMockModule):
        mod = _AutoMockModule(name)
        sys.modules[name] = mod
        if "." in name:
            parent_name, attr = name.rsplit(".", 1)
            setattr(_register(parent_name), attr, mod)
    return mod


# Stub the heavy imports calendar_tools pulls at module load.
for _name in [
    "httpx",
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "database",
    "database.users",
    "database.notifications",
    "models",
    "models.calendar_mutation",
    "utils",
    "utils.conversations",
    "utils.executors",
    "utils.http_client",
    "utils.integration_telemetry",
    "utils.log_sanitizer",
    "utils.retrieval",
    "utils.retrieval.tools",
    "utils.retrieval.tools.integration_base",
    "utils.retrieval.tools.google_utils",
]:
    _register(_name)

# Passthrough @tool decorator so the tool stays a plain callable.
sys.modules["langchain_core.tools"].tool = lambda func=None, **kw: (func if func is not None else (lambda f: f))


def _load_module_from_file(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


model_text = _load_module_from_file("utils.model_text", BACKEND_DIR / "utils" / "model_text.py")
_load_module_from_file("utils.user_clock", BACKEND_DIR / "utils" / "user_clock.py")
_load_module_from_file(
    "utils.conversations.datetime_utils",
    BACKEND_DIR / "utils" / "conversations" / "datetime_utils.py",
)
_load_module_from_file(
    "utils.retrieval.tools.calendar_render",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "calendar_render.py",
)

calendar_tools = _load_module_from_file(
    "utils.retrieval.tools.calendar_tools",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "calendar_tools.py",
)

# 22:00 UTC == 15:00 in America/Los_Angeles (PDT, UTC-7 in June).
_UTC_INSTANT = datetime(2026, 6, 30, 22, 0, 0, tzinfo=timezone.utc)
_LA = ZoneInfo("America/Los_Angeles")


def test_calendar_span_is_turn_local_labelled_and_precomputes_duration():
    clock = model_text.DisplayClock.from_name("Asia/Ho_Chi_Minh")
    out = calendar_tools.format_span(
        "2026-09-26T07:18:00Z",
        "2026-09-26T09:30:00Z",
        clock,
    )
    assert out == "Sat 26 Sep 2026, 14:18–16:30 Asia/Ho_Chi_Minh (UTC+07:00), 2h 12m"
