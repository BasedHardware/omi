"""Rejected-but-well-formed folder-assignment completions must be salvaged, not discarded.

Prod pusher, 2026-10-21 (Loop S feed, ~x59-76 per 30 minutes at the peak):

    ERROR:utils.llm.conversation_folder:Error assigning conversation to folder:
    Invalid json output: {"folder_id": "4801c997-...", "confidence": 0.72,
    "reasoning": "Despite music-f...

The logged payload is itself well-formed JSON. The strict
``PydanticOutputParser`` refuses a completion whenever the model wraps the JSON
object in anything non-``json.loads``-able — a lead-in sentence ("Here is the
assignment:"), prose around the object, or a truncated tail behind prose — and
the whole completion is discarded. Each refusal burned one paid LLM call per
conversation, filed nothing, and logged an ERROR whose sample looked like a
parser bug. ``assign_conversation_to_folder`` now salvages the completion text
out of the parser's exception, re-validates it against the same
``FolderAssignment`` schema the parser enforces, and only falls back when the
completion genuinely carries no usable assignment.

Failure-Class: FC-out-of-vocabulary-model-token-discards-extraction — a
provider completion is parsed strictly; when parse wrapper damage (prose,
fencing, truncation) raises, the parser fails the entire response and every
well-formed field the model produced — the folder_id, the confidence, the
reasoning — is lost with it, one paid call and one conversation filing at a
time. The salvage path validates recovered payloads against the same production
schema (strict where it is load-bearing: an out-of-range confidence still
fails) and keeps the typed fallback for genuinely unusable completions. The
regression tests replay real prod-shaped completions through the production
parser seam (real ``PydanticOutputParser``, real chain coercion) rather than
mocking the parser.
"""

import logging
import os
from typing import List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnableLambda

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import utils.llm.clients as _clients  # noqa: E402

# conversation_folder imports get_llm from utils.llm.clients at module scope.
# The real get_llm builds provider clients; stub it BEFORE importing the module
# under test. utils/llm/__init__.py is empty, so the package imports cleanly.
_clients.get_llm = MagicMock(return_value=MagicMock())

import utils.llm.conversation_folder as conv_folder  # noqa: E402
from utils.llm.conversation_folder import (  # noqa: E402
    FolderAssignment,
    assign_conversation_to_folder,
)

FOLDERS: List[dict] = [
    {"id": "w", "name": "Work", "description": "Work stuff"},
    {"id": "p", "name": "Personal", "description": "Personal stuff"},
    {"id": "def", "name": "Other", "is_default": True},
]


class _ScriptedLLM(RunnableLambda):
    """Runnable that stands in for the chat model inside a real chain."""

    def __init__(self, completion: str):
        super().__init__(lambda *_args, **_kwargs: completion)


def _run_with_completion(completion: str) -> Tuple[Optional[str], float, str]:
    """Drive the REAL prompt -> model -> parser chain with a scripted completion."""
    with patch.object(conv_folder, "get_llm", return_value=_ScriptedLLM(completion)):
        return assign_conversation_to_folder(
            "Quarterly budget",
            "Talked through next quarter spend",
            "finance",
            FOLDERS,
            category_folder_id="w",
        )


def _refusal(completion: str) -> OutputParserException:
    """Produce the parser's exact exception for a completion, unmodified."""
    parser = PydanticOutputParser(pydantic_object=FolderAssignment)
    with pytest.raises(OutputParserException) as exc_info:
        parser.parse(completion)
    return exc_info.value


# ---------------------------------------------------------------------------
# The production parser seam: real refusal shapes and their salvage
# ---------------------------------------------------------------------------


def test_prod_shape_lead_in_prose_is_parser_refused_and_salvaged():
    # The prod sample shape: a prose lead-in, then a well-formed assignment.
    completion = (
        'Here is the assignment:\n{"folder_id": "w", "confidence": 0.72, "reasoning": "Mainly about a concept."}'
    )
    exc = _refusal(completion)
    salvaged = conv_folder._salvage_folder_assignment(exc)
    assert salvaged == FolderAssignment(folder_id="w", confidence=0.72, reasoning="Mainly about a concept.")


