"""Tests for people's names in conversation titles (issue #3602).

Conversation titles should reliably contain the correct people's names, Granola-style
("Sarah and John Discuss Q2 Budget"), not just for scheduled calendar meetings. The
structuring prompts used to be told to put participant names in the title only when
CALENDAR MEETING CONTEXT was present. They now also receive an explicit roster of the
people identified in the conversation and are instructed to use those exact names (and
never to invent one, which keeps the names correct).

Covers:
1. identified_participant_names builds an ordered, de-duplicated, clean roster.
2. _build_conversation_context injects the roster (and omits it when there is none).
3. The name-in-title instruction is unconditional (not gated on calendar context).
4. The roster actually reaches the model for both structuring functions.
"""

import contextlib
import importlib.util
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


def _load_module_from_file(module_name, file_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub heavy dependencies so conversation_processing.py imports without external services.
for mod_name in [
    "firebase_admin",
    "firebase_admin.firestore",
    "firebase_admin.auth",
    "firebase_admin.messaging",
    "firebase_admin.credentials",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.cloud.storage",
    "opuslib",
    "sentry_sdk",
    "database._client",
    "database.redis_db",
    "database.auth",
]:
    if mod_name not in sys.modules:
        _stub_module(mod_name)

if not hasattr(sys.modules.get("database", None), "__path__"):
    _stub_package("database")
sys.modules["database.auth"].get_user_name = MagicMock(return_value="Test User")

# Stub langchain core pieces used at import time.
if not hasattr(sys.modules.get("langchain_core", None), "__path__"):
    _stub_package("langchain_core")
langchain_output_parsers = sys.modules.get("langchain_core.output_parsers") or _stub_module(
    "langchain_core.output_parsers"
)
langchain_output_parsers.PydanticOutputParser = MagicMock()
langchain_prompts = sys.modules.get("langchain_core.prompts") or _stub_module("langchain_core.prompts")
langchain_prompts.ChatPromptTemplate = MagicMock()

# Stub utils packages and the LLM client module.
if not hasattr(sys.modules.get("utils", None), "__path__"):
    _stub_package("utils")
if not hasattr(sys.modules.get("utils.llm", None), "__path__"):
    _stub_package("utils.llm")
llm_clients_stub = sys.modules.get("utils.llm.clients") or _stub_module("utils.llm.clients")
llm_clients_stub.get_llm = MagicMock(return_value=MagicMock())
llm_clients_stub.get_llm_gateway_chat_structured = MagicMock(return_value=MagicMock())
llm_clients_stub.parser = MagicMock()

conversation_folder_stub = sys.modules.get("utils.llm.conversation_folder") or _stub_module(
    "utils.llm.conversation_folder"
)
conversation_folder_stub.FolderAssignment = MagicMock()
conversation_folder_stub.assign_conversation_to_folder = MagicMock(return_value=(None, 0.0, "test stub"))
conversation_folder_stub.build_folders_context = MagicMock(return_value="")

# conversation_processing imports these after the origin/main merge; stub them so the
# module under test imports in isolation (they are not exercised by these title tests).
byok_stub = sys.modules.get("utils.byok") or _stub_module("utils.byok")
byok_stub.has_byok_keys = MagicMock(return_value=False)

gateway_client_stub = sys.modules.get("utils.llm.gateway_client") or _stub_module("utils.llm.gateway_client")
gateway_client_stub.invoke_chat_structured_gateway = MagicMock()
gateway_client_stub.record_chat_extraction_gateway_result = MagicMock()
gateway_client_stub.BACKGROUND_CHAT_EXTRACTION_TIMEOUT_SECONDS = 35.0

gateway_obs_stub = sys.modules.get("utils.llm.gateway_observability") or _stub_module("utils.llm.gateway_observability")
gateway_obs_stub.record_gateway_shadow_comparison = MagicMock()

# get_transcript_structure imports usage_tracker at its invocation boundary, so this one is
# needed at call time rather than import time. track_usage is used as `with track_usage(uid,
# Features.CONVERSATION_STRUCTURE):`, so the stub must be a context manager.
usage_tracker_stub = sys.modules.get("utils.llm.usage_tracker") or _stub_module("utils.llm.usage_tracker")
usage_tracker_stub.Features = MagicMock()
usage_tracker_stub.track_usage = MagicMock(side_effect=lambda *args, **kwargs: contextlib.nullcontext())

# Real models (pure pydantic) resolve from the models package directory.
if not hasattr(sys.modules.get("models", None), "__path__"):
    _stub_package("models")
sys.modules["models"].__path__ = [str(BACKEND_DIR / "models")]

conv_proc = _load_module_from_file(
    "utils.llm.conversation_processing",
    BACKEND_DIR / "utils" / "llm" / "conversation_processing.py",
)


def _person(name):
    """A minimal object shaped like models.other.Person for the roster helper."""
    return types.SimpleNamespace(name=name)


_DT = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)


