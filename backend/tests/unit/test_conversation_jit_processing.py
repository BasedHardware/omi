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

    for name, attrs in {
        "database.conversations": (),
        "database.notifications": (),
        "database.users": (),
        "database.vector_db": (),
        "models.other": ("Person",),
        "utils.conversations.factory": ("deserialize_conversation",),
        "utils.conversations.render": ("conversations_to_string",),
        "utils.conversations.mcp_transcript_search": ("build_transcript_match_snippets",),
        "utils.conversations.search": (
            "conversation_matches_date_range",
            "keyword_search_conversation_ids",
            "merge_conversation_search_ids",
            "parse_exact_conversation_reference",
        ),
    }.items():
        module = types.ModuleType(name)
        for attr in attrs:
            setattr(module, attr, MagicMock())
        install(name, module)

    module_name = "utils.retrieval.tools._conversation_tools_jit_test"
    source = BACKEND_DIR / "utils/retrieval/tools/conversation_tools.py"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    install(module_name, module)
    spec.loader.exec_module(module)
    return module


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
    summary = conversation_tools_module.format_jit_results(
        [conversation],
        evidence_references=summary_references,
    )
    assert "conversation:jit-conversation-001:summary" in summary
    assert "Private transcript evidence." not in summary
    assert [item["kind"] for item in summary_references] == ["conversation_summary"]

    evidence_references = []
    evidence = conversation_tools_module.format_jit_results(
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
    assert evidence == conversation_tools_module.format_jit_results(
        [conversation],
        hydrate_transcript_windows=True,
        transcript_window_segments=1,
    )