def test_prod_sensor_sample_prose_plus_truncation_salvages_with_partial_json():
    # The Loop S sample line cuts mid-string after a prose lead-in — the shape
    # the strict parser refuses outright (langchain auto-repairs bare
    # truncation, but not truncation behind prose).
    raw = 'Sure thing! {"folder_id": "4801c997-3184-41e0-9378-18e6cbe041af", "confidence": 0.72, "reasoning": "Despite music-f'
    exc = _refusal(raw)
    salvaged = conv_folder._salvage_folder_assignment(exc)
    assert salvaged is not None
    assert salvaged.folder_id == "4801c997-3184-41e0-9378-18e6cbe041af"
    assert salvaged.confidence == 0.72


def test_truncated_span_repair_recovers_completed_fields():
    # Unit level: the pinned parser auto-repairs bare truncation, so the
    # repair branch is exercised through the candidate-payload helper.
    payload = conv_folder._salvage_candidate_payloads('{"folder_id": "w", "confidence": 0.9, "reasoning": "Main')
    assert payload == {"folder_id": "w", "confidence": 0.9, "reasoning": "Main"}


def test_salvage_returns_none_for_completion_without_any_json():
    exc = _refusal("I could not decide which folder fits this conversation.")
    assert conv_folder._salvage_folder_assignment(exc) is None


def test_salvage_rejects_payload_failing_schema_validation():
    # Strictness stays load-bearing: out-of-range confidence must not salvage.
    exc = _refusal('Sure: {"folder_id": "w", "confidence": 1.5}')
    assert conv_folder._salvage_folder_assignment(exc) is None


def test_salvage_rejects_negative_confidence_payload():
    exc = _refusal('{"folder_id": "w", "confidence": -0.1}')
    assert conv_folder._salvage_folder_assignment(exc) is None


def test_salvage_rejects_non_object_payload():
    exc = _refusal('["folder_id", "w"]')
    assert conv_folder._salvage_folder_assignment(exc) is None


def test_salvage_reads_completion_from_llm_output_attribute():
    # The parser carries the full completion in llm_output.
    completion = 'Prefix text {"folder_id": "w", "confidence": 0.8}'
    exc = _refusal(completion)
    assert exc.llm_output == completion
    assert conv_folder._salvage_folder_assignment(exc) is not None


def test_salvage_falls_back_to_message_text_without_llm_output():
    # A wrapped/refactored exception that only stringifies still salvages.
    completion = 'Prefix text {"folder_id": "w", "confidence": 0.8}'
    stripped = OutputParserException("Invalid json output: " + completion)
    assert getattr(stripped, "llm_output", None) is None
    assert conv_folder._salvage_folder_assignment(stripped) is not None


def test_salvage_survives_non_parser_exception_types():
    # The salvage path is driven by the exception's carried text, not its type.
    class _OpaqueError(Exception):
        pass

    assert conv_folder._salvage_folder_assignment(_OpaqueError('meta {"folder_id": "p"}')) == FolderAssignment(
        folder_id="p"
    )


def test_salvage_ignores_whitespace_llm_output_and_uses_message():
    exc = OutputParserException('{"folder_id": "w"}', llm_output="   ")
    assert conv_folder._salvage_folder_assignment(exc) == FolderAssignment(folder_id="w")


# ---------------------------------------------------------------------------
# Assignment-from-payload: the schema is applied exactly as the parser would
# ---------------------------------------------------------------------------


def test_assignment_from_salvaged_payload_requires_mapping():
    assert conv_folder._assignment_from_salvaged_payload(None) is None
    assert conv_folder._assignment_from_salvaged_payload([1, 2]) is None
    assert conv_folder._assignment_from_salvaged_payload("folder_id") is None


def test_assignment_from_salvaged_payload_applies_schema_defaults():
    assert conv_folder._assignment_from_salvaged_payload({"folder_id": "w"}) == FolderAssignment(folder_id="w")


def test_assignment_from_salvaged_payload_coerces_string_confidence():
    # The parser's own model_validate coerces "0.72" to float; same here.
    assert conv_folder._assignment_from_salvaged_payload({"folder_id": "w", "confidence": "0.72"}) == (
        FolderAssignment(folder_id="w", confidence=0.72)
    )


