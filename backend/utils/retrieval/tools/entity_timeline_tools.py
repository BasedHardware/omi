"""Bounded, read-only entity timeline retrieval over canonical memory items.

The tool consumes canonical, chat-visible ``MemoryItem`` rows and exposes only
compact fact entries plus stable evidence references.  It never expands
transcript bodies, playbook bodies, trigger conditions, or arbitrary profile
fields.  Entity input is intentionally strict: callers must use a canonical
``user``/``person``/``project``/``organization``/``place``/``entity``
reference, so an unsupported natural-language entity cannot accidentally
become a broad profile search.
"""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import islice
import logging
import re
from typing import Any, Dict, Iterable, Iterator, List, Literal, Optional, Tuple, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]
from pydantic import BaseModel, ConfigDict, field_validator

from models.product_memory import MemoryAccessPolicy, MemoryItem, MemoryItemStatus, MemoryKind, MemorySubjectScope
from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items

logger = logging.getLogger(__name__)

MAX_TIMELINE_LIMIT = 40
MAX_TIMELINE_SCAN = 500
MAX_TIMELINE_RESULT_CHARS = 12_000
MAX_TIMELINE_CONTENT_CHARS = 600
MAX_ENTITY_REFERENCE_CHARS = 128
SUPPORTED_ENTITY_KINDS = frozenset({"user", "person", "project", "organization", "place", "entity"})
EntityKind = Literal["user", "person", "project", "organization", "place", "entity"]


class EntityReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: EntityKind
    identifier: str

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = (value or "").strip().casefold()
        if not normalized or len(normalized) > MAX_ENTITY_REFERENCE_CHARS:
            raise ValueError("entity identifier is blank or too long")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", normalized):
            raise ValueError("entity identifier must be a canonical stable id")
        return normalized

    @property
    def key(self) -> str:
        return "user" if self.kind == "user" else f"{self.kind}:{self.identifier}"


class TimelineEntry(BaseModel):
    """A compact fact projection; no transcript or arbitrary MemoryItem fields."""

    model_config = ConfigDict(frozen=True)

    memory_id: str
    status: MemoryItemStatus
    content: str
    occurred_at: datetime
    valid_to: Optional[datetime] = None
    evidence_refs: Tuple[str, ...] = ()
    source_refs: Tuple[str, ...] = ()

    @field_validator("content")
    @classmethod
    def bound_content(cls, value: str) -> str:
        # Keep each projection line-shaped.  Newlines in a fact must not turn
        # this compact tool response into an accidental transcript dump.
        return " ".join((value or "").split())[:MAX_TIMELINE_CONTENT_CHARS]


