"""Flag-gated per-uid classification of legacy rows that carry no belief_class.

Callable so unit tests can drive it with a fake LLM and store. The admin script
under ``backend/scripts/backfill_belief_classes.py`` is the operator entry.
Writes go through the existing apply path; status, tier, expires_at, and content
are never changed.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field, field_validator

from models.memory_contracts import LifecycleState
from models.product_memory import MemoryItem, MemoryItemStatus
from utils.memory.belief_model import (
    HALF_LIFE_DAYS_BY_CLASS,
    KNOWN_SUBJECT_SCOPES,
    SUBJECT_SCOPE_ALIASES,
    belief_model_enabled,
    horizon_from_extraction,
)

logger = logging.getLogger(__name__)

# Cheap binary/light classification lane (gpt-5-nano). Same feature the category
# helper already uses; do not add a model.
BELIEF_BACKFILL_LLM_FEATURE = "memory_category"
BELIEF_BACKFILL_BATCH_SIZE = 40
BELIEF_BACKFILL_MUTATION_KIND = "belief_backfill"
_ACTIVE_OR_HIDDEN = {MemoryItemStatus.active.value, MemoryItemStatus.hidden.value}

ItemReader = Callable[[str, Any], Sequence[Any]]
ClassifierFn = Callable[[Sequence[Any], Optional[str]], Sequence["BeliefBackfillRow"]]
ApplierFn = Callable[[str, Any, "BeliefBackfillRow", Any], Any]


class BeliefBackfillRow(BaseModel):
    memory_id: str
    belief_class: str
    subject_scope: str
    half_life_days: Optional[float] = None
    valid_to: Optional[datetime] = None

    @field_validator("belief_class")
    @classmethod
    def validate_belief_class(cls, value: str) -> str:
        if value not in HALF_LIFE_DAYS_BY_CLASS:
            raise ValueError(f"unknown belief_class: {value}")
        return value

    @field_validator("subject_scope")
    @classmethod
    def validate_subject_scope(cls, value: str) -> str:
        scope = (value or "").strip().lower()
        scope = SUBJECT_SCOPE_ALIASES.get(scope, scope)
        if scope not in KNOWN_SUBJECT_SCOPES:
            raise ValueError(f"unknown subject_scope: {value}")
        return scope


class BeliefBackfillBatch(BaseModel):
    items: List[BeliefBackfillRow] = Field(default_factory=list)


@dataclass
class BeliefBackfillReport:
    uid: str
    dry_run: bool
    classified: int = 0
    written: int = 0
    skipped: int = 0
    class_counts: Dict[str, int] = field(default_factory=dict)
    scope_counts: Dict[str, int] = field(default_factory=dict)


def _item_status(item: Any) -> Optional[str]:
    status = getattr(item, "status", None)
    raw = getattr(status, "value", status)
    return raw if isinstance(raw, str) else None


def _lifecycle_for_item(item: Any) -> str:
    if _item_status(item) == MemoryItemStatus.hidden.value:
        return LifecycleState.hidden.value
    return LifecycleState.active.value


def _unclassified(item: Any) -> bool:
    if _item_status(item) not in _ACTIVE_OR_HIDDEN:
        return False
    return not getattr(item, "belief_class", None)


def _default_item_reader(uid: str, db_client: Any) -> Sequence[MemoryItem]:
    from database.memory_collections import MemoryCollections

    items: List[MemoryItem] = []
    for snapshot in db_client.collection(MemoryCollections(uid=uid).memory_items).stream():
        raw = snapshot.to_dict() if getattr(snapshot, "to_dict", None) else None
        if not isinstance(raw, dict):
            continue
        try:
            item = MemoryItem.model_validate(raw)
        except Exception:
            continue
        if item.uid != uid:
            continue
        items.append(item)
    return items


def _default_classifier(rows: Sequence[Any], user_name: Optional[str] = None) -> Sequence[BeliefBackfillRow]:
    from langchain_core.output_parsers import PydanticOutputParser

    from utils.llm.clients import get_llm

    if not rows:
        return []
    parser = PydanticOutputParser(pydantic_object=BeliefBackfillBatch)
    listed = "\n".join(f"- id={getattr(row, 'memory_id', '')} content={getattr(row, 'content', '')!r}" for row in rows)
    prompt = (
        "Classify each existing memory row. Do not rewrite content.\n"
        f"Account owner name: {user_name or 'unknown'}.\n"
        "belief_class: identity | relationship | preference | state | plan | episodic | "
        "meta_standing (durable instruction to Omi) | meta_residue (session leftover).\n"
        "subject_scope: primary_user (about the owner) | third_party (another person) | "
        "media_screen (video, article, game, or on-screen content only).\n"
        "Optional half_life_days override from wording (e.g. this week → 7). "
        "Optional valid_to ISO timestamp when the text names an end date.\n"
        f"{parser.get_format_instructions()}\n"
        f"ROWS:\n{listed}"
    )
    content = get_llm(BELIEF_BACKFILL_LLM_FEATURE).invoke([("human", prompt)]).content
    text = "\n".join(str(part) for part in content) if isinstance(content, list) else str(content)
    parsed = parser.parse(text)
    batch = BeliefBackfillBatch.model_validate(parsed)
    allowed = {getattr(row, "memory_id", None) for row in rows}
    return [row for row in batch.items if row.memory_id in allowed]


def patch_for_belief_backfill(item: Any, classification: BeliefBackfillRow) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (logical_updates, extra_item_updates). Never touches status/tier/content."""
    user_asserted = bool(getattr(item, "user_asserted", False))
    resolved_class, resolved_half_life = horizon_from_extraction(
        belief_class=classification.belief_class,
        half_life_days_override=classification.half_life_days,
        user_asserted=user_asserted,
    )
    logical: Dict[str, Any] = {
        "result_status": _lifecycle_for_item(item),
        "subject_scope": classification.subject_scope,
        "metadata": {"mutation_kind": BELIEF_BACKFILL_MUTATION_KIND},
    }
    extra: Dict[str, Any] = {
        "belief_class": resolved_class,
        "half_life_days": None if user_asserted else resolved_half_life,
    }
    if classification.valid_to is not None:
        logical["valid_to"] = classification.valid_to
    return logical, extra