def test_assignment_from_salvaged_payload_coerces_bool_confidence():
    # bool is an int in Python; pydantic's float coercion accepts True as 1.0.
    assert conv_folder._assignment_from_salvaged_payload({"folder_id": "w", "confidence": True}) == (
        FolderAssignment(folder_id="w", confidence=1.0)
    )


def test_assignment_from_salvaged_payload_accepts_boundary_confidence():
    assert conv_folder._assignment_from_salvaged_payload({"folder_id": "w", "confidence": 0}) == (
        FolderAssignment(folder_id="w", confidence=0.0)
    )
    assert conv_folder._assignment_from_salvaged_payload({"folder_id": "w", "confidence": 1}) == (
        FolderAssignment(folder_id="w", confidence=1.0)
    )


def test_assignment_from_salvaged_payload_rejects_out_of_range_confidence():
    for bad in (1.5, -0.1, "high", None):
        assert conv_folder._assignment_from_salvaged_payload({"folder_id": "w", "confidence": bad}) is None


def test_assignment_from_salvaged_payload_rejects_non_string_folder_id():
    assert conv_folder._assignment_from_salvaged_payload({"folder_id": 123}) is None
    assert conv_folder._assignment_from_salvaged_payload({"folder_id": None}) is None


def test_assignment_from_salvaged_payload_requires_folder_id():
    assert conv_folder._assignment_from_salvaged_payload({}) is None
    assert conv_folder._assignment_from_salvaged_payload({"confidence": 0.9}) is None


def test_assignment_from_salvaged_payload_drops_unknown_keys():
    assert conv_folder._assignment_from_salvaged_payload({"folder_id": "w", "zzz": 1}) == FolderAssignment(
        folder_id="w"
    )


def test_assignment_from_salvaged_payload_rejects_nested_assignment_object():
    assert conv_folder._assignment_from_salvaged_payload({"assignment": {"folder_id": "w"}}) is None


def test_salvaged_assignment_missing_confidence_uses_schema_default():
    salvaged = conv_folder._salvage_folder_assignment(_refusal('Answer: {"folder_id": "w"}'))
    assert salvaged == FolderAssignment(folder_id="w", confidence=0.5, reasoning="")


# ---------------------------------------------------------------------------
# Span extraction and decode candidate ordering
# ---------------------------------------------------------------------------


def test_salvage_raw_completion_prefers_llm_output_attribute():
    exc = OutputParserException("boom", llm_output='{"folder_id": "w"}')
    assert conv_folder._salvage_raw_completion(exc) == '{"folder_id": "w"}'


def test_salvage_raw_completion_falls_back_to_message_text():
    assert conv_folder._salvage_raw_completion(ValueError('x {"folder_id": "w"}')) == 'x {"folder_id": "w"}'


def test_top_level_spans_skip_braces_inside_strings():
    spans = conv_folder._top_level_json_spans('{"a": "}{"}')
    assert spans == ['{"a": "}{"}']


def test_top_level_spans_capture_each_object():
    spans = conv_folder._top_level_json_spans('{"a": 1} {"folder_id": "w"}')
    assert spans == ['{"a": 1}', '{"folder_id": "w"}']


def test_top_level_spans_keep_unterminated_tail():
    spans = conv_folder._top_level_json_spans('{"folder_id": "w", "reasoning": "abc')
    assert spans == ['{"folder_id": "w", "reasoning": "abc']


def test_top_level_spans_scan_prose_without_json():
    assert conv_folder._top_level_json_spans("no braces at all") == []


def test_salvage_candidate_payloads_prefers_brace_span():
    payload = conv_folder._salvage_candidate_payloads('lead {"folder_id": "w", "n": 1} tail')
    assert payload == {"folder_id": "w", "n": 1}


def test_salvage_candidate_payloads_uses_raw_text_when_no_braces():
    payload = conv_folder._salvage_candidate_payloads('[1, 2, 3]')
    assert payload == [1, 2, 3]


def test_salvage_candidate_payloads_raises_last_decode_error_when_nothing_decodes():
    with pytest.raises(Exception):
        conv_folder._salvage_candidate_payloads("still not json")


def test_best_assignment_skips_non_matching_first_object():
    # A greedy first-span decode returns the FIRST object; the assignment in
    # the second span must still win through the schema-checked candidate list.
    salvaged = conv_folder._salvage_folder_assignment(Exception('{"a": 1} {"folder_id": "w", "confidence": 0.9}'))
    assert salvaged == FolderAssignment(folder_id="w", confidence=0.9)


