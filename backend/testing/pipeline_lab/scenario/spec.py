"""The scenario file: a declarative capture -> Finish -> Home story, validated into an ordered event plan.

Stdlib only (no product imports), so the format and the plan are unit-tested without a stack.

A scenario is one JSON object. Times are seconds from ``t0`` (a synthetic UTC instant)::

    {
      "name": "finish_single_recording_fast",
      "description": "...",
      "t0": "2026-03-14T09:00:00Z",                    # optional, this default
      "env": {"CONVERSATIONS_V3_...": "on"},            # overlay env on top of the production profile
      "origins": [{"id": "O", "source": "omi"}],         # capture devices (source omi|phone)
      "recordings": [                                    # batch-lane captures (audio now, transcript later)
        {"id": "B", "origin": "O", "session": "S1", "audio": [0, 40],
         "sealed_at": 41,                                 # capture close; default: audio end
         "transcript_at": 120,                            # canonical batch transcript lands; null = never
         "speech": [ {"at": 0.5, "end": 3.5, "text": "...", "speaker": "SPEAKER_00", "is_user": true},
                     {"fill": [4, 40], "every": 4, "words": 10, "speakers": ["SPEAKER_00", "SPEAKER_01"]} ]}
      ],
      "gaps": [{"origin": "O", "between": ["A", "B"], "reason": "reconnect"}],   # stream gaps (checked)
      "sync": [{"id": "F", "origin": "O", "audio": [1.5, 2.7], "arrives_at": 162, "speech": [...]}],
      "finish": {"at": 38, "fast_finish": true, "provisional_latency": 15},
      "expect": [{"at": 60, "label": "finish_visible", "conversation_of": "@finish", "visible": true}],
      "expected_failure": {"reason": "SCA-xxxx: ...", "checks": ["finish_visible"], "strict": true},
      "tail_seconds": 1800
    }

Labels name documents (``scn-<label lowercased>``), so recording ids, and origin ids, must differ in more
than case. Every field of one ``expect`` row must hold for the same conversation, so put membership,
visibility and manual end of one conversation in one row.

``expected_failure`` names the ``label`` of each check the known bug fails (``checks``). Every other check
must still pass: a scenario whose unnamed check fails is ``failed``, not ``xfail``.

Speech text must be synthetic. ``fill`` writes placeholder lines from a fixed word list; a line whose
text contains ``switching topics`` makes the lab's fake outline start a new conversation there.

The plan (``plan_events``) is what the runner feeds the v3 driver, earliest first:

- ``capture_start`` (each recording's first audio): the live row is created through capture admission;
- ``finish`` (the tap): the product's Finish branch is taken at that instant; a batch recording is still
  capturing from its first audio until its seal (inclusive, since a tie runs the tap first), and the tap
  ends the latest-started one, as ``get_in_progress_conversation`` orders by ``created_at``;
- ``seal`` (capture close): the row completes; a Finish that landed while it was capturing is stored on it;
- ``sync`` (a device-sync fragment arrives): a completed recording with its transcript;
- ``admission`` (batch record admission): the manual-finish hook runs; with fast finish on it is placed at
  ``finish.at + provisional_latency`` for the recording the Finish cut, so the provisional transcript
  lands at that instant;
- ``transcript`` (the canonical batch transcript lands);
- ``checkpoint`` (an ``expect`` row with ``at``): the conversations are read and the checks evaluated.

Ties at one instant run in that order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping, Optional, Sequence

DEFAULT_T0 = '2026-03-14T09:00:00+00:00'
DEFAULT_TAIL_SECONDS = 1800.0
DEFAULT_ADMISSION_LAG = 5.0
EVENT_ORDER = ('capture_start', 'finish', 'seal', 'sync', 'admission', 'transcript', 'checkpoint')
SOURCES = ('omi', 'phone')
FINISH_ALIAS = '@finish'
# A neutral, obviously synthetic vocabulary for ``fill`` lines.
FILL_WORDS = (
    'lantern', 'harbor', 'maple', 'pebble', 'orchard', 'canvas', 'meadow', 'copper', 'willow', 'saffron',
    'beacon', 'thistle', 'juniper', 'quarry', 'marble', 'hazel', 'tundra', 'velvet', 'cobalt', 'fennel',
)  # fmt: skip
CHECK_FIELDS = ('recordings', 'recordings_include', 'visible', 'manual_end', 'hidden_reason', 'min_words', 'kind')
_LABEL = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')


class ScenarioError(ValueError):
    """The scenario file is malformed."""


@dataclass(frozen=True)
class Line:
    start: float
    end: float
    text: str
    speaker: str = 'SPEAKER_00'
    is_user: bool = True


@dataclass(frozen=True)
class Recording:
    label: str
    origin: str
    lane: str  # batch | sync
    audio: tuple[float, float]
    lines: tuple[Line, ...]
    session: Optional[str] = None
    sealed_at: Optional[float] = None  # batch
    transcript_at: Optional[float] = None  # batch; None = never lands
    arrives_at: Optional[float] = None  # sync

    @property
    def doc_id(self) -> str:
        return 'scn-' + self.label.lower()

    @property
    def sealed(self) -> float:
        """When the capture closes (batch): ``sealed_at``, else the end of its audio."""
        return float(self.sealed_at if self.sealed_at is not None else self.audio[1])

    def words(self) -> int:
        return sum(len(line.text.split()) for line in self.lines)


@dataclass(frozen=True)
class Finish:
    at: float
    fast_finish: bool = True
    provisional_latency: float = 15.0


@dataclass(frozen=True)
class Check:
    """One expectation. ``conversation_of`` names a recording label or ``@finish``; ``no_hidden_with`` is
    the label whose speech no hidden conversation may hold."""

    raw: Mapping[str, Any]
    at: Optional[float] = None
    label: Optional[str] = None
    conversation_of: Optional[str] = None
    no_hidden_with: Optional[str] = None
    fields: Mapping[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        when = (f'[{self.label}] ' if self.label else '') + (f'@+{self.at:g}s ' if self.at is not None else '')
        if self.no_hidden_with:
            return f'{when}no hidden conversation holds {self.no_hidden_with}'
        parts = ', '.join(f'{k}={json.dumps(v)}' for k, v in self.fields.items())
        return f'{when}conversation of {self.conversation_of}: {parts}'


@dataclass(frozen=True)
class Origin:
    label: str
    source: str = 'omi'


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    t0: datetime
    origins: Mapping[str, Origin]
    recordings: tuple[Recording, ...]
    finish: Optional[Finish]
    checks: tuple[Check, ...]
    env: Mapping[str, str]
    gaps: tuple[Mapping[str, Any], ...] = ()
    expected_failure: Optional[Mapping[str, Any]] = None
    tail_seconds: float = DEFAULT_TAIL_SECONDS
    admission_lag: float = DEFAULT_ADMISSION_LAG
    path: Optional[str] = None

    def at(self, seconds: float) -> datetime:
        return self.t0 + timedelta(seconds=seconds)

    def offset(self, instant: datetime) -> float:
        return round((instant - self.t0).total_seconds(), 3)

    def recording(self, label: str) -> Recording:
        for rec in self.recordings:
            if rec.label == label:
                return rec
        raise KeyError(label)

    def label_of(self, doc_id: str) -> str:
        for rec in self.recordings:
            if rec.doc_id == doc_id:
                return rec.label
        return '?' + doc_id[:8]

    def open_at(self, seconds: float) -> list[Recording]:
        """Batch recordings still ``in_progress`` at a Finish tap at ``seconds``: from their first audio
        (``capture_start`` runs before a tied tap) through their seal (the tap runs before a tied seal)."""
        return [rec for rec in self.recordings if rec.lane == 'batch' and rec.audio[0] <= seconds <= rec.sealed]

    def finish_target(self) -> Optional[Recording]:
        """The batch recording the tap ends: production's in-progress branch takes the newest in-progress
        row (``created_at`` = first audio)."""
        if self.finish is None:
            return None
        capturing = self.open_at(self.finish.at)
        return max(capturing, key=lambda rec: rec.audio[0]) if capturing else None


@dataclass(frozen=True)
class ScenarioEvent:
    """One scripted event. ``instant``/``recording_id``/``instant_source`` are what ``v3.driver.V3Driver``
    reads from an arrival, so the real driver loop runs these unchanged."""

    instant: datetime
    kind: str
    ref: str
    check_index: Optional[int] = None

    @property
    def recording_id(self) -> str:
        return self.ref

    @property
    def instant_source(self) -> str:
        return self.kind


# ---- parsing ------------------------------------------------------------------------------------


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioError(f'{where}: expected a number of seconds')
    return float(value)


def _span(value: Any, where: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ScenarioError(f'{where}: expected [start, end] seconds')
    start, end = _number(value[0], where), _number(value[1], where)
    if not start < end:
        raise ScenarioError(f'{where}: start must be before end')
    return start, end


def _label(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _LABEL.match(value):
        raise ScenarioError(f'{where}: a label is a letter then up to 31 letters, digits, - or _')
    return value


def _keys(raw: Mapping[str, Any], allowed: Sequence[str], where: str) -> None:
    unknown = sorted(set(raw) - set(allowed))
    if unknown:
        raise ScenarioError(f'{where}: unknown keys {unknown}')


def fill_lines(
    span: tuple[float, float], *, every: float, words: int, speakers: Sequence[str], seed: int
) -> list[Line]:
    """Placeholder lines over ``span``: one per ``every`` seconds, ``words`` words each, speakers in turn
    (the first speaker is the wearer)."""
    if every <= 0.5 or words <= 0:
        raise ScenarioError('fill: every must exceed 0.5 s and words must be positive')
    out: list[Line] = []
    at, index = span[0], 0
    while at + 0.5 <= span[1]:
        speaker = speakers[index % len(speakers)]
        text = ' '.join(FILL_WORDS[(seed + index * words + k) % len(FILL_WORDS)] for k in range(words))
        out.append(Line(at, min(at + every - 0.5, span[1]), text.capitalize() + '.', speaker, speaker == speakers[0]))
        at += every
        index += 1
    return out


def _lines(raw: Any, where: str, audio: tuple[float, float], seed: int) -> tuple[Line, ...]:
    if not isinstance(raw, list) or not raw:
        raise ScenarioError(f'{where}: speech must be a non-empty list')
    lines: list[Line] = []
    for i, item in enumerate(raw):
        here = f'{where}[{i}]'
        if not isinstance(item, Mapping):
            raise ScenarioError(f'{here}: expected an object')
        if 'fill' in item:
            _keys(item, ('fill', 'every', 'words', 'speakers'), here)
            speakers = item.get('speakers') or ['SPEAKER_00']
            if not isinstance(speakers, list) or not all(isinstance(s, str) and s for s in speakers):
                raise ScenarioError(f'{here}: speakers must be a list of labels')
            lines.extend(
                fill_lines(
                    _span(item['fill'], here + '.fill'),
                    every=_number(item.get('every', 4), here + '.every'),
                    words=int(_number(item.get('words', 10), here + '.words')),
                    speakers=speakers,
                    seed=seed + i,
                )
            )
            continue
        _keys(item, ('at', 'end', 'text', 'speaker', 'is_user'), here)
        start, end = _span([item.get('at'), item.get('end')], here)
        text = item.get('text')
        if not isinstance(text, str) or not text.strip():
            raise ScenarioError(f'{here}: text must be non-empty synthetic text')
        lines.append(
            Line(start, end, text.strip(), str(item.get('speaker') or 'SPEAKER_00'), bool(item.get('is_user', True)))
        )
    lines.sort(key=lambda line: (line.start, line.end))
    for line in lines:
        if line.start < audio[0] - 0.01 or line.end > audio[1] + 0.01:
            raise ScenarioError(f'{where}: a line at {line.start:g}-{line.end:g}s is outside the audio {audio}')
    return tuple(lines)


def _recording(raw: Any, where: str, origins: Mapping[str, Origin], lane: str, seed: int) -> Recording:
    if not isinstance(raw, Mapping):
        raise ScenarioError(f'{where}: expected an object')
    allowed = ('id', 'origin', 'audio', 'speech', 'session')
    allowed += ('sealed_at', 'transcript_at') if lane == 'batch' else ('arrives_at',)
    _keys(raw, allowed, where)
    label = _label(raw.get('id'), where + '.id')
    origin = raw.get('origin')
    if origin not in origins:
        raise ScenarioError(f'{where}: origin {origin!r} is not declared in origins')
    audio = _span(raw.get('audio'), where + '.audio')
    lines = _lines(raw.get('speech'), where + '.speech', audio, seed)
    if lane == 'sync':
        arrives = _number(raw.get('arrives_at'), where + '.arrives_at')
        if arrives < audio[1]:
            raise ScenarioError(f'{where}: a sync fragment arrives after its audio ends')
        return Recording(label, origin, lane, audio, lines, session=raw.get('session'), arrives_at=arrives)
    sealed = _number(raw['sealed_at'], where + '.sealed_at') if raw.get('sealed_at') is not None else audio[1]
    if sealed < audio[1]:
        raise ScenarioError(f'{where}: sealed_at is before the audio ends')
    landed = _number(raw['transcript_at'], where + '.transcript_at') if raw.get('transcript_at') is not None else None
    if landed is not None and landed < sealed:
        raise ScenarioError(f'{where}: the batch transcript lands before the capture is sealed')
    return Recording(
        label, origin, lane, audio, lines, session=raw.get('session'), sealed_at=sealed, transcript_at=landed
    )


def _check(raw: Any, where: str, labels: set[str], has_finish: bool) -> Check:
    if not isinstance(raw, Mapping):
        raise ScenarioError(f'{where}: expected an object')
    _keys(raw, ('at', 'label', 'conversation_of', 'no_hidden_with', *CHECK_FIELDS), where)
    at = _number(raw['at'], where + '.at') if raw.get('at') is not None else None
    target, hidden = raw.get('conversation_of'), raw.get('no_hidden_with')
    if (target is None) == (hidden is None):
        raise ScenarioError(f'{where}: give exactly one of conversation_of or no_hidden_with')
    for name in (target, hidden):
        if name is None:
            continue
        if name == FINISH_ALIAS and not has_finish:
            raise ScenarioError(f'{where}: {FINISH_ALIAS} needs a finish')
        if name != FINISH_ALIAS and name not in labels:
            raise ScenarioError(f'{where}: unknown recording {name!r}')
    label = raw.get('label')
    if label is not None and (not isinstance(label, str) or not re.match(r'^[a-z0-9_]{1,64}$', label)):
        raise ScenarioError(f'{where}.label: lowercase letters, digits and _')
    fields = {k: raw[k] for k in CHECK_FIELDS if k in raw}
    if target is not None and not fields:
        raise ScenarioError(f'{where}: a conversation check names at least one of {list(CHECK_FIELDS)}')
    if hidden is not None and fields:
        raise ScenarioError(f'{where}: no_hidden_with takes no other fields')
    for key in ('recordings', 'recordings_include'):
        if key in fields:
            value = fields[key]
            if not isinstance(value, list) or not value or any(v not in labels for v in value):
                raise ScenarioError(f'{where}.{key}: a list of declared recording labels')
    return Check(raw=dict(raw), at=at, label=label, conversation_of=target, no_hidden_with=hidden, fields=fields)


def parse_scenario(raw: Any, *, path: Optional[str] = None) -> Scenario:
    if not isinstance(raw, Mapping):
        raise ScenarioError('a scenario is a JSON object')
    _keys(
        raw,
        (
            'name', 'description', 't0', 'env', 'origins', 'recordings', 'gaps', 'sync', 'finish', 'expect',
            'expected_failure', 'tail_seconds', 'admission_lag',
        ),
        'scenario',
    )  # fmt: skip
    name = raw.get('name')
    if not isinstance(name, str) or not re.match(r'^[a-z0-9_]{1,80}$', name):
        raise ScenarioError('name: lowercase letters, digits and _')
    try:
        t0 = datetime.fromisoformat(str(raw.get('t0') or DEFAULT_T0).replace('Z', '+00:00'))
    except ValueError:
        raise ScenarioError('t0: an ISO-8601 UTC instant') from None
    if t0.tzinfo is None:
        raise ScenarioError('t0: give a timezone (Z)')
    t0 = t0.astimezone(timezone.utc)
    env = raw.get('env') or {}
    if not isinstance(env, Mapping) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise ScenarioError('env: an object of string values')
    origins: dict[str, Origin] = {}
    for i, item in enumerate(raw.get('origins') or []):
        if not isinstance(item, Mapping):
            raise ScenarioError(f'origins[{i}]: expected an object')
        _keys(item, ('id', 'source'), f'origins[{i}]')
        source = item.get('source', 'omi')
        if source not in SOURCES:
            raise ScenarioError(f'origins[{i}].source: one of {SOURCES}')
        label = _label(item.get('id'), f'origins[{i}].id')
        if label.lower() in {o.lower() for o in origins}:
            raise ScenarioError(f'origins[{i}].id: origin ids must be unique, ignoring case')
        origins[label] = Origin(label, source)
    if not origins:
        raise ScenarioError('origins: declare at least one capture origin')
    recordings = [
        _recording(item, f'recordings[{i}]', origins, 'batch', seed=i * 7)
        for i, item in enumerate(raw.get('recordings') or [])
    ]
    recordings += [
        _recording(item, f'sync[{i}]', origins, 'sync', seed=100 + i * 7)
        for i, item in enumerate(raw.get('sync') or [])
    ]
    if not any(r.lane == 'batch' for r in recordings):
        raise ScenarioError('recordings: at least one')
    labels = [r.label for r in recordings]
    if len({r.doc_id for r in recordings}) != len(recordings):
        raise ScenarioError('recording ids must be unique across recordings and sync, ignoring case')
    finish = None
    if raw.get('finish') is not None:
        item = raw['finish']
        if not isinstance(item, Mapping):
            raise ScenarioError('finish: expected an object')
        _keys(item, ('at', 'fast_finish', 'provisional_latency'), 'finish')
        finish = Finish(
            at=_number(item.get('at'), 'finish.at'),
            fast_finish=bool(item.get('fast_finish', True)),
            provisional_latency=_number(item.get('provisional_latency', 15.0), 'finish.provisional_latency'),
        )
    gaps = tuple(_gap(item, f'gaps[{i}]', recordings) for i, item in enumerate(raw.get('gaps') or []))
    checks = tuple(
        _check(item, f'expect[{i}]', set(labels), finish is not None) for i, item in enumerate(raw.get('expect') or [])
    )
    check_labels = [c.label for c in checks if c.label is not None]
    if len(set(check_labels)) != len(check_labels):
        raise ScenarioError('expect: check labels must be unique')
    failure = raw.get('expected_failure')
    if failure is not None:
        if not isinstance(failure, Mapping) or not str(failure.get('reason') or '').strip():
            raise ScenarioError('expected_failure: {"reason": "...", "checks": ["label"], "strict": true}')
        _keys(failure, ('reason', 'checks', 'strict'), 'expected_failure')
        named = failure.get('checks')
        if not isinstance(named, list) or not named or not all(isinstance(n, str) for n in named):
            raise ScenarioError('expected_failure.checks: the labels of the checks the known bug fails')
        if any(n not in check_labels for n in named):
            raise ScenarioError(f'expected_failure.checks: unknown check label in {named}')
        if len(set(named)) == len(checks):
            raise ScenarioError('expected_failure.checks: leave at least one check that must pass')
    scenario = Scenario(
        name=name,
        description=str(raw.get('description') or ''),
        t0=t0,
        origins=origins,
        recordings=tuple(recordings),
        finish=finish,
        checks=checks,
        env=dict(env),
        gaps=gaps,
        expected_failure=dict(failure) if failure else None,
        tail_seconds=_number(raw.get('tail_seconds', DEFAULT_TAIL_SECONDS), 'tail_seconds'),
        admission_lag=_number(raw.get('admission_lag', DEFAULT_ADMISSION_LAG), 'admission_lag'),
        path=path,
    )
    if finish is not None:
        capturing = scenario.open_at(finish.at)
        if len({rec.audio[0] for rec in capturing}) != len(capturing):
            raise ScenarioError('finish: two capturing recordings started at the same instant; the target is ambiguous')
    target = scenario.finish_target()
    if finish is not None and target is not None and finish.fast_finish:
        if finish.at + finish.provisional_latency < target.sealed:
            raise ScenarioError('finish: the provisional transcript cannot land before the capture is sealed')
    return scenario


def _gap(raw: Any, where: str, recordings: Sequence[Recording]) -> Mapping[str, Any]:
    """A stream gap between two batch recordings of one origin: a reconnect opens a new session."""
    if not isinstance(raw, Mapping):
        raise ScenarioError(f'{where}: expected an object')
    _keys(raw, ('origin', 'between', 'reason'), where)
    pair = raw.get('between')
    if not isinstance(pair, list) or len(pair) != 2:
        raise ScenarioError(f'{where}.between: [earlier recording, later recording]')
    by_label = {r.label: r for r in recordings if r.lane == 'batch'}
    if any(p not in by_label for p in pair):
        raise ScenarioError(f'{where}.between: two declared batch recordings')
    first, second = by_label[pair[0]], by_label[pair[1]]
    if first.origin != raw.get('origin') or second.origin != raw.get('origin'):
        raise ScenarioError(f'{where}: both recordings must come from origin {raw.get("origin")!r}')
    if not first.audio[1] < second.audio[0]:
        raise ScenarioError(f'{where}: the earlier recording must end before the later one starts')
    if raw.get('reason', 'reconnect') == 'reconnect' and first.session == second.session:
        raise ScenarioError(f'{where}: a reconnect starts a new recording session')
    return {
        'origin': raw.get('origin'),
        'between': list(pair),
        'reason': raw.get('reason', 'reconnect'),
        'seconds': round(second.audio[0] - first.audio[1], 3),
    }


def load_scenario(path: str | Path) -> Scenario:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as error:
        raise ScenarioError(f'{path.name}: not valid JSON ({error.msg} at line {error.lineno})') from None
    return parse_scenario(raw, path=str(path))


# ---- plan ---------------------------------------------------------------------------------------


def admission_offset(scenario: Scenario, rec: Recording) -> float:
    """When batch record admission (and with it the manual-finish hook) runs for a batch recording."""
    target = scenario.finish_target()
    finish = scenario.finish
    if finish is not None and target is not None and rec.label == target.label and finish.fast_finish:
        return finish.at + finish.provisional_latency
    return rec.sealed + scenario.admission_lag


def plan_events(scenario: Scenario) -> list[ScenarioEvent]:
    events: list[tuple[float, int, int, ScenarioEvent]] = []

    def add(seconds: float, kind: str, ref: str, check_index: Optional[int] = None) -> None:
        event = ScenarioEvent(scenario.at(seconds), kind, ref, check_index)
        events.append((seconds, EVENT_ORDER.index(kind), len(events), event))

    for rec in scenario.recordings:
        if rec.lane == 'sync':
            add(float(rec.arrives_at or rec.audio[1]), 'sync', rec.label)
            continue
        add(rec.audio[0], 'capture_start', rec.label)
        add(rec.sealed, 'seal', rec.label)
        add(admission_offset(scenario, rec), 'admission', rec.label)
        if rec.transcript_at is not None:
            add(rec.transcript_at, 'transcript', rec.label)
    if scenario.finish is not None:
        add(scenario.finish.at, 'finish', 'finish')
    for index, check in enumerate(scenario.checks):
        if check.at is not None:
            add(check.at, 'checkpoint', f'expect[{index}]', index)
    events.sort(key=lambda row: row[:3])
    return [row[3] for row in events]


def describe_plan(scenario: Scenario) -> list[str]:
    """The planned timeline, one line per event (no product state)."""
    out = []
    for event in plan_events(scenario):
        out.append(f'+{scenario.offset(event.instant):>8.1f}s  {event.kind:<13} {event.ref}')
    return out
