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
    # JIT bypass is part of the trigger's mode, never a caller flag.
    assert "bypass_jit_first_open" not in {argument.arg for argument in process.args.args + process.args.kwonlyargs}

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
        module.__path__ = [str(BACKEND_DIR / name.replace('.', '/'))] if name.startswith('utils') or name == 'database' else []  # type: ignore[attr-defined]
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
        "database.auth": ("get_user_name",),
        "database.notifications": ("get_user_time_zone",),
        "database.users": ("get_people_by_ids",),
        "database.vector_db": ("search_transcript_chunks",),
        "models.other": ("Person",),
        "models.transcript_segment": ("TranscriptSegment",),
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

    sys.modules["database.auth"].get_user_name.return_value = "Stephen"
    sys.modules["database.users"].get_people_by_ids.return_value = []
    transcript_module_name = "utils.conversations.transcript_for_llm"
    transcript_source = BACKEND_DIR / "utils/conversations/transcript_for_llm.py"
    transcript_spec = importlib.util.spec_from_file_location(transcript_module_name, transcript_source)
    assert transcript_spec is not None and transcript_spec.loader is not None
    transcript_module = importlib.util.module_from_spec(transcript_spec)
    install(transcript_module_name, transcript_module)
    transcript_spec.loader.exec_module(transcript_module)

    class ChatTranscriptSearch:
        def __init__(self, rows, searched):
            self.rows = rows
            self.searched = searched

        @property
        def conversation_ids(self):
            return list(dict.fromkeys(row['conversation_id'] for row in self.rows))

    transcript_search = sys.modules["utils.conversations.mcp_transcript_search"]
    transcript_search.ChatTranscriptSearch = ChatTranscriptSearch
    transcript_search.chat_transcript_coverage_note = lambda _searched: ""
    transcript_search.chat_transcript_excerpts = lambda _conversations, _search: {}
    transcript_search.merge_chat_conversation_ids = lambda keywords, transcripts, vectors, limit: list(
        dict.fromkeys(keywords + transcripts + vectors)
    )[: limit * 2]
    transcript_search.merge_summary_and_transcript_ids = lambda chunk_ids, summary_ids, limit: list(
        dict.fromkeys(chunk_ids + summary_ids)
    )[:limit]
    transcript_search.search_chat_transcript_chunks = lambda *args, **kwargs: ChatTranscriptSearch([], False)

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


def test_jit_card_uses_turn_timezone_generated_labels_and_action_state(conversation_tools_module) -> None:
    row = _conversation_fixture()
    row['created_at'] = '2026-09-26T07:18:00Z'
    row['started_at'] = '2026-09-26T07:18:00Z'
    row['finished_at'] = '2026-09-26T09:30:00Z'
    row['structured'].update(
        title='Sync with john at ibm',
        overview='John reviewed the IBM rollout.',
        action_items=[
            {'description': 'Ship to AWS', 'completed': True},
            {'description': 'Call Dr. Kim', 'completed': False},
        ],
    )

    result = _jit_module().format_jit_results([row], configurable={'user_timezone': 'Asia/Ho_Chi_Minh'})

    assert 'Sat 26 Sep 2026, 14:18–16:30 Asia/Ho_Chi_Minh (UTC+07:00), 2h 12m' in result
    assert '07:18 UTC' not in result
    assert 'Title (AI-generated summary, not a quote): Sync with john at ibm' in result
    assert 'Overview (AI-generated summary, not a quote): John reviewed the IBM rollout.' in result
    assert 'Action Items (AI-generated summary, not a quote):' in result
    assert '- [done] Ship to AWS' in result
    assert '- [open] Call Dr. Kim' in result
    assert result.count('<untrusted source="conversation">') == 1
    assert result.count('Text inside <untrusted> blocks') == 1


def test_jit_transcript_windows_label_speakers_gate_weak_owner_and_fence_once(conversation_tools_module) -> None:
    row = _conversation_fixture()
    row['transcript_segments'] = [
        {
            'id': 'owner-a',
            'speaker_id': 0,
            'is_user': True,
            'start': 0.0,
            'end': 1.0,
            'text': 'I will send the draft.',
        },
        {
            'id': 'owner-b',
            'speaker_id': 1,
            'is_user': True,
            'start': 1.0,
            'end': 2.0,
            'text': 'I will approve it.',
        },
        {'id': 'unknown', 'start': 2.0, 'end': 3.0, 'text': 'Unattributed words.'},
    ]

    result = _jit_module().format_jit_results(
        [row], hydrate_transcript_windows=True, transcript_window_segments=3, user_name='Stephen'
    )

    assert 'owner identity is UNTRUSTED' in result
    assert 'speaker: Speaker 0' in result
    assert 'speaker: Speaker 1' in result
    assert 'speaker: Unknown speaker' in result
    assert 'Stephen:' not in result
    assert result.count('<untrusted source="transcript">') == 3
    assert result.count('Text inside <untrusted> blocks') == 1
    assert result.count('Transcript times like [+0:12:30]') == 1


