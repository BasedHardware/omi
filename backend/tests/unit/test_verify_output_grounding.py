"""Tests for content-level grounding checks in verify_output stage (T-H9)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from utils.memory_ingestion.models import (
    CreateMemoryMutation,
    EntityRef,
    EvidenceSpan,
    FrameObject,
    FrameResolution,
    MemoryDecision,
    MemoryEventFrame,
    MemoryMutationPlan,
    MemoryPipelineOutput,
    ModelManifest,
    PipelineStats,
    SensitivityClassification,
    SourceRef,
    VectorMutationPlan,
)
from utils.memory_ingestion.stages.verify_output import (
    _check_confidence_contradiction,
    _check_grounding,
    _check_near_duplicates,
    _edit_distance,
    verify_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_ref() -> SourceRef:
    return SourceRef(conversation_id="conv_1")


def _make_evidence(quote: str | None = None) -> EvidenceSpan:
    return EvidenceSpan(
        evidence_id="ev_1",
        source_event_id="raw_1",
        source_ref=_make_source_ref(),
        quote=quote,
    )


def _make_frame(
    frame_id: str = "frame_1",
    canonical_text: str = "Alice likes pizza",
    confidence: str = "high",
    uncertainty_reasons: list[str] | None = None,
    evidence_quotes: list[str | None] | None = None,
) -> MemoryEventFrame:
    evs = [_make_evidence(q) for q in (evidence_quotes or [])]
    return MemoryEventFrame(
        frame_id=frame_id,
        frame_type="personal_fact",
        subject=EntityRef(entity_id="ent_alice", entity_type="person", canonical_name="Alice"),
        predicate="likes",
        object=FrameObject(object_type="literal", value="pizza"),
        canonical_text=canonical_text,
        confidence=confidence,  # type: ignore[arg-type]
        uncertainty_reasons=uncertainty_reasons or [],  # type: ignore[arg-type]
        evidence=evs,
        source_event_ids=["raw_1"],
    )


def _make_create(
    mutation_id: str = "mut_1",
    text: str = "Alice likes pizza",
    confidence: str = "high",
    uncertainty_reasons: list[str] | None = None,
    evidence_quotes: list[str | None] | None = None,
) -> CreateMemoryMutation:
    evs = [_make_evidence(q) for q in (evidence_quotes or [])]
    return CreateMemoryMutation(
        mutation_id=mutation_id,
        decision_id="dec_1",
        frame_id="frame_1",
        memory_id="mem_1",
        text=text,
        kind="personal_fact",
        subject=EntityRef(entity_id="ent_alice", entity_type="person", canonical_name="Alice"),
        entities=[],
        status="active",
        confidence=confidence,  # type: ignore[arg-type]
        uncertainty_reasons=uncertainty_reasons or [],  # type: ignore[arg-type]
        source_refs=[],
        evidence=evs,
        event_frame_ids=[],
        ontology_version="v0",
    )


def _make_output(
    frames: list[MemoryEventFrame] | None = None,
    creates: list[CreateMemoryMutation] | None = None,
) -> MemoryPipelineOutput:
    frames = frames or []
    creates = creates or []
    return MemoryPipelineOutput(
        run_id="run_1",
        mode="production",  # type: ignore[arg-type]
        status="ok",  # type: ignore[arg-type]
        input_fingerprint="fp1",
        pipeline_version="v1",
        ontology_version="v0",
        config_version="v1",
        model_manifest=ModelManifest(
            extractor_model="stub",
            normalizer_model=None,
            entity_linker_model=None,
            embedding_model=None,
            provider_versions={},
            prompt_versions={},
        ),
        event_frames=frames,
        frame_resolutions=[
            FrameResolution(frame_id=f.frame_id, status="decisioned", decision_id=f"dec_{f.frame_id}", rationale="")
            for f in frames
        ],
        derived_triples=[],
        decisions=[
            MemoryDecision(
                decision_id=f"dec_{f.frame_id}",
                frame_id=f.frame_id,
                action="create_memory",  # type: ignore[arg-type]
                rationale="",
                confidence="high",  # type: ignore[arg-type]
                uncertainty_reasons=[],
                preconditions=[],
            )
            for f in frames
        ]
        + [
            MemoryDecision(
                decision_id=c.decision_id,
                frame_id=c.frame_id,
                action="create_memory",  # type: ignore[arg-type]
                rationale="",
                confidence="high",  # type: ignore[arg-type]
                uncertainty_reasons=[],
                preconditions=[],
            )
            for c in creates
        ],
        entity_ops=[],
        relationship_ops=[],
        mutation_plan=MemoryMutationPlan(
            plan_id="plan_1",
            creates=creates,
            updates=[],
            invalidations=[],
            evidence_links=[],
            review_upserts=[],
            task_routes=[],
        ),
        vector_plan=VectorMutationPlan(upserts=[], deletes=[]),
        review_items=[],
        rejected_items=[],
        audit={
            "trace_id": "t1",
            "run_id": "run_1",
            "stage_traces": [],
            "redactions": [],
            "dropped_artifacts": [],
            "prompt_call_refs": [],
            "lint_results": [],
        },
        stats=PipelineStats(),
    )


# ---------------------------------------------------------------------------
# _edit_distance
# ---------------------------------------------------------------------------


class TestEditDistance:
    def test_identical_strings(self):
        assert _edit_distance("hello", "hello") == 0

    def test_completely_different(self):
        assert _edit_distance("abc", "xyz") == 3

    def test_one_insertion(self):
        assert _edit_distance("hello", "helllo") == 1  # extra 'l'

    def test_one_substitution(self):
        assert _edit_distance("cat", "bat") == 1

    def test_empty_string(self):
        assert _edit_distance("", "abc") == 3
        assert _edit_distance("abc", "") == 3


# ---------------------------------------------------------------------------
# _check_confidence_contradiction
# ---------------------------------------------------------------------------


class TestConfidenceContradiction:
    def test_high_confidence_with_inferred_not_stated_on_frame(self):
        output = _make_output(
            frames=[
                _make_frame(confidence="high", uncertainty_reasons=["inferred_not_stated"]),
            ]
        )
        lints = _check_confidence_contradiction(output)
        assert len(lints) == 1
        assert lints[0].code == "confidence_contradiction"
        assert lints[0].severity == "error"

    def test_high_confidence_with_inferred_not_stated_on_create(self):
        output = _make_output(
            creates=[
                _make_create(mutation_id="mut_x", confidence="high", uncertainty_reasons=["inferred_not_stated"]),
            ]
        )
        lints = _check_confidence_contradiction(output)
        assert len(lints) == 1
        assert lints[0].code == "confidence_contradiction"
        assert lints[0].mutation_id == "mut_x"

    def test_medium_confidence_with_inferred_not_stated_is_ok(self):
        output = _make_output(
            frames=[
                _make_frame(confidence="medium", uncertainty_reasons=["inferred_not_stated"]),
            ]
        )
        lints = _check_confidence_contradiction(output)
        assert len(lints) == 0

    def test_high_confidence_without_inferred_not_stated_is_ok(self):
        output = _make_output(
            frames=[
                _make_frame(confidence="high", uncertainty_reasons=["weak_evidence"]),
            ]
        )
        lints = _check_confidence_contradiction(output)
        assert len(lints) == 0

    def test_no_uncertainty_reasons_is_ok(self):
        output = _make_output(
            frames=[
                _make_frame(confidence="high"),
            ]
        )
        lints = _check_confidence_contradiction(output)
        assert len(lints) == 0


# ---------------------------------------------------------------------------
# _check_grounding
# ---------------------------------------------------------------------------


class TestGrounding:
    def test_canonical_text_found_in_quote_no_warning(self):
        output = _make_output(
            frames=[
                _make_frame(canonical_text="Alice likes pizza", evidence_quotes=["She said Alice likes pizza"]),
            ]
        )
        lints = _check_grounding(output)
        assert len(lints) == 0

    def test_canonical_text_not_in_quote_warns(self):
        output = _make_output(
            frames=[
                _make_frame(canonical_text="Alice hates pizza", evidence_quotes=["Bob ordered a burger"]),
            ]
        )
        lints = _check_grounding(output)
        assert len(lints) == 1
        assert lints[0].code == "ungrounded_content"
        assert lints[0].severity == "warning"

    def test_case_insensitive_match(self):
        output = _make_output(
            frames=[
                _make_frame(canonical_text="ALICE LIKES PIZZA", evidence_quotes=["alice likes pizza"]),
            ]
        )
        lints = _check_grounding(output)
        assert len(lints) == 0

    def test_no_evidence_skips_check(self):
        """Frames without evidence quotes should not trigger ungrounded warning."""
        output = _make_output(
            frames=[
                _make_frame(canonical_text="Alice likes pizza", evidence_quotes=[]),
            ]
        )
        lints = _check_grounding(output)
        assert len(lints) == 0

    def test_empty_canonical_text_skips_check(self):
        output = _make_output(
            frames=[
                _make_frame(canonical_text="   ", evidence_quotes=["something"]),
            ]
        )
        lints = _check_grounding(output)
        assert len(lints) == 0

    def test_create_mutation_text_found_in_quote(self):
        output = _make_output(
            creates=[
                _make_create(text="Alice likes coffee", evidence_quotes=["She said Alice likes coffee today"]),
            ]
        )
        lints = _check_grounding(output)
        assert len(lints) == 0

    def test_create_mutation_text_not_in_quote_warns(self):
        output = _make_output(
            creates=[
                _make_create(text="Alice likes tea", evidence_quotes=["Bob ordered coffee"]),
            ]
        )
        lints = _check_grounding(output)
        assert len(lints) == 1
        assert lints[0].code == "ungrounded_content"


# ---------------------------------------------------------------------------
# _check_near_duplicates
# ---------------------------------------------------------------------------


class TestNearDuplicates:
    def test_identical_texts_flagged(self):
        output = _make_output(
            frames=[
                _make_frame(frame_id="f1", canonical_text="Alice likes pizza"),
                _make_frame(frame_id="f2", canonical_text="Alice likes pizza"),
            ]
        )
        lints = _check_near_duplicates(output)
        assert len(lints) == 1
        assert lints[0].code == "near_duplicate_canonical_text"
        assert lints[0].severity == "warning"

    def test_edit_distance_one_flagged(self):
        output = _make_output(
            frames=[
                _make_frame(frame_id="f1", canonical_text="Alice likes pizza"),
                _make_frame(frame_id="f2", canonical_text="Alice like pizza"),  # missing 's'
            ]
        )
        lints = _check_near_duplicates(output)
        assert len(lints) == 1
        assert "edit distance=1" in lints[0].message

    def test_edit_distance_two_flagged(self):
        output = _make_output(
            frames=[
                _make_frame(frame_id="f1", canonical_text="Alice likes pizza"),
                _make_frame(frame_id="f2", canonical_text="Alic like pizza"),  # missing 'e' and 's'
            ]
        )
        lints = _check_near_duplicates(output)
        assert len(lints) == 1
        assert "edit distance=2" in lints[0].message

    def test_edit_distance_three_not_flagged(self):
        output = _make_output(
            frames=[
                _make_frame(frame_id="f1", canonical_text="Alice likes pizza"),
                _make_frame(frame_id="f2", canonical_text="Ali like pizza"),  # dist >= 3
            ]
        )
        lints = _check_near_duplicates(output)
        assert len(lints) == 0

    def test_single_frame_no_lint(self):
        output = _make_output(
            frames=[
                _make_frame(frame_id="f1", canonical_text="Alice likes pizza"),
            ]
        )
        lints = _check_near_duplicates(output)
        assert len(lints) == 0

    def test_empty_canonical_text_ignored(self):
        output = _make_output(
            frames=[
                _make_frame(frame_id="f1", canonical_text=""),
                _make_frame(frame_id="f2", canonical_text="  "),
            ]
        )
        lints = _check_near_duplicates(output)
        assert len(lints) == 0

    def test_multiple_pairs_all_flagged(self):
        output = _make_output(
            frames=[
                _make_frame(frame_id="f1", canonical_text="same text here"),
                _make_frame(frame_id="f2", canonical_text="same text here"),
                _make_frame(frame_id="f3", canonical_text="different thing"),
                _make_frame(frame_id="f4", canonical_text="differen thing"),  # dist=1 from f3
            ]
        )
        lints = _check_near_duplicates(output)
        assert len(lints) == 2  # (f1,f2) and (f3,f4)


# ---------------------------------------------------------------------------
# Integration: all three checks wired into verify_output()
# ---------------------------------------------------------------------------


class TestVerifyOutputIntegration:
    def test_all_checks_fire_together(self):
        """Verify that all three new checks are called inside verify_output()."""
        output = _make_output(
            frames=[
                # triggers confidence_contradiction + near_duplicate pair
                _make_frame(
                    frame_id="f1",
                    canonical_text="Alice likes pizza",
                    confidence="high",
                    uncertainty_reasons=["inferred_not_stated"],
                    evidence_quotes=["Bob said something totally different"],  # triggers grounding too
                ),
                _make_frame(
                    frame_id="f2",
                    canonical_text="Alice likes pizza",  # identical → near-dup
                    confidence="high",
                    evidence_quotes=[],
                ),
            ],
            creates=[
                # triggers confidence_contradiction on create + grounding
                _make_create(
                    mutation_id="mut_x",
                    text="She loves cats",
                    confidence="high",
                    uncertainty_reasons=["inferred_not_stated"],
                    evidence_quotes=["He talked about dogs"],  # not grounded
                ),
            ],
        )
        lints = verify_output(output)
        codes = {l.code for l in lints}
        assert "confidence_contradiction" in codes
        assert "ungrounded_content" in codes
        assert "near_duplicate_canonical_text" in codes

    def test_clean_output_passes_new_checks(self):
        output = _make_output(
            frames=[
                _make_frame(
                    frame_id="f1",
                    canonical_text="Alice likes pizza",
                    confidence="high",
                    evidence_quotes=["Yes, Alice likes pizza"],
                ),
            ],
        )
        lints = verify_output(output)
        new_codes = {l.code for l in lints} & {
            "confidence_contradiction",
            "ungrounded_content",
            "near_duplicate_canonical_text",
        }
        assert len(new_codes) == 0
