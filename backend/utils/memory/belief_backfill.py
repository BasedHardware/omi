"""Flag-gated per-uid classification of legacy rows that carry no belief_class.

Callable so unit tests can drive it with a fake LLM and store. The admin script
under ``backend/scripts/backfill_belief_classes.py`` is the operator entry.
Writes go through the existing apply path; status, tier, expires_at, and content
are never changed.
"""

from __future__ import annotations

import logging
import inspect
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, MutableMapping, Optional, Sequence

from pydantic import BaseModel, Field, field_validator, model_validator

from models.memory_contracts import LifecycleState
from models.product_memory import MemoryItem, MemoryItemStatus
from utils.memory.belief_model import (
    HALF_LIFE_DAYS_BY_CLASS,
    belief_automation_enabled,
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

ItemReader = Callable[..., Sequence[Any]]
ClassifierFn = Callable[[Sequence[Any], Optional[str]], Sequence["BeliefBackfillRow"]]
ApplierFn = Callable[[str, Any, "BeliefBackfillRow", Any], Any]
CheckpointWriter = Callable[[MutableMapping[str, Any]], None]


class BeliefBackfillPage(list):
    """A bounded physical page with a cursor independent of valid rows."""

    def __init__(self, items: Sequence[Any], *, next_cursor: Optional[str], scanned: int, errors: int, has_more: bool):
        super().__init__(items)
        self.next_cursor = next_cursor
        self.scanned = scanned
        self.errors = errors
        self.has_more = has_more


class BeliefBackfillRow(BaseModel):
    memory_id: str
    """A classification-only result.

    ``subject_scope`` and ``valid_to`` are accepted for decoding old operator
    artifacts, but are deliberately ignored by every mutation path. New
    classifiers must return only the class and optional horizon override.
    ``unknown`` is a terminal, explicit result and is never coerced to a class.
    """

    classification_status: str = "classified"
    belief_class: Optional[str] = None
    half_life_days: Optional[float] = None
    # Compatibility-only fields. These are not part of the mutation contract.
    subject_scope: Optional[str] = None
    valid_to: Optional[datetime] = None

    @field_validator("belief_class")
    @classmethod
    def validate_belief_class(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in HALF_LIFE_DAYS_BY_CLASS:
            raise ValueError(f"unknown belief_class: {value}")
        return value

    @field_validator("half_life_days")
    @classmethod
    def validate_half_life_days(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("half_life_days must be non-negative")
        return value

    @field_validator("classification_status")
    @classmethod
    def validate_classification_status(cls, value: str) -> str:
        if value not in {"classified", "unknown"}:
            raise ValueError("classification_status must be classified or unknown")
        return value

    @model_validator(mode="after")
    def validate_result_contract(self) -> "BeliefBackfillRow":
        if self.classification_status == "unknown" and self.belief_class is not None:
            raise ValueError("unknown classification must not carry a belief_class")
        if self.classification_status == "unknown" and self.half_life_days is not None:
            raise ValueError("unknown classification must not carry a half_life_days override")
        if self.classification_status == "classified" and self.belief_class is None:
            raise ValueError("classified result requires a belief_class")
        return self


class BeliefBackfillBatch(BaseModel):
    items: List[BeliefBackfillRow] = Field(default_factory=list)


@dataclass
class BeliefBackfillReport:
    uid: str
    dry_run: bool
    classified: int = 0
    written: int = 0
    already_classified: int = 0
    unknown: int = 0
    skipped: int = 0
    errors: int = 0
    partial: bool = False
    complete: bool = False
    next_cursor: Optional[str] = None
    class_counts: Dict[str, int] = field(default_factory=dict)
    # Kept as an empty compatibility field. Classification no longer changes
    # subject scope, so no scope distribution is authoritative here.
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


def _default_item_reader(
    uid: str,
    db_client: Any,
    *,
    start_after: Optional[str] = None,
    limit: Optional[int] = None,
) -> Sequence[MemoryItem]:
    from database.memory_collections import MemoryCollections

    items: List[MemoryItem] = []
    scanned = 0
    errors = 0
    next_cursor: Optional[str] = None
    take = max(1, int(limit)) if limit is not None else None
    collection = db_client.collection(MemoryCollections(uid=uid).memory_items)
    query = collection.order_by("__name__")
    if start_after:
        # Firestore requires a DocumentReference in the __name__ cursor slot;
        # a bare string id fails at query build on every resume.
        query = query.start_after({"__name__": collection.document(start_after)})
    if take is not None:
        query = query.limit(take)
    for snapshot in query.stream():
        scanned += 1
        next_cursor = str(getattr(snapshot, "id", "") or "") or next_cursor
        raw = snapshot.to_dict() if getattr(snapshot, "to_dict", None) else None
        if not isinstance(raw, dict):
            errors += 1
            continue
        try:
            item = MemoryItem.model_validate(raw)
        except Exception:
            errors += 1
            continue
        if item.uid != uid:
            errors += 1
            continue
        items.append(item)
    return BeliefBackfillPage(
        items,
        next_cursor=next_cursor,
        scanned=scanned,
        errors=errors,
        has_more=take is not None and scanned >= take,
    )


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
        "Return classification_status=unknown when the retained text is not enough "
        "to choose a class. Unknown is a valid result and must not be guessed.\n"
        "Optional half_life_days is a numeric override from wording (e.g. this week → 7); "
        "null means use the class prior. Return no subject, validity, status, tier, or content fields.\n"
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
    """Return a class/horizon-only patch.

    This function intentionally does not emit subject scope, validity, status,
    tier, expiry, or content updates. Unknown results have no mutation patch.
    """
    if classification.classification_status == "unknown" or classification.belief_class is None:
        return {}, {}
    user_asserted = bool(getattr(item, "user_asserted", False))
    resolved_class, resolved_half_life = horizon_from_extraction(
        belief_class=classification.belief_class,
        half_life_days_override=classification.half_life_days,
        user_asserted=user_asserted,
    )
    logical: Dict[str, Any] = {
        # Keep the canonical mutation's lifecycle/status invariant explicit;
        # the apply owner revalidates the authoritative row before writing.
        "result_status": _lifecycle_for_item(item),
    }
    extra: Dict[str, Any] = {
        "belief_class": resolved_class,
        "half_life_days": resolved_half_life,
    }
    return logical, extra


def _default_applier(uid: str, item: Any, classification: BeliefBackfillRow, db_client: Any) -> Any:
    from utils.memory.canonical_memory_adapter import apply_canonical_user_mutation

    expected_revision = getattr(item, "item_revision", None)

    def build_patch(current_item: MemoryItem, _now: datetime) -> tuple[Dict[str, Any], Dict[str, Any]]:
        # The canonical owner performs the authoritative read in its retrying
        # transaction. Never apply an LLM result to a row changed since it was
        # classified, even if only the content or an explicit correction changed.
        if expected_revision is not None and current_item.item_revision != expected_revision:
            raise ValueError("belief backfill source revision changed")
        if not _unclassified(current_item):
            raise ValueError("belief backfill source is no longer unclassified")
        return patch_for_belief_backfill(current_item, classification)

    _previous, updated = apply_canonical_user_mutation(
        uid,
        classification.memory_id,
        mutation_kind=BELIEF_BACKFILL_MUTATION_KIND,
        build_patch=build_patch,
        required_source_item=item,
        automated=True,
        db_client=db_client,
    )
    return updated


def _require_belief_automation() -> None:
    if not belief_model_enabled():
        raise ValueError("MEMORY_BELIEF_MODEL_ENABLED must be true to run a belief backfill")
    if not belief_automation_enabled():
        raise ValueError("belief automation is paused")


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
    page_size: Optional[int] = None,
    limit: Optional[int] = None,
    start_after: Optional[str] = None,
    checkpoint: Optional[MutableMapping[str, Any]] = None,
    checkpoint_writer: Optional[CheckpointWriter] = None,
) -> BeliefBackfillReport:
    """Run one bounded, resumable classification page for one uid.

    The checkpoint is an operator-owned artifact, not a Firestore collection.
    It caches classifier results before apply so an interrupted run retries the
    canonical write without paying for classification again. ``dry_run`` never
    applies a cached result.
    """
    if not uid or not str(uid).strip():
        raise ValueError("--uid is required")
    report = BeliefBackfillReport(uid=uid, dry_run=dry_run)
    _require_belief_automation()

    client = db_client
    if client is None:
        from database._client import db as default_db_client

        client = default_db_client
    reader = item_reader or _default_item_reader
    classify = classifier or (lambda rows, name: _default_classifier(rows, name))
    apply_row = applier or (
        lambda _uid, item, classification, _db: _default_applier(_uid, item, classification, client)
    )

    page_size_value = max(1, int(page_size or batch_size or BELIEF_BACKFILL_BATCH_SIZE))
    remaining = None if limit is None or int(limit) <= 0 else max(0, int(limit))
    state: MutableMapping[str, Any] = checkpoint if checkpoint is not None else {}
    if state.get("uid") not in {None, uid}:
        raise ValueError("checkpoint uid does not match --uid")
    state.setdefault("version", 1)
    state["uid"] = uid
    state.setdefault("cursor", start_after)
    state.setdefault("results", {})
    state.setdefault("completed", {})
    state.setdefault("errors", {})
    cursor = state.get("cursor") if start_after is None else start_after
    if start_after is None:
        pending_page_starts = [
            entry["page_start"]
            for mid, entry in state["results"].items()
            if mid not in state["completed"] and isinstance(entry, dict) and "page_start" in entry
        ]
        if pending_page_starts:
            # A dry-run preview caches classifications without applying them
            # while still advancing the checkpoint cursor past the page (the
            # physical cursor must advance past unreadable rows). Re-read the
            # earliest cached-but-unapplied page so a later --apply run
            # consumes the cache instead of stranding it behind the cursor.
            # Entries without a recorded page start predate this rescue and
            # keep their previous resume behavior.
            cursor = None if None in pending_page_starts else min(pending_page_starts)

    def save_checkpoint() -> None:
        if checkpoint_writer is not None:
            checkpoint_writer(state)

    def read_page() -> Sequence[Any]:
        # Keep injected test readers and existing operators compatible while the
        # production reader receives deterministic cursor/page bounds.
        try:
            parameters = inspect.signature(reader).parameters
            names = list(parameters)
        except (TypeError, ValueError):
            names = []
        take = page_size_value if remaining is None else min(page_size_value, remaining)
        if reader is _default_item_reader or {"start_after", "limit"}.intersection(names):
            kwargs = {}
            if reader is _default_item_reader or "start_after" in names:
                kwargs["start_after"] = cursor
            if reader is _default_item_reader or "limit" in names:
                kwargs["limit"] = take
            return reader(uid, client, **kwargs)
        return reader(uid, client)

    raw_page = read_page()
    page = list(raw_page)
    physical_cursor = getattr(raw_page, "next_cursor", None)
    read_errors = int(getattr(raw_page, "errors", 0) or 0)
    reader_has_more = getattr(raw_page, "has_more", None)
    page.sort(key=lambda row: str(getattr(row, "memory_id", "")))
    if remaining is not None:
        page = page[:remaining]
    if not page:
        report.errors += read_errors
        report.partial = bool(read_errors) or bool(reader_has_more)
        report.complete = not report.partial
        report.next_cursor = physical_cursor if report.partial else None
        state["cursor"] = report.next_cursor
        save_checkpoint()
        return report

    report.errors += read_errors
    if read_errors:
        report.partial = True

    cached_results = state["results"]
    completed = state["completed"]

    def has_fresh_cache(item: Any) -> bool:
        memory_id = getattr(item, "memory_id", None)
        cached = cached_results.get(memory_id) if isinstance(memory_id, str) else None
        return isinstance(cached, dict) and cached.get("revision") == getattr(item, "item_revision", None)

    # A completed outcome belongs to its source revision, exactly like a
    # cached classification. If the owner edited the item after the checkpoint
    # recorded the terminal result, the entry is stale: drop it so a rerun
    # reclassifies the row instead of skipping it forever.
    for item in page:
        memory_id = getattr(item, "memory_id", None)
        entry = completed.get(memory_id) if isinstance(memory_id, str) else None
        if isinstance(entry, dict) and entry.get("revision") != getattr(item, "item_revision", None):
            completed.pop(memory_id, None)

    # Only rows with no terminal checkpoint result need a paid classifier call.
    to_classify = [
        item
        for item in page
        if _unclassified(item) and getattr(item, "memory_id", None) not in completed and not has_fresh_cache(item)
    ]
    for item in to_classify:
        # A cached judgment belongs to its source revision. If the owner edited
        # the item after classification, discard the stale result and pay for a
        # fresh judgment rather than relying on the applier to reject forever.
        memory_id = getattr(item, "memory_id", None)
        if isinstance(memory_id, str) and isinstance(cached_results.get(memory_id), dict):
            if cached_results[memory_id].get("revision") != getattr(item, "item_revision", None):
                cached_results.pop(memory_id, None)
    cursor_blocked = False
    if to_classify:
        classify_batch_size = max(1, int(batch_size))
        for offset in range(0, len(to_classify), classify_batch_size):
            classify_batch = to_classify[offset : offset + classify_batch_size]
            _require_belief_automation()
            try:
                classified_rows = list(classify(classify_batch, user_name))
            except Exception:
                logger.warning(
                    "belief backfill classify failed uid=%s cursor=%s offset=%s",
                    uid,
                    cursor,
                    offset,
                    exc_info=False,
                )
                report.errors += len(classify_batch)
                report.partial = True
                cursor_blocked = True
                save_checkpoint()
                continue
            by_id = {row.memory_id: row for row in classified_rows}
            for item in classify_batch:
                memory_id = getattr(item, "memory_id", None)
                classification = by_id.get(memory_id) if isinstance(memory_id, str) else None
                if classification is None:
                    # A missing row is an explicit skipped outcome. It is retained
                    # in the operator artifact so a rerun does not pay repeatedly.
                    if isinstance(memory_id, str):
                        completed[memory_id] = {
                            "status": "skipped",
                            "revision": getattr(item, "item_revision", None),
                        }
                    report.skipped += 1
                    report.partial = True
                    continue
                cached_results[memory_id] = {
                    "classification_status": classification.classification_status,
                    "belief_class": classification.belief_class,
                    "half_life_days": classification.half_life_days,
                    # Diagnostic compatibility only; never copied into a memory.
                    "subject_scope": classification.subject_scope,
                    "revision": getattr(item, "item_revision", None),
                    # Read cursor of the page that produced this cache entry, so
                    # a later apply run can re-read stranded dry-run pages.
                    "page_start": cursor,
                }
            save_checkpoint()

    class_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    for item in page:
        memory_id = getattr(item, "memory_id", None)
        if not isinstance(memory_id, str):
            report.skipped += 1
            report.partial = True
            continue
        if memory_id in completed:
            status = completed[memory_id].get("status") if isinstance(completed[memory_id], dict) else None
            if status == "unknown":
                report.unknown += 1
            elif status == "written":
                report.written += 1
            elif status == "already_classified":
                report.already_classified += 1
            else:
                report.skipped += 1
            continue
        if not _unclassified(item):
            completed[memory_id] = {"status": "already_classified", "revision": getattr(item, "item_revision", None)}
            report.already_classified += 1
            continue
        raw = cached_results.get(memory_id)
        if not isinstance(raw, dict):
            report.skipped += 1
            report.partial = True
            continue
        try:
            # Validate the JSON-shaped checkpoint payload as a mapping. Keeping
            # it as a typed payload avoids widening each optional field to
            # pyright's Unknown while preserving Pydantic's runtime checks.
            cached_payload: Dict[str, Any] = {
                "memory_id": memory_id,
                **{
                    key: raw.get(key)
                    for key in ("classification_status", "belief_class", "half_life_days", "subject_scope")
                    if key in raw
                },
            }
            classification = BeliefBackfillRow.model_validate(cached_payload)
        except Exception:
            report.errors += 1
            cursor_blocked = True
            report.partial = True
            continue
        if classification.classification_status == "unknown":
            completed[memory_id] = {"status": "unknown", "revision": getattr(item, "item_revision", None)}
            report.unknown += 1
            save_checkpoint()
            continue
        report.classified += 1
        class_counts[classification.belief_class or "unknown"] += 1
        if classification.subject_scope:
            scope_counts[classification.subject_scope] += 1
        if dry_run:
            # A dry-run is a preview, not a committed outcome. Keep the cached
            # classification available for a later apply run.
            save_checkpoint()
            continue
        try:
            _require_belief_automation()
            apply_row(uid, item, classification, client)
        except Exception:
            logger.warning("belief backfill apply failed memory_id=%s", memory_id, exc_info=False)
            report.errors += 1
            cursor_blocked = True
            report.partial = True
            save_checkpoint()
            continue
        completed[memory_id] = {"status": "written", "revision": getattr(item, "item_revision", None)}
        report.written += 1
        save_checkpoint()

    # Keep the cursor at the start of a failed page so cached classifications
    # can be retried without another LLM call. Terminal outcomes may advance.
    last_id = str(getattr(page[-1], "memory_id", ""))
    next_cursor = physical_cursor or last_id or (str(cursor) if cursor else None)
    if cursor_blocked:
        report.next_cursor = str(cursor) if cursor else None
    else:
        report.next_cursor = next_cursor
        state["cursor"] = report.next_cursor
    has_more = (
        bool(reader_has_more)
        if reader_has_more is not None
        else len(page) >= page_size_value and (remaining is None or remaining >= len(page))
    )
    report.partial = report.partial or has_more or bool(read_errors)
    report.complete = not report.partial
    save_checkpoint()
    report.class_counts = dict(class_counts)
    report.scope_counts = dict(scope_counts)
    return report