def test_jit_transcript_match_uses_owner_and_person_names(conversation_tools_module) -> None:
    row = _conversation_fixture()
    row['transcript_segments'] = [
        {
            'id': 'owner',
            'speaker_id': 0,
            'is_user': True,
            'start': 0.0,
            'end': 1.0,
            'text': 'I found the invoice.',
        },
        {
            'id': 'person',
            'speaker_id': 2,
            'person_id': 'person-1',
            'is_user': False,
            'start': 1.0,
            'end': 2.0,
            'text': 'Alice sent the receipt.',
        },
    ]
    _jit_module().build_transcript_match_snippets.return_value = [
        {'segment_id': 'person', 'start_ms': 1000, 'end_ms': 2000, 'text': 'Alice sent the receipt.'}
    ]

    result = _jit_module().format_jit_results(
        [row],
        query='receipt',
        hydrate_transcript_windows=True,
        user_name='Stephen',
        people_names={'person-1': 'Alice'},
    )

    assert 'speaker: Alice' in result
    assert 'elapsed: +0:00:01–+0:00:02' in result
    assert 'Transcript times like [+0:12:30]' in result
    assert '<untrusted source="transcript">' in result


def test_legacy_transcript_owner_gate_runs_before_segment_truncation(conversation_tools_module) -> None:
    row = _conversation_fixture()
    row['transcript_segments'] = [
        {
            'id': 'owner-one',
            'speaker_id': 0,
            'is_user': True,
            'start': 0.0,
            'end': 1.0,
            'text': 'I will send the draft.',
        },
        {
            'id': 'owner-two',
            'speaker_id': 1,
            'is_user': True,
            'start': 1.0,
            'end': 2.0,
            'text': 'I will approve it.',
        },
    ]
    conversation = types.SimpleNamespace(
        id=row['id'],
        transcript_segments=[dict(segment) for segment in row['transcript_segments']],
        get_person_ids=lambda: set(),
    )
    conversation_tools_module.conversations_db.get_conversations = MagicMock(return_value=[row])
    conversation_tools_module.deserialize_conversation = MagicMock(return_value=conversation)
    conversation_tools_module.conversations_to_string.return_value = '[1 conversations formatted]'

    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.get_conversations_tool,
        {'include_transcript': True, 'max_transcript_segments': 1},
        config=_tool_config(enabled=False),
    )

    rendered_conversation = conversation_tools_module.conversations_to_string.call_args.args[0][0]
    assert result == '[1 conversations formatted]'
    assert len(rendered_conversation.transcript_segments) == 1
    assert rendered_conversation.transcript_segments[0]['is_user'] is False
    assert rendered_conversation.transcript_segments[0]['person_id'] is None
    assert 'Showing 1 of 2 transcript segments' in next(
        iter(conversation_tools_module.conversations_to_string.call_args.kwargs['truncation_notes'].values())
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
    assert "Showing 12 of 20 calendar participant names" in result


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

    assert "more were omitted, not absent" in result
    assert "conversation evidence records" in result
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
    assert _jit_module().JIT_TRUNCATION_MARKER in result


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
    assert _jit_module().JIT_TRUNCATION_MARKER in result


def test_jit_deduplicates_conversation_rows_before_emitting_refs(conversation_tools_module) -> None:
    row = _conversation_fixture()
    references: list = []

    result = _jit_module().format_jit_results([row, dict(row)], evidence_references=references)

    assert len(references) == 1
    assert result.count("summary_evidence_ref:") == 1
    assert _jit_module().JIT_TRUNCATION_MARKER in result


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
            "user_timezone": "UTC",
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


def test_feature_gate_requires_uid_scoped_request_opt_in(conversation_tools_module) -> None:
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


def test_gate_off_preserves_legacy_get_tool_path(conversation_tools_module) -> None:
    """Without an explicit opt-in, the released formatter and deserializer remain authoritative."""

    raw = _conversation_fixture()
    conversation_tools_module.conversations_db.get_conversations = MagicMock(return_value=[raw])
    legacy_conversation = types.SimpleNamespace(
        id=raw["id"], transcript_segments=[], model_dump=lambda: {"id": raw["id"]}
    )
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


def test_locked_rows_are_withheld_and_discarded_rows_stay_filtered_in_the_query(conversation_tools_module) -> None:
    locked = {
        'id': 'locked-1',
        'is_locked': True,
        'structured': {'title': 'private locked title'},
        'transcript_segments': [{'text': 'private locked transcript'}],
    }
    conversation_tools_module.conversations_db.get_conversations = MagicMock(return_value=[locked])
    config = _tool_config(enabled=False)

    get_result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.get_conversations_tool,
        {'include_transcript': True},
        config=config,
    )

    # Discarded rows are filtered before limit/offset so they cannot shrink the visible page.
    assert conversation_tools_module.conversations_db.get_conversations.call_args.kwargs['include_discarded'] is False
    assert 'No conversations found in the requested scope' in get_result
    assert '1 conversations exist here but were not read: locked on the current plan' in get_result
    assert 'private locked' not in get_result
    conversation_tools_module.deserialize_conversation.assert_not_called()


