from __future__ import annotations

from collections import Counter

from utils.memory_ingestion.ids import stable_hash
from utils.memory_ingestion.models import LintResult, MemoryPipelineOutput


def verify_output(output: MemoryPipelineOutput) -> list[LintResult]:
    lints: list[LintResult] = []
    frame_ids = {frame.frame_id for frame in output.event_frames}
    decision_ids = {decision.decision_id for decision in output.decisions}
    decisioned_resolution_ids = {
        resolution.decision_id for resolution in output.frame_resolutions if resolution.status == "decisioned"
    }
    resolution_frame_ids = {resolution.frame_id for resolution in output.frame_resolutions}

    for frame_id, count in Counter(resolution_frame_ids).items():
        if count > 1:
            lints.append(
                _lint("error", "duplicate_frame_resolution", f"Frame {frame_id} has multiple resolutions", frame_id)
            )
    for frame_id in frame_ids - resolution_frame_ids:
        lints.append(_lint("error", "missing_frame_resolution", f"Frame {frame_id} has no resolution", frame_id))
    for decision in output.decisions:
        if decision.frame_id not in frame_ids:
            lints.append(
                _lint(
                    "error",
                    "decision_missing_frame",
                    f"Decision {decision.decision_id} references a missing frame",
                    decision.frame_id,
                    decision.decision_id,
                )
            )
    for resolution in output.frame_resolutions:
        if resolution.status == "decisioned" and resolution.decision_id not in decision_ids:
            lints.append(
                _lint(
                    "error",
                    "resolution_missing_decision",
                    f"Resolution for {resolution.frame_id} references a missing decision",
                    resolution.frame_id,
                    resolution.decision_id,
                )
            )
        if resolution.status == "merged" and resolution.merged_into_frame_id not in frame_ids:
            lints.append(
                _lint(
                    "error",
                    "resolution_missing_merge_target",
                    f"Merged frame {resolution.frame_id} references a missing survivor",
                    resolution.frame_id,
                )
            )
    if decisioned_resolution_ids != decision_ids:
        lints.append(
            _lint("error", "decision_resolution_mismatch", "Decisioned resolutions must map one-to-one to decisions")
        )

    frames_by_id = {frame.frame_id: frame for frame in output.event_frames}
    for mutation in output.mutation_plan.creates:
        frame = frames_by_id.get(mutation.frame_id)
        if mutation.decision_id not in decision_ids:
            lints.append(
                _lint(
                    "error",
                    "mutation_missing_decision",
                    f"Create mutation {mutation.mutation_id} references a missing decision",
                    mutation.frame_id,
                    mutation.decision_id,
                    mutation.mutation_id,
                )
            )
        if not mutation.evidence:
            lints.append(
                _lint(
                    "error",
                    "active_memory_without_evidence",
                    f"Create mutation {mutation.mutation_id} has no evidence",
                    mutation.frame_id,
                    mutation.decision_id,
                    mutation.mutation_id,
                )
            )
        if frame and (
            frame.sensitivity.level == "blocked" or frame.frame_type in ("non_memory", "task", "task_candidate")
        ):
            lints.append(
                _lint(
                    "error",
                    "unsafe_active_memory_mutation",
                    f"Create mutation {mutation.mutation_id} comes from a blocked/non-memory/task frame",
                    mutation.frame_id,
                    mutation.decision_id,
                    mutation.mutation_id,
                )
            )
    upsert_source_ids = {upsert.source_id for upsert in output.vector_plan.upserts if upsert.source_type == "memory"}
    for mutation in output.mutation_plan.creates:
        if mutation.status == "active" and mutation.memory_id not in upsert_source_ids:
            lints.append(
                _lint(
                    "error",
                    "missing_vector_upsert",
                    f"Active memory create {mutation.mutation_id} has no matching vector upsert",
                    mutation.frame_id,
                    mutation.decision_id,
                    mutation.mutation_id,
                )
            )
    delete_source_ids = {delete.source_id for delete in output.vector_plan.deletes if delete.source_type == "memory"}
    for invalidation in output.mutation_plan.invalidations:
        if invalidation.memory_id not in delete_source_ids:
            lints.append(
                _lint(
                    "error",
                    "missing_vector_delete",
                    f"Invalidation {invalidation.mutation_id} has no matching vector delete",
                    invalidation.frame_id,
                    invalidation.decision_id,
                    invalidation.mutation_id,
                )
            )
    active_texts = [
        (create.subject.entity_id or create.subject.canonical_name, create.text.casefold())
        for create in output.mutation_plan.creates
        if create.status == "active"
    ]
    for key, count in Counter(active_texts).items():
        if count > 1:
            lints.append(_lint("error", "duplicate_active_create", f"Duplicate active memory create for {key}"))
    return lints


def _lint(
    severity: str,
    code: str,
    message: str,
    frame_id: str | None = None,
    decision_id: str | None = None,
    mutation_id: str | None = None,
) -> LintResult:
    return LintResult(
        lint_id=f"lint_{stable_hash(severity, code, message, frame_id, decision_id, mutation_id, length=20)}",
        severity=severity,  # type: ignore[arg-type]
        code=code,
        message=message,
        frame_id=frame_id,
        decision_id=decision_id,
        mutation_id=mutation_id,
    )
