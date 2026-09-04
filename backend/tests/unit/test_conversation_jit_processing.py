"""Hermetic contracts for additive JIT retrieval before capture cutover.

The implementation can land card-first retrieval and stable evidence references
without disabling the currently locked capture-time memory lifecycle.  The
cutover guard below prevents a foundation PR from silently crossing that gate.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found")


def test_foundation_does_not_activate_jit_prompt_before_eval_gate() -> None:
    prompt_source = (BACKEND_DIR / "utils/llm/chat.py").read_text(encoding="utf-8")

    assert "summary_card_only=true" not in prompt_source
    assert "hydrate_transcript_windows=true" not in prompt_source
    assert "get_entity_timeline_tool" not in prompt_source


def test_foundation_does_not_silently_cross_capture_cutover_gate() -> None:
    process = _function(
        _module_tree(BACKEND_DIR / "utils/conversations/process_conversation.py"),
        "process_conversation",
    )
    defaults = {
        argument.arg: default
        for argument, default in zip(
            process.args.args[-len(process.args.defaults) :],
            process.args.defaults,
        )
    }
    assert isinstance(defaults["defer_memory_extraction"], ast.Constant)
    assert defaults["defer_memory_extraction"].value is False
    assert isinstance(defaults["bypass_jit_first_open"], ast.Constant)
    assert defaults["bypass_jit_first_open"].value is False

    finalizer = _function(
        _module_tree(BACKEND_DIR / "utils/conversations/finalizer.py"),
        "finalize_persisted_conversation",
    )
    referenced_names = {node.id for node in ast.walk(finalizer) if isinstance(node, ast.Name)}
    assert "extract_memories" in referenced_names


@pytest.fixture
def conversation_tools_module(monkeypatch: pytest.MonkeyPatch):
    """Load the bounded retrieval formatter with heavy leaves replaced."""

    def install(name: str, module: types.ModuleType) -> None:
        monkeypatch.setitem(sys.modules, name, module)

    def package(name: str) -> types.ModuleType:
        module = types.ModuleType(name)
        module.__path__ = []  # type: ignore[attr-defined]
        install(name, module)
        return module

    for name in (
        "database",
        "models",
        "utils",
        "utils.conversations",
        "utils.retrieval",
        "utils.retrieval.tools",
    ):
        package(name)
    sys.modules["utils.retrieval.tools"].__path__ = [  # type: ignore[attr-defined]
        str(BACKEND_DIR / "utils" / "retrieval" / "tools")
    ]

    for name, attrs in {
        "database.conversations": (),
        "database.notifications": ("get_user_time_zone",),
        "database.users": (),
        "database.vector_db": (),
        "models.other": ("Person",),
        "utils.conversations.factory": ("deserialize_conversation",),
        "utils.conversations.render": ("conversation_to_citation_card", "conversations_to_string"),
        "utils.conversations.mcp_transcript_search": ("build_transcript_match_snippets",),
        "utils.conversations.search": (
            "conversation_matches_date_range",
            "keyword_search_conversation_ids",
            "merge_conversation_search_ids",
            "parse_exact_conversation_reference",
        ),
        "utils.retrieval.chat_scope": (),
    }.items():
        module = types.ModuleType(name)
        for attr in attrs:
            setattr(module, attr, MagicMock())
        install(name, module)

    chat_scope = sys.modules["utils.retrieval.chat_scope"]
    chat_scope.chat_scope_from_config = lambda _configurable: None
    chat_scope.apply_chat_scope_dates = lambda _scope, start_date, end_date: (start_date, end_date, None)

    jit_module_name = "utils.retrieval.tools.conversation_jit"
    jit_source = BACKEND_DIR / "utils/retrieval/tools/conversation_jit.py"
    jit_spec = importlib.util.spec_from_file_location(jit_module_name, jit_source)
    assert jit_spec is not None and jit_spec.loader is not None
    jit_module = importlib.util.module_from_spec(jit_spec)
    install(jit_module_name, jit_module)
    jit_spec.loader.exec_module(jit_module)

    module_name = "utils.retrieval.tools._conversation_tools_jit_test"
    source = BACKEND_DIR / "utils/retrieval/tools/conversation_tools.py"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    install(module_name, module)
    spec.loader.exec_module(module)
    return module


def _jit_module():
    return sys.modules["utils.retrieval.tools.conversation_jit"]


def _validate_message_conversation(value: dict):
    # models/chat.py imports models.feedback for the rating enum. The fixture
    # installs `models` as an empty package, so load the real (dependency-free)
    # feedback module first or that import cannot resolve. It is removed again
    # below: leaving it behind would outlive the `models` stub it hangs off,
    # and a later test installing its own `models` package would inherit a
    # stale submodule it never asked for.
    installed_feedback = "models.feedback" not in sys.modules
    if installed_feedback:
        feedback_spec = importlib.util.spec_from_file_location("models.feedback", BACKEND_DIR / "models/feedback.py")
        assert feedback_spec is not None and feedback_spec.loader is not None
        feedback_module = importlib.util.module_from_spec(feedback_spec)
        sys.modules["models.feedback"] = feedback_module
        feedback_spec.loader.exec_module(feedback_module)

    module_name = "_jit_message_conversation_contract"
    spec = importlib.util.spec_from_file_location(module_name, BACKEND_DIR / "models/chat.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module.MessageConversation.model_validate(value)
    finally:
        sys.modules.pop(module_name, None)
        if installed_feedback:
            sys.modules.pop("models.feedback", None)


def test_retrieval_is_summary_only_until_explicit_evidence_hydration(conversation_tools_module) -> None:
    """The consumer receives stable evidence refs, not transcript bulk by default."""

    conversation = {
        "id": "jit-conversation-001",
        "created_at": "2026-08-23T12:00:00Z",
        "structured": {
            "title": "Release review",
            "overview": "The team reviewed the release checklist.",
            "category": "work",
            "action_items": [{"description": "Publish the checklist"}],
        },
        "transcript_segments": [
            {"id": "segment-1", "start": 0.0, "end": 1.0, "text": "Private transcript evidence."},
            {"id": "segment-2", "start": 1.0, "end": 2.0, "text": "A second evidence line."},
        ],
    }

    summary_references = []
    summary = _jit_module().format_jit_results(
        [conversation],
        evidence_references=summary_references,
    )
    assert "conversation:jit-conversation-001:summary" in summary
    assert "Private transcript evidence." not in summary
    assert [item["kind"] for item in summary_references] == ["conversation_summary"]

    evidence_references = []
    evidence = _jit_module().format_jit_results(
        [conversation],
        hydrate_transcript_windows=True,
        transcript_window_segments=1,
        evidence_references=evidence_references,
    )
    assert "conversation:jit-conversation-001:segment:segment-1" in evidence
    assert "Private transcript evidence." in evidence
    assert "A second evidence line." not in evidence
    assert [item["kind"] for item in evidence_references] == [
        "conversation_summary",
        "conversation_segment",
    ]
    assert evidence == _jit_module().format_jit_results(
        [conversation],
        hydrate_transcript_windows=True,
        transcript_window_segments=1,
    )


def test_jit_cards_project_only_bounded_calendar_backed_participant_names(conversation_tools_module) -> None:
    conversation = _conversation_fixture()
    conversation["external_data"] = {
        "calendar_meeting_context": {
            "calendar_source": "google_calendar",
            "participants": [
                {"name": " Ada   Lovelace ", "email": "ada@example.com"},
                {"name": "ada lovelace", "email": "duplicate@example.com"},
                {"name": "email-only@example.com", "email": "email-only@example.com"},
            ],
        },
        "screen_meeting_context": {"participants": [{"name": "Untrusted OCR Name"}]},
    }
    conversation["calendar_event"] = {
        "attendees": ["Grace Hopper", "Ada Lovelace"],
        "attendee_emails": ["grace@example.com", "ada@example.com"],
    }

    result = _jit_module().format_jit_results([conversation])

    assert "participants: Ada Lovelace | Grace Hopper" in result
    assert "example.com" not in result
    assert "Untrusted OCR Name" not in result


def test_jit_cards_reject_unattributed_calendar_context_and_bound_participants(conversation_tools_module) -> None:
    conversation = _conversation_fixture()
    conversation["external_data"] = {
        "calendar_meeting_context": {
            "participants": [{"name": "Unattributed Name"}],
        }
    }
    conversation["calendar_event"] = {
        "attendees": [f"Participant {index}" for index in range(20)],
    }

    result = _jit_module().format_jit_results([conversation])

    assert "Unattributed Name" not in result
    assert "Participant 11" in result
    assert "Participant 12" not in result


def test_jit_evidence_rejects_unresolvable_conversation_identity(conversation_tools_module) -> None:
    references: list = []
    result = _jit_module().format_jit_results(
        [
            {
                "id": "conversation-" + ("x" * 400),
                "structured": {"title": "t" * 400, "overview": "s" * 1_000},
            }
        ],
        evidence_references=references,
    )

    assert result == "[Bounded JIT result omitted additional evidence records.]"
    assert references == []


def _emitted_evidence_refs(result: str) -> list[str]:
    prefixes = ("summary_evidence_ref: ", "evidence_ref: ")
    return [line.removeprefix(prefix) for line in result.splitlines() for prefix in prefixes if line.startswith(prefix)]


def test_jit_reference_cap_admits_text_and_envelope_atomically(conversation_tools_module, monkeypatch) -> None:
    rows = []
    snippets = []
    for index in range(20):
        row = _conversation_fixture()
        row["id"] = f"conversation-{index}"
        rows.append(row)
        snippets.append(
            {
                "segment_id": f"segment-{index}",
                "start_ms": index * 1000,
                "end_ms": (index + 1) * 1000,
                "text": f"matching transcript {index}",
            }
        )
    monkeypatch.setattr(
        sys.modules["utils.retrieval.tools.conversation_jit"],
        "build_transcript_match_snippets",
        lambda *_args, **_kwargs: snippets[:3],
    )
    references: list = []

    result = _jit_module().format_jit_results(
        rows,
        query="matching",
        hydrate_transcript_windows=True,
        evidence_references=references,
    )

    emitted = _emitted_evidence_refs(result)
    assert len(references) == _jit_module().MAX_CHAT_EVIDENCE_REFERENCES
    assert emitted == [item["id"] for item in references]
    assert "[Bounded JIT result omitted additional evidence records.]" in result


def test_jit_character_cap_admits_text_and_envelope_atomically(conversation_tools_module) -> None:
    rows = []
    for index in range(20):
        row = _conversation_fixture()
        row["id"] = f"conversation-{index}"
        row["structured"]["overview"] = "o" * 600
        row["structured"]["action_items"] = [{"description": "a" * 240} for _ in range(5)]
        rows.append(row)
    references: list = []

    result = _jit_module().format_jit_results(rows, evidence_references=references)

    assert len(result) <= _jit_module().MAX_JIT_RESULT_CHARS
    assert _emitted_evidence_refs(result) == [item["id"] for item in references]
    assert len(references) < len(rows)
    assert "[Bounded JIT result omitted additional evidence records.]" in result


def test_jit_deduplicates_conversation_rows_before_emitting_refs(conversation_tools_module) -> None:
    row = _conversation_fixture()
    references: list = []

    result = _jit_module().format_jit_results([row, dict(row)], evidence_references=references)

    assert len(references) == 1
    assert result.count("summary_evidence_ref:") == 1
    assert "[Bounded JIT result omitted additional evidence records.]" in result


def test_jit_query_snippets_get_unique_fallback_refs(conversation_tools_module) -> None:
    row = _conversation_fixture()
    _jit_module().build_transcript_match_snippets.return_value = [
        {"segment_id": "same", "start_ms": 0, "end_ms": 1000, "text": "first match"},
        {"segment_id": "same-duplicate-2-1", "start_ms": 1000, "end_ms": 2000, "text": "second match"},
        {"segment_id": "same", "start_ms": 2000, "end_ms": 3000, "text": "third match"},
    ]
    references: list = []

    result = _jit_module().format_jit_results(
        [row],
        query="match",
        hydrate_transcript_windows=True,
        max_transcript_snippets=3,
        evidence_references=references,
    )

    emitted = _emitted_evidence_refs(result)
    assert emitted == [item["id"] for item in references]
    assert len(emitted) == len(set(emitted)) == 4


def test_jit_window_segments_disambiguate_duplicate_refs(conversation_tools_module) -> None:
    row = _conversation_fixture()
    row["transcript_segments"] = [
        {"id": "same", "text": "first line"},
        {"id": "same-duplicate-2-1", "text": "second line"},
        {"id": "same", "text": "third line"},
    ]
    references: list = []

    result = _jit_module().format_jit_results(
        [row],
        hydrate_transcript_windows=True,
        transcript_window_segments=3,
        evidence_references=references,
    )

    emitted = _emitted_evidence_refs(result)
    assert emitted == [item["id"] for item in references]
    assert len(emitted) == len(set(emitted)) == 4


def _conversation_fixture() -> dict:
    return {
        "id": "jit-conversation-002",
        "created_at": "2026-08-23T12:00:00Z",
        "structured": {
            "title": "Release review",
            "overview": "The team reviewed the release checklist.",
            "category": "work",
        },
        "transcript_segments": [
            {"id": "segment-1", "start": 0.0, "end": 1.0, "text": "Ship the release."},
            {"id": "segment-2", "start": 1.0, "end": 2.0, "text": "Follow up with QA."},
            {"id": "segment-3", "start": 2.0, "end": 3.0, "text": "A later line outside the requested window."},
        ],
    }


def _tool_config(*, enabled: object, evidence: list | None = None, collected: list | None = None) -> dict:
    return {
        "configurable": {
            "user_id": "jit-user-001",
            "jit_conversation_retrieval_enabled": enabled,
            "evidence_references": evidence if evidence is not None else [],
            "conversations_collected": collected if collected is not None else [],
            "safety_guard": types.SimpleNamespace(),
        }
    }


def _invoke_tool(conversation_tools_module, tool, arguments: dict, *, config: dict) -> str:
    """Keep the hermetic dynamic import on the production config-fallback path."""
    token = conversation_tools_module.agent_config_context.set(config)
    try:
        return tool.invoke(arguments, config=config)
    finally:
        conversation_tools_module.agent_config_context.reset(token)


def test_feature_gate_requires_uid_scoped_request_opt_in(
    conversation_tools_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_jit_module().JIT_CONVERSATION_RETRIEVAL_ENV, "true")

    assert conversation_tools_module.is_jit_conversation_retrieval_enabled({}) is False
    assert conversation_tools_module.is_jit_conversation_retrieval_enabled({"user_id": "jit-user-001"}) is False
    assert (
        conversation_tools_module.is_jit_conversation_retrieval_enabled(
            {
                "user_id": "jit-user-001",
                _jit_module().JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY: True,
            }
        )
        is True
    )
    assert (
        conversation_tools_module.is_jit_conversation_retrieval_enabled(
            {
                "user_id": "jit-user-001",
                _jit_module().JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY: False,
            }
        )
        is False
    )
    assert (
        conversation_tools_module.is_jit_conversation_retrieval_enabled(
            {
                "user_id": "jit-user-001",
                _jit_module().JIT_CONVERSATION_RETRIEVAL_CONFIG_KEY: {"unexpected": "value"},
            }
        )
        is False
    )


def test_feature_gate_never_activates_from_process_environment_alone(
    conversation_tools_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_jit_module().JIT_CONVERSATION_RETRIEVAL_ENV, "true")

    assert conversation_tools_module.is_jit_conversation_retrieval_enabled({"user_id": "jit-user-001"}) is False


def test_gate_off_preserves_legacy_get_tool_path(conversation_tools_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an explicit opt-in, the released formatter and deserializer remain authoritative."""

    monkeypatch.delenv(_jit_module().JIT_CONVERSATION_RETRIEVAL_ENV, raising=False)
    raw = _conversation_fixture()
    conversation_tools_module.conversations_db.get_conversations = MagicMock(return_value=[raw])
    legacy_conversation = types.SimpleNamespace(transcript_segments=[], model_dump=lambda: {"id": raw["id"]})
    conversation_tools_module.deserialize_conversation = MagicMock(return_value=legacy_conversation)
    conversation_tools_module.conversations_to_string = MagicMock(return_value="LEGACY_FORMAT_RESULT")

    config = _tool_config(enabled=False)
    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.get_conversations_tool,
        {"limit": 5000, "include_transcript": False},
        config=config,
    )

    assert result == "LEGACY_FORMAT_RESULT"
    assert conversation_tools_module.conversations_db.get_conversations.call_args.kwargs["limit"] == 5000
    conversation_tools_module.deserialize_conversation.assert_called_once_with(raw)


