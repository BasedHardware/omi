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
from enum import Enum
from itertools import islice
import logging
import re
import unicodedata
from typing import Any, Dict, Iterable, Iterator, List, Literal, Optional, Sequence, Tuple, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]
from pydantic import BaseModel, ConfigDict, field_validator

from database import _client as database_client
from database.entity_timeline_sources import (
    list_entity_timeline_conversations,
    list_entity_timeline_meetings,
    list_entity_timeline_screen_activity,
)
from models.product_memory import MemoryAccessPolicy, MemoryItem, MemoryItemStatus, MemoryKind, MemorySubjectScope
from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items
from utils.memory.canonical_memory_adapter import memory_item_to_memorydb
from utils.memory.ledger_history_policy import is_ledger_history_item

logger = logging.getLogger(__name__)

MAX_TIMELINE_LIMIT = 40
MAX_TIMELINE_SCAN = 500
MAX_TIMELINE_SOURCE_SCAN = 200
MAX_TIMELINE_RESULT_CHARS = 12_000
MAX_TIMELINE_CONTENT_CHARS = 600
MAX_ENTITY_REFERENCE_CHARS = 128
MAX_ALIAS_PEOPLE_SCAN = 200
SUPPORTED_ENTITY_KINDS = frozenset({"user", "person", "project", "organization", "place", "entity"})
EntityKind = Literal["user", "person", "project", "organization", "place", "entity"]


class TimelineSource(str, Enum):
    ledger = "ledger"
    conversations = "conversations"
    calendar = "calendar"
    screen = "screen"


DEFAULT_TIMELINE_SOURCES = (TimelineSource.ledger,)


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


class EntityAliases(BaseModel):
    """Exact owner-scoped aliases for one canonical entity.

    Alias values are match inputs only and are never rendered.  This lets an
    email join a calendar record without disclosing it in the tool response.
    """

    model_config = ConfigDict(frozen=True)

    entity: EntityReference
    values: Tuple[str, ...] = ()
    resolved: bool = False
    ambiguous: bool = False


class TimelineEntry(BaseModel):
    """A compact fact projection; no transcript or arbitrary MemoryItem fields."""

    model_config = ConfigDict(frozen=True)

    source: TimelineSource = TimelineSource.ledger
    record_id: str
    memory_id: Optional[str] = None
    status: Optional[MemoryItemStatus] = None
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
    aliases_resolved: bool = False
    aliases_ambiguous: bool = False
    requested_sources: Tuple[TimelineSource, ...] = ()
    truncated_sources: Tuple[TimelineSource, ...] = ()
    unavailable_sources: Tuple[TimelineSource, ...] = ()


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


