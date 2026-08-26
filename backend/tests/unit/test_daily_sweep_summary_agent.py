"""run_daily_sweep_summary_agent: two-phase protocol, bounds, and strictness."""

from __future__ import annotations

import json
import os
from contextlib import nullcontext

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import pytest

from models.memory_contracts import MemoryExtractionError
from utils.llm import memories as memories_module
from utils.llm.memories import run_daily_sweep_summary_agent


class _ScriptedLlm:
    """Returns scripted JSON responses; records every prompt it saw."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def invoke(self, prompt_value):
        self.prompts.append(str(prompt_value))
        if not self.responses:
            raise AssertionError("unexpected extra model call")
        return self.responses.pop(0)


def _response(memories=(), transcript_requests=(), folder_assignments=()):
    return json.dumps(
        {
            "memories": list(memories),
            "transcript_requests": list(transcript_requests),
            "folder_assignments": list(folder_assignments),
        }
    )


@pytest.fixture(autouse=True)
def _stub_context(monkeypatch):
    monkeypatch.setattr(memories_module, "get_prompt_memories", lambda _uid: ("Dave", "existing facts"))
    monkeypatch.setattr(memories_module, "current_date_for_uid", lambda _uid: "2026-08-26")
    monkeypatch.setattr(memories_module, "track_usage", lambda *_args, **_kwargs: nullcontext())


_ROWS = (
    ("conversation-1", "10:02 (work) Pricing call — agreed on a number with Nik"),
    ("conversation-2", "14:30 (personal) Gym plans — wants to lift on Tuesdays"),
)
_TRANSCRIPTS = {
    "conversation-1": "SPEAKER 0: so let's lock it at forty two dollars a seat",
    "conversation-2": "SPEAKER 0: tuesdays work best for the gym",
}


def test_single_pass_when_no_transcript_requested():
    llm = _ScriptedLlm(
        [
            _response(
                memories=[
                    {"content": "Dave lifts on Tuesdays", "conversation_ids": ["conversation-2"]},
                    {"content": "no provenance", "conversation_ids": ["unknown-id"]},
                ]
            )
        ]
    )
    output = run_daily_sweep_summary_agent("uid-1", _ROWS, dict(_TRANSCRIPTS), llm=llm)
    assert len(llm.prompts) == 1
    assert "[conversation-1]" in llm.prompts[0] and "[conversation-2]" in llm.prompts[0]
    assert [memory.content for memory in output.memories] == ["Dave lifts on Tuesdays"]
    assert output.transcript_requests == []


def test_two_phase_verification_sends_excerpts_and_uses_final_memories():
    llm = _ScriptedLlm(
        [
            _response(
                memories=[
                    {"content": "Agreed a price with Nik (verify amount)", "conversation_ids": ["conversation-1"]}
                ],
                transcript_requests=[{"conversation_id": "conversation-1", "reason": "exact price"}],
            ),
            _response(
                memories=[{"content": "Agreed with Nik on $42/seat", "conversation_ids": ["conversation-1"]}],
                folder_assignments=[{"conversation_id": "conversation-1", "folder_id": "folder-work"}],
            ),
        ]
    )
    output = run_daily_sweep_summary_agent("uid-1", _ROWS, dict(_TRANSCRIPTS), llm=llm)
    assert len(llm.prompts) == 2
    assert "forty two dollars" in llm.prompts[1]
    assert "Agreed a price with Nik" in llm.prompts[1]
    assert [memory.content for memory in output.memories] == ["Agreed with Nik on $42/seat"]
    assert [assignment.folder_id for assignment in output.folder_assignments] == ["folder-work"]


def test_requests_for_unknown_or_empty_transcripts_do_not_trigger_second_pass():
    llm = _ScriptedLlm(
        [
            _response(
                memories=[{"content": "Dave lifts on Tuesdays", "conversation_ids": ["conversation-2"]}],
                transcript_requests=[
                    {"conversation_id": "not-in-day", "reason": "x"},
                    {"conversation_id": "conversation-1", "reason": "x"},
                ],
            )
        ]
    )
    lookup = dict(_TRANSCRIPTS)
    lookup["conversation-1"] = ""
    output = run_daily_sweep_summary_agent("uid-1", _ROWS, lookup, llm=llm)
    assert len(llm.prompts) == 1
    assert [memory.content for memory in output.memories] == ["Dave lifts on Tuesdays"]


def test_transcript_fetch_budget_is_enforced():
    rows = tuple((f"conversation-{index}", f"summary {index}") for index in range(6))
    lookup = {conversation_id: f"transcript {conversation_id}" for conversation_id, _ in rows}
    llm = _ScriptedLlm(
        [
            _response(
                transcript_requests=[
                    {"conversation_id": conversation_id, "reason": "detail"} for conversation_id, _ in rows
                ]
            ),
            _response(memories=[{"content": "final", "conversation_ids": ["conversation-0"]}]),
        ]
    )
    output = run_daily_sweep_summary_agent("uid-1", rows, lookup, max_transcript_fetches=2, llm=llm)
    assert len(llm.prompts) == 2
    included = [conversation_id for conversation_id, _ in rows if f"transcript {conversation_id}" in llm.prompts[1]]
    assert len(included) == 2
    assert [memory.content for memory in output.memories] == ["final"]


def test_candidate_cap_and_folder_sanitization():
    llm = _ScriptedLlm(
        [
            _response(
                memories=[{"content": f"fact {index}", "conversation_ids": ["conversation-1"]} for index in range(5)],
                folder_assignments=[
                    {"conversation_id": "conversation-1", "folder_id": "folder-work"},
                    {"conversation_id": "not-in-day", "folder_id": "folder-work"},
                ],
            )
        ]
    )
    output = run_daily_sweep_summary_agent("uid-1", _ROWS, dict(_TRANSCRIPTS), max_candidates=3, llm=llm)
    assert len(output.memories) == 3
    assert [assignment.conversation_id for assignment in output.folder_assignments] == ["conversation-1"]


def test_unparseable_model_output_raises_strict_error():
    llm = _ScriptedLlm(["not json at all"])
    with pytest.raises(MemoryExtractionError):
        run_daily_sweep_summary_agent("uid-1", _ROWS, dict(_TRANSCRIPTS), llm=llm)


def test_empty_day_returns_empty_without_model_call():
    llm = _ScriptedLlm([])
    output = run_daily_sweep_summary_agent("uid-1", (), {}, llm=llm)
    assert output.memories == [] and llm.prompts == []


def test_memory_lookups_trigger_second_pass_with_results():
    queries = []

    def searcher(query):
        queries.append(query)
        return (f"prior fact about {query} [slot: gym_schedule]",)

    llm = _ScriptedLlm(
        [
            _response(
                memories=[{"content": "Dave lifts on Tuesdays", "conversation_ids": ["conversation-2"]}],
                # memory_lookups ride the same output schema
            ).replace(
                '"folder_assignments": []', '"folder_assignments": [], "memory_lookups": [{"query": "gym schedule"}]'
            ),
            _response(
                memories=[
                    {
                        "content": "Dave now lifts on Tuesdays and Fridays",
                        "conversation_ids": ["conversation-2"],
                        "slot": "gym_schedule",
                    }
                ]
            ),
        ]
    )
    output = run_daily_sweep_summary_agent("uid-1", _ROWS, dict(_TRANSCRIPTS), memory_searcher=searcher, llm=llm)
    assert queries == ["gym schedule"]
    assert len(llm.prompts) == 2
    assert "prior fact about gym schedule" in llm.prompts[1]
    assert [memory.slot for memory in output.memories] == ["gym_schedule"]


def test_lookups_without_searcher_stay_single_pass():
    llm = _ScriptedLlm(
        [
            _response(memories=[{"content": "Dave lifts on Tuesdays", "conversation_ids": ["conversation-2"]}]).replace(
                '"folder_assignments": []', '"folder_assignments": [], "memory_lookups": [{"query": "anything"}]'
            )
        ]
    )
    output = run_daily_sweep_summary_agent("uid-1", _ROWS, dict(_TRANSCRIPTS), llm=llm)
    assert len(llm.prompts) == 1
    assert [memory.content for memory in output.memories] == ["Dave lifts on Tuesdays"]


def test_failing_searcher_degrades_to_empty_results():
    def searcher(_query):
        raise RuntimeError("index down")

    llm = _ScriptedLlm(
        [
            _response().replace(
                '"folder_assignments": []', '"folder_assignments": [], "memory_lookups": [{"query": "x"}]'
            ),
            _response(memories=[{"content": "final", "conversation_ids": ["conversation-1"]}]),
        ]
    )
    output = run_daily_sweep_summary_agent("uid-1", _ROWS, dict(_TRANSCRIPTS), memory_searcher=searcher, llm=llm)
    assert len(llm.prompts) == 2
    assert "(no matches)" in llm.prompts[1]
    assert [memory.content for memory in output.memories] == ["final"]


def test_phase_prompts_share_a_cacheable_prefix():
    """Phase B must reuse phase A's provider prompt cache: the two rendered
    prompts must be byte-identical through the summaries block (OpenAI prompt
    caching is strict prefix matching)."""

    import os as _os

    from langchain_core.output_parsers import PydanticOutputParser
    from utils.llm.memories import DailySweepAgentPassOutput as _Out
    from utils.llm.memories import _daily_sweep_folder_task, _daily_sweep_summaries_block
    from utils.prompts import daily_sweep_summary_agent_prompt, daily_sweep_transcript_review_prompt

    parser = PydanticOutputParser(pydantic_object=_Out)
    common = {
        "user_name": "Dave",
        "current_date": "2026-08-26",
        "memories_str": "existing facts",
        "summaries_block": _daily_sweep_summaries_block(_ROWS),
        "folder_task": _daily_sweep_folder_task((), ()),
        "max_candidates": 8,
        "format_instructions": parser.get_format_instructions(),
    }
    phase_a = (
        daily_sweep_summary_agent_prompt.invoke({**common, "max_transcript_fetches": 8, "max_memory_lookups": 4})
        .to_messages()[0]
        .content
    )
    phase_b = (
        daily_sweep_transcript_review_prompt.invoke(
            {**common, "draft_block": "- d", "excerpts_block": "e", "prior_memories_block": "p"}
        )
        .to_messages()[0]
        .content
    )
    shared = _os.path.commonprefix([phase_a, phase_b])
    # The shared prefix must cover everything up to and including the day's
    # summaries — the bulk of the tokens.
    assert common["summaries_block"] in shared
    assert len(shared) >= phase_a.find(common["summaries_block"]) + len(common["summaries_block"])


def test_untrusted_text_cannot_close_prompt_fences_and_phase_b_inputs_are_clamped():
    """Summaries/transcripts are third-party speech and phase-A output is
    model-controlled: fences are neutralized and every phase-B addition is
    length-clamped so the pre-call cost ceiling stays honest."""

    rows = (("conversation-1", "pricing ``` fake headers"),)
    transcripts = {"conversation-1": "SPEAKER 0: ``` injected block"}
    long_content = "x" * 2_000
    long_reason = "r" * 1_000
    llm = _ScriptedLlm(
        [
            _response(
                memories=[{"content": long_content, "conversation_ids": ["conversation-1"]}],
                transcript_requests=[{"conversation_id": "conversation-1", "reason": long_reason}],
            ),
            _response(memories=[{"content": "final", "conversation_ids": ["conversation-1"]}]),
        ]
    )
    output = run_daily_sweep_summary_agent("uid-1", rows, dict(transcripts), llm=llm)
    # Fences in untrusted text are neutralized in both phases. (Assertions
    # avoid quote characters: prompts are captured as message reprs.)
    assert "fake headers" in llm.prompts[0]
    assert "pricing ``` fake headers" not in llm.prompts[0]
    assert "injected block" in llm.prompts[1]
    assert "``` injected block" not in llm.prompts[1]
    # Phase-B draft content and request reasons are clamped.
    assert long_content not in llm.prompts[1]
    assert "x" * 600 in llm.prompts[1]
    assert long_reason not in llm.prompts[1]
    assert "r" * 200 in llm.prompts[1]
    assert [memory.content for memory in output.memories] == ["final"]


def test_phase_b_overhead_constant_covers_the_clamped_blocks():
    from utils.llm.memories import (
        DAILY_SWEEP_DRAFT_CONTENT_CHARACTERS,
        DAILY_SWEEP_DRAFT_ROW_LIMIT,
        daily_sweep_phase_b_overhead_characters,
    )

    overhead = daily_sweep_phase_b_overhead_characters(4)
    assert overhead >= DAILY_SWEEP_DRAFT_ROW_LIMIT * DAILY_SWEEP_DRAFT_CONTENT_CHARACTERS
    assert daily_sweep_phase_b_overhead_characters(0) < overhead