def test_gate_on_get_clamps_database_read_before_jit_projection(conversation_tools_module) -> None:
    conversation_tools_module.conversations_db.get_conversations = MagicMock(return_value=[])
    config = _tool_config(enabled=True)

    _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.get_conversations_tool,
        {"limit": 5000, "include_transcript": False},
        config=config,
    )

    assert conversation_tools_module.conversations_db.get_conversations.call_args.kwargs["limit"] == 20


def test_gate_on_search_clamps_hydration_ids_before_database_read(conversation_tools_module) -> None:
    conversation_tools_module.parse_exact_conversation_reference.return_value = None
    conversation_tools_module.keyword_search_conversation_ids.return_value = [f"keyword-{index}" for index in range(20)]
    conversation_tools_module.vector_db.query_vectors = MagicMock(
        return_value=[f"vector-{index}" for index in range(20)]
    )
    conversation_tools_module.merge_conversation_search_ids.return_value = [f"result-{index}" for index in range(40)]
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[])
    config = _tool_config(enabled=True)

    _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {"query": "release", "limit": 20, "include_transcript": False},
        config=config,
    )

    hydrated_ids = conversation_tools_module.conversations_db.get_conversations_by_id.call_args.args[1]
    assert hydrated_ids == [f"result-{index}" for index in range(20)]