class EntityTimeline(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity: EntityReference
    entries: Tuple[TimelineEntry, ...] = ()
    truncated: bool = False
    scanned_count: int = 0


def _agent_config() -> Optional[Dict[str, Any]]:
    try:
        from utils.retrieval.agentic import agent_config_context

        return cast(Optional[Dict[str, Any]], agent_config_context.get())
    except (ImportError, LookupError):
        return None


def _resolve_uid(config: RunnableConfig | None) -> Optional[str]:
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
    if not cfg:
        return None
    configurable = cfg.get("configurable")
    if not isinstance(configurable, dict):
        return None
    uid = configurable.get("user_id")
    return uid.strip() if isinstance(uid, str) and uid.strip() else None


def parse_entity_reference(raw: str) -> EntityReference:
    """Parse only canonical entity references; bare display names fail closed."""

    value = (raw or "").strip().casefold()
    if value in {"me", "user", "primary_user"}:
        return EntityReference(kind="user", identifier="user")
    if ":" not in value:
        raise ValueError("unsupported entity reference; use kind:stable_id")
    kind, identifier = value.split(":", 1)
    if kind not in SUPPORTED_ENTITY_KINDS:
        raise ValueError(f"unsupported entity kind: {kind}")
    if kind == "user":
        if identifier not in {"me", "user", "primary_user"}:
            raise ValueError("user entity must be the primary user")
        identifier = "user"
    return EntityReference(kind=cast(EntityKind, kind), identifier=identifier)


def _validate_bounds(limit: int, start: Optional[datetime], end: Optional[datetime]) -> int:
    if limit < 1 or limit > MAX_TIMELINE_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_TIMELINE_LIMIT}")
    for label, value in (("start", start), ("end", end)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError(f"{label} must be timezone-aware")
    if start and end and start > end:
        raise ValueError("start must be before or equal to end")
    return limit


def _item_matches_entity(item: MemoryItem, entity: EntityReference) -> bool:
    subject_id = (item.subject_entity_id or "").strip().casefold()
    if entity.kind == "user":
        return item.subject_scope == MemorySubjectScope.primary_user and subject_id in {"", "user", "entity:user"}
    return subject_id == entity.key


def _timeline_time(item: MemoryItem) -> datetime:
    return item.valid_from or item.captured_at


def _evidence_refs(item: MemoryItem) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    evidence_refs: List[str] = []
    source_refs: List[str] = []
    for evidence in sorted(item.evidence, key=lambda value: value.evidence_id):
        evidence_refs.append(f"memory:{item.memory_id}:evidence:{evidence.evidence_id}")
        if evidence.source_id:
            source_refs.append(f"{evidence.source_type}:{evidence.source_id}")
    return tuple(sorted(set(evidence_refs))), tuple(sorted(set(source_refs)))


def build_entity_timeline(
    items: Iterable[MemoryItem],
    entity: EntityReference | str,
    *,
    limit: int = 20,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    scanned_count: Optional[int] = None,
) -> EntityTimeline:
    """Build a deterministic, bounded timeline from already-read canonical rows."""

    reference = entity if isinstance(entity, EntityReference) else parse_entity_reference(entity)
    bounded_limit = _validate_bounds(limit, start, end)
    candidates: List[MemoryItem] = []
    scanned = 0
    for item in items:
        scanned += 1
        if item.kind != MemoryKind.fact:
            continue
        if item.status not in {MemoryItemStatus.active, MemoryItemStatus.superseded}:
            continue
        # A canonical row can outlive its source.  Do not surface a fact whose
        # evidence/source has been explicitly tombstoned or purged.
        if item.source_state.value != "active":
            continue
        if not _item_matches_entity(item, reference):
            continue
        occurred_at = _timeline_time(item)
        if start and occurred_at < start:
            continue
        if end and occurred_at > end:
            continue
        candidates.append(item)

    candidates.sort(key=lambda item: (_timeline_time(item), item.updated_at, item.memory_id))
    truncated = len(candidates) > bounded_limit
    selected = candidates[-bounded_limit:]
    entries: List[TimelineEntry] = []
    for item in selected:
        evidence_refs, source_refs = _evidence_refs(item)
        entries.append(
            TimelineEntry(
                memory_id=item.memory_id,
                status=item.status,
                content=item.content or "",
                occurred_at=_timeline_time(item),
                valid_to=item.valid_to,
                evidence_refs=evidence_refs,
                source_refs=source_refs,
            )
        )
    return EntityTimeline(
        entity=reference,
        entries=tuple(entries),
        truncated=truncated,
        scanned_count=scanned if scanned_count is None else scanned_count,
    )


def _parse_iso_date(value: Optional[str], label: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO timestamp with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def format_entity_timeline(timeline: EntityTimeline) -> str:
    """Render only bounded timeline facts and opaque/stable evidence refs."""

    if not timeline.entries:
        return f"No entity timeline entries found for {timeline.entity.key}."
    lines = [f"Entity timeline: {timeline.entity.key}", ""]
    for entry in timeline.entries:
        block = [
            f"- {entry.occurred_at.isoformat()} [{entry.status.value}] {entry.memory_id}",
            f"  {entry.content}",
        ]
        if entry.valid_to:
            block.append(f"  valid_to: {entry.valid_to.isoformat()}")
        if entry.evidence_refs:
            block.append("  evidence: " + ", ".join(entry.evidence_refs))
        if entry.source_refs:
            block.append("  sources: " + ", ".join(entry.source_refs))
        candidate = "\n".join(lines + block)
        if len(candidate) > MAX_TIMELINE_RESULT_CHARS:
            break
        lines.extend(block)
    if timeline.truncated or len(lines) < 3 + (len(timeline.entries) * 2):
        lines.extend(["", "[Timeline output is bounded; ask for a narrower entity or date range.]"])
    return "\n".join(lines).strip()


def _iter_authoritative_items(uid: str, *, db_client: Any, limit: int) -> Iterator[MemoryItem]:
    from utils.memory.product_memory_read_service import iter_authoritative_product_memory_items_newest_first

    return iter_authoritative_product_memory_items_newest_first(uid, db_client=db_client, limit=limit)


def _chat_visible_items(items: List[MemoryItem]) -> List[MemoryItem]:
    """Apply the shared chat policy and the paid-content lock before projection."""
    visible = filter_canonical_default_visible_items(
        items,
        policy=MemoryAccessPolicy.for_omi_chat(archive_capability=False),
        now=datetime.now(timezone.utc),
    )
    return [item for item in visible if (item.promotion or {}).get("is_locked") is not True]


@tool
def get_entity_timeline_tool(
    entity: str,
    limit: int = 20,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]
) -> str:
    """Read a bounded, current chat-visible timeline for one canonical entity.

    ``entity`` must be ``user``/``me`` or a stable reference such as
    ``person:alice`` or ``project:omi``.  The result contains fact entries and
    stable evidence/source refs only; it never returns transcripts or profile
    bodies.  Unsupported references fail closed before any data read.
    """

    try:
        reference = parse_entity_reference(entity)
        start = _parse_iso_date(start_date, "start_date")
        end = _parse_iso_date(end_date, "end_date")
        bounded_limit = _validate_bounds(limit, start, end)
    except ValueError as exc:
        return f"Error: unsupported or invalid entity timeline request: {exc}"

    uid = _resolve_uid(config)
    if not uid:
        return "Error: User ID not found in configuration"

    try:
        from database._client import get_firestore_client

        firestore_db = get_firestore_client()
        stream = _iter_authoritative_items(uid, db_client=firestore_db, limit=MAX_TIMELINE_SCAN + 1)
        # Keep the consumer boundary independently bounded even if a future
        # reader implementation fails to honor its explicit storage limit.
        scanned_rows = list(islice(stream, MAX_TIMELINE_SCAN + 1))
        scan_truncated = len(scanned_rows) > MAX_TIMELINE_SCAN
        timeline = build_entity_timeline(
            _chat_visible_items(scanned_rows[:MAX_TIMELINE_SCAN]),
            reference,
            limit=bounded_limit,
            start=start,
            end=end,
            scanned_count=len(scanned_rows[:MAX_TIMELINE_SCAN]),
        )
        if scan_truncated:
            timeline = timeline.model_copy(update={"truncated": True})
        return format_entity_timeline(timeline)
    except Exception as exc:
        logger.error("get_entity_timeline_tool failed error_type=%s", type(exc).__name__)
        return f"Error reading entity timeline: {type(exc).__name__}"


__all__ = [
    "EntityReference",
    "EntityTimeline",
    "TimelineEntry",
    "build_entity_timeline",
    "format_entity_timeline",
    "get_entity_timeline_tool",
    "parse_entity_reference",
    "MAX_TIMELINE_LIMIT",
    "MAX_TIMELINE_SCAN",
]