def _normalize_alias(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = " ".join(unicodedata.normalize("NFKC", value).split()).strip().casefold()
    if not normalized or len(normalized) > MAX_ENTITY_REFERENCE_CHARS:
        return None
    return normalized


def _parse_sources(values: Optional[Sequence[str]]) -> Tuple[TimelineSource, ...]:
    if values is None:
        return DEFAULT_TIMELINE_SOURCES
    resolved: List[TimelineSource] = []
    for value in values:
        try:
            source = TimelineSource(str(value).strip().casefold())
        except ValueError as exc:
            raise ValueError(f"unsupported timeline source: {value}") from exc
        if source not in resolved:
            resolved.append(source)
    if not resolved:
        raise ValueError("at least one timeline source is required")
    return tuple(resolved)


def _resolve_entity_aliases(uid: str, entity: EntityReference, *, db_client: Any) -> EntityAliases:
    """Resolve exact aliases from the owner's canonical people document.

    The people document ID remains authority.  Display-name equality is never
    used to choose a person document, so duplicate names cannot cross-link two
    stable people.  Existing optional ``aliases``/``emails`` fields are read
    when present without making them mutation authority.
    """

    if entity.kind == "user":
        return EntityAliases(entity=entity, resolved=True)
    if entity.kind != "person":
        return EntityAliases(entity=entity)
    user_ref = db_client.collection("users").document(uid)
    people = user_ref.collection("people")
    snapshot = people.document(entity.identifier).get()
    if not getattr(snapshot, "exists", False):
        return EntityAliases(entity=entity)
    raw = snapshot.to_dict()
    if not isinstance(raw, dict):
        return EntityAliases(entity=entity)
    candidates = _person_alias_values(raw)

    # Alias equality is not identity when two owner-scoped entities share the
    # same name or address. Suppress every collision rather than cross-linking
    # an unkeyed calendar/screen record to the selected stable person.
    collisions: set[str] = set()
    owner_snapshot = user_ref.get()
    owner_raw = owner_snapshot.to_dict() if getattr(owner_snapshot, "exists", False) else None
    if isinstance(owner_raw, dict):
        collisions.update(_person_alias_values(owner_raw))
    siblings = list(islice(people.limit(MAX_ALIAS_PEOPLE_SCAN + 1).stream(), MAX_ALIAS_PEOPLE_SCAN + 1))
    if len(siblings) > MAX_ALIAS_PEOPLE_SCAN:
        return EntityAliases(entity=entity, resolved=True, ambiguous=True)
    for sibling in siblings:
        if str(getattr(sibling, "id", "")) == entity.identifier:
            continue
        sibling_raw = sibling.to_dict()
        if isinstance(sibling_raw, dict):
            collisions.update(_person_alias_values(sibling_raw))
    aliases = tuple(sorted(candidates - collisions))
    return EntityAliases(entity=entity, values=aliases, resolved=True, ambiguous=aliases != tuple(sorted(candidates)))


def _person_alias_values(raw: Dict[str, Any]) -> set[str]:
    candidates: List[Any] = [raw.get("name"), raw.get("email")]
    for field in ("aliases", "emails"):
        values = raw.get(field)
        if isinstance(values, (list, tuple)):
            candidates.extend(values[:24])
    return {alias for value in candidates if (alias := _normalize_alias(value)) is not None}


def _participant_matches(value: Any, aliases: EntityAliases) -> bool:
    if isinstance(value, dict):
        return any(_normalize_alias(value.get(field)) in aliases.values for field in ("name", "email", "display_name"))
    return _normalize_alias(value) in aliases.values


def _text_contains_alias(value: Any, aliases: EntityAliases) -> bool:
    normalized = _normalize_alias(value)
    if normalized is None:
        return False
    for alias in aliases.values:
        # Screen matching is deliberately exact-token/phrase based.  A stable
        # entity is never inferred from fuzzy or semantic text similarity.
        if len(alias) < 3 and "@" not in alias:
            continue
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            return True
    return False


def _public_metadata_text(value: Any, *, fallback: str, limit: int) -> str:
    """Project compact metadata without returning email addresses.

    Email aliases are match inputs only. Titles and window metadata are still
    user-authored strings, so strip any address-shaped value before rendering
    rather than assuming the structured participant fields are the only place
    one can appear.
    """

    # Firestore is schemaless at this boundary. Never stringify a malformed
    # mapping/list into a field that is allowed to reach the agent: protected
    # transcript, note, frame, or attendee data can otherwise hitchhike inside
    # a nominal title/window value.
    public_value = value if isinstance(value, str) else fallback
    compact = " ".join(public_value.split())
    # Redact the whole non-whitespace token around ``@``. This deliberately
    # favors false-positive redaction over leaking Unicode/IDN addresses that
    # an ASCII-TLD expression would miss.
    without_emails = re.sub(r"\S*@\S*", "[redacted email]", compact)
    return without_emails[:limit]


def _datetime_value(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
            except ValueError:
                return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _in_range(value: datetime, start: Optional[datetime], end: Optional[datetime]) -> bool:
    return not ((start is not None and value < start) or (end is not None and value > end))


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


def _ledger_entries(
    items: Sequence[MemoryItem],
    entity: EntityReference,
    *,
    include_history: bool,
    include_rejected: bool,
    start: Optional[datetime],
    end: Optional[datetime],
) -> List[TimelineEntry]:
    visible_ids = {item.memory_id for item in _chat_visible_items(list(items))}
    entries: List[TimelineEntry] = []
    for item in items:
        if item.kind != MemoryKind.fact or not _item_matches_entity(item, entity):
            continue
        occurred_at = _timeline_time(item)
        if not _in_range(occurred_at, start, end):
            continue
        row = memory_item_to_memorydb(item)
        is_current = item.memory_id in visible_ids and item.status == MemoryItemStatus.active
        is_history = include_history and is_ledger_history_item(item, row)
        if is_history and row.user_review is False and not include_rejected:
            is_history = False
        if not is_current and not is_history:
            continue
        evidence_refs, source_refs = _evidence_refs(item)
        entries.append(
            TimelineEntry(
                source=TimelineSource.ledger,
                record_id=item.memory_id,
                memory_id=item.memory_id,
                status=item.status,
                content=item.content or "",
                occurred_at=occurred_at,
                valid_to=item.valid_to,
                evidence_refs=evidence_refs,
                source_refs=source_refs,
            )
        )
    return entries


def _calendar_participants(record: Dict[str, Any]) -> List[Any]:
    participants: List[Any] = []
    direct = record.get("participants")
    if isinstance(direct, (list, tuple)):
        participants.extend(direct)
    external = record.get("external_data")
    external_data = external if isinstance(external, dict) else {}
    context = external_data.get("calendar_meeting_context") or record.get("calendar_meeting_context")
    if isinstance(context, dict) and isinstance(context.get("participants"), (list, tuple)):
        participants.extend(context["participants"])
    event = record.get("calendar_event")
    if isinstance(event, dict) and isinstance(event.get("attendees"), (list, tuple)):
        participants.extend(event["attendees"])
    return participants


def _conversation_matches(record: Dict[str, Any], aliases: EntityAliases) -> bool:
    segments = record.get("transcript_segments")
    if isinstance(segments, list):
        for segment in segments[:4096]:
            if not isinstance(segment, dict):
                continue
            if aliases.entity.kind == "user" and segment.get("is_user") is True:
                return True
            person_id = str(segment.get("person_id") or "").strip().casefold()
            if aliases.entity.kind == "person" and person_id in {
                aliases.entity.identifier,
                aliases.entity.key,
            }:
                return True
    return bool(aliases.values) and any(
        _participant_matches(value, aliases) for value in _calendar_participants(record)
    )


def _conversation_entry(record: Dict[str, Any], aliases: EntityAliases) -> Optional[TimelineEntry]:
    if record.get("is_locked") is True or not _conversation_matches(record, aliases):
        return None
    record_id = str(record.get("id") or "").strip()
    occurred_at = _datetime_value(record.get("started_at") or record.get("created_at"))
    if not record_id or occurred_at is None or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._~-]*", record_id) is None:
        return None
    structured = record.get("structured")
    summary = structured if isinstance(structured, dict) else {}
    title = _public_metadata_text(summary.get("title"), fallback="Conversation", limit=160)
    overview = _public_metadata_text(summary.get("overview"), fallback="", limit=400)
    content = title if not overview else f"{title} — {overview}"
    reference = f"conversation:{record_id}:summary"
    return TimelineEntry(
        source=TimelineSource.conversations,
        record_id=record_id,
        content=content,
        occurred_at=occurred_at,
        evidence_refs=(reference,),
        source_refs=(f"conversation:{record_id}",),
    )


def _calendar_entry(record: Dict[str, Any], aliases: EntityAliases) -> Optional[TimelineEntry]:
    if not aliases.values or not any(_participant_matches(value, aliases) for value in _calendar_participants(record)):
        return None
    record_id = str(record.get("id") or "").strip()
    occurred_at = _datetime_value(record.get("start_time"))
    if not record_id or occurred_at is None or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._~-]*", record_id) is None:
        return None
    title = _public_metadata_text(record.get("title"), fallback="Calendar meeting", limit=MAX_TIMELINE_CONTENT_CHARS)
    reference = f"calendar-meeting:{record_id}"
    return TimelineEntry(
        source=TimelineSource.calendar,
        record_id=record_id,
        content=title,
        occurred_at=occurred_at,
        evidence_refs=(reference,),
        source_refs=(reference,),
    )