def test_gate_on_rejects_fifth_summary_search_before_storage_access(conversation_tools_module) -> None:
    conversation_tools_module.parse_exact_conversation_reference.return_value = None
    conversation_tools_module.conversations_db.get_conversations = MagicMock(return_value=[])
    conversation_tools_module.keyword_search_conversation_ids = MagicMock(return_value=[])
    config = _tool_config(enabled=True)

    for _ in range(4):
        result = _invoke_tool(
            conversation_tools_module,
            conversation_tools_module.get_conversations_tool,
            {"include_transcript": False},
            config=config,
        )
        assert result.startswith("No conversations found")

    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {"query": "materially different reformulation", "include_transcript": False},
        config=config,
    )

    assert result == conversation_tools_module._JIT_SEARCH_BUDGET_EXHAUSTED
    assert conversation_tools_module.conversations_db.get_conversations.call_count == 4
    conversation_tools_module.keyword_search_conversation_ids.assert_not_called()


def test_gate_on_transcript_requests_still_consume_shared_summary_search_budget(conversation_tools_module) -> None:
    """Transcript snippets do not turn a candidate search into free exact hydration."""

    conversation_tools_module.parse_exact_conversation_reference.return_value = None
    conversation_tools_module.conversations_db.get_conversations = MagicMock(return_value=[])
    conversation_tools_module.keyword_search_conversation_ids = MagicMock(return_value=[])
    conversation_tools_module.vector_db.query_vectors = MagicMock(return_value=[])
    conversation_tools_module.merge_conversation_search_ids.return_value = []
    config = _tool_config(enabled=True)

    for _ in range(2):
        result = _invoke_tool(
            conversation_tools_module,
            conversation_tools_module.get_conversations_tool,
            {"include_transcript": True, "max_transcript_segments": 2},
            config=config,
        )
        assert result.startswith("No conversations found")

    for _ in range(2):
        result = _invoke_tool(
            conversation_tools_module,
            conversation_tools_module.search_conversations_tool,
            {"query": "release", "include_transcript": True, "max_transcript_segments": 1},
            config=config,
        )
        assert result.startswith("No conversations found")

    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {"query": "another candidate query", "include_transcript": True, "max_transcript_segments": 1},
        config=config,
    )

    assert result == conversation_tools_module._JIT_SEARCH_BUDGET_EXHAUSTED
    assert conversation_tools_module.conversations_db.get_conversations.call_count == 2
    assert conversation_tools_module.keyword_search_conversation_ids.call_count == 2