def test_addressable_conversation_results_emit_each_legend_once(conversation_tools_module) -> None:
    from utils.model_text import ELAPSED_LEGEND, UNTRUSTED_LEGEND

    rendered_block = f"{ELAPSED_LEGEND}\n{UNTRUSTED_LEGEND}\nConversation block"
    conversation_tools_module.conversations_to_string.return_value = rendered_block
    conversations = [
        types.SimpleNamespace(id='conversation-a', get_person_ids=lambda: set()),
        types.SimpleNamespace(id='conversation-b', get_person_ids=lambda: set()),
    ]

    result = conversation_tools_module._render_addressable_conversations(
        conversations,
        configurable={'conversations_collected': []},
        use_transcript=True,
        include_timestamps=True,
    )

    assert result.count(ELAPSED_LEGEND) == 1
    assert result.count(UNTRUSTED_LEGEND) == 1
    assert result.count('Conversation block') == 2

    discarded = {
        'id': 'discarded-1',
        'discarded': True,
        'structured': {'title': 'private discarded title'},
        'transcript_segments': [{'text': 'private discarded transcript'}],
    }
    conversation_tools_module.parse_exact_conversation_reference.return_value = None
    conversation_tools_module.keyword_search_conversation_ids = MagicMock(return_value=['discarded-1'])
    conversation_tools_module.vector_db.query_vectors = MagicMock(return_value=[])
    conversation_tools_module.merge_chat_conversation_ids = MagicMock(return_value=['discarded-1'])
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[discarded])

    search_result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {'query': 'planning', 'include_transcript': True},
        config=_tool_config(enabled=False),
    )

    assert 'No conversations found matching query' in search_result
    assert '1 conversations exist here but were not read: discarded' in search_result
    assert 'private discarded' not in search_result
    conversation_tools_module.deserialize_conversation.assert_not_called()


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
    conversation_tools_module.merge_chat_conversation_ids = MagicMock(
        return_value=[f"result-{index}" for index in range(40)]
    )
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


def test_gate_on_transcript_hit_returns_bounded_summary_card_before_hydration(conversation_tools_module) -> None:
    raw = _conversation_fixture()
    raw['transcript_segments'][0]['text'] = 'The private invoice was 47 dollars.'
    conversation_tools_module.parse_exact_conversation_reference.return_value = None
    conversation_tools_module.keyword_search_conversation_ids = MagicMock(return_value=[])
    conversation_tools_module.vector_db.query_vectors = MagicMock(return_value=[])
    conversation_tools_module.vector_db.index = object()
    conversation_tools_module.vector_db.embeddings = MagicMock()
    conversation_tools_module.vector_db.embeddings.embed_query.return_value = [0.5]
    chunk_search = MagicMock(
        return_value=conversation_tools_module.ChatTranscriptSearch(
            [{'conversation_id': raw['id'], 'chunk_index': 0}], True
        )
    )
    conversation_tools_module.search_chat_transcript_chunks = chunk_search
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[raw])
    config = _tool_config(enabled=True)

    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {'query': 'invoice amount', 'include_transcript': False},
        config=config,
    )

    assert raw['id'] in result
    assert '47 dollars' not in result
    assert 'conversation:' + raw['id'] + ':summary' in result
    assert [item['kind'] for item in config['configurable']['evidence_references']] == ['conversation_summary']
    assert chunk_search.call_args.kwargs['index_available'] is True
    assert chunk_search.call_args.kwargs['query_vector'] == [0.5]


def test_gate_on_summary_hit_discloses_unavailable_transcript_index_within_bound(conversation_tools_module) -> None:
    raw = _conversation_fixture()
    conversation_tools_module.parse_exact_conversation_reference.return_value = None
    conversation_tools_module.keyword_search_conversation_ids = MagicMock(return_value=[raw['id']])
    conversation_tools_module.vector_db.query_vectors = MagicMock(return_value=[])
    conversation_tools_module.chat_transcript_coverage_note = lambda _searched: 'Transcript text was not searched.'
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[raw])

    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {'query': 'invoice amount', 'include_transcript': False},
        config=_tool_config(enabled=True),
    )

    assert 'Transcript text was not searched.' in result
    assert raw['id'] in result
    assert len(result) <= _jit_module().MAX_JIT_RESULT_CHARS


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
    conversation_tools_module.merge_chat_conversation_ids = MagicMock(return_value=[])
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
    assert 'transcript segments in this window' in hydrated
    assert [item["id"] for item in collected] == [raw["id"]]
    assert [item["kind"] for item in evidence] == ["conversation_summary", "conversation_segment"]


