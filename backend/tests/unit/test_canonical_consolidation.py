"""Contract tests for batched, total canonical L2 routing."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.product_memory import RESTRICTED_SENSITIVITY_LABELS
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
from models.memory_apply import MemoryControlState, memory_content_hash
from models.memory_evidence import (
    ArtifactPreservationState,
    MemoryEvidence,
    SourceState,
)
from models.memory_recurrence import CanonicalRecurrenceSignal
from models.product_memory import (
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    MemoryItem,
)
from utils.memory import canonical_consolidation as consolidation
from utils.memory.canonical_consolidation import (
    CONSOLIDATION_CONTEXT_ARGUMENTS_MAX_CHARS,
    CONSOLIDATION_CONTEXT_CANDIDATE_CONTENT_MAX_CHARS,
    CONSOLIDATION_CONTEXT_EVIDENCE_IDS_MAX_COUNT,
    CONSOLIDATION_CONTEXT_EVIDENCE_QUOTE_MAX_CHARS,
    CONSOLIDATION_CONTEXT_EVIDENCE_QUOTES_MAX_COUNT,
    CONSOLIDATION_CONTEXT_EVIDENCE_SOURCE_IDS_MAX_COUNT,
    CONSOLIDATION_CONTEXT_MEMORY_CONTENT_MAX_CHARS,
    CONSOLIDATION_CONTEXT_PROMOTION_MAX_CHARS,
    CONSOLIDATION_CONTEXT_REDACTED_TEXT,
    ConsolidationAgentBatch,
    ConsolidationAgentDecision,
    ConsolidationCandidate,
    ConsolidationContext,
    _validate_agent_batch,
    consolidation_trigger_reason,
    format_consolidation_llm_context,
    gather_consolidation_candidates,
    invoke_consolidation_agent,
    build_consolidation_llm_messages,
    run_canonical_consolidation,
)
from utils.memory.memory_system import MemorySystem
from utils.memory.rejected_memory_feedback import RejectedMemoryFeedback

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
UID = "uid-canonical"


def _llm_payload_text(payload) -> str:
    if isinstance(payload, str):
        return payload
    chunks: list[str] = []
    for message in payload:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            chunks.append(content)
            continue
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    chunks.append(str(part.get("text") or ""))
                else:
                    chunks.append(str(part))
            continue
        chunks.append(str(content))
    return "\n".join(chunks)


def _item(
    memory_id: str,
    content: str,
    *,
    tier: MemoryTier = MemoryTier.short_term,
    sensitivity_labels: list[str] | None = None,
) -> MemoryItem:
    evidence = MemoryEvidence(
        evidence_id=f"ev_{memory_id}",
        source_id="conv-1",
        source_type="conversation",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
        quote_refs=[{"quote": content, "speaker": "user"}],
    )
    return MemoryItem(
        memory_id=memory_id,
        uid=UID,
        version=1,
        tier=tier,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[evidence],
        source_state=SourceState.active,
        sensitivity_labels=sensitivity_labels or [],
        visibility="private",
        user_asserted=False,
        captured_at=NOW - timedelta(hours=1),
        updated_at=NOW,
        expires_at=NOW + timedelta(days=30) if tier == MemoryTier.short_term else None,
        ledger_commit_id="commit-1",
        ledger_sequence=1,
        item_revision=1,
        source_commit_id="commit-1",
        content_hash=memory_content_hash(content=content, evidence_ids=[evidence.evidence_id]),
        account_generation=1,
        subject_entity_id="user",
        promotion={
            "source_attribution": {
                "subject_entity_id": "user",
                "subject_attribution": "user",
            }
        },
    )


def _promote(item: MemoryItem, **overrides) -> ConsolidationAgentDecision:
    values = {
        "source_memory_id": item.memory_id,
        "route": "promote",
        "reconciliation": "create",
        "memory_text": f"The user said: {item.content}",
        "evidence_ids": [evidence.evidence_id for evidence in item.evidence],
        "subject_entity_id": "user",
        "predicate": "stated_preference",
        "arguments": {"preference": item.content},
        "relationship_to_user": "self",
        "aboutness": "primary_user",
        "basis_for_memory": "explicit",
        "confidence": "high",
    }
    values.update(overrides)
    return ConsolidationAgentDecision(**values)


def _archive(item: MemoryItem) -> ConsolidationAgentDecision:
    return ConsolidationAgentDecision(
        source_memory_id=item.memory_id,
        route="archive",
        rationale="Useful source context but not stable profile truth.",
    )


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def get(self, transaction=None):
        if self.path not in self._db.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db.docs[self.path], exists=True)

    def set(self, data, merge=False):
        if merge and self.path in self._db.docs:
            merged = dict(self._db.docs[self.path])
            merged.update(data)
            self._db.docs[self.path] = merged
        else:
            self._db.docs[self.path] = data

    def delete(self):
        self._db.docs.pop(self.path, None)


class _CollectionRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def stream(self):
        prefix = self.path + "/"
        for path, data in sorted(self._db.docs.items()):
            if path.startswith(prefix) and "/" not in path[len(prefix) :]:
                yield _Snapshot(data)


class _FakeTransaction:
    def __init__(self, db):
        self._db = db
        self._read_only = False
        self._max_attempts = 1
        self._id = None
        self._writes = []
        self._deletes = []

    def _clean_up(self):
        self._id = None
        self._writes = []
        self._deletes = []

    def _begin(self, retry_id=None):
        self._id = retry_id or "txn-1"
        self._writes = []
        self._deletes = []

    def set(self, ref, data):
        self._writes.append((ref.path, data))

    def delete(self, ref):
        self._deletes.append(ref.path)

    def _commit(self):
        for path, data in self._writes:
            self._db.docs[path] = data
        for path in self._deletes:
            self._db.docs.pop(path, None)

    def _rollback(self):
        self._writes = []
        self._deletes = []
        self._id = None


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def document(self, path):
        return _DocRef(self, path)

    def collection(self, path):
        return _CollectionRef(self, path)

    def transaction(self):
        return _FakeTransaction(self)


def _context(items: list[MemoryItem], candidates=None) -> ConsolidationContext:
    return ConsolidationContext(
        uid=UID,
        pending_items=items,
        candidates_by_anchor=candidates or {item.memory_id: [] for item in items},
    )


def test_every_nonempty_pending_set_is_due():
    assert consolidation_trigger_reason(pending_count=10) == "pending_items"
    assert consolidation_trigger_reason(pending_count=1) == "pending_items"
    assert consolidation_trigger_reason(pending_count=0) is None


def test_gather_excludes_superseded_candidates():
    active = _item("mem_a", "Lives in Seattle")
    superseded = _item("mem_old", "Lives in NYC", tier=MemoryTier.long_term)
    superseded.status = MemoryItemStatus.superseded
    hydrated = _item(
        "mem_candidate",
        "Has a health appointment",
        tier=MemoryTier.long_term,
        sensitivity_labels=["health"],
    )
    db = _FakeDb(
        {
            f"users/{UID}/memory_items/{active.memory_id}": active.model_dump(mode="python"),
            f"users/{UID}/memory_items/{superseded.memory_id}": superseded.model_dump(mode="python"),
            f"users/{UID}/memory_items/{hydrated.memory_id}": hydrated.model_dump(mode="python"),
        }
    )
    hits = [
        MagicMock(memory_id=superseded.memory_id, score=0.95),
        MagicMock(memory_id=hydrated.memory_id, score=0.9),
    ]

    with patch(
        "utils.memory.canonical_consolidation.query_memory_vector_candidates",
        return_value=MagicMock(hits=hits),
    ):
        context = gather_consolidation_candidates(UID, [active], db_client=db)

    assert [candidate.memory_id for candidate in context.candidates_by_anchor[active.memory_id]] == [hydrated.memory_id]
    assert context.candidates_by_anchor[active.memory_id][0].sensitivity_labels == ("health",)


def test_recent_rejection_reaches_the_volatile_prompt_even_after_vector_projection_deletion():
    active = _item("mem-new", "The user prefers aisle seats")
    rejected = _item("mem-rejected", "The user prefers aisle seating", tier=MemoryTier.long_term)
    rejected.promotion = {**(rejected.promotion or {}), "reviewed": True, "user_review": False}
    db = _FakeDb(
        {
            f"users/{UID}/memory_items/{active.memory_id}": active.model_dump(mode="python"),
            f"users/{UID}/memory_items/{rejected.memory_id}": rejected.model_dump(mode="python"),
        }
    )

    with (
        patch(
            "utils.memory.canonical_consolidation.query_memory_vector_candidates",
            return_value=MagicMock(hits=[]),
        ),
        patch(
            "utils.memory.canonical_consolidation.get_recent_rejected_memory_feedback",
            return_value=(
                RejectedMemoryFeedback(
                    memory_id=rejected.memory_id,
                    content=rejected.content or "",
                    updated_at=rejected.updated_at,
                ),
            ),
        ),
    ):
        context = gather_consolidation_candidates(UID, [active], db_client=db)

    payload = json.loads(format_consolidation_llm_context(context))
    messages = build_consolidation_llm_messages(context)
    prefix = _llm_payload_text(messages[:1])
    suffix = _llm_payload_text(messages[1:])

    assert context.candidates_by_anchor[active.memory_id] == []
    assert payload["owner_rejected_examples"] == [
        {
            "content": rejected.content,
            "memory_id": rejected.memory_id,
            "updated_at": rejected.updated_at.isoformat(),
            "user_rejected": True,
        }
    ]
    assert "owner-rejected" in prefix
    assert "MUST NOT route promote" in prefix
    assert "mem-rejected" not in prefix
    assert '"user_rejected":true' in suffix


def test_gather_never_sends_restricted_pending_text_to_vector_search():
    restricted = _item("mem_secret", "password-like material", sensitivity_labels=["credential"])
    db = _FakeDb(
        {
            f"users/{UID}/memory_items/{restricted.memory_id}": restricted.model_dump(mode="python"),
        }
    )

    with patch("utils.memory.canonical_consolidation.query_memory_vector_candidates") as vector_query:
        context = gather_consolidation_candidates(UID, [restricted], db_client=db)

    vector_query.assert_not_called()
    assert context.candidates_by_anchor[restricted.memory_id] == []


def test_llm_context_leaves_normal_content_and_quotes_unchanged_within_bounds():
    item = _item("mem_a", "Enjoys hiking", sensitivity_labels=["preference"])
    item.arguments = {"activity": "hiking"}
    item.promotion = {"category": "preference"}
    candidate = ConsolidationCandidate(
        anchor_memory_id=item.memory_id,
        memory_id="mem_existing",
        content="Enjoys walking trails",
        score=0.91,
        tier=MemoryTier.long_term.value,
        captured_at=NOW.isoformat(),
        sensitivity_labels=("preference",),
    )
    payload = json.loads(format_consolidation_llm_context(_context([item], {item.memory_id: [candidate]})))

    assert payload["memories"][0]["content"] == "Enjoys hiking"
    assert payload["memories"][0]["evidence_ids"] == ["ev_mem_a"]
    assert payload["memories"][0]["evidence_quotes"] == [{"quote": "Enjoys hiking", "speaker": "user"}]
    assert payload["memories"][0]["sensitivity_labels"] == ["preference"]
    assert payload["memories"][0]["arguments"] == {"activity": "hiking"}
    assert payload["memories"][0]["promotion"] == {"category": "preference"}
    assert payload["candidate_groups"][0]["candidates"][0]["content"] == "Enjoys walking trails"


def test_llm_context_redacts_restricted_pending_and_candidate_content():
    pending_secret = "pending-secret-must-not-leave-process"
    quote_secret = "quoted-secret-must-not-leave-process"
    argument_secret = "argument-secret-must-not-leave-process"
    promotion_secret = "promotion-secret-must-not-leave-process"
    candidate_secret = "candidate-secret-must-not-leave-process"
    item = _item("mem_restricted", pending_secret, sensitivity_labels=["secret"])
    item.evidence[0].quote_refs = [{"quote": quote_secret, "speaker": "user"}]
    item.arguments = {"credential": argument_secret}
    item.promotion = {"rationale": promotion_secret}
    candidate = ConsolidationCandidate(
        anchor_memory_id=item.memory_id,
        memory_id="mem_restricted_candidate",
        content=candidate_secret,
        score=0.93,
        tier=MemoryTier.long_term.value,
        captured_at=NOW.isoformat(),
        sensitivity_labels=("health",),
    )

    serialized = format_consolidation_llm_context(_context([item], {item.memory_id: [candidate]}))
    payload = json.loads(serialized)
    pending_payload = payload["memories"][0]
    candidate_payload = payload["candidate_groups"][0]["candidates"][0]

    assert pending_secret not in serialized
    assert quote_secret not in serialized
    assert argument_secret not in serialized
    assert promotion_secret not in serialized
    assert candidate_secret not in serialized
    assert pending_payload["content"] == CONSOLIDATION_CONTEXT_REDACTED_TEXT
    assert pending_payload["evidence_quotes"] == []
    assert pending_payload["arguments"] == {}
    assert pending_payload["promotion"] == {"redacted": True}
    assert pending_payload["memory_id"] == item.memory_id
    assert pending_payload["evidence_ids"] == ["ev_mem_restricted"]
    assert pending_payload["evidence_source_ids"] == ["conv-1"]
    assert pending_payload["sensitivity_labels"] == ["secret"]
    assert candidate_payload["content"] == CONSOLIDATION_CONTEXT_REDACTED_TEXT
    assert candidate_payload["memory_id"] == candidate.memory_id
    assert candidate_payload["sensitivity_labels"] == ["health"]


def test_llm_context_has_deterministic_text_and_quote_bounds():
    pathological_text = "x" * 50_000
    item = _item("mem_pathological", pathological_text)
    item.evidence[0].quote_refs = [
        {"quote": f"{index}:{pathological_text}", "speaker": "user"}
        for index in range(CONSOLIDATION_CONTEXT_EVIDENCE_QUOTES_MAX_COUNT + 10)
    ]
    item.evidence.extend(
        MemoryEvidence(
            evidence_id=f"ev_pathological_{index}",
            source_id=f"conv-pathological-{index}",
            source_type="conversation",
            source_version="v1",
            artifact_preservation=ArtifactPreservationState.preserved,
        )
        for index in range(CONSOLIDATION_CONTEXT_EVIDENCE_IDS_MAX_COUNT + 10)
    )
    item.arguments = {f"detail_{index}": pathological_text for index in range(20)}
    item.promotion = {f"rationale_{index}": pathological_text for index in range(20)}
    candidate = ConsolidationCandidate(
        anchor_memory_id=item.memory_id,
        memory_id="mem_pathological_candidate",
        content=pathological_text,
        score=0.9,
        tier=MemoryTier.long_term.value,
        captured_at=NOW.isoformat(),
    )

    serialized = format_consolidation_llm_context(_context([item], {item.memory_id: [candidate]}))
    payload = json.loads(serialized)
    pending_payload = payload["memories"][0]
    quotes = pending_payload["evidence_quotes"]
    candidate_payload = payload["candidate_groups"][0]["candidates"][0]
    text_budget = (
        CONSOLIDATION_CONTEXT_MEMORY_CONTENT_MAX_CHARS
        + CONSOLIDATION_CONTEXT_CANDIDATE_CONTENT_MAX_CHARS
        + CONSOLIDATION_CONTEXT_EVIDENCE_QUOTES_MAX_COUNT * CONSOLIDATION_CONTEXT_EVIDENCE_QUOTE_MAX_CHARS
        + CONSOLIDATION_CONTEXT_ARGUMENTS_MAX_CHARS
        + CONSOLIDATION_CONTEXT_PROMOTION_MAX_CHARS
    )

    assert len(pending_payload["content"]) == CONSOLIDATION_CONTEXT_MEMORY_CONTENT_MAX_CHARS
    assert len(pending_payload["evidence_ids"]) == CONSOLIDATION_CONTEXT_EVIDENCE_IDS_MAX_COUNT
    assert len(pending_payload["evidence_source_ids"]) == CONSOLIDATION_CONTEXT_EVIDENCE_SOURCE_IDS_MAX_COUNT
    assert len(quotes) == CONSOLIDATION_CONTEXT_EVIDENCE_QUOTES_MAX_COUNT
    assert all(len(quote["quote"]) == CONSOLIDATION_CONTEXT_EVIDENCE_QUOTE_MAX_CHARS for quote in quotes)
    assert pending_payload["arguments"] == {"truncated": True}
    assert pending_payload["promotion"] == {"truncated": True}
    assert len(candidate_payload["content"]) == CONSOLIDATION_CONTEXT_CANDIDATE_CONTENT_MAX_CHARS
    assert len(serialized) <= text_budget + 3_000


def test_llm_prompt_exposes_candidate_sensitivity_and_promotion_safety_rules():
    item = _item("mem_a", "Enjoys hiking", sensitivity_labels=["credential"])
    candidate = ConsolidationCandidate(
        anchor_memory_id=item.memory_id,
        memory_id="mem_existing",
        content="Existing health detail",
        score=0.91,
        tier=MemoryTier.long_term.value,
        captured_at=NOW.isoformat(),
        sensitivity_labels=("health",),
    )
    context = _context([item], {item.memory_id: [candidate]})
    response = ConsolidationAgentBatch(decisions=[_archive(item)]).model_dump_json()
    prompts: list[str] = []

    parsed = invoke_consolidation_agent(
        context,
        llm_invoke=lambda prompt: prompts.append(prompt) or response,
    )

    payload = json.loads(format_consolidation_llm_context(context))
    assert payload["candidate_groups"][0]["candidates"][0]["sensitivity_labels"] == ["health"]
    assert parsed.decisions[0].route == "archive"
    blob = _llm_payload_text(prompts[0])
    assert '"sensitivity_labels":["credential"]' in blob
    assert "MUST NOT route promote" in blob
    assert "aboutness=third_party MUST NOT route promote" in blob
    assert "aboutness=unclear is not a veto" in blob
    assert "ambient media dialogue, quoted characters" in blob
    assert "adopted user preference or commitment" in blob
    assert "requires_normalization=true" in blob


def test_pending_required_items_are_flagged_for_inline_normalization():
    processed = _item("mem_processed", "Enjoys hiking")
    required = processed.model_copy(
        update={
            "memory_id": "mem_required",
            "processing_state": ProcessingState.pending,
            "promotion": {
                "required": True,
                "processing_status": "pending_processing",
                "source_attribution": {
                    "subject_entity_id": "user",
                    "subject_attribution": "user",
                },
            },
        }
    )
    payload = json.loads(format_consolidation_llm_context(_context([processed, required], {})))
    by_id = {row["memory_id"]: row for row in payload["memories"]}
    assert by_id["mem_processed"]["requires_normalization"] is False
    assert by_id["mem_required"]["requires_normalization"] is True


def test_consolidation_batch_threshold_defaults_to_twenty(monkeypatch):
    monkeypatch.delenv("MEMORY_CANONICAL_CONSOLIDATION_BATCH_THRESHOLD", raising=False)
    monkeypatch.delenv("MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP", raising=False)
    assert consolidation.DEFAULT_CONSOLIDATION_BATCH_THRESHOLD == 20
    assert consolidation.consolidation_batch_threshold() == 20
    assert consolidation.consolidation_batch_cap() == 20


def test_consolidation_messages_cache_the_planner_prefix_not_the_batch_json():
    item = _item("mem_a", "Enjoys hiking")
    messages = build_consolidation_llm_messages(_context([item], {}))
    prefix = messages[0].content[0]
    suffix = messages[1].content

    assert prefix["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert "MUST NOT route promote" in prefix["text"]
    assert "mem_a" not in prefix["text"]
    assert "Enjoys hiking" not in prefix["text"]
    assert '"memory_id":"mem_a"' in suffix
    assert "Enjoys hiking" in suffix


def test_consolidation_prompt_forbids_age_alone_when_belief_flag_on(monkeypatch):
    item = _item("mem_a", "Enjoys hiking")
    monkeypatch.delenv("MEMORY_BELIEF_MODEL_ENABLED", raising=False)
    off = build_consolidation_llm_messages(_context([item], {}))[0].content[0]["text"]
    assert "age or elapsed time alone" not in off

    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    on = build_consolidation_llm_messages(_context([item], {}))[0].content[0]["text"]
    assert "Do not archive or supersede a row because of age or elapsed time alone" in on


def test_promote_decision_requires_structured_graph_and_durable_basis():
    item = _item("mem_a", "Enjoys hiking")
    with pytest.raises(ValueError, match="graph|subject|predicate"):
        ConsolidationAgentDecision(
            source_memory_id=item.memory_id,
            route="promote",
            memory_text="The user enjoys hiking.",
            evidence_ids=["ev_mem_a"],
            relationship_to_user="self",
            basis_for_memory="explicit",
        )
    with pytest.raises(ValueError, match="basis"):
        _promote(item, basis_for_memory="weak_or_none")


def test_promote_decision_rejects_incoherent_reconciliation_mutations():
    item = _item("mem_a", "Enjoys hiking")
    with pytest.raises(ValueError, match="duplicate"):
        _promote(item, reconciliation="duplicate", target_memory_id="mem_old")
    with pytest.raises(ValueError, match="supersede its target"):
        _promote(item, reconciliation="replace", target_memory_id="mem_old")
    with pytest.raises(ValueError, match="cannot supersede"):
        _promote(item, reconciliation="keep_both", supersedes=["mem_old"])


@pytest.mark.parametrize(
    "decisions",
    [
        [],
        [
            ConsolidationAgentDecision(source_memory_id="mem_a", route="archive"),
            ConsolidationAgentDecision(source_memory_id="mem_a", route="reject"),
        ],
        [ConsolidationAgentDecision(source_memory_id="mem_unknown", route="archive")],
    ],
)
def test_batch_output_must_be_an_exact_partition(decisions):
    context = _context([_item("mem_a", "A"), _item("mem_b", "B")])
    error = _validate_agent_batch(context, ConsolidationAgentBatch(decisions=decisions))
    assert error is not None
    assert error.startswith("output_invalid:")


def test_batch_rejects_evidence_not_owned_by_source():
    item = _item("mem_a", "A")
    decision = _promote(item, evidence_ids=["ev_other"])

    error = _validate_agent_batch(_context([item]), ConsolidationAgentBatch(decisions=[decision]))

    assert error == "output_invalid:evidence_not_owned_by_source:mem_a"


@pytest.mark.parametrize("label", sorted(RESTRICTED_SENSITIVITY_LABELS))
def test_batch_rejects_restricted_sensitivity_promotion(label):
    item = _item("mem_a", "A", sensitivity_labels=[label])

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item)]),
    )

    assert error == "output_invalid:restricted_sensitivity_promotion:mem_a"


def test_batch_never_promotes_a_pending_memory_the_owner_rejected():
    item = _item("mem_a", "The user prefers aisle seats")
    item.promotion = {**(item.promotion or {}), "reviewed": True, "user_review": False}

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item)]),
    )

    assert error == "output_invalid:user_rejected_promotion:mem_a"


def test_batch_rejects_third_party_promotion():
    item = _item("mem_a", "A")

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item, aboutness="third_party")]),
    )

    assert error == "output_invalid:unsafe_aboutness_promotion:mem_a"


def test_batch_rejects_rewriting_authoritative_third_party_source_as_user():
    item = _item("mem_a", "The other speaker works at Acme.").model_copy(
        update={
            "subject_entity_id": "person:other-person",
            "promotion": {
                "source_attribution": {
                    "subject_entity_id": "person:other-person",
                    "subject_attribution": "third_party",
                }
            },
        }
    )

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item)]),
    )

    assert error == "output_invalid:source_subject_contradiction:mem_a"


def test_batch_rejects_changing_authoritative_third_party_entity():
    item = _item("mem_a", "The other speaker works at Acme.").model_copy(
        update={
            "subject_entity_id": "person:other-person",
            "promotion": {
                "source_attribution": {
                    "subject_entity_id": "person:other-person",
                    "subject_attribution": "third_party",
                }
            },
        }
    )

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(
            decisions=[
                _promote(
                    item,
                    subject_entity_id="person:different-person",
                    relationship_to_user="other_speaker",
                    aboutness="user_relationship",
                    basis_for_memory="recurring",
                )
            ]
        ),
    )

    assert error == "output_invalid:source_subject_contradiction:mem_a"


def test_batch_allows_consistent_recurring_third_party_relationship():
    item = _item("mem_a", "The user's partner prefers early flights.").model_copy(
        update={
            "subject_entity_id": "person:partner",
            "promotion": {
                "source_attribution": {
                    "subject_entity_id": "person:partner",
                    "subject_attribution": "third_party",
                }
            },
        }
    )

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(
            decisions=[
                _promote(
                    item,
                    subject_entity_id="person:partner",
                    relationship_to_user="other_speaker",
                    aboutness="user_relationship",
                    basis_for_memory="recurring",
                )
            ]
        ),
    )

    assert error is None


def test_batch_allows_conserved_source_scoped_project_for_owned_work():
    item = _item("mem_a", "The Omi project launch moved to Friday.").model_copy(
        update={
            "subject_entity_id": "source:omi-project",
            "promotion": {
                "source_attribution": {
                    "subject_entity_id": "source:omi-project",
                    "subject_attribution": "third_party",
                    "subject_kind": "entity",
                }
            },
        }
    )

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(
            decisions=[
                _promote(
                    item,
                    subject_entity_id="source:omi-project",
                    relationship_to_user="owned_work",
                    aboutness="user_owned_project",
                )
            ]
        ),
    )

    assert error is None


def test_batch_rejects_non_user_subject_as_self():
    item = _item("mem_a", "The Omi project launch moved to Friday.").model_copy(
        update={
            "subject_entity_id": "source:omi-project",
            "promotion": {
                "source_attribution": {
                    "subject_entity_id": "source:omi-project",
                    "subject_attribution": "third_party",
                    "subject_kind": "entity",
                }
            },
        }
    )

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item, subject_entity_id="source:omi-project")]),
    )

    assert error == "output_invalid:source_subject_contradiction:mem_a"


def test_batch_rejects_promoting_authoritatively_unknown_subject():
    item = _item("mem_a", "Someone mentioned Acme.").model_copy(
        update={
            "subject_entity_id": None,
            "promotion": {
                "source_attribution": {
                    "subject_entity_id": None,
                    "subject_attribution": "unknown",
                }
            },
        }
    )

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item)]),
    )

    assert error == "output_invalid:unknown_source_subject_promotion:mem_a"


def test_batch_rejects_promoting_source_without_authoritative_attribution():
    item = _item("mem_a", "Legacy candidate with no attribution.").model_copy(
        update={
            "promotion": {},
        }
    )

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item)]),
    )

    assert error == "output_invalid:missing_source_attribution:mem_a"


def test_batch_preserves_processed_manual_user_subject():
    item = _item("mem_a", "I explicitly prefer dark mode.").model_copy(
        update={
            "user_asserted": True,
            "subject_entity_id": "user",
            "promotion": {
                "source_attribution": {
                    "subject_entity_id": "user",
                    "subject_attribution": "user",
                    "subject_kind": "user",
                }
            },
        }
    )

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item)]),
    )

    assert error is None


def test_batch_user_asserted_known_third_party_cannot_become_user():
    item = _item("mem_a", "Sarah prefers early flights.").model_copy(
        update={
            "user_asserted": True,
            "subject_entity_id": "person:sarah",
            "promotion": {
                "source_attribution": {
                    "subject_entity_id": "person:sarah",
                    "subject_attribution": "third_party",
                    "subject_kind": "person",
                }
            },
        }
    )

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item)]),
    )

    assert error == "output_invalid:source_subject_contradiction:mem_a"


def test_batch_allows_unclear_aboutness_when_other_authority_is_durable():
    item = _item("mem_a", "A")

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item, aboutness="unclear")]),
    )

    assert error is None


@pytest.mark.parametrize("relationship", ["asking_about", "encountered", "unclear"])
def test_batch_rejects_weak_relationship_promotion(relationship):
    item = _item("mem_a", "A")

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(decisions=[_promote(item, relationship_to_user=relationship)]),
    )

    assert error == "output_invalid:weak_relationship_promotion:mem_a"


def test_batch_allows_recurring_user_relationship_from_other_speaker():
    item = _item("mem_a", "The user's partner prefers early flights.").model_copy(
        update={
            "subject_entity_id": "person:partner",
            "promotion": {
                "source_attribution": {
                    "subject_entity_id": "person:partner",
                    "subject_attribution": "third_party",
                    "subject_kind": "person",
                }
            },
        }
    )

    error = _validate_agent_batch(
        _context([item]),
        ConsolidationAgentBatch(
            decisions=[
                _promote(
                    item,
                    subject_entity_id="person:partner",
                    relationship_to_user="other_speaker",
                    aboutness="user_relationship",
                    basis_for_memory="recurring",
                )
            ]
        ),
    )

    assert error is None


def test_batch_rejects_cross_pending_supersedes():
    first = _item("mem_a", "A")
    second = _item("mem_b", "B")
    decision_a = _promote(
        first,
        reconciliation="replace",
        target_memory_id=second.memory_id,
        supersedes=[second.memory_id],
    )

    error = _validate_agent_batch(
        _context([first, second]),
        ConsolidationAgentBatch(decisions=[decision_a, _archive(second)]),
    )

    assert error == "output_invalid:cross_pending_reference:mem_a"


def test_batch_allows_non_promote_targeting_pending_promote():
    survivor = _item("mem_survivor", "A")
    duplicate = _item("mem_duplicate", "A again")
    archive_duplicate = ConsolidationAgentDecision(
        source_memory_id=duplicate.memory_id,
        route="archive",
        reconciliation="duplicate",
        target_memory_id=survivor.memory_id,
    )

    error = _validate_agent_batch(
        _context([survivor, duplicate]),
        ConsolidationAgentBatch(decisions=[archive_duplicate, _promote(survivor)]),
    )

    assert error is None


def test_batch_rejects_non_promote_targeting_pending_non_promote():
    first = _item("mem_a", "A")
    second = _item("mem_b", "B")
    archive_duplicate = ConsolidationAgentDecision(
        source_memory_id=first.memory_id,
        route="archive",
        reconciliation="duplicate",
        target_memory_id=second.memory_id,
    )

    error = _validate_agent_batch(
        _context([first, second]),
        ConsolidationAgentBatch(decisions=[archive_duplicate, _archive(second)]),
    )

    assert error == "output_invalid:cross_pending_reference:mem_a"


def test_batch_rejects_promote_targeting_pending_promote():
    first = _item("mem_a", "A")
    second = _item("mem_b", "B")
    merge_into_pending = _promote(
        first,
        reconciliation="merge",
        target_memory_id=second.memory_id,
        supersedes=[second.memory_id],
    )

    error = _validate_agent_batch(
        _context([first, second]),
        ConsolidationAgentBatch(decisions=[merge_into_pending, _promote(second)]),
    )

    assert error == "output_invalid:cross_pending_reference:mem_a"


def test_valid_replace_may_only_supersede_hydrated_long_term_candidate():
    source = _item("mem_new", "Lives in Seattle")
    old = _item("mem_old", "Lives in Portland", tier=MemoryTier.long_term)
    candidate = ConsolidationCandidate(
        anchor_memory_id=source.memory_id,
        memory_id=old.memory_id,
        content=old.content or "",
        score=0.9,
        tier=old.tier.value,
        captured_at=old.captured_at.isoformat(),
    )
    decision = _promote(
        source,
        reconciliation="replace",
        target_memory_id=old.memory_id,
        supersedes=[old.memory_id],
    )

    error = _validate_agent_batch(
        _context([source], {source.memory_id: [candidate]}),
        ConsolidationAgentBatch(decisions=[decision]),
    )

    assert error is None


def test_batch_rejects_duplicate_supersede_across_decisions():
    """Two decisions must not supersede the same Long-term candidate.

    Without this batch-level guard the first promotion commits and marks the
    target superseded; the second decision then reaches the apply phase with an
    inactive target and fails, producing a partial-apply maintenance run that
    could have been preflighted.
    """
    source_a = _item("mem_new_a", "Lives in Seattle")
    source_b = _item("mem_new_b", "Moved to Portland")
    old = _item("mem_old", "Lives in Portland", tier=MemoryTier.long_term)
    candidate = ConsolidationCandidate(
        anchor_memory_id="mem_new_a",
        memory_id=old.memory_id,
        content=old.content or "",
        score=0.9,
        tier=old.tier.value,
        captured_at=old.captured_at.isoformat(),
    )
    decision_a = _promote(
        source_a,
        reconciliation="replace",
        target_memory_id=old.memory_id,
        supersedes=[old.memory_id],
    )
    decision_b = _promote(
        source_b,
        reconciliation="replace",
        target_memory_id=old.memory_id,
        supersedes=[old.memory_id],
    )

    error = _validate_agent_batch(
        _context(
            [source_a, source_b],
            {source_a.memory_id: [candidate], source_b.memory_id: [candidate]},
        ),
        ConsolidationAgentBatch(decisions=[decision_a, decision_b]),
    )

    assert error == "output_invalid:duplicate_supersede_target:mem_new_b"


def test_clean_total_batch_routes_advances_watermark_and_logs_text_free_decision(caplog):
    item = _item("mem_a", "Enjoys hiking")
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})
    context = _context([item])
    response = ConsolidationAgentBatch(decisions=[_promote(item)])

    with caplog.at_level(logging.INFO, logger=consolidation.__name__):
        with (
            patch(
                "utils.memory.canonical_consolidation.resolve_memory_system",
                return_value=MemorySystem.CANONICAL,
            ),
            patch(
                "utils.memory.canonical_consolidation.list_pending_consolidation_items",
                return_value=[item],
            ),
            patch(
                "utils.memory.canonical_consolidation.gather_consolidation_candidates",
                return_value=context,
            ),
            patch(
                "utils.memory.canonical_consolidation.invoke_consolidation_agent",
                return_value=response,
            ),
            patch(
                "utils.memory.canonical_consolidation.apply_consolidation_decision",
                return_value=[item.memory_id],
            ) as apply_route,
        ):
            report = run_canonical_consolidation(UID, db_client=db, run_id="run-1", now=NOW)

    assert report.promoted_memory_ids == [item.memory_id]
    assert report.batched_memory_ids == [item.memory_id]
    assert report.watermark_blocked is False
    assert report.last_consolidation_run_at == NOW
    apply_route.assert_called_once()
    messages = [
        record.getMessage() for record in caplog.records if "canonical_memory_decision_path.v1" in record.getMessage()
    ]
    assert len(messages) == 1
    event = json.loads(messages[0].split("canonical_memory_decision_path.v1 ", 1)[1])
    assert event == {
        "aboutness": "primary_user",
        "basis_for_memory": "explicit",
        "confidence": "high",
        "memory_id": item.memory_id,
        "reason_code": "create:self:primary_user:explicit",
        "reconciliation": "create",
        "relationship_to_user": "self",
        "route": "promote",
        "stage": "promotion",
        "status": "applied",
        "uid": UID,
    }
    assert item.content not in messages[0]


def test_one_pass_caps_llm_batches_and_leaves_overflow_for_next_pass():
    items = [_item(f"mem_{index}", f"Observation {index}") for index in range(11)]
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})

    def context_for_batch(uid, pending_batch, **kwargs):
        assert uid == UID
        return _context(pending_batch)

    def response_for_batch(context, **kwargs):
        assert len(context.pending_items) == 1
        return ConsolidationAgentBatch(decisions=[_archive(context.pending_items[0])])

    with (
        patch(
            "utils.memory.canonical_consolidation.resolve_memory_system",
            return_value=MemorySystem.CANONICAL,
        ),
        patch(
            "utils.memory.canonical_consolidation.list_pending_consolidation_items",
            return_value=items,
        ),
        patch(
            "utils.memory.canonical_consolidation.consolidation_batch_cap",
            return_value=1,
        ),
        patch(
            "utils.memory.canonical_consolidation.max_consolidation_batches_per_pass",
            return_value=10,
        ),
        patch(
            "utils.memory.canonical_consolidation.gather_consolidation_candidates",
            side_effect=context_for_batch,
        ),
        patch(
            "utils.memory.canonical_consolidation.invoke_consolidation_agent",
            side_effect=response_for_batch,
        ),
        patch(
            "utils.memory.canonical_consolidation.apply_consolidation_decision",
            side_effect=lambda uid, *, decision, **kwargs: [decision.source_memory_id],
        ) as apply_route,
    ):
        report = run_canonical_consolidation(UID, db_client=db, run_id="run-all", now=NOW)

    assert report.trigger_reason == "pending_items"
    assert report.batched_memory_ids == [item.memory_id for item in items[:10]]
    assert report.archived_memory_ids == [item.memory_id for item in items[:10]]
    assert apply_route.call_count == 10


def test_query_cap_overflow_remains_due_on_the_next_scheduler_pass():
    selected = _item("mem-selected", "Selected by the first bounded query")
    overflow = _item("mem-overflow", "Overflow from the first bounded query")
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})

    def context_for_batch(uid, pending_batch, **kwargs):
        assert uid == UID
        return _context(pending_batch)

    def response_for_batch(context, **kwargs):
        return ConsolidationAgentBatch(decisions=[_archive(context.pending_items[0])])

    with (
        patch(
            "utils.memory.canonical_consolidation.resolve_memory_system",
            return_value=MemorySystem.CANONICAL,
        ),
        patch(
            "utils.memory.canonical_consolidation.list_pending_consolidation_items",
            side_effect=[[selected], [overflow]],
        ),
        patch(
            "utils.memory.canonical_consolidation.gather_consolidation_candidates",
            side_effect=context_for_batch,
        ),
        patch(
            "utils.memory.canonical_consolidation.invoke_consolidation_agent",
            side_effect=response_for_batch,
        ),
        patch(
            "utils.memory.canonical_consolidation.apply_consolidation_decision",
            side_effect=lambda uid, *, decision, **kwargs: [decision.source_memory_id],
        ),
    ):
        first = run_canonical_consolidation(UID, db_client=db, run_id="run-capped-1", now=NOW)
        second = run_canonical_consolidation(
            UID,
            db_client=db,
            run_id="run-capped-2",
            now=NOW + timedelta(hours=1),
        )

    assert first.batched_memory_ids == [selected.memory_id]
    assert second.trigger_reason == "pending_items"
    assert second.skipped_reason is None
    assert second.batched_memory_ids == [overflow.memory_id]


def test_run_applies_promote_before_non_promote_pending_dependent():
    survivor = _item("mem_survivor", "Enjoys hiking")
    duplicate = _item("mem_duplicate", "Also enjoys hiking")
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})
    context = _context([survivor, duplicate])
    archive_duplicate = ConsolidationAgentDecision(
        source_memory_id=duplicate.memory_id,
        route="archive",
        reconciliation="duplicate",
        target_memory_id=survivor.memory_id,
    )
    response = ConsolidationAgentBatch(decisions=[archive_duplicate, _promote(survivor)])
    applied_order: list[str] = []

    def record_apply(uid, *, decision, **kwargs):
        applied_order.append(decision.source_memory_id)
        return [decision.source_memory_id]

    with (
        patch(
            "utils.memory.canonical_consolidation.resolve_memory_system",
            return_value=MemorySystem.CANONICAL,
        ),
        patch(
            "utils.memory.canonical_consolidation.list_pending_consolidation_items",
            return_value=[survivor, duplicate],
        ),
        patch(
            "utils.memory.canonical_consolidation.gather_consolidation_candidates",
            return_value=context,
        ),
        patch(
            "utils.memory.canonical_consolidation.invoke_consolidation_agent",
            return_value=response,
        ),
        patch(
            "utils.memory.canonical_consolidation.apply_consolidation_decision",
            side_effect=record_apply,
        ),
    ):
        report = run_canonical_consolidation(UID, db_client=db, run_id="run-1", now=NOW)

    assert applied_order == [survivor.memory_id, duplicate.memory_id]
    assert report.promoted_memory_ids == [survivor.memory_id]
    assert report.archived_memory_ids == [duplicate.memory_id]
    assert report.watermark_blocked is False


def test_incomplete_output_blocks_all_mutation_and_logs_each_memory_without_text(caplog):
    items = [_item("mem_a", "Private observation A"), _item("mem_b", "Private observation B")]
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})

    with caplog.at_level(logging.INFO, logger=consolidation.__name__):
        with (
            patch(
                "utils.memory.canonical_consolidation.resolve_memory_system",
                return_value=MemorySystem.CANONICAL,
            ),
            patch(
                "utils.memory.canonical_consolidation.list_pending_consolidation_items",
                return_value=items,
            ),
            patch(
                "utils.memory.canonical_consolidation.gather_consolidation_candidates",
                return_value=_context(items),
            ),
            patch(
                "utils.memory.canonical_consolidation.invoke_consolidation_agent",
                return_value=ConsolidationAgentBatch(decisions=[_archive(items[0])]),
            ),
            patch("utils.memory.canonical_consolidation.apply_consolidation_decision") as apply_route,
        ):
            report = run_canonical_consolidation(UID, db_client=db, run_id="run-1", now=NOW)

    assert report.watermark_blocked is True
    assert report.batched_memory_ids == []
    assert report.last_consolidation_run_at is None
    apply_route.assert_not_called()
    messages = [
        record.getMessage() for record in caplog.records if "canonical_memory_decision_path.v1" in record.getMessage()
    ]
    events = [json.loads(message.split("canonical_memory_decision_path.v1 ", 1)[1]) for message in messages]
    assert events == [
        {
            "memory_id": "mem_a",
            "reason_code": "output_invalid:partition_mismatch",
            "route": "archive",
            "stage": "promotion",
            "status": "decision_invalid",
            "uid": UID,
        },
        {
            "memory_id": "mem_b",
            "reason_code": "output_invalid:partition_mismatch",
            "route": "none",
            "stage": "promotion",
            "status": "decision_invalid",
            "uid": UID,
        },
    ]
    assert all(item.content not in " ".join(messages) for item in items)


def test_recurrence_handoff_failure_blocks_routes_and_watermark():
    item = _item("mem_loop", "Investor update remains unresolved")
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})
    signal = CanonicalRecurrenceSignal(
        signal_id="observation-1",
        title="Investor update",
        objective="Send the revised investor update",
        anchor_task_description="Prepare the investor email",
        occurrence_count=2,
        distinct_day_count=2,
        unresolved=True,
        confidence=0.9,
        first_seen_at=NOW - timedelta(days=1),
        last_seen_at=NOW,
        evidence_refs=[
            EvidenceRef(
                kind=EvidenceKind.memory_item,
                id=item.memory_id,
                scope=EvidenceScope.canonical,
            )
        ],
    )
    response = ConsolidationAgentBatch(decisions=[_archive(item)], recurrence_signals=[signal])

    with (
        patch(
            "utils.memory.canonical_consolidation.resolve_memory_system",
            return_value=MemorySystem.CANONICAL,
        ),
        patch(
            "utils.memory.canonical_consolidation.list_pending_consolidation_items",
            return_value=[item],
        ),
        patch(
            "utils.memory.canonical_consolidation.gather_consolidation_candidates",
            return_value=_context([item]),
        ),
        patch(
            "utils.memory.canonical_consolidation.invoke_consolidation_agent",
            return_value=response,
        ),
        patch("utils.memory.canonical_consolidation.apply_consolidation_decision") as apply_route,
    ):
        report = run_canonical_consolidation(
            UID,
            db_client=db,
            run_id="run-1",
            now=NOW,
            recurrence_signal_sink=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")),
        )

    assert report.watermark_blocked is True
    assert report.last_consolidation_run_at is None
    apply_route.assert_not_called()


def test_poison_source_has_bounded_llm_retries_then_terminal_review_without_starving_later_batch():
    poison = _item("mem_poison", "Requires manual interpretation")
    healthy = _item("mem_healthy", "Ordinary source context")
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})
    pending_by_run = [[poison, healthy], [poison, healthy], [poison]]
    llm_sources: list[str] = []
    applied_routes: list[tuple[str, str]] = []

    def invoke(context, **_kwargs):
        item = context.pending_items[0]
        llm_sources.append(item.memory_id)
        if item.memory_id == poison.memory_id:
            return ConsolidationAgentBatch(decisions=[])
        return ConsolidationAgentBatch(decisions=[_archive(item)])

    def apply(uid, *, decision, **_kwargs):
        assert uid == UID
        applied_routes.append((decision.source_memory_id, decision.route))
        return [decision.source_memory_id]

    with (
        patch.object(consolidation, "resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch.object(
            consolidation,
            "list_pending_consolidation_items",
            side_effect=pending_by_run,
        ),
        patch.object(consolidation, "consolidation_batch_cap", return_value=2),
        patch.object(
            consolidation,
            "gather_consolidation_candidates",
            side_effect=lambda uid, items, **_kwargs: _context(items),
        ),
        patch.object(consolidation, "invoke_consolidation_agent", side_effect=invoke),
        patch.object(consolidation, "apply_consolidation_decision", side_effect=apply),
    ):
        first = run_canonical_consolidation(UID, db_client=db, run_id="retry-1", now=NOW)
        second = run_canonical_consolidation(
            UID,
            db_client=db,
            run_id="retry-2",
            now=NOW + timedelta(minutes=1),
        )
        third = run_canonical_consolidation(
            UID,
            db_client=db,
            run_id="retry-3",
            now=NOW + timedelta(minutes=2),
        )

    assert first.batched_memory_ids == []
    assert first.retryable_memory_ids == [poison.memory_id, healthy.memory_id]
    assert first.watermark_blocked is True
    assert second.batched_memory_ids == [healthy.memory_id]
    assert second.archived_memory_ids == [healthy.memory_id]
    assert second.retryable_memory_ids == [poison.memory_id]
    assert third.review_memory_ids == [poison.memory_id]
    assert third.retryable_memory_ids == []
    assert third.watermark_blocked is True
    assert llm_sources.count(poison.memory_id) == consolidation.MAX_CONSOLIDATION_FAILURE_ATTEMPTS
    assert applied_routes == [
        (healthy.memory_id, "archive"),
        (poison.memory_id, "review"),
    ]
    retry_docs = {
        payload["memory_id"]: payload
        for path, payload in db.docs.items()
        if "/memory_runs/consolidation_retry_" in path
    }
    assert retry_docs[poison.memory_id]["attempt_count"] == consolidation.MAX_CONSOLIDATION_FAILURE_ATTEMPTS
    assert retry_docs[poison.memory_id]["status"] == "terminal_review"
    assert healthy.memory_id not in retry_docs


def test_exhausted_apply_failure_is_quarantined_and_skipped_without_starving_later_source():
    poison = _item("mem_poison", "Cannot be applied safely")
    healthy = _item("mem_healthy", "Retain as source context")
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})
    invoked_batches: list[list[str]] = []

    def invoke(context, **_kwargs):
        invoked_batches.append([item.memory_id for item in context.pending_items])
        item = context.pending_items[0]
        if item.memory_id == poison.memory_id:
            return ConsolidationAgentBatch(decisions=[])
        return ConsolidationAgentBatch(decisions=[_archive(item)])

    def apply(uid, *, decision, quarantine=False, **_kwargs):
        assert uid == UID
        if decision.source_memory_id == poison.memory_id and not quarantine:
            raise consolidation.ConsolidationApplySkipped("injected terminal apply conflict")
        return [decision.source_memory_id]

    with (
        patch.object(consolidation, "resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch.object(
            consolidation,
            "list_pending_consolidation_items",
            side_effect=[[poison], [poison, healthy]],
        ),
        patch.object(consolidation, "MAX_CONSOLIDATION_FAILURE_ATTEMPTS", 1),
        patch.object(consolidation, "consolidation_batch_cap", return_value=1),
        patch.object(
            consolidation,
            "gather_consolidation_candidates",
            side_effect=lambda uid, items, **_kwargs: _context(items),
        ),
        patch.object(consolidation, "invoke_consolidation_agent", side_effect=invoke),
        patch.object(consolidation, "apply_consolidation_decision", side_effect=apply),
    ):
        first = run_canonical_consolidation(UID, db_client=db, run_id="quarantine-1", now=NOW)
        second = run_canonical_consolidation(
            UID,
            db_client=db,
            run_id="quarantine-2",
            now=NOW + timedelta(minutes=1),
        )

    assert first.quarantined_memory_ids == [poison.memory_id]
    assert first.watermark_blocked is True
    assert second.quarantined_memory_ids == [poison.memory_id]
    assert second.batched_memory_ids == [healthy.memory_id]
    assert second.archived_memory_ids == [healthy.memory_id]
    assert invoked_batches == [[poison.memory_id], [healthy.memory_id]]
    retry_docs = {
        payload["memory_id"]: payload
        for path, payload in db.docs.items()
        if "/memory_runs/consolidation_retry_" in path
    }
    assert retry_docs[poison.memory_id]["status"] == "quarantined"


def test_terminal_store_failure_advances_durable_scan_cursor_past_query_window():
    poison = _item("mem_poison", "Cannot settle while its evidence store is unavailable")
    healthy = _item("mem_healthy", "A later healthy item")
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})
    cursors: list[tuple[datetime, str] | None] = []

    def list_pending(uid, *, start_after=None, **_kwargs):
        assert uid == UID
        cursors.append(start_after)
        return [poison] if start_after is None else [healthy]

    def invoke(context, **_kwargs):
        item = context.pending_items[0]
        return (
            ConsolidationAgentBatch(decisions=[])
            if item.memory_id == poison.memory_id
            else ConsolidationAgentBatch(decisions=[_archive(item)])
        )

    def apply(uid, *, decision, **_kwargs):
        assert uid == UID
        if decision.source_memory_id == poison.memory_id:
            raise consolidation.ConsolidationApplySkipped("injected evidence-store conflict")
        return [decision.source_memory_id]

    with (
        patch.object(consolidation, "resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch.object(consolidation, "list_pending_consolidation_items", side_effect=list_pending),
        patch.object(consolidation, "MAX_CONSOLIDATION_FAILURE_ATTEMPTS", 1),
        patch.object(consolidation, "consolidation_batch_cap", return_value=1),
        patch.object(
            consolidation,
            "gather_consolidation_candidates",
            side_effect=lambda uid, items, **_kwargs: _context(items),
        ),
        patch.object(consolidation, "invoke_consolidation_agent", side_effect=invoke),
        patch.object(consolidation, "apply_consolidation_decision", side_effect=apply),
    ):
        first = run_canonical_consolidation(UID, db_client=db, run_id="cursor-1", now=NOW)
        second = run_canonical_consolidation(
            UID,
            db_client=db,
            run_id="cursor-2",
            now=NOW + timedelta(minutes=1),
        )

    assert first.retryable_memory_ids == [poison.memory_id]
    assert first.quarantined_memory_ids == []
    assert second.batched_memory_ids == [healthy.memory_id]
    assert second.archived_memory_ids == [healthy.memory_id]
    assert cursors == [None, (poison.captured_at, poison.memory_id)]
    assert consolidation._scan_cursor_document_path(UID) not in db.docs


def test_attempt_claim_is_durable_before_work_and_enforces_concurrent_cost_bound():
    item = _item("mem_claimed", "One exact revision")
    db = _FakeDb()

    first, first_claimed = consolidation._claim_retry_state(
        UID,
        item,
        lease_owner="runner-a",
        now=NOW,
        db_client=db,
    )
    concurrent, concurrent_claimed = consolidation._claim_retry_state(
        UID,
        item,
        lease_owner="runner-b",
        now=NOW,
        db_client=db,
    )

    assert first_claimed is True
    assert first.attempt_count == 1
    assert first.status == "in_progress"
    assert concurrent_claimed is False
    assert concurrent.attempt_count == 1

    expired_time = NOW + timedelta(seconds=consolidation.CONSOLIDATION_ATTEMPT_LEASE_SECONDS + 1)
    state, expired_claimed = consolidation._claim_retry_state(
        UID,
        item,
        lease_owner="runner-b",
        now=expired_time,
        db_client=db,
    )
    assert expired_claimed is True
    assert state.attempt_count == 2
    state = consolidation._transition_retry_state(
        UID,
        item,
        status="retryable",
        error_code="output_invalid:partition_mismatch",
        now=expired_time,
        db_client=db,
        expected_lease_owner="runner-b",
    )
    state, claimed = consolidation._claim_retry_state(
        UID,
        item,
        lease_owner="runner-c",
        now=expired_time + timedelta(minutes=1),
        db_client=db,
    )
    assert claimed is True
    assert state.attempt_count == 3
    consolidation._transition_retry_state(
        UID,
        item,
        status="retryable",
        error_code="output_invalid:partition_mismatch",
        now=expired_time + timedelta(minutes=1),
        db_client=db,
        expected_lease_owner="runner-c",
    )

    exhausted, claimed = consolidation._claim_retry_state(
        UID,
        item,
        lease_owner="runner-d",
        now=expired_time + timedelta(minutes=2),
        db_client=db,
    )
    assert claimed is False
    assert exhausted.attempt_count == consolidation.MAX_CONSOLIDATION_FAILURE_ATTEMPTS


def test_attempt_claim_accepts_a_longer_flex_lease():
    item = _item("mem_flex_claimed", "One Flex revision")
    db = _FakeDb()

    state, claimed = consolidation._claim_retry_state(
        UID,
        item,
        lease_owner="flex-runner",
        now=NOW,
        db_client=db,
        lease_seconds=1_200,
    )

    assert claimed is True
    assert state.lease_expires_at == NOW + timedelta(seconds=1_200)


def test_deferred_flex_attempt_releases_lease_without_consuming_quality_budget():
    item = _item("mem_flex_deferred", "Retry this Flex revision later")
    db = _FakeDb()
    claimed_state, claimed = consolidation._claim_retry_state(
        UID,
        item,
        lease_owner="flex-runner",
        now=NOW,
        db_client=db,
        lease_seconds=1_200,
    )
    assert claimed is True
    assert claimed_state.lease_owner is not None

    released = consolidation._release_deferred_retry_state_transaction(
        db.transaction(),
        db,
        UID,
        item,
        "flex_deferred:PromotionFlexDeferred",
        NOW,
        claimed_state.lease_owner,
    )

    assert released.status == "retryable"
    assert released.attempt_count == 0
    assert released.lease_owner is None
    assert released.lease_expires_at is None


def test_run_consolidation_defers_flex_unavailability_without_applying_or_spending_attempt():
    from utils.memory.promotion_flex import PromotionFlexDeferred

    item = _item("mem_flex_unavailable", "Retry this unavailable Flex call")
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})

    def defer(_prompt):
        raise PromotionFlexDeferred("RateLimitError")

    with (
        patch(
            "utils.memory.canonical_consolidation.list_pending_consolidation_items",
            return_value=[item],
        ),
        patch(
            "utils.memory.canonical_consolidation.gather_consolidation_candidates",
            return_value=_context([item]),
        ),
        patch("utils.memory.canonical_consolidation.apply_consolidation_decision") as apply_route,
        pytest.raises(PromotionFlexDeferred, match="RateLimitError"),
    ):
        run_canonical_consolidation(
            UID,
            db_client=db,
            run_id="flex-deferred",
            now=NOW,
            llm_invoke=defer,
            attempt_lease_seconds=1_200,
        )

    state = consolidation._read_retry_state(UID, item, db_client=db)
    assert state is not None
    assert state.attempt_count == 0
    assert state.status == "retryable"
    apply_route.assert_not_called()


def test_run_consolidation_stops_the_uid_after_flex_deferral(monkeypatch):
    from utils.memory.promotion_flex import PromotionFlexDeferred

    first = _item("mem_flex_first", "First batch is deferred")
    second = _item("mem_flex_second", "Second batch must not run")
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})
    gathered_ids: list[str] = []

    def defer(_prompt):
        raise PromotionFlexDeferred("job_budget")

    def gather(uid, pending_items, **_kwargs):
        gathered_ids.extend(item.memory_id for item in pending_items)
        return _context(pending_items)

    monkeypatch.setenv("MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP", "1")
    with (
        patch(
            "utils.memory.canonical_consolidation.list_pending_consolidation_items",
            return_value=[first, second],
        ),
        patch(
            "utils.memory.canonical_consolidation.gather_consolidation_candidates",
            side_effect=gather,
        ),
        pytest.raises(PromotionFlexDeferred, match="job_budget"),
    ):
        run_canonical_consolidation(
            UID,
            db_client=db,
            run_id="flex-stop-page",
            now=NOW,
            llm_invoke=defer,
            attempt_lease_seconds=1_200,
        )

    assert gathered_ids == [first.memory_id]
    assert consolidation._read_retry_state(UID, second, db_client=db) is None


def test_new_revision_does_not_inherit_old_revision_quarantine():
    item = _item("mem_revised", "Original revision")
    db = _FakeDb()
    claimed_state, claimed = consolidation._claim_retry_state(
        UID,
        item,
        lease_owner="runner-a",
        now=NOW,
        db_client=db,
    )
    assert claimed is True
    consolidation._transition_retry_state(
        UID,
        item,
        status="quarantined",
        error_code="output_invalid:partition_mismatch",
        now=NOW,
        db_client=db,
        expected_lease_owner=claimed_state.lease_owner,
    )
    revised = item.model_copy(
        update={
            "item_revision": item.item_revision + 1,
            "content": "Corrected revision",
            "content_hash": "corrected-content-hash",
        }
    )

    assert consolidation._read_retry_state(UID, revised, db_client=db) is None
    revised_state, revised_claimed = consolidation._claim_retry_state(
        UID,
        revised,
        lease_owner="runner-b",
        now=NOW + timedelta(minutes=1),
        db_client=db,
    )
    assert revised_claimed is True
    assert revised_state.attempt_count == 1


def test_terminal_review_retry_state_is_not_reported_as_quarantine():
    item = _item("mem_terminal_review", "Already escalated")
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{UID}/memory_state/apply_control": control.model_dump(mode="python")})
    state, claimed = consolidation._claim_retry_state(
        UID,
        item,
        lease_owner="runner-a",
        now=NOW,
        db_client=db,
    )
    assert claimed is True
    consolidation._transition_retry_state(
        UID,
        item,
        status="terminal_review",
        error_code="output_invalid:partition_mismatch",
        now=NOW,
        db_client=db,
        expected_lease_owner=state.lease_owner,
    )

    with (
        patch.object(consolidation, "resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch.object(consolidation, "list_pending_consolidation_items", return_value=[item]),
        patch.object(consolidation, "invoke_consolidation_agent") as invoke,
        patch.object(consolidation, "apply_consolidation_decision") as apply_route,
    ):
        report = run_canonical_consolidation(UID, db_client=db, run_id="terminal-state", now=NOW)

    assert report.review_memory_ids == [item.memory_id]
    assert report.quarantined_memory_ids == []
    assert report.errors == ["consolidation_terminal_review_source_still_pending"]
    invoke.assert_not_called()
    apply_route.assert_not_called()