def test_gate_on_exact_card_hydration_uses_window_and_does_not_consume_search_budget(
    conversation_tools_module,
) -> None:
    raw = _conversation_fixture()
    conversation_tools_module.parse_exact_conversation_reference.return_value = raw["id"]
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[raw])
    snippet_builder = sys.modules["utils.retrieval.tools.conversation_jit"].build_transcript_match_snippets
    config = _tool_config(enabled=True)

    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {
            "query": f"conversation:{raw['id']}",
            "include_transcript": True,
            "max_transcript_segments": 2,
        },
        config=config,
    )

    assert "transcript_window" in result
    assert "conversation:jit-conversation-002:segment:segment-1" in result
    assert "conversation:jit-conversation-002:segment:segment-2" in result
    snippet_builder.assert_not_called()
    assert not hasattr(config["configurable"]["safety_guard"], "_jit_conversation_summary_search_count")


def test_gate_on_exact_hydration_reuses_a_previously_collected_card(conversation_tools_module) -> None:
    """Summary triage may hydrate its selected card without duplicating its citation index."""
    raw = _conversation_fixture()
    conversation_tools_module.conversations_db.get_conversations = MagicMock(return_value=[raw])
    conversation_tools_module.parse_exact_conversation_reference.return_value = raw["id"]
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[raw])
    evidence: list = []
    collected: list = []
    config = _tool_config(enabled=True, evidence=evidence, collected=collected)

    summary = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.get_conversations_tool,
        {"include_transcript": False},
        config=config,
    )
    hydrated = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {
            "query": f"conversation:{raw['id']}",
            "include_transcript": True,
            "max_transcript_segments": 1,
        },
        config=config,
    )

    assert "Conversation card #1" in summary
    assert "Conversation card #2" not in hydrated
    assert "transcript_window" in hydrated
    assert "conversation:jit-conversation-002:segment:segment-1" in hydrated
    assert _jit_module().JIT_TRUNCATION_MARKER not in hydrated
    assert [item["id"] for item in collected] == [raw["id"]]
    assert [item["kind"] for item in evidence] == ["conversation_summary", "conversation_segment"]