def test_gate_off_owner_scoped_card_reference_remains_semantic_search(conversation_tools_module) -> None:
    raw = _conversation_fixture()
    conversation_tools_module.keyword_search_conversation_ids.return_value = [raw["id"]]
    conversation_tools_module.vector_db.query_vectors = MagicMock(return_value=[])
    conversation_tools_module.merge_chat_conversation_ids = MagicMock(return_value=[raw["id"]])
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
        "jit-user-001", [conversation_id], include_discarded=True
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
    conversation_tools_module.merge_chat_conversation_ids = MagicMock(return_value=[raw["id"]])
    conversation_tools_module.conversations_db.get_conversations_by_id = MagicMock(return_value=[raw])
    legacy_conversation = types.SimpleNamespace(
        id=raw["id"], transcript_segments=[], model_dump=lambda: {"id": raw["id"]}
    )
    conversation_tools_module.deserialize_conversation = MagicMock(return_value=legacy_conversation)
    conversation_tools_module.conversations_to_string = MagicMock(return_value="LEGACY_SEARCH_RESULT")

    config = _tool_config(enabled=False)
    result = _invoke_tool(
        conversation_tools_module,
        conversation_tools_module.search_conversations_tool,
        {"query": "QA", "include_transcript": False},
        config=config,
    )

    assert result == (
        "1 nearest conversations for 'QA' "
        "(semantic search returns the closest matches even when none is relevant; check before citing)"
        "\n\nLEGACY_SEARCH_RESULT"
    )
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
    conversation_tools_module.merge_chat_conversation_ids = MagicMock(return_value=[raw["id"]])
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
    conversation_tools_module.merge_chat_conversation_ids = MagicMock(return_value=[raw["id"]])
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
    # One extra candidate lets the formatter report whether more snippets matched.
    assert snippet_builder.call_args.kwargs["max_snippets"] == 2


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


def _attribute_name(node: ast.AST | None) -> str | None:
    return node.attr if isinstance(node, ast.Attribute) else None


def test_running_now_still_defers_first_open_when_rollout_admits() -> None:
    """Only triggers whose mode bypasses JIT may run derived work eagerly."""
    from utils.conversations.processing_trigger import PROCESSING_MODES, ProcessingTrigger

    process_source = (BACKEND_DIR / "utils/conversations/process_conversation.py").read_text(encoding="utf-8")
    assert "if not bypass_jit_first_open and not is_reprocess and not discarded:" in process_source
    assert "if not force_process and not is_reprocess and not discarded:" not in process_source

    conversations = _module_tree(BACKEND_DIR / "routers/conversations.py")
    create_kwargs = _call_keywords(conversations, "process_in_progress_conversation", "process_conversation")
    assert _attribute_name(create_kwargs.get("trigger")) == "CLIENT_FINALIZE"

    # The route owns the retry claim; the shared executor owns the processing mode.
    _call_keywords(conversations, "reprocess_conversation", "execute_reprocess")
    reprocess_kwargs = _call_keywords(conversations, "execute_reprocess", "process_conversation")
    assert _attribute_name(reprocess_kwargs.get("trigger")) == "USER_REPROCESS"

    transcription_kwargs = _call_keywords(conversations, "reprocess_conversation_transcription", "process_conversation")
    assert _attribute_name(transcription_kwargs.get("trigger")) == "USER_REPROCESS"

    finalize_kwargs = _call_keywords(conversations, "finalize_conversation", "request_finalization")
    assert _attribute_name(finalize_kwargs.get("trigger")) == "CLIENT_FINALIZE"

    client_finalize = PROCESSING_MODES[ProcessingTrigger.CLIENT_FINALIZE]
    assert client_finalize.run_now and not client_finalize.bypass_jit_first_open
    assert PROCESSING_MODES[ProcessingTrigger.USER_REPROCESS].bypass_jit_first_open

    # Mode lives in one table: no call site may pass a mode flag directly.
    for kwargs in (create_kwargs, reprocess_kwargs, transcription_kwargs, finalize_kwargs):
        assert not {"force_process", "is_reprocess", "bypass_jit_first_open"} & set(kwargs)

    finalizer_source = (BACKEND_DIR / "utils/conversations/finalizer.py").read_text(encoding="utf-8")
    assert "bypass_jit_first_open" not in finalizer_source
