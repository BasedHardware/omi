"""Typed records for the pipeline-lab store contract (DESIGN "Store contract").

Dependency-free (stdlib only) and stable: every lane imports these at integration.
Each record is a dataclass with ``to_json()`` / ``from_json()``. Unknown keys read
from disk are kept in ``extra`` and written back unchanged, so a lane may add a
field before the contract names it without another lane's round trip dropping it.

Times are ISO-8601 UTC strings (``utc_iso``). ``content_key`` gives the stable
item key verdicts attach to: it hashes normalized content, so the same task or
memory text keeps its key across re-runs.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import typing
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional, TypeVar

CONTRACT_VERSION = 1


class Stage(str, Enum):
    """Pipeline stages in execution order (DESIGN "Stages")."""

    INGEST = 'ingest'
    TRANSCRIBE = 'transcribe'
    BOUNDARIES = 'boundaries'
    SPEAKERS = 'speakers'
    DISCARD = 'discard'
    NOTES = 'notes'
    MEMORIES = 'memories'
    TASKS = 'tasks'
    NOTIFICATIONS = 'notifications'
    GOALS = 'goals'
    DAILY_SUMMARY = 'daily_summary'
    CHAT_INDEX = 'chat_index'


STAGES: tuple[str, ...] = tuple(stage.value for stage in Stage)


def wire_speaker_label(voice: int) -> str:
    """The stored segment ``speaker`` value for diarized voice ``voice`` (``SPEAKER_00``): an id on the
    wire, never display text. Display names come from ``utils.speakers.display``."""
    return 'SPEAKER_' + format(voice, '02d')


def stage_index(stage: str) -> int:
    try:
        return STAGES.index(stage)
    except ValueError:
        raise ValueError(f'unknown stage {stage!r}; expected one of {", ".join(STAGES)}') from None


class ItemKind(str, Enum):
    SUMMARY = 'summary'
    TASK = 'task'
    MEMORY = 'memory'
    NOTIFICATION = 'notification'
    BOUNDARY = 'boundary'
    SPEAKER = 'speaker'
    TRANSCRIPT = 'transcript'
    DAILY_SUMMARY = 'daily_summary'


ITEM_KINDS: tuple[str, ...] = tuple(kind.value for kind in ItemKind)


class Mark(str, Enum):
    GOOD = 'good'
    BAD = 'bad'
    CLEAR = 'clear'  # withdraws an earlier mark on the same target (RULINGS 4)


MARKS: tuple[str, ...] = tuple(mark.value for mark in Mark)


class RunStatus(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETE = 'complete'
    FAILED = 'failed'
    STOPPED = 'stopped'  # spend cap or operator stop; resumable


class StageState(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETE = 'complete'
    CACHED = 'cached'
    FAILED = 'failed'
    SKIPPED = 'skipped'
    NOT_REGISTERED = 'not_registered'


class Lane(str, Enum):
    """How production captured a conversation (DESIGN measured facts)."""

    RECORD = 'record'  # record_lane_owner=batch_live_v1: device records, server batch transcribes
    SYNC = 'sync'  # /v2/sync-local-files offline sync
    STREAMING = 'streaming'  # /v4/listen
    UNKNOWN = 'unknown'


class GapKind(str, Enum):
    UNKNOWN = 'unknown'
    SILENCE = 'silence'
    OFFLINE = 'offline'


START_STATE_APPROXIMATE = 'approximate'


def utc_iso(value: Optional[datetime] = None) -> str:
    """ISO-8601 UTC with a ``Z`` suffix; naive datetimes are taken as UTC."""
    moment = value or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def parse_time(value: Any) -> Optional[datetime]:
    """Lenient reader for snapshot and contract times: ISO (``Z`` allowed), epoch seconds or a datetime.

    Returns an aware UTC datetime, or None for empty or unparseable values.
    """
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        try:
            return parse_utc(value)
        except ValueError:
            return None
    return None


# ---- stable content keys -------------------------------------------------------

_SPACE = re.compile(r'\s+')
_EDGE_PUNCT = re.compile(r'^[\s\W_]+|[\s\W_]+$', re.UNICODE)


def normalize_text(text: str) -> str:
    """NFKC, casefold, collapse whitespace, trim edge punctuation.

    Inner punctuation is kept: "3.5" and "35" must not collide.
    """
    folded = unicodedata.normalize('NFKC', text).casefold()
    folded = _SPACE.sub(' ', folded)
    return _EDGE_PUNCT.sub('', folded)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=_json_default)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, Mapping):
        return {str(k): _normalize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(v) for v in value]
    return value


def content_key(kind: str, content: Any) -> str:
    """Stable 16-hex key of normalized content, namespaced by item kind.

    ``content`` is the identity-bearing text (a task description, a memory's
    content) or a small mapping of identity fields. Timestamps, ids and model
    metadata must not be passed in: they change between runs.
    """
    if kind not in ITEM_KINDS:
        raise ValueError(f'unknown item kind {kind!r}')
    digest = hashlib.sha256(f'{kind}\x00{canonical_json(_normalize_value(content))}'.encode('utf-8'))
    return digest.hexdigest()[:16]


def task_key(description: str) -> str:
    return content_key(ItemKind.TASK.value, description)


def memory_key(content: str) -> str:
    return content_key(ItemKind.MEMORY.value, content)


def notification_key(title: str, body: str) -> str:
    return content_key(ItemKind.NOTIFICATION.value, {'title': title, 'body': body})


# ---- JSON (de)serialisation ------------------------------------------------------


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return utc_iso(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return value.to_json()  # type: ignore[union-attr]
    raise TypeError(f'not JSON serialisable: {type(value).__name__}')


R = TypeVar('R', bound='Record')
_HINTS: dict[type, dict[str, Any]] = {}


def _hints(cls: type) -> dict[str, Any]:
    if cls not in _HINTS:
        _HINTS[cls] = typing.get_type_hints(cls)
    return _HINTS[cls]


def _decode(tp: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = typing.get_origin(tp)
    if origin is typing.Union:
        options = [arg for arg in typing.get_args(tp) if arg is not type(None)]
        return _decode(options[0], value) if len(options) == 1 else value
    if origin in (list, tuple):
        (item,) = typing.get_args(tp)[:1] or (Any,)
        return [_decode(item, v) for v in value]
    if origin is dict:
        args = typing.get_args(tp)
        item = args[1] if len(args) == 2 else Any
        return {str(k): _decode(item, v) for k, v in value.items()}
    if isinstance(tp, type) and issubclass(tp, Record):
        return tp.from_json(value)
    if tp is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def _encode(value: Any) -> Any:
    if isinstance(value, Record):
        return value.to_json()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    return value


class Record:
    """Base for contract records: dataclass fields plus a pass-through ``extra``."""

    extra: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for item in dataclasses.fields(self):  # type: ignore[arg-type]
            if item.name == 'extra':
                continue
            out[item.name] = _encode(getattr(self, item.name))
        for key, value in (self.extra or {}).items():
            out.setdefault(key, value)
        return out

    @classmethod
    def from_json(cls: type[R], data: Mapping[str, Any]) -> R:
        if not isinstance(data, Mapping):
            raise TypeError(f'{cls.__name__} expects an object, got {type(data).__name__}')
        hints = _hints(cls)
        names = {item.name for item in dataclasses.fields(cls) if item.name != 'extra'}  # type: ignore[arg-type]
        kwargs = {name: _decode(hints[name], data[name]) for name in names if name in data}
        extra = {key: value for key, value in data.items() if key not in names}
        return cls(**kwargs, extra=extra)  # type: ignore[call-arg]

    def to_line(self) -> str:
        return canonical_json(self.to_json())


def _extra() -> dict[str, Any]:
    return field(default_factory=dict)


# ---- corpus ---------------------------------------------------------------------


@dataclass
class Gap(Record):
    start: str
    end: str
    kind: str = GapKind.UNKNOWN.value
    extra: dict[str, Any] = _extra()


@dataclass
class Coverage(Record):
    audio_seconds: float = 0.0
    conversations: int = 0
    with_audio: int = 0
    lanes: dict[str, int] = field(default_factory=dict)
    gaps: list[Gap] = field(default_factory=list)
    extra: dict[str, Any] = _extra()


@dataclass
class CorpusDay(Record):
    """``corpus/<day_id>/day.json``."""

    day_id: str
    date: str  # YYYY-MM-DD in ``timezone``
    timezone: str
    source_snapshot: Optional[str] = None  # a label, never a private path in git
    start_state_snapshot: Optional[str] = None
    coverage: Coverage = field(default_factory=Coverage)
    extra: dict[str, Any] = _extra()


@dataclass
class AudioIndexEntry(Record):
    """One row of ``corpus/<day_id>/audio/index.json`` (a JSON list)."""

    conversation_id: str
    path: str  # relative to the audio directory
    start: str
    end: str
    codec: str
    sample_rate: int
    extra: dict[str, Any] = _extra()


# ---- run --------------------------------------------------------------------------


@dataclass
class StageRun(Record):
    status: str = StageState.PENDING.value
    cache_hits: int = 0
    cache_misses: int = 0
    extra: dict[str, Any] = _extra()


@dataclass
class RunRecord(Record):
    """``runs/<run_id>/run.json``."""

    run_id: str
    day_id: str
    ref: str
    commit: Optional[str] = None  # full sha the ref resolved to (RULINGS 2)
    backend_tree: Optional[str] = None
    overlay: dict[str, Any] = field(default_factory=dict)
    start_state: str = START_STATE_APPROXIMATE
    status: str = RunStatus.PENDING.value
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    spend_usd: float = 0.0
    budget_usd: float = 5.0
    timings: dict[str, float] = field(default_factory=dict)
    stages: dict[str, StageRun] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = _extra()


@dataclass
class Segment(Record):
    start: float  # seconds from conversation start
    end: float
    speaker: Optional[str] = None
    speaker_name: Optional[str] = None
    is_user: bool = False
    text: str = ''
    extra: dict[str, Any] = _extra()


@dataclass
class Structured(Record):
    title: str = ''
    overview: str = ''
    emoji: str = ''
    category: str = ''
    events: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = _extra()


@dataclass
class ActionItem(Record):
    key: str
    description: str
    due_at: Optional[str] = None
    completed: bool = False
    extra: dict[str, Any] = _extra()

    @classmethod
    def make(cls, description: str, **kwargs: Any) -> 'ActionItem':
        return cls(key=task_key(description), description=description, **kwargs)


@dataclass
class MemoryItem(Record):
    key: str
    content: str
    category: str = ''
    extra: dict[str, Any] = _extra()

    @classmethod
    def make(cls, content: str, **kwargs: Any) -> 'MemoryItem':
        return cls(key=memory_key(content), content=content, **kwargs)


@dataclass
class Notification(Record):
    at: str
    title: str
    body: str
    trigger: str
    extra: dict[str, Any] = _extra()


@dataclass
class Evaluable(Record):
    boundaries: bool = True
    reason: str = ''
    extra: dict[str, Any] = _extra()


@dataclass
class ConversationRecord(Record):
    """``runs/<run_id>/conversations/<id>.json``; baseline rows use the same shape."""

    id: str
    baseline_id: Optional[str] = None
    baseline_ids: Optional[list[str]] = None  # set when a replay merged several production rows (RULINGS 2)
    lane: str = Lane.UNKNOWN.value
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    discarded: bool = False
    discard_reason: Optional[str] = None
    language: Optional[str] = None
    segments: list[Segment] = field(default_factory=list)
    structured: Optional[Structured] = None
    action_items: list[ActionItem] = field(default_factory=list)
    memories: list[MemoryItem] = field(default_factory=list)
    notifications: list[Notification] = field(default_factory=list)
    llm_call_ids: list[str] = field(default_factory=list)
    evaluable: Evaluable = field(default_factory=Evaluable)
    # Conversations v3: the source recordings a window was planned over (in order) and what the
    # phone's Home reads (visible, home_hidden_reason, kind, tile_state, notes state). ``None``
    # on classic rows. Pairing with production is by shared recording (``v3/export.py``).
    recordings: Optional[list[str]] = None
    v3: Optional[dict[str, Any]] = None
    extra: dict[str, Any] = _extra()


@dataclass
class DailySummary(Record):
    """``runs/<id>/day.json`` ``daily_summary`` and ``corpus/<day>/baseline/daily_summary.json`` (RULINGS 5)."""

    title: str = ''
    overview: str = ''
    highlights: list[Any] = field(default_factory=list)
    extra: dict[str, Any] = _extra()


@dataclass
class Goal(Record):
    title: str = ''
    progress_before: Optional[float] = None
    progress_after: Optional[float] = None
    target: Optional[float] = None
    note: str = ''
    extra: dict[str, Any] = _extra()


@dataclass
class MemoryDelta(Record):
    added: list[Any] = field(default_factory=list)
    updated: list[Any] = field(default_factory=list)
    removed: list[Any] = field(default_factory=list)
    extra: dict[str, Any] = _extra()


@dataclass
class RunDay(Record):
    """``runs/<run_id>/day.json``."""

    daily_summary: Optional[DailySummary] = None
    goals: list[Goal] = field(default_factory=list)
    memory_delta: MemoryDelta = field(default_factory=MemoryDelta)
    notifications: list[Notification] = field(default_factory=list)
    chat_index: Optional[dict[str, Any]] = None  # readiness of the replayed day for chat (chain lane)
    recap: Optional[dict[str, Any]] = None  # how and when the daily summary ran
    extra: dict[str, Any] = _extra()


@dataclass
class LlmCall(Record):
    """One row of ``runs/<run_id>/llm_calls.jsonl``."""

    id: str
    at: str
    stage: Optional[str] = None
    conversation_id: Optional[str] = None
    feature: Optional[str] = None
    model: Optional[str] = None
    prompt: Any = None
    output: Any = None
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    cache_hit: bool = False
    ms: float = 0.0
    extra: dict[str, Any] = _extra()


@dataclass
class VendorLogEntry(Record):
    """One row of ``runs/<run_id>/vendor_log.jsonl``: what audio went where."""

    at: str
    vendor: str
    purpose: str
    audio_seconds: float = 0.0
    usd: float = 0.0
    destination: str = ''
    extra: dict[str, Any] = _extra()


@dataclass
class Decision(Record):
    """One row of ``runs/<run_id>/decisions.jsonl``: a pinned serving/mode decision."""

    at: str
    name: str
    mode: str
    source: str
    extra: dict[str, Any] = _extra()


@dataclass
class Verdict(Record):
    """One row of ``$VERDICTS/verdicts.jsonl``. Append-only; the latest row per item wins.

    ``conversation_id`` is the production (baseline) id when the item's conversation has one,
    else the replay id, so a mark follows its item across runs (RULINGS 4). A ``clear`` row
    withdraws the earlier mark on the same target.
    """

    id: str
    at: str
    run_id: str
    day_id: str
    ref: str
    conversation_id: Optional[str]
    item_kind: str
    item_key: str
    mark: str
    note: str = ''
    item_snapshot: Any = None
    reviewer: Optional[str] = None  # the tailnet login when marked through tailscale serve
    extra: dict[str, Any] = _extra()

    def validate(self) -> 'Verdict':
        if self.item_kind not in ITEM_KINDS:
            raise ValueError(f'unknown item_kind {self.item_kind!r}')
        if self.mark not in MARKS:
            raise ValueError(f'mark must be one of {", ".join(MARKS)}, got {self.mark!r}')
        if not self.item_key:
            raise ValueError('item_key is required')
        return self

    @property
    def target(self) -> tuple[str, Optional[str], str, str]:
        """Identity a newer verdict replaces: same day, conversation, kind and key."""
        return (self.day_id, self.conversation_id, self.item_kind, self.item_key)