def test_gate_off_owner_scoped_card_reference_remains_semantic_search(conversation_tools_module) -> None:
    raw = _conversation_fixture()
    conversation_tools_module.keyword_search_conversation_ids.return_value = [raw["id"]]
    conversation_tools_module.vector_db.query_vectors = MagicMock(return_value=[])
    conversation_tools_module.merge_conversation_search_ids.return_value = [raw["id"]]
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[])
    config = _tool_config(enabled=False)

    _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {"query": f"conversation:{raw['id']}", "include_transcript": False},
        config=config,
    )

    conversation_tools_module.parse_exact_conversation_reference.assert_not_called()
    conversation_tools_module.keyword_search_conversation_ids.assert_called_once()
    conversation_tools_module.vector_db.query_vectors.assert_called_once()


@pytest.mark.parametrize(
    "query",
    [
        "e8c05000-52f0-4a95-951c-ccd715523429",
        "https://h.omi.me/conversations/e8c05000-52f0-4a95-951c-ccd715523429",
    ],
)
def test_gate_off_released_exact_references_still_bypass_semantic_search(conversation_tools_module, query: str) -> None:
    conversation_id = "e8c05000-52f0-4a95-951c-ccd715523429"
    conversation_tools_module.parse_exact_conversation_reference.return_value = conversation_id
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[])
    conversation_tools_module.vector_db.query_vectors = MagicMock(return_value=[])
    config = _tool_config(enabled=False)

    _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {"query": query, "include_transcript": False},
        config=config,
    )

    conversation_tools_module.conversations_db.get_conversations_by_id.assert_called_once_with(
        "jit-user-001", [conversation_id]
    )
    conversation_tools_module.keyword_search_conversation_ids.assert_not_called()
    conversation_tools_module.vector_db.query_vectors.assert_not_called()