def test_best_assignment_repairs_from_later_brace_after_prose_brace():
    salvaged = conv_folder._salvage_folder_assignment(Exception('use {curly. {"folder_id": "w"}'))
    assert salvaged == FolderAssignment(folder_id="w")


def test_best_assignment_recovers_truncated_reasoning_with_quoted_brace():
    salvaged = conv_folder._salvage_folder_assignment(
        Exception('{"folder_id": "w", "reasoning": "uses } char and more')
    )
    assert salvaged is not None
    assert salvaged.folder_id == "w"
    assert "uses } char" in salvaged.reasoning


def test_best_assignment_handles_nested_object_payload():
    salvaged = conv_folder._salvage_folder_assignment(Exception('prefix {"folder_id": "w", "meta": {"k": 1}}'))
    assert salvaged == FolderAssignment(folder_id="w")


def test_best_assignment_none_when_payloads_are_all_invalid():
    for completion in (
        "nothing here",
        '{"folder_id": 123}',
        '{"folder_id": "w", "confidence": "high"}',
        "[1, 2]",
    ):
        assert conv_folder._salvage_folder_assignment(Exception(completion)) is None


# ---------------------------------------------------------------------------
# End-to-end: the real chain through assign_conversation_to_folder
# ---------------------------------------------------------------------------


def test_end_to_end_wrapped_json_assignment_is_filed_not_dropped(caplog):
    completion = 'Here is the assignment:\n{"folder_id": "w", "confidence": 0.72, "reasoning": "Budget talk."}'
    with caplog.at_level(logging.WARNING, logger="utils.llm.conversation_folder"):
        folder_id, confidence, reasoning = _run_with_completion(completion)
    assert folder_id == "w"
    assert confidence == 0.72
    assert reasoning == "Budget talk."
    assert any("Recovered folder assignment" in r.message for r in caplog.records)
    assert not any("Error assigning conversation to folder" in r.message for r in caplog.records)


def test_end_to_end_truncated_completion_keeps_recovered_fields():
    completion = 'Sure!\n{"folder_id": "w", "confidence": 0.9, "reasoning": "Main'
    folder_id, confidence, reasoning = _run_with_completion(completion)
    assert folder_id == "w"
    assert confidence == 0.9
    # The salvaged reasoning string is whatever survived the truncation.
    assert reasoning.startswith("Main")


def test_end_to_end_unusable_json_falls_back_to_category_folder(caplog):
    with caplog.at_level(logging.ERROR, logger="utils.llm.conversation_folder"):
        folder_id, confidence, reasoning = _run_with_completion("No JSON here at all.")
    assert folder_id == "w"  # category folder fallback, unchanged typed path
    assert confidence == 0.0
    assert reasoning.startswith("Error:")
    assert any("Error assigning conversation to folder" in r.message for r in caplog.records)


def test_end_to_end_salvage_respects_low_confidence_fallback():
    # Salvage must not become an acceptance bypass: a recovered low-confidence
    # assignment still flows through validate_folder_assignment's fallback.
    completion = 'Sure!\n{"folder_id": "w", "confidence": 0.3, "reasoning": "Guessing."}'
    folder_id, confidence, _ = _run_with_completion(completion)
    assert folder_id == "w"  # category folder, not the model's raw guess slot
    assert confidence == 0.3


def test_end_to_end_salvaged_valid_folder_without_category_folder():
    completion = 'Assignment:\n{"folder_id": "p", "confidence": 0.95, "reasoning": "Personal."}'
    with patch.object(conv_folder, "get_llm", return_value=_ScriptedLLM(completion)):
        folder_id, confidence, reasoning = assign_conversation_to_folder(
            "Family trip", "Trip planning", "personal", FOLDERS, category_folder_id=None
        )
    assert (folder_id, confidence, reasoning) == ("p", 0.95, "Personal.")


def test_end_to_end_invalid_folder_id_in_salvaged_payload_falls_back():
    # A salvaged payload naming a folder the user does not have must still go
    # through validate_folder_assignment's invalid-id fallback, never be filed.
    completion = 'Here:\n{"folder_id": "nonexistent", "confidence": 0.99, "reasoning": "x"}'
    folder_id, confidence, _ = _run_with_completion(completion)
    assert folder_id == "w"  # category-aligned fallback
    assert confidence == 0.3


