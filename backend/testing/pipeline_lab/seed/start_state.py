"""Snapshot -> start state for one replayed day (DESIGN L8). Pure: no IO beyond reading.

Rules, all applied to every entity:
1. **Cut**: rows created at or after ``day_start`` are removed (conversations by
   ``created_at``/``started_at``; daily summaries also by their ``date``). Edits made
   after the day start cannot be undone from a later snapshot, so the result is
   always labelled ``start_state: approximate``.
2. **Strip** stored LLM input/output hashes (``notes_llm_input_hash`` and friends) so
   the product's ``llm_input_dedupe`` cannot reuse production notes.
3. **Remap** the source uid to ``local-dev-user`` everywhere it appears: values, map
   keys, ids such as ``<uid>-<cid>`` and document paths. The source uid is never
   logged or written; only counts are reported.
4. **Drop** exporter byte markers (``{"_bytes": n}``): the bytes are not in the
   snapshot (e.g. a speaker embedding), so the field is removed rather than faked.
5. Add a synthetic FCM token so notification paths reach the capture sink.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping

from testing.pipeline_lab.stack import LAB_UID
from testing.pipeline_lab.stack.io import parse_time

HASH_FIELD = re.compile(r'(^|_)llm_(input|output)_hash$|_llm_hashes$|^llm_hashes$')
SYNTHETIC_FCM_TOKEN = 'pipeline-lab-synthetic-fcm-token'
SYNTHETIC_DEVICE_KEY = 'pipeline-lab-device'

# Created-at field preference per entity (first present wins).
CREATED_FIELDS: dict[str, tuple[str, ...]] = {
    'conversations': ('created_at', 'started_at'),
    'memories': ('created_at',),
    'action_items': ('created_at',),
    'people': ('created_at',),
    'goals': ('created_at',),
    'daily_summaries': ('created_at',),
    'meetings': ('start_time', 'created_at'),
}


class SourceUidError(ValueError):
    pass


@dataclass
class StartStateReport:
    kept: dict[str, int] = field(default_factory=dict)
    cut: dict[str, int] = field(default_factory=dict)
    undated: dict[str, int] = field(default_factory=dict)
    hashes_stripped: int = 0
    byte_fields_dropped: int = 0
    uid_replacements: int = 0
    start_state: str = 'approximate'

    def as_dict(self) -> dict[str, Any]:
        return {
            'kept': self.kept,
            'cut': self.cut,
            'undated': self.undated,
            'hashes_stripped': self.hashes_stripped,
            'byte_fields_dropped': self.byte_fields_dropped,
            'uid_replacements': self.uid_replacements,
            'start_state': self.start_state,
        }


@dataclass
class StartState:
    uid: str
    day_start: datetime
    profile: dict[str, Any]
    conversations: list[dict[str, Any]]
    memories: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    people: list[dict[str, Any]]
    goals: list[dict[str, Any]]
    daily_summaries: list[dict[str, Any]]
    meetings: list[dict[str, Any]]
    fcm_token: dict[str, Any]
    report: StartStateReport

    def entities(self) -> dict[str, list[dict[str, Any]]]:
        return {
            'conversations': self.conversations,
            'memories': self.memories,
            'action_items': self.action_items,
            'people': self.people,
            'goals': self.goals,
            'daily_summaries': self.daily_summaries,
            'meetings': self.meetings,
        }


class _Rewriter:
    def __init__(self, source_uid: str, target_uid: str, report: StartStateReport):
        if not source_uid or len(source_uid) < 6:
            raise SourceUidError('source uid is required for remapping')
        self.source = source_uid
        self.target = target_uid
        self.report = report

    def text(self, value: str) -> str:
        if self.source in value:
            self.report.uid_replacements += value.count(self.source)
            return value.replace(self.source, self.target)
        return value

    def __call__(self, value: Any, key: str = '') -> Any:
        if isinstance(value, dict):
            if set(value) == {'_bytes'}:
                return _DROP
            out = {}
            for k, v in value.items():
                if isinstance(k, str) and HASH_FIELD.search(k):
                    self.report.hashes_stripped += 1
                    continue
                rewritten = self(v, k)
                if rewritten is _DROP:
                    self.report.byte_fields_dropped += 1
                    continue
                out[self.text(k) if isinstance(k, str) else k] = rewritten
            return out
        if isinstance(value, list):
            items = [self(item, key) for item in value]
            dropped = sum(1 for item in items if item is _DROP)
            self.report.byte_fields_dropped += dropped
            return [item for item in items if item is not _DROP]
        if isinstance(value, str):
            return self.text(value)
        return value


_DROP = object()


def detect_source_uid(rows: Iterable[Mapping[str, Any]], uid_prefix: str | None) -> str:
    """Find the owner uid from row ``uid`` fields, checked against the manifest prefix."""
    seen: set[str] = set()
    for row in rows:
        value = row.get('uid')
        if isinstance(value, str) and value:
            seen.add(value)
        if len(seen) > 1:
            break
    if len(seen) != 1:
        raise SourceUidError('could not detect exactly one source uid; pass it explicitly')
    uid = next(iter(seen))
    if uid_prefix and not uid.startswith(uid_prefix):
        raise SourceUidError('detected uid does not match the manifest prefix')
    return uid


def created_at(kind: str, row: Mapping[str, Any]) -> datetime | None:
    for name in CREATED_FIELDS.get(kind, ('created_at',)):
        parsed = parse_time(row.get(name))
        if parsed is not None:
            return parsed
    return None


def _keep(kind: str, row: Mapping[str, Any], day_start: datetime, day_date: str, report: StartStateReport) -> bool:
    if kind == 'daily_summaries' and isinstance(row.get('date'), str) and row['date'] >= day_date:
        report.cut[kind] = report.cut.get(kind, 0) + 1
        return False
    when = created_at(kind, row)
    if when is None:
        report.undated[kind] = report.undated.get(kind, 0) + 1
        return True
    if when >= day_start:
        report.cut[kind] = report.cut.get(kind, 0) + 1
        return False
    return True


def build_start_state(
    snapshot: Any,
    day_start: datetime,
    *,
    day_date: str,
    source_uid: str | None = None,
    target_uid: str = LAB_UID,
    time_zone: str | None = None,
) -> StartState:
    """``snapshot`` is a :class:`SnapshotReader` (or anything with the same methods)."""
    if day_start.tzinfo is None:
        raise ValueError('day_start must be timezone-aware')
    day_start = day_start.astimezone(timezone.utc)
    report = StartStateReport()
    raw = {
        'conversations': list(snapshot.conversations()),
        'memories': list(snapshot.memories()),
        'action_items': list(snapshot.action_items()),
        'people': list(snapshot.people()),
        'goals': list(snapshot.goals()),
        'daily_summaries': list(snapshot.daily_summaries()),
        'meetings': list(snapshot.meetings()),
    }
    if source_uid is None:
        source_uid = detect_source_uid(
            (row for rows in raw.values() for row in rows), snapshot.manifest().get('uid_prefix')
        )
    rewrite = _Rewriter(source_uid, target_uid, report)
    kept: dict[str, list[dict[str, Any]]] = {}
    for kind, rows in raw.items():
        selected = [rewrite(row) for row in rows if _keep(kind, row, day_start, day_date, report)]
        for row in selected:
            if 'uid' in row:
                row['uid'] = target_uid
        kept[kind] = selected
        report.kept[kind] = len(selected)
    profile = rewrite(snapshot.profile())
    if isinstance(profile, dict):
        profile['uid'] = target_uid
        profile.pop('id', None)
    else:
        profile = {'uid': target_uid}
    tz = time_zone or profile.get('time_zone') or 'UTC'
    fcm = {'device_key': SYNTHETIC_DEVICE_KEY, 'fcm_token': SYNTHETIC_FCM_TOKEN, 'time_zone': tz}
    return StartState(
        uid=target_uid,
        day_start=day_start,
        profile=profile,
        fcm_token=fcm,
        report=report,
        **kept,
    )


def assert_no_source_uid(state: StartState, source_uid: str) -> None:
    """Defence in depth before any write: the source uid must not survive anywhere."""
    from testing.pipeline_lab.stack.io import dumps

    payload = dumps({'profile': state.profile, **state.entities(), 'fcm': state.fcm_token})
    if source_uid in payload:
        raise SourceUidError('source uid survived remapping')