def test_gate_on_missing_request_budget_fails_closed_before_database_read(conversation_tools_module) -> None:
    conversation_tools_module.conversations_db.get_conversations = MagicMock(return_value=[])
    config = _tool_config(enabled=True)
    config["configurable"].pop("safety_guard")

    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.get_conversations_tool,
        {"include_transcript": False},
        config=config,
    )

    assert result == conversation_tools_module._JIT_SEARCH_BUDGET_EXHAUSTED
    conversation_tools_module.conversations_db.get_conversations.assert_not_called()


def test_gate_off_preserves_legacy_search_tool_path(conversation_tools_module) -> None:
    raw = _conversation_fixture()
    conversation_tools_module.parse_exact_conversation_reference.return_value = None
    conversation_tools_module.keyword_search_conversation_ids.return_value = [raw["id"]]
    conversation_tools_module.vector_db.query_vectors = MagicMock(return_value=[])
    conversation_tools_module.merge_conversation_search_ids.return_value = [raw["id"]]
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[raw])
    legacy_conversation = types.SimpleNamespace(transcript_segments=[], model_dump=lambda: {"id": raw["id"]})
    conversation_tools_module.deserialize_conversation = MagicMock(return_value=legacy_conversation)
    conversation_tools_module.conversations_to_string = MagicMock(return_value="LEGACY_SEARCH_RESULT")

    config = _tool_config(enabled=False)
    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {"query": "QA", "include_transcript": False},
        config=config,
    )

    assert result == "Found 1 conversations semantically matching 'QA':\n\nLEGACY_SEARCH_RESULT"
    conversation_tools_module.deserialize_conversation.assert_called_once_with(raw)


