"""Unit tests for goals suggest/advice/progress null hardening, Wrapped 2025 locked filtering, and BLE firmware padding."""

import contextlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _empty_pkg(name: str) -> ModuleType:
    pkg = ModuleType(name)
    pkg.__path__ = []  # type: ignore[attr-defined]
    return pkg


def _parse_kv(body):
    if not body:
        return {}
    m = re.search(r"<!-- KEY_VALUE_START\s*(.*?)\s*KEY_VALUE_END -->", body, re.DOTALL)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


@pytest.fixture(scope="module")
def modules():
    generated_compute_mod = ModuleType("utils.generated_compute")
    generated_compute_mod.generated_compute_allowed = lambda *a, **kw: True
    generated_compute_mod.generated_compute_scoped = lambda fn: fn

    goals_db_mod = ModuleType("database.goals")
    goals_db_mod.get_goal_by_id = MagicMock()
    goals_db_mod.get_user_goals = MagicMock(return_value=[])
    goals_db_mod.update_goal_progress = MagicMock()

    conv_db_mod = ModuleType("database.conversations")
    conv_db_mod.get_conversations_by_id = MagicMock(return_value=[])
    conv_db_mod.get_conversations = MagicMock(return_value=[])
    conv_db_mod.get_conversations_without_photos = MagicMock(return_value=[])

    chat_db_mod = ModuleType("database.chat")
    chat_db_mod.get_messages = MagicMock(return_value=[])

    client_mod = ModuleType("database._client")
    client_mod.db = MagicMock()

    vector_db_mod = ModuleType("database.vector_db")
    vector_db_mod.query_vectors = MagicMock(return_value=[])

    llm_clients_mod = ModuleType("utils.llm.clients")
    llm_clients_mod.get_llm = MagicMock()

    usage_tracker_mod = ModuleType("utils.llm.usage_tracker")
    usage_tracker_mod.track_usage = lambda *a, **kw: contextlib.nullcontext()
    usage_tracker_mod.Features = SimpleNamespace(GOALS="goals")

    memory_service_mod = ModuleType("utils.memory.memory_service")
    memory_service_mod.MemoryService = MagicMock()

    wrapped_db_mod = ModuleType("database.wrapped")
    wrapped_db_mod.WrappedStatus = SimpleNamespace(DONE="done", ERROR="error")
    wrapped_db_mod.update_wrapped_progress = MagicMock()
    wrapped_db_mod.update_wrapped_status = MagicMock()

    action_items_db_mod = ModuleType("database.action_items")
    action_items_db_mod.get_action_items = MagicMock(return_value=[])

    conv_model_mod = ModuleType("models.conversation")
    conv_model_mod.Conversation = object

    conv_factory_mod = ModuleType("utils.conversations.factory")
    conv_factory_mod.deserialize_conversations = lambda data: data

    notif_mod = ModuleType("utils.notifications")
    notif_mod.send_notification = MagicMock()

    gh_releases_mod = ModuleType("utils.github_releases")
    gh_releases_mod.get_omi_github_releases = MagicMock(return_value=[])
    gh_releases_mod.extract_key_value_pairs = _parse_kv

    fakes = {
        "utils": _empty_pkg("utils"),
        "utils.llm": _empty_pkg("utils.llm"),
        "utils.memory": _empty_pkg("utils.memory"),
        "utils.wrapped": _empty_pkg("utils.wrapped"),
        "utils.conversations": _empty_pkg("utils.conversations"),
        "database": _empty_pkg("database"),
        "models": _empty_pkg("models"),
        "routers": _empty_pkg("routers"),
        "utils.generated_compute": generated_compute_mod,
        "database.goals": goals_db_mod,
        "database.conversations": conv_db_mod,
        "database.chat": chat_db_mod,
        "database._client": client_mod,
        "database.vector_db": vector_db_mod,
        "utils.llm.clients": llm_clients_mod,
        "utils.llm.usage_tracker": usage_tracker_mod,
        "utils.memory.memory_service": memory_service_mod,
        "database.wrapped": wrapped_db_mod,
        "database.action_items": action_items_db_mod,
        "models.conversation": conv_model_mod,
        "utils.conversations.factory": conv_factory_mod,
        "utils.notifications": notif_mod,
        "utils.github_releases": gh_releases_mod,
    }
    with stub_modules(fakes):
        goals_llm = load_module_fresh(
            "utils.llm.goals",
            os.path.join(str(BACKEND_DIR), "utils", "llm", "goals.py"),
        )
        wrapped_2025 = load_module_fresh(
            "utils.wrapped.generate_2025",
            os.path.join(str(BACKEND_DIR), "utils", "wrapped", "generate_2025.py"),
        )
        firmware_router = load_module_fresh(
            "routers.firmware",
            os.path.join(str(BACKEND_DIR), "routers", "firmware.py"),
        )
        yield SimpleNamespace(
            goals_llm=goals_llm,
            wrapped_2025=wrapped_2025,
            firmware_router=firmware_router,
        )


