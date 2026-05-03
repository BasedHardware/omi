"""Unit tests for `extract_decisions` (Decisions lens, v0).

Covers:
1. Happy path — LLM returns valid decisions, returned with backend uuids.
2. Malformed JSON — ValueError from parser is swallowed, returns [].
3. All indexes invalid (>20%) — discarded, returns [].
4. Partial invalid (<20%) — invalid indexes dropped, decisions kept.
5. LLM timeout / network error — exception propagates to caller.
6. Empty action_items — decisions can have empty related_action_item_ids.
"""

import os
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# Stub the heavy clients module so the real LLM is never instantiated.
if "utils.llm.clients" not in sys.modules:
    llm_clients_stub = _stub_module("utils.llm.clients")
    llm_clients_stub.llm_medium_experiment = MagicMock()
    llm_clients_stub.llm_mini = MagicMock()
    llm_clients_stub.parser = MagicMock()
    llm_clients_stub.llm_high = MagicMock()


# Make sure backend dir is on sys.path so `models.*` imports cleanly.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from models.conversation import ActionItem, Decision, DecisionStatus, Structured  # noqa: E402
from utils.llm import decisions as decisions_module  # noqa: E402


def _make_structured(n_actions: int) -> Structured:
    items = [ActionItem(description=f"task {i}") for i in range(n_actions)]
    return Structured(title="Test", overview="Test overview", action_items=items)


def _patched_chain(response_or_exc):
    """Build a mock chain whose .invoke returns the given object or raises the given exception."""
    chain = MagicMock()
    if isinstance(response_or_exc, Exception):
        chain.invoke.side_effect = response_or_exc
    else:
        chain.invoke.return_value = response_or_exc
    chain.__or__ = MagicMock(return_value=chain)
    return chain


def _patch_dependencies(chain):
    """Patch llm + parser + prompt classes inside utils.llm.decisions."""
    llm_patch = patch.object(decisions_module, 'llm_medium_experiment')
    parser_patch = patch.object(decisions_module, 'PydanticOutputParser')
    prompt_patch = patch.object(decisions_module, 'ChatPromptTemplate')

    llm_mock = llm_patch.start()
    parser_cls_mock = parser_patch.start()
    prompt_cls_mock = prompt_patch.start()

    llm_mock.bind.return_value = llm_mock
    llm_mock.__or__ = MagicMock(return_value=chain)

    parser_instance = MagicMock()
    parser_instance.get_format_instructions.return_value = "format-instructions"
    parser_cls_mock.return_value = parser_instance

    prompt_instance = MagicMock()
    prompt_instance.__or__ = MagicMock(return_value=chain)
    prompt_cls_mock.from_messages.return_value = prompt_instance

    return [llm_patch, parser_patch, prompt_patch]


def _stop(patches):
    for p in patches:
        p.stop()


# ===========================================================================


def test_happy_path_returns_decisions_with_backend_uuids():
    structured = _make_structured(n_actions=3)
    response = decisions_module.DecisionsExtraction(
        decisions=[
            Decision(id="bogus-id-1", statement="Use Postgres.", related_action_item_ids=[0, 1]),
            Decision(id="bogus-id-2", statement="Ship Friday.", owner_name="Sarah", related_action_item_ids=[2]),
        ]
    )
    chain = _patched_chain(response)
    patches = _patch_dependencies(chain)
    try:
        result = decisions_module.extract_decisions(structured, "transcript text", conversation_id="conv-1")
    finally:
        _stop(patches)

    assert len(result) == 2
    assert result[0].statement == "Use Postgres."
    assert result[0].related_action_item_ids == [0, 1]
    assert result[1].owner_name == "Sarah"
    # Backend always assigns a fresh uuid hex regardless of LLM-provided id.
    assert result[0].id != "bogus-id-1"
    assert result[1].id != "bogus-id-2"
    assert len(result[0].id) == 32  # uuid4 hex length
    chain.invoke.assert_called_once()


def test_malformed_json_returns_empty_list():
    structured = _make_structured(n_actions=2)
    chain = _patched_chain(ValueError("Failed to parse Decisions: invalid JSON"))
    patches = _patch_dependencies(chain)
    try:
        result = decisions_module.extract_decisions(structured, "transcript", conversation_id="conv-2")
    finally:
        _stop(patches)

    assert result == []


def test_all_indexes_invalid_discards_response():
    """When >20% of related_action_item_ids are out of range, return []."""
    structured = _make_structured(n_actions=2)  # valid indexes: 0, 1
    response = decisions_module.DecisionsExtraction(
        decisions=[
            Decision(id="x", statement="Decision A", related_action_item_ids=[5, 6]),
            Decision(id="y", statement="Decision B", related_action_item_ids=[7, 8]),
        ]
    )
    chain = _patched_chain(response)
    patches = _patch_dependencies(chain)
    try:
        result = decisions_module.extract_decisions(structured, "transcript", conversation_id="conv-3")
    finally:
        _stop(patches)

    assert result == []


def test_partial_invalid_drops_invalid_keeps_decisions():
    """When <20% of indexes are invalid, drop just the bad ones and keep the decisions."""
    structured = _make_structured(n_actions=10)  # valid indexes 0..9
    response = decisions_module.DecisionsExtraction(
        decisions=[
            Decision(
                id="z",
                statement="Mixed validity decision",
                # 9 valid, 1 invalid -> 10% invalid (< 20% threshold)
                related_action_item_ids=[0, 1, 2, 3, 4, 5, 6, 7, 8, 99],
            ),
        ]
    )
    chain = _patched_chain(response)
    patches = _patch_dependencies(chain)
    try:
        result = decisions_module.extract_decisions(structured, "transcript", conversation_id="conv-4")
    finally:
        _stop(patches)

    assert len(result) == 1
    assert result[0].related_action_item_ids == [0, 1, 2, 3, 4, 5, 6, 7, 8]
    assert 99 not in result[0].related_action_item_ids


def test_llm_network_error_propagates():
    structured = _make_structured(n_actions=1)

    class _Timeout(Exception):
        pass

    chain = _patched_chain(_Timeout("upstream timeout"))
    patches = _patch_dependencies(chain)
    try:
        with pytest.raises(_Timeout):
            decisions_module.extract_decisions(structured, "transcript", conversation_id="conv-5")
    finally:
        _stop(patches)


def test_empty_action_items_allows_decisions_with_no_links():
    structured = _make_structured(n_actions=0)
    response = decisions_module.DecisionsExtraction(
        decisions=[
            Decision(id="a", statement="A casual decision with no actions", related_action_item_ids=[]),
        ]
    )
    chain = _patched_chain(response)
    patches = _patch_dependencies(chain)
    try:
        result = decisions_module.extract_decisions(structured, "transcript", conversation_id="conv-6")
    finally:
        _stop(patches)

    assert len(result) == 1
    assert result[0].related_action_item_ids == []
    assert result[0].status == DecisionStatus.open