def test_end_to_end_empty_folders_short_circuit_unchanged():
    assert assign_conversation_to_folder("t", "o", "finance", [], category_folder_id=None) == (
        None,
        0.0,
        "No folders available",
    )


def test_end_to_end_no_default_folder_falls_back_to_unfiled():
    # Users without a default folder: an unusable completion stays unfiled.
    folders = [{"id": "w", "name": "Work"}]
    with patch.object(conv_folder, "get_llm", return_value=_ScriptedLLM("not json")):
        folder_id, confidence, _ = assign_conversation_to_folder("t", "o", "other", folders, category_folder_id=None)
    assert folder_id is None
    assert confidence == 0.0


def test_end_to_end_salvage_log_is_warning_not_error(caplog):
    completion = 'Answer:\n{"folder_id": "w", "confidence": 0.9, "reasoning": "ok"}'
    with caplog.at_level(logging.INFO, logger="utils.llm.conversation_folder"):
        _run_with_completion(completion)
    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "Recovered folder assignment" in r.message]
    assert errors == []
    assert warnings


# ---------------------------------------------------------------------------
# Additional verified completion shapes (each replays through the real parser
# or the real chain, matching a prod-observed wrapper-damage family)
# ---------------------------------------------------------------------------


def test_fenced_json_with_prose_inside_the_fence_salvages():
    completion = '```json\nI choose Work.\n{"folder_id": "w", "confidence": 0.9}\n```'
    exc = _refusal(completion)
    salvaged = conv_folder._salvage_folder_assignment(exc)
    assert salvaged == FolderAssignment(folder_id="w", confidence=0.9)


def test_pretty_printed_json_behind_prose_salvages():
    completion = 'Here you go:\n{\n  "folder_id": "w",\n  "confidence": 0.88,\n  "reasoning": "Budget."\n}'
    exc = _refusal(completion)
    salvaged = conv_folder._salvage_folder_assignment(exc)
    assert salvaged == FolderAssignment(folder_id="w", confidence=0.88, reasoning="Budget.")


def test_single_quoted_python_dict_completion_stays_unsalvaged():
    # Python-dict syntax is not JSON: no span decodes, the typed fallback keeps.
    exc = _refusal("{'folder_id': 'w', 'confidence': 0.9}")
    assert conv_folder._salvage_folder_assignment(exc) is None


def test_json_array_of_assignments_salvages_first_schema_match():
    # The model listed candidates; the array is not an assignment, its spans are.
    exc = _refusal('[{"folder_id": "w", "confidence": 0.9}, {"folder_id": "p"}]')
    salvaged = conv_folder._salvage_folder_assignment(exc)
    assert salvaged == FolderAssignment(folder_id="w", confidence=0.9)


def test_non_string_reasoning_payload_stays_unsalvaged():
    exc = _refusal('prose {"folder_id": "w", "reasoning": 42}')
    assert conv_folder._salvage_folder_assignment(exc) is None


def test_duplicate_keys_decode_last_wins():
    exc = _refusal('x {"folder_id": "p", "folder_id": "w", "confidence": 0.9}')
    salvaged = conv_folder._salvage_folder_assignment(exc)
    assert salvaged == FolderAssignment(folder_id="w", confidence=0.9)


def test_unicode_escapes_decode_behind_prose():
    exc = _refusal('ans {"folder_id": "w", "reasoning": "caf\\u00e9 \\u00e9tude"}')
    salvaged = conv_folder._salvage_folder_assignment(exc)
    assert salvaged == FolderAssignment(folder_id="w", reasoning="café étude")


def test_end_to_end_fenced_prose_completion_is_filed():
    completion = '```json\nI choose Work.\n{"folder_id": "w", "confidence": 0.9}\n```'
    folder_id, confidence, _ = _run_with_completion(completion)
    assert folder_id == "w"
    assert confidence == 0.9


def test_end_to_end_pretty_printed_completion_keeps_all_fields():
    completion = 'Here you go:\n{\n  "folder_id": "w",\n  "confidence": 0.88,\n  "reasoning": "Budget."\n}'
    folder_id, confidence, reasoning = _run_with_completion(completion)
    assert (folder_id, confidence, reasoning) == ("w", 0.88, "Budget.")


