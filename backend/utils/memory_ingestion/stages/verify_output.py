from __future__ import annotations

from collections import Counter
import re

from utils.memory_ingestion.ids import stable_hash
from utils.memory_ingestion.models import EvidenceSpan, LintResult, MemoryPipelineOutput


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        return _edit_distance(b, a)
    if len(b) == 0:
        return len(a)
    prev_row = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (ca != cb)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _check_confidence_contradiction(output: MemoryPipelineOutput) -> list[LintResult]:
    """Flag high-confidence units that claim 'inferred_not_stated' — a contradiction."""
    lints: list[LintResult] = []
    for frame in output.event_frames:
        if frame.confidence == "high" and "inferred_not_stated" in frame.uncertainty_reasons:
            lints.append(
                _lint(
                    "error",
                    "confidence_contradiction",
                    f"Frame {frame.frame_id} has high confidence but claims inferred_not_stated",
                    frame.frame_id,
                )
            )
    for create in output.mutation_plan.creates:
        if create.confidence == "high" and "inferred_not_stated" in create.uncertainty_reasons:
            lints.append(
                _lint(
                    "error",
                    "confidence_contradiction",
                    f"Create {create.mutation_id} has high confidence but claims inferred_not_stated",
                    create.frame_id,
                    create.decision_id,
                    create.mutation_id,
                )
            )
    return lints


def _check_grounding(output: MemoryPipelineOutput) -> list[LintResult]:
    """Warn when canonical_text / memory text is not substantiated by evidence quotes."""
    lints: list[LintResult] = []
    for frame in output.event_frames:
        if not frame.canonical_text.strip():
            continue
        quotes = [ev.quote for ev in frame.evidence if ev.quote]
        if quotes and not any(frame.canonical_text.casefold() in q.casefold() for q in quotes):
            lints.append(
                _lint(
                    "warning",
                    "ungrounded_content",
                    f"Frame {frame.frame_id} canonical_text not found in any evidence quote",
                    frame.frame_id,
                )
            )
    for create in output.mutation_plan.creates:
        if not create.text.strip():
            continue
        quotes = [ev.quote for ev in create.evidence if ev.quote]
        if quotes and not any(create.text.casefold() in q.casefold() for q in quotes):
            lints.append(
                _lint(
                    "warning",
                    "ungrounded_content",
                    f"Create {create.mutation_id} text not found in any evidence quote",
                    create.frame_id,
                    create.decision_id,
                    create.mutation_id,
                )
            )
    return lints


def _check_near_duplicates(output: MemoryPipelineOutput) -> list[LintResult]:
    """Flag pairs of event frames whose canonical_texts are nearly identical (edit distance < 3)."""
    lints: list[LintResult] = []
    frames = [f for f in output.event_frames if f.canonical_text.strip()]
    for i in range(len(frames)):
        for j in range(i + 1, len(frames)):
            dist = _edit_distance(frames[i].canonical_text, frames[j].canonical_text)
            if dist < 3:
                lints.append(
                    _lint(
                        "warning",
                        "near_duplicate_canonical_text",
                        f"Frames {frames[i].frame_id} and {frames[j].frame_id} have near-identical "
                        f"canonical texts (edit distance={dist})",
                        frames[i].frame_id,
                    )
                )
    return lints


_BLOCKING_CREATE_UNCERTAINTIES = {"weak_evidence", "inferred_not_stated", "unsupported_by_existing_state"}
_GROUNDING_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "at",
    "for",
    "from",
    "has",
    "have",
    "her",
    "his",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "our",
    "the",
    "their",
    "to",
    "user",
    "was",
    "we",
    "with",
}
_FIRST_PERSON_RE = re.compile(
    r"\b(i|i['’]m|i['’]ve|i['’]d|i['’]ll|me|my|mine|we|we['’]re|we['’]ve|we['’]d|we['’]ll|our|ours)\b"
)


def _meaningful_words(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9][a-z0-9'_-]*", text.casefold()))
    return {word for word in words if len(word) > 2 and word not in _GROUNDING_STOPWORDS}


def _check_active_create_guardrails(output: MemoryPipelineOutput) -> list[LintResult]:
    """Error when an active create bypasses uncertainty, quote, or speaker guardrails."""
    lints: list[LintResult] = []
    for create in output.mutation_plan.creates:
        if create.status != "active":
            continue
        blocking = sorted(_BLOCKING_CREATE_UNCERTAINTIES & set(create.uncertainty_reasons))
        if blocking:
            lints.append(
                _lint(
                    "error",
                    "uncertain_active_memory_mutation",
                    f"Active create {create.mutation_id} has blocking uncertainty reasons: {', '.join(blocking)}",
                    create.frame_id,
                    create.decision_id,
                    create.mutation_id,
                )
            )
        create_words = _meaningful_words(create.text)
        quotes = [evidence.quote for evidence in create.evidence if evidence.quote]
        if create_words and quotes:
            quote_overlaps = [len(create_words & _meaningful_words(quote)) for quote in quotes]
            best_overlap = max(quote_overlaps, default=0)
            required_overlap = 2 if len(create_words) >= 4 else 1
            if best_overlap < required_overlap:
                lints.append(
                    _lint(
                        "error",
                        "active_memory_weak_quote_overlap",
                        f"Active create {create.mutation_id} lacks meaningful quote overlap ({best_overlap}/{required_overlap})",
                        create.frame_id,
                        create.decision_id,
                        create.mutation_id,
                    )
                )
            unrelated_count = sum(1 for overlap in quote_overlaps if overlap == 0)
            if unrelated_count:
                lints.append(
                    _lint(
                        "error",
                        "active_memory_unrelated_evidence_span",
                        f"Active create {create.mutation_id} has {unrelated_count} quoted evidence span(s) with no content-token overlap",
                        create.frame_id,
                        create.decision_id,
                        create.mutation_id,
                    )
                )
        evidence_with_speakers = [evidence for evidence in create.evidence if evidence.speaker is not None]
        if evidence_with_speakers and not any(
            evidence.speaker and evidence.speaker.is_actor_user is True for evidence in evidence_with_speakers
        ):
            lints.append(
                _lint(
                    "error",
                    "active_memory_without_actor_quote",
                    f"Active create {create.mutation_id} has no actor-authored supporting evidence",
                    create.frame_id,
                    create.decision_id,
                    create.mutation_id,
                )
            )
        create_text = (create.text or "").casefold()
        subject_name = (create.subject.canonical_name or create.subject.entity_id or "").casefold()
        if (
            (
                create_text.startswith(("user ", "user's "))
                or (subject_name and create_text.startswith((f"{subject_name} ", f"{subject_name}'s ")))
            )
            and any(evidence.quote for evidence in create.evidence)
            and not _has_self_report_evidence(create.evidence)
        ):
            lints.append(
                _lint(
                    "error",
                    "active_memory_without_self_report_evidence",
                    f"Active create {create.mutation_id} has no actor or first-person self-report evidence",
                    create.frame_id,
                    create.decision_id,
                    create.mutation_id,
                )
            )
    return lints


def _has_self_report_evidence(evidence_spans: list[EvidenceSpan]) -> bool:
    for evidence in evidence_spans:
        if evidence.speaker and evidence.speaker.is_actor_user is True:
            return True
        if evidence.quote and _FIRST_PERSON_RE.search(evidence.quote.casefold()):
            return True
    return False


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

    # --- content-level grounding checks ---
    lints.extend(_check_confidence_contradiction(output))
    lints.extend(_check_grounding(output))
    lints.extend(_check_near_duplicates(output))
    lints.extend(_check_active_create_guardrails(output))

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