class TestGoalsSuggestionAndNullHardening:
    def test_suggest_goal_returns_default_without_llm_when_all_memories_are_locked(self, modules, monkeypatch):
        goals_llm = modules.goals_llm
        locked_mem = MagicMock()
        locked_mem.dict.return_value = {"content": "Secret locked note", "is_locked": True}
        mock_service = MagicMock()
        mock_service.read.return_value = [locked_mem]
        monkeypatch.setattr(goals_llm, "MemoryService", lambda db_client=None: mock_service)

        mock_llm = MagicMock()
        monkeypatch.setattr(goals_llm, "get_llm", lambda *args, **kwargs: mock_llm)

        suggestion = goals_llm.suggest_goal("uid-locked")
        assert suggestion["suggested_title"] == "Learn something new every day"
        assert suggestion["suggested_target"] == 10
        assert suggestion["suggested_min"] == 0
        assert suggestion["suggested_max"] == 10
        mock_llm.invoke.assert_not_called()

    def test_suggest_goal_coerces_null_numeric_fields_from_llm_json(self, modules, monkeypatch):
        goals_llm = modules.goals_llm
        unlocked_mem = MagicMock()
        unlocked_mem.dict.return_value = {"content": "I enjoy running marathons", "is_locked": False}
        mock_service = MagicMock()
        mock_service.read.return_value = [unlocked_mem]
        monkeypatch.setattr(goals_llm, "MemoryService", lambda db_client=None: mock_service)

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content='{"suggested_title": "Run weekly", "suggested_type": "numeric", "suggested_target": null, "suggested_min": null, "suggested_max": null, "reasoning": null}'
        )
        monkeypatch.setattr(goals_llm, "get_llm", lambda *args, **kwargs: mock_llm)

        suggestion = goals_llm.suggest_goal("uid-1")
        assert suggestion["suggested_title"] == "Run weekly"
        assert suggestion["suggested_target"] == 10.0
        assert suggestion["suggested_min"] == 0.0
        assert suggestion["suggested_max"] == 10.0
        assert suggestion["reasoning"] != ""

    def test_suggest_goal_preserves_valid_fields_when_one_numeric_field_is_non_numeric_string(
        self, modules, monkeypatch
    ):
        goals_llm = modules.goals_llm
        unlocked_mem = MagicMock()
        unlocked_mem.dict.return_value = {"content": "I want to exercise regularly", "is_locked": False}
        mock_service = MagicMock()
        mock_service.read.return_value = [unlocked_mem]
        monkeypatch.setattr(goals_llm, "MemoryService", lambda db_client=None: mock_service)

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content='{"suggested_title": "Exercise 5 times a week", "suggested_type": "numeric", "suggested_target": "five", "suggested_min": 1, "suggested_max": 7, "reasoning": "Consistent workouts build habits"}'
        )
        monkeypatch.setattr(goals_llm, "get_llm", lambda *args, **kwargs: mock_llm)

        suggestion = goals_llm.suggest_goal("uid-non-numeric")
        assert suggestion["suggested_title"] == "Exercise 5 times a week"
        assert suggestion["suggested_type"] == "numeric"
        assert suggestion["suggested_target"] == 10.0
        assert suggestion["suggested_min"] == 1.0
        assert suggestion["suggested_max"] == 7.0
        assert suggestion["reasoning"] == "Consistent workouts build habits"


class TestWrapped2025Hardening:
    def test_compute_conversation_duration_ignores_none_segment_end(self, modules):
        wrapped_2025 = modules.wrapped_2025
        conv = SimpleNamespace(
            transcript_segments=[
                SimpleNamespace(end=None),
                SimpleNamespace(end=145.0),
                SimpleNamespace(end=None),
            ]
        )
        assert wrapped_2025._compute_conversation_duration(conv) == 145.0

    def test_build_conversations_context_and_signature_phrases_skip_locked_conversations(self, modules):
        wrapped_2025 = modules.wrapped_2025
        locked_conv = SimpleNamespace(
            is_locked=True,
            created_at=datetime(2025, 5, 1, 10, 0, tzinfo=timezone.utc),
            structured=SimpleNamespace(title="Private Locked Title", overview="Confidential overview"),
            transcript_segments=[SimpleNamespace(is_user=True, text="let's do this sounds good")],
        )
        unlocked_conv = SimpleNamespace(
            is_locked=False,
            created_at=datetime(2025, 5, 2, 10, 0, tzinfo=timezone.utc),
            structured=SimpleNamespace(title="Public Title", overview="Public overview"),
            transcript_segments=[SimpleNamespace(is_user=True, text="makes sense")],
        )

        ctx = wrapped_2025._build_conversations_context([locked_conv, unlocked_conv])
        assert "Private Locked Title" not in ctx
        assert "Confidential overview" not in ctx
        assert "Public Title" in ctx

        phrases = wrapped_2025._find_signature_phrases([locked_conv, unlocked_conv])
        assert "let's do this" not in phrases
        assert phrases.get("makes sense") == 1


class TestFirmwareVersionPaddingAndValidation:
    def test_parse_firmware_version_strips_null_bytes_and_whitespace(self, modules):
        firmware_router = modules.firmware_router
        assert firmware_router._parse_firmware_version("v2.1.3\x00\x00") == (2, 1, 3)
        assert firmware_router._parse_firmware_version("  v3.0.15\x00 ") == (3, 0, 15)
        assert firmware_router._parse_firmware_version("\x00  \x00") is None

    def test_find_candidate_releases_skips_unparseable_release_version_when_current_is_none(self, modules):
        firmware_router = modules.firmware_router
        releases = [
            {
                "tag_name": "Omi_CV1_v3.0.15",
                "draft": False,
                "prerelease": False,
                "published_at": "2025-10-01T00:00:00Z",
                "body": "<!-- KEY_VALUE_START\nrelease_firmware_version: invalid_ver\nKEY_VALUE_END -->",
            },
            {
                "tag_name": "Omi_CV1_v3.0.14",
                "draft": False,
                "prerelease": False,
                "published_at": "2025-09-01T00:00:00Z",
                "body": "<!-- KEY_VALUE_START\nrelease_firmware_version: v3.0.14\nKEY_VALUE_END -->",
            },
        ]
        candidates = firmware_router._find_candidate_releases(releases, "Omi_CV1", current_firmware_tuple=None)
        assert len(candidates) == 1
        assert candidates[0]["tag_name"] == "Omi_CV1_v3.0.14"