def test_gate_on_get_tool_returns_bounded_cards_and_callback_evidence(conversation_tools_module) -> None:
    raw = _conversation_fixture()
    conversation_tools_module.conversations_db.get_conversations = MagicMock(return_value=[raw])
    evidence: list = []
    collected: list = []

    config = _tool_config(enabled=True, evidence=evidence, collected=collected)
    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.get_conversations_tool,
        {"include_transcript": True, "max_transcript_segments": 2},
        config=config,
    )

    assert "conversation:jit-conversation-002:summary" in result
    assert "conversation:jit-conversation-002:segment:segment-1" in result
    assert "conversation:jit-conversation-002:segment:segment-2" in result
    assert "segment-3" not in result
    assert [item["kind"] for item in evidence] == [
        "conversation_summary",
        "conversation_segment",
        "conversation_segment",
    ]
    assert collected == [
        {
            "id": "jit-conversation-002",
            "created_at": "2026-08-23T12:00:00+00:00",
            "started_at": None,
            "finished_at": None,
            "structured": {
                "title": "Release review",
                "emoji": "",
                "overview": "The team reviewed the release checklist.",
                "category": "work",
            },
        }
    ]
    validated = _validate_message_conversation(collected[0])
    assert validated.id == "jit-conversation-002"
    assert "transcript_segments" not in collected[0]
    conversation_tools_module.deserialize_conversation.assert_not_called()