def test_end_to_end_default_only_folder_list_salvages_to_default():
    folders = [
        {"id": "w", "name": "Work", "description": "Work stuff"},
        {"id": "def", "name": "Other", "is_default": True},
    ]
    completion = 'Sure: {"folder_id": "def", "confidence": 0.95}'
    with patch.object(conv_folder, "get_llm", return_value=_ScriptedLLM(completion)):
        folder_id, confidence, _ = assign_conversation_to_folder("t", "o", "finance", folders, category_folder_id=None)
    assert folder_id == "def"
    assert confidence == 0.95


def test_end_to_end_category_folder_not_in_list_still_files_salvaged_pick():
    # The category id is only a fallback candidate; a confident salvaged pick of
    # a real folder files there even when the category id resolves to nothing.
    completion = 'Sure: {"folder_id": "w", "confidence": 0.95}'
    folder_id, confidence, _ = _run_with_completion(completion)
    assert folder_id == "w"
    assert confidence == 0.95


def test_end_to_end_whitespace_folder_id_is_invalid_and_falls_back():
    completion = 'Answer: {"folder_id": " w ", "confidence": 0.9}'
    folder_id, confidence, reasoning = _run_with_completion(completion)
    assert folder_id == "w"  # category-aligned fallback
    assert confidence == 0.3
    assert "Invalid folder ID" in reasoning


def test_end_to_end_confidence_at_threshold_is_accepted():
    completion = 'Sure: {"folder_id": "w", "confidence": 0.7}'
    folder_id, confidence, _ = _run_with_completion(completion)
    assert (folder_id, confidence) == ("w", 0.7)


def test_end_to_end_confidence_just_below_threshold_falls_back_keeping_confidence():
    completion = 'Sure: {"folder_id": "w", "confidence": 0.69}'
    folder_id, confidence, reasoning = _run_with_completion(completion)
    assert folder_id == "w"
    assert confidence == 0.69
    assert "Low confidence" in reasoning


def test_end_to_end_whitespace_wrapped_bare_json_parses_normally(caplog):
    # No refusal at all: the strict path still files it, no salvage warning.
    completion = '   \n{"folder_id": "w", "confidence": 0.9, "reasoning": "ok"}\n  '
    with caplog.at_level(logging.INFO, logger="utils.llm.conversation_folder"):
        folder_id, confidence, reasoning = _run_with_completion(completion)
    assert (folder_id, confidence, reasoning) == ("w", 0.9, "ok")
    assert not [r for r in caplog.records if "Recovered folder assignment" in r.message]


def test_salvage_warning_emitted_exactly_once_per_refusal(caplog):
    completion = 'Sure: {"folder_id": "w", "confidence": 0.9}'
    with caplog.at_level(logging.WARNING, logger="utils.llm.conversation_folder"):
        _run_with_completion(completion)
    recovered = [r for r in caplog.records if "Recovered folder assignment" in r.message]
    assert len(recovered) == 1


def test_salvage_candidate_payloads_handles_string_with_escapes():
    payload = conv_folder._salvage_candidate_payloads('x {"folder_id": "w", "reasoning": "line\\nbreak"}')
    assert payload == {"folder_id": "w", "reasoning": "line\nbreak"}


def test_best_assignment_returns_first_schema_matching_payload_not_last():
    # Two assignment-shaped spans: the FIRST schema-valid one wins (stable
    # candidate order), not the last.
    salvaged = conv_folder._salvage_folder_assignment(Exception('{"folder_id": "p"} {"folder_id": "w"}'))
    assert salvaged == FolderAssignment(folder_id="p")


# ---------------------------------------------------------------------------
# Wrapper-shape edge rows (each behavior observed against the real helpers)
# ---------------------------------------------------------------------------


def test_bom_prefixed_completion_salvages_end_to_end():
    folder_id, confidence, _ = _run_with_completion('﻿{"folder_id": "w", "confidence": 0.9}')
    assert (folder_id, confidence) == ("w", 0.9)