def _default_applier(uid: str, item: Any, classification: BeliefBackfillRow, db_client: Any) -> Any:
    from utils.memory.canonical_memory_adapter import apply_canonical_user_mutation

    def build_patch(_item: MemoryItem, _now: datetime) -> tuple[Dict[str, Any], Dict[str, Any]]:
        return patch_for_belief_backfill(item, classification)

    _previous, updated = apply_canonical_user_mutation(
        uid,
        classification.memory_id,
        mutation_kind=BELIEF_BACKFILL_MUTATION_KIND,
        build_patch=build_patch,
        db_client=db_client,
    )
    return updated


def backfill_belief_classes(
    uid: str,
    *,
    db_client: Any = None,
    dry_run: bool = True,
    batch_size: int = BELIEF_BACKFILL_BATCH_SIZE,
    user_name: Optional[str] = None,
    item_reader: Optional[ItemReader] = None,
    classifier: Optional[ClassifierFn] = None,
    applier: Optional[ApplierFn] = None,
) -> BeliefBackfillReport:
    """Classify ``belief_class is None`` rows for one uid. Idempotent. Dry-run writes nothing."""
    if not uid or not str(uid).strip():
        raise ValueError("--uid is required")
    report = BeliefBackfillReport(uid=uid, dry_run=dry_run)
    if not dry_run and not belief_model_enabled():
        raise ValueError("MEMORY_BELIEF_MODEL_ENABLED must be true to write a belief backfill")

    client = db_client
    if client is None:
        from database._client import db as default_db_client

        client = default_db_client
    reader = item_reader or (lambda _uid, _db: _default_item_reader(_uid, client))
    classify = classifier or (lambda rows, name: _default_classifier(rows, name))
    apply_row = applier or (
        lambda _uid, item, classification, _db: _default_applier(_uid, item, classification, client)
    )

    pending = [item for item in reader(uid, client) if _unclassified(item)]
    class_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    size = max(1, batch_size)
    for offset in range(0, len(pending), size):
        batch = pending[offset : offset + size]
        try:
            classified_rows = list(classify(batch, user_name))
        except Exception:
            logger.warning("belief backfill classify failed uid=%s offset=%s", uid, offset, exc_info=False)
            report.skipped += len(batch)
            continue
        by_id = {row.memory_id: row for row in classified_rows}
        for item in batch:
            memory_id = getattr(item, "memory_id", None)
            classification = by_id.get(memory_id) if isinstance(memory_id, str) else None
            if classification is None:
                report.skipped += 1
                continue
            report.classified += 1
            class_counts[classification.belief_class] += 1
            scope_counts[classification.subject_scope] += 1
            if dry_run:
                continue
            original_status = _item_status(item)
            try:
                apply_row(uid, item, classification, client)
            except Exception:
                logger.warning("belief backfill apply failed memory_id=%s", memory_id, exc_info=False)
                report.skipped += 1
                continue
            report.written += 1
            if original_status is not None and _item_status(item) != original_status:
                logger.warning("belief backfill must not change status memory_id=%s", memory_id)
    report.class_counts = dict(class_counts)
    report.scope_counts = dict(scope_counts)
    return report