def test_gate_on_search_tool_uses_query_snippets_and_stable_evidence_refs(conversation_tools_module) -> None:
    raw = _conversation_fixture()
    conversation_tools_module.parse_exact_conversation_reference.return_value = None
    conversation_tools_module.keyword_search_conversation_ids.return_value = [raw["id"]]
    conversation_tools_module.vector_db.query_vectors = MagicMock(return_value=[])
    conversation_tools_module.merge_conversation_search_ids.return_value = [raw["id"]]
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[raw])
    sys.modules["utils.retrieval.tools.conversation_jit"].build_transcript_match_snippets.return_value = [
        {"segment_id": "segment-2", "start_ms": 1000, "end_ms": 2000, "text": "Follow up with QA."}
    ]
    evidence: list = []

    config = _tool_config(enabled=True, evidence=evidence)
    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {"query": "QA", "max_transcript_segments": 1},
        config=config,
    )

    assert "conversation:jit-conversation-002:summary" in result
    assert "conversation:jit-conversation-002:segment:segment-2" in result
    assert [item["kind"] for item in evidence] == ["conversation_summary", "conversation_segment"]


def test_gate_on_search_honors_one_segment_bound(conversation_tools_module) -> None:
    raw = _conversation_fixture()
    conversation_tools_module.parse_exact_conversation_reference.return_value = None
    conversation_tools_module.keyword_search_conversation_ids.return_value = [raw["id"]]
    conversation_tools_module.vector_db.query_vectors = MagicMock(return_value=[])
    conversation_tools_module.merge_conversation_search_ids.return_value = [raw["id"]]
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[raw])
    snippet_builder = sys.modules["utils.retrieval.tools.conversation_jit"].build_transcript_match_snippets
    snippet_builder.return_value = [{"segment_id": "segment-1", "start_ms": 0, "end_ms": 1000, "text": "QA one"}]

    config = _tool_config(enabled=True)
    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {"query": "QA", "include_transcript": True, "max_transcript_segments": 1},
        config=config,
    )

    assert "segment:segment-1" in result
    assert snippet_builder.call_args.kwargs["context_neighbors"] == 0
    assert snippet_builder.call_args.kwargs["max_snippets"] == 1


def _call_keywords(tree: ast.AST, function_name: str, callee: str) -> dict[str, ast.AST]:
    func = _function(tree, function_name)
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
        if name != callee:
            continue
        return {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
    raise AssertionError(f"call to {callee!r} not found in {function_name!r}")


def _constant_bool(node: ast.AST | None) -> bool | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


def test_force_process_still_defers_first_open_when_rollout_admits() -> None:
    process_source = (BACKEND_DIR / "utils/conversations/process_conversation.py").read_text(encoding="utf-8")
    assert "if not bypass_jit_first_open and not is_reprocess and not discarded:" in process_source
    assert "if not force_process and not is_reprocess and not discarded:" not in process_source

    conversations = _module_tree(BACKEND_DIR / "routers/conversations.py")
    create_kwargs = _call_keywords(conversations, "process_in_progress_conversation", "process_conversation")
    assert _constant_bool(create_kwargs.get("force_process")) is True
    assert "bypass_jit_first_open" not in create_kwargs

    reprocess_kwargs = _call_keywords(conversations, "reprocess_conversation", "process_conversation")
    assert _constant_bool(reprocess_kwargs.get("force_process")) is True
    assert _constant_bool(reprocess_kwargs.get("bypass_jit_first_open")) is True

    finalize_kwargs = _call_keywords(conversations, "finalize_conversation", "request_finalization")
    assert _constant_bool(finalize_kwargs.get("force_process")) is True
    assert "bypass_jit_first_open" not in finalize_kwargs

    worker = _module_tree(BACKEND_DIR / "routers/conversation_finalization.py")
    worker_kwargs = _call_keywords(worker, "run_listen_finalization_job", "finalize_persisted_conversation")
    assert "bypass_jit_first_open" not in worker_kwargs

    finalizer_source = (BACKEND_DIR / "utils/conversations/finalizer.py").read_text(encoding="utf-8")
    assert "bypass_jit_first_open" not in finalizer_source