def _run_structuring(fn, patch_context=True, **kwargs):
    """Run a structuring function with the LLM chain mocked.

    With patch_context=False the real _build_conversation_context runs, so the value the
    model is invoked with reflects the actual assembled context (used to prove the roster
    reaches the model).

    Returns {'invoke': <dict passed to chain.invoke>, 'system_text': <joined system text>}.
    """
    mock_response = MagicMock()
    mock_response.events = []
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = mock_response
    mock_chain.__or__ = MagicMock(return_value=mock_chain)
    mock_llm = MagicMock()
    mock_llm.__or__ = MagicMock(return_value=mock_chain)

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(conv_proc, "get_llm", return_value=mock_llm))
        mock_prompt_cls = stack.enter_context(patch.object(conv_proc, "ChatPromptTemplate"))
        if patch_context:
            stack.enter_context(patch.object(conv_proc, "_build_conversation_context", return_value="ctx"))
        mock_prompt = MagicMock()
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)
        mock_prompt_cls.from_messages.return_value = mock_prompt
        fn(**kwargs)
        messages = mock_prompt_cls.from_messages.call_args[0][0]

    system_text = "\n".join(text for _role, text in messages)
    return {"invoke": mock_chain.invoke.call_args[0][0], "system_text": system_text}


# ===========================================================================
# identified_participant_names — pure roster logic
# ===========================================================================


class TestIdentifiedParticipantNames:
    def test_orders_and_keeps_distinct_names(self):
        assert conv_proc.identified_participant_names([_person("Sarah"), _person("John")]) == ["Sarah", "John"]

    def test_de_duplicates_repeated_names(self):
        people = [_person("Sarah"), _person("Sarah"), _person("John")]
        assert conv_proc.identified_participant_names(people) == ["Sarah", "John"]

    def test_skips_blank_and_missing_names(self):
        people = [_person(""), _person("   "), _person(None), _person("Sarah")]
        assert conv_proc.identified_participant_names(people) == ["Sarah"]

    def test_strips_surrounding_whitespace(self):
        assert conv_proc.identified_participant_names([_person("  Sarah  ")]) == ["Sarah"]

    def test_empty_or_none_input_returns_empty_list(self):
        assert conv_proc.identified_participant_names(None) == []
        assert conv_proc.identified_participant_names([]) == []


# ===========================================================================
# _build_conversation_context — roster injection
# ===========================================================================


class TestBuildContextRoster:
    def test_roster_added_before_transcript(self):
        ctx = conv_proc._build_conversation_context("Sarah: hi", None, None, ["Sarah", "John"])
        assert "IDENTIFIED PARTICIPANTS" in ctx
        assert "Sarah, John" in ctx
        # The model should read the authoritative roster before the raw transcript.
        assert ctx.index("IDENTIFIED PARTICIPANTS") < ctx.index("Transcript:")

    def test_no_roster_when_names_absent(self):
        assert "IDENTIFIED PARTICIPANTS" not in conv_proc._build_conversation_context("Sarah: hi", None, None)

    def test_empty_roster_is_omitted(self):
        assert "IDENTIFIED PARTICIPANTS" not in conv_proc._build_conversation_context("Sarah: hi", None, None, [])


# ===========================================================================
# Prompt wording — name-in-title guidance is unconditional, not calendar-gated
# ===========================================================================


class TestTitleNameInstruction:
    def test_transcript_structure_instruction_is_not_calendar_gated(self):
        # The guidance is present even with no calendar context and no roster passed,
        # so the model is always told to use identified names when they exist.
        text = _run_structuring(
            conv_proc.get_transcript_structure,
            transcript="x",
            started_at=_DT,
            language_code="en",
            tz=None,
            uid="u1",
        )["system_text"]
        assert "IDENTIFIED PARTICIPANTS" in text
        assert "Never invent, guess, or assume a name" in text
        assert "most relevant participant name" in text

    def test_reprocess_instruction_includes_name_guidance(self):
        text = _run_structuring(
            conv_proc.get_reprocess_transcript_structure,
            transcript="x",
            started_at=_DT,
            language_code="en",
            tz=None,
            title="",
        )["system_text"]
        assert "IDENTIFIED PARTICIPANTS" in text
        assert "never invent a name" in text


# ===========================================================================
# The roster actually reaches the model
# ===========================================================================


class TestRosterReachesModel:
    def test_transcript_structure_passes_roster_to_model(self):
        ctx = _run_structuring(
            conv_proc.get_transcript_structure,
            patch_context=False,
            transcript="Sarah: hi\n\nUser: hello",
            started_at=_DT,
            language_code="en",
            tz=None,
            uid="u1",
            participant_names=["Sarah", "John"],
        )["invoke"]["conversation_context"]
        assert "IDENTIFIED PARTICIPANTS" in ctx
        assert "Sarah, John" in ctx

    def test_reprocess_passes_roster_to_model(self):
        full_context = _run_structuring(
            conv_proc.get_reprocess_transcript_structure,
            transcript="Sarah: hi",
            started_at=_DT,
            language_code="en",
            tz=None,
            title="",
            participant_names=["Sarah", "John"],
        )["invoke"]["full_context"]
        assert "IDENTIFIED PARTICIPANTS" in full_context
        assert "Sarah, John" in full_context