def test_tabs_and_blank_lines_before_prose_salvage_end_to_end():
    folder_id, confidence, _ = _run_with_completion('\t\n\nSure thing.\n\n{"folder_id": "w", "confidence": 0.9}')
    assert (folder_id, confidence) == ("w", 0.9)


def test_whitespace_only_completion_falls_back_to_category_folder():
    folder_id, confidence, reasoning = _run_with_completion("   ")
    assert folder_id == "w"
    assert confidence == 0.0
    assert reasoning.startswith("Error:")


def test_empty_completion_falls_back_to_category_folder():
    folder_id, confidence, _ = _run_with_completion("")
    assert folder_id == "w"
    assert confidence == 0.0


def test_model_echoing_placeholder_folder_id_falls_back():
    # The model echoed the prompt's placeholder text as the id: schema-valid,
    # but validate_folder_assignment refuses the unknown id — never filed raw.
    folder_id, confidence, reasoning = _run_with_completion(
        '{"folder_id": "<best matching folder ID>", "confidence": 0.9}'
    )
    assert folder_id == "w"
    assert confidence == 0.3
    assert "Invalid folder ID" in reasoning


def test_scientific_notation_confidence_coerces_end_to_end():
    folder_id, confidence, _ = _run_with_completion('Sure: {"folder_id": "w", "confidence": 9e-1}')
    assert (folder_id, confidence) == ("w", 0.9)


def test_empty_string_folder_id_falls_back():
    folder_id, confidence, reasoning = _run_with_completion('Sure: {"folder_id": "", "confidence": 0.9}')
    assert folder_id == "w"
    assert confidence == 0.3
    assert "Invalid folder ID" in reasoning


def test_very_long_reasoning_survives_salvage_intact():
    reasoning = "x" * 4000
    folder_id, confidence, recovered = _run_with_completion(
        'Sure: {"folder_id": "w", "confidence": 0.9, "reasoning": "' + reasoning + '"}'
    )
    assert folder_id == "w"
    assert recovered == reasoning


def test_confident_salvaged_pick_of_default_folder_is_accepted_verbatim():
    folders = [
        {"id": "w", "name": "Work", "description": "Work stuff"},
        {"id": "def", "name": "Other", "is_default": True},
    ]
    completion = 'Sure: {"folder_id": "def", "confidence": 0.9}'
    with patch.object(conv_folder, "get_llm", return_value=_ScriptedLLM(completion)):
        folder_id, confidence, _ = assign_conversation_to_folder("t", "o", "finance", folders, category_folder_id="w")
    assert (folder_id, confidence) == ("def", 0.9)


def test_truncated_reasoning_mid_escape_salvages_prefix():
    folder_id, confidence, reasoning = _run_with_completion(
        'Sure: {"folder_id": "w", "confidence": 0.9, "reasoning": "line1\\'
    )
    assert folder_id == "w"
    assert confidence == 0.9
    assert reasoning.startswith("line1")


def test_truncated_reasoning_with_nested_braces_salvages_verbatim_text():
    folder_id, _, reasoning = _run_with_completion(
        'Sure: {"folder_id": "w", "confidence": 0.9, "reasoning": "uses {a} and {b} and mor'
    )
    assert folder_id == "w"
    assert "uses {a} and {b}" in reasoning


def test_top_level_spans_of_only_open_braces_keep_single_tail():
    assert conv_folder._top_level_json_spans("{{{") == ["{{{"]
    assert conv_folder._top_level_json_spans("") == []


def test_top_level_spans_inside_arrays_are_top_level_members():
    assert conv_folder._top_level_json_spans('[{"a": 1}, {"b": 2}]') == ['{"a": 1}', '{"b": 2}']


def test_boolean_and_numeric_payloads_are_not_assignments():
    assert conv_folder._salvage_folder_assignment(Exception("true")) is None
    assert conv_folder._salvage_folder_assignment(Exception("prose 42 tail")) is None


def test_non_string_llm_output_attribute_falls_back_to_message():
    class _WeirdAttr(Exception):
        llm_output = 12345

    exc = _WeirdAttr('msg {"folder_id": "w"}')
    assert conv_folder._salvage_raw_completion(exc) == 'msg {"folder_id": "w"}'


def test_exception_with_empty_message_yields_no_salvage():
    assert conv_folder._salvage_folder_assignment(Exception()) is None