def _screen_entry(record: Dict[str, Any], aliases: EntityAliases) -> Optional[TimelineEntry]:
    if not aliases.values or not any(
        _text_contains_alias(record.get(field), aliases) for field in ("ocrText", "windowTitle")
    ):
        return None
    record_id = str(record.get("id") or "").strip()
    occurred_at = _datetime_value(record.get("timestamp"))
    if not record_id or occurred_at is None or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._~-]*", record_id) is None:
        return None
    app = _public_metadata_text(record.get("appName"), fallback="Screen activity", limit=120)
    window = _public_metadata_text(record.get("windowTitle"), fallback="", limit=240)
    content = app if not window else f"{app} — {window}"
    reference = f"screen:{record_id}"
    return TimelineEntry(
        source=TimelineSource.screen,
        record_id=record_id,
        content=content,
        occurred_at=occurred_at,
        evidence_refs=(reference,),
        source_refs=(reference,),
    )


def _merge_timeline_entries(
    entries: Iterable[TimelineEntry],
    *,
    limit: int,
) -> Tuple[Tuple[TimelineEntry, ...], bool]:
    by_identity: Dict[Tuple[TimelineSource, str], TimelineEntry] = {}
    for entry in entries:
        by_identity[(entry.source, entry.record_id)] = entry
    ordered = sorted(
        by_identity.values(),
        key=lambda entry: (entry.occurred_at, entry.source.value, entry.record_id),
    )
    truncated = len(ordered) > limit
    return tuple(ordered[-limit:]), truncated


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
                source=TimelineSource.ledger,
                record_id=item.memory_id,
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
        requested_sources=(TimelineSource.ledger,),
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
        lines = [f"No entity timeline entries found for {timeline.entity.key}."]
        if timeline.truncated_sources:
            lines.append(
                "[Source windows were partial: "
                + ", ".join(source.value for source in timeline.truncated_sources)
                + ".]"
            )
        if timeline.unavailable_sources:
            lines.append(
                "[Sources unavailable: " + ", ".join(source.value for source in timeline.unavailable_sources) + ".]"
            )
        if timeline.entity.kind == "person" and not timeline.aliases_resolved:
            lines.append("[No owner-scoped alias record was found; only canonical-ID joins were attempted.]")
        elif timeline.entity.kind == "person" and timeline.aliases_ambiguous:
            lines.append("[Ambiguous owner-scoped aliases were suppressed; canonical-ID joins remain authoritative.]")
        return "\n".join(lines)
    source_names = ", ".join(source.value for source in timeline.requested_sources)
    lines = [f"Entity timeline: {timeline.entity.key}", f"Sources: {source_names}", ""]
    output_truncated = False
    truncation_notice = "[Timeline output is bounded; ask for a narrower entity or date range.]"
    postambles: List[str] = []
    if timeline.truncated_sources:
        postambles.append(
            "[Source windows were partial: " + ", ".join(source.value for source in timeline.truncated_sources) + ".]"
        )
    if timeline.unavailable_sources:
        postambles.append(
            "[Sources unavailable: " + ", ".join(source.value for source in timeline.unavailable_sources) + ".]"
        )
    if timeline.entity.kind == "person" and not timeline.aliases_resolved:
        postambles.append("[No owner-scoped alias record was found; only canonical-ID joins were attempted.]")
    elif timeline.entity.kind == "person" and timeline.aliases_ambiguous:
        postambles.append("[Ambiguous owner-scoped aliases were suppressed; canonical-ID joins remain authoritative.]")
    # Always reserve the possible truncation notice plus every deterministic
    # postamble. A result that needs all disclosures must still honor the hard
    # transport cap.
    reserved_chars = len(truncation_notice) + sum(len(value) + 1 for value in postambles) + 2
    for entry in timeline.entries:
        status = f"/{entry.status.value}" if entry.status is not None else ""
        block = [
            f"- {entry.occurred_at.isoformat()} [{entry.source.value}{status}] {entry.record_id}",
            f"  {entry.content}",
        ]
        if entry.valid_to:
            block.append(f"  valid_to: {entry.valid_to.isoformat()}")
        if entry.evidence_refs:
            block.append("  evidence: " + ", ".join(entry.evidence_refs))
        if entry.source_refs:
            block.append("  sources: " + ", ".join(entry.source_refs))
        candidate = "\n".join(lines + block)
        # Reserve room for the required disclosure when the character budget,
        # rather than the entry-count budget, stops rendering.
        if len(candidate) + reserved_chars > MAX_TIMELINE_RESULT_CHARS:
            output_truncated = True
            break
        lines.extend(block)
    if timeline.truncated or output_truncated:
        lines.extend(["", truncation_notice])
    lines.extend(postambles)
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
    sources: Optional[List[str]] = None,
    include_history: bool = False,
    include_rejected: bool = False,
    limit: int = 20,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]
) -> str:
    """Read a bounded multi-source timeline for one canonical entity.

    ``entity`` must be ``user``/``me`` or a stable reference such as
    ``person:<stable_person_id>`` or ``project:omi``. ``sources`` explicitly
    selects any of ``ledger``, ``conversations``, ``calendar``, and ``screen``.
    Set ``include_history`` only when current knowledge is insufficient and the
    agent needs closed, superseded, episodic, or migrated-legacy ledger facts.
    Rejected rows remain excluded unless the agent explicitly requests audit
    mode with ``include_rejected``. No query-word heuristic enables history.

    Person aliases are resolved by exact stable person ID from the owner's
    people record, then joined exactly across completed conversations, calendar
    participants, and screen metadata. The response never includes transcripts,
    OCR text, alias emails, playbook bodies, or trigger conditions.
    """

    try:
        reference = parse_entity_reference(entity)
        requested_sources = _parse_sources(sources)
        start = _parse_iso_date(start_date, "start_date")
        end = _parse_iso_date(end_date, "end_date")
        bounded_limit = _validate_bounds(limit, start, end)
        if include_rejected and not include_history:
            raise ValueError("include_rejected requires include_history")
    except ValueError as exc:
        return f"Error: unsupported or invalid entity timeline request: {exc}"

    uid = _resolve_uid(config)
    if not uid:
        return "Error: User ID not found in configuration"

    try:
        firestore_db = database_client.get_firestore_client()
    except Exception as exc:
        logger.error("get_entity_timeline_tool storage unavailable error_type=%s", type(exc).__name__)
        return f"Error reading entity timeline: {type(exc).__name__}"

    try:
        aliases = _resolve_entity_aliases(uid, reference, db_client=firestore_db)
    except Exception as exc:
        logger.warning("get_entity_timeline_tool alias resolution unavailable error_type=%s", type(exc).__name__)
        aliases = EntityAliases(entity=reference)

    entries: List[TimelineEntry] = []
    truncated_sources: List[TimelineSource] = []
    unavailable_sources: List[TimelineSource] = []
    scanned_count = 0

    if TimelineSource.ledger in requested_sources:
        try:
            stream = _iter_authoritative_items(uid, db_client=firestore_db, limit=MAX_TIMELINE_SCAN + 1)
            rows = list(islice(stream, MAX_TIMELINE_SCAN + 1))
            scanned_count += min(len(rows), MAX_TIMELINE_SCAN)
            if len(rows) > MAX_TIMELINE_SCAN:
                truncated_sources.append(TimelineSource.ledger)
            entries.extend(
                _ledger_entries(
                    rows[:MAX_TIMELINE_SCAN],
                    reference,
                    include_history=include_history,
                    include_rejected=include_rejected,
                    start=start,
                    end=end,
                )
            )
        except Exception as exc:
            logger.error("entity timeline ledger unavailable error_type=%s", type(exc).__name__)
            unavailable_sources.append(TimelineSource.ledger)

    if TimelineSource.conversations in requested_sources:
        try:
            rows = list(
                islice(
                    list_entity_timeline_conversations(
                        uid,
                        db_client=firestore_db,
                        limit=MAX_TIMELINE_SOURCE_SCAN + 1,
                        start_date=start,
                        end_date=end,
                    ),
                    MAX_TIMELINE_SOURCE_SCAN + 1,
                )
            )
            scanned_count += min(len(rows), MAX_TIMELINE_SOURCE_SCAN)
            if len(rows) > MAX_TIMELINE_SOURCE_SCAN:
                truncated_sources.append(TimelineSource.conversations)
            entries.extend(
                entry
                for row in rows[:MAX_TIMELINE_SOURCE_SCAN]
                if (entry := _conversation_entry(row, aliases)) is not None and _in_range(entry.occurred_at, start, end)
            )
        except Exception as exc:
            logger.error("entity timeline conversations unavailable error_type=%s", type(exc).__name__)
            unavailable_sources.append(TimelineSource.conversations)

    if TimelineSource.calendar in requested_sources and aliases.values:
        try:
            rows = list(
                islice(
                    list_entity_timeline_meetings(
                        uid,
                        db_client=firestore_db,
                        limit=MAX_TIMELINE_SOURCE_SCAN + 1,
                        start_date=start,
                        end_date=end,
                    ),
                    MAX_TIMELINE_SOURCE_SCAN + 1,
                )
            )
            scanned_count += min(len(rows), MAX_TIMELINE_SOURCE_SCAN)
            if len(rows) > MAX_TIMELINE_SOURCE_SCAN:
                truncated_sources.append(TimelineSource.calendar)
            entries.extend(
                entry
                for row in rows[:MAX_TIMELINE_SOURCE_SCAN]
                if (entry := _calendar_entry(row, aliases)) is not None and _in_range(entry.occurred_at, start, end)
            )
        except Exception as exc:
            logger.error("entity timeline calendar unavailable error_type=%s", type(exc).__name__)
            unavailable_sources.append(TimelineSource.calendar)

    if TimelineSource.screen in requested_sources and aliases.values:
        try:
            rows = list(
                islice(
                    list_entity_timeline_screen_activity(
                        uid,
                        db_client=firestore_db,
                        limit=MAX_TIMELINE_SOURCE_SCAN + 1,
                        start_date=start,
                        end_date=end,
                    ),
                    MAX_TIMELINE_SOURCE_SCAN + 1,
                )
            )
            scanned_count += min(len(rows), MAX_TIMELINE_SOURCE_SCAN)
            if len(rows) > MAX_TIMELINE_SOURCE_SCAN:
                truncated_sources.append(TimelineSource.screen)
            entries.extend(
                entry
                for row in rows[:MAX_TIMELINE_SOURCE_SCAN]
                if (entry := _screen_entry(row, aliases)) is not None and _in_range(entry.occurred_at, start, end)
            )
        except Exception as exc:
            logger.error("entity timeline screen unavailable error_type=%s", type(exc).__name__)
            unavailable_sources.append(TimelineSource.screen)

    merged, result_truncated = _merge_timeline_entries(entries, limit=bounded_limit)
    timeline = EntityTimeline(
        entity=reference,
        entries=merged,
        truncated=result_truncated or bool(truncated_sources),
        scanned_count=scanned_count,
        aliases_resolved=aliases.resolved,
        aliases_ambiguous=aliases.ambiguous,
        requested_sources=requested_sources,
        truncated_sources=tuple(truncated_sources),
        unavailable_sources=tuple(unavailable_sources),
    )
    return format_entity_timeline(timeline)


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
