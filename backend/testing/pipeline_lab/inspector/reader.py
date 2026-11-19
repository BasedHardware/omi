"""Read-only view of the pipeline-lab run store for the inspector, plus the verdict writer.

Reads the store contract's JSON layout; ids, content keys and item kinds come from ``contracts`` /
``store`` (the single source). Every id that becomes a path is checked
against the contract's id pattern and every resolved path must stay inside its root.

Pairing, grouping and change classification come from ``baseline/compare.py`` (:meth:`Reader.comparison`).
Item lists (tasks, memories, pushes) on the conversation page pair by stable content key first, then by
word overlap, so the UI can show a word diff for near matches; that is presentation only.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from testing.pipeline_lab.baseline import compare
from testing.pipeline_lab.contracts import ITEM_KINDS, content_key, normalize_text  # noqa: F401 - re-exported
from testing.pipeline_lab.contracts import MARKS as CONTRACT_MARKS
from testing.pipeline_lab.store import SEGMENT_PATTERN, StoreRefused, safe_segment

ID_PATTERN = SEGMENT_PATTERN
MARKS = tuple(m for m in CONTRACT_MARKS if m != 'clear')  # marks the UI counts; ``clear`` withdraws one
NEAR_MATCH = 0.45
MAX_NOTE_CHARS = 4000


class NotFound(LookupError):
    """The requested run, day, conversation or item does not exist (or the id is not a valid id)."""


class BadRequest(ValueError):
    """The request is malformed; the message is safe to show."""


def safe_id(value: Any, what: str = 'id') -> str:
    """``store.safe_segment`` with the inspector's error type: a bad id reads as not found."""
    try:
        return safe_segment(value, what)
    except StoreRefused:
        raise NotFound(f'invalid {what}') from None


def inside(root: Path, *parts: str) -> Path:
    """``root/parts`` resolved, refusing anything that escapes ``root`` (symlinks included)."""
    base = root.resolve()
    path = base.joinpath(*parts).resolve()
    if path != base and base not in path.parents:
        raise NotFound('path outside the store')
    return path


# ---- content keys: the contract's recipe (``contracts.content_key``) -------------------------

_WORD = re.compile(r'\w+', re.UNICODE)


def summary_key(structured: Optional[Mapping[str, Any]]) -> str:
    structured = structured or {}
    return content_key(
        'summary', {'title': structured.get('title') or '', 'overview': structured.get('overview') or ''}
    )


def task_key(item: Mapping[str, Any]) -> str:
    return item.get('key') or content_key('task', item.get('description') or '')


def memory_key(item: Mapping[str, Any]) -> str:
    return item.get('key') or content_key('memory', item.get('content') or '')


def notification_key(item: Mapping[str, Any]) -> str:
    return item.get('key') or content_key(
        'notification', {'title': item.get('title') or '', 'body': item.get('body') or ''}
    )


def transcript_text(conversation: Mapping[str, Any]) -> str:
    return ' '.join((seg.get('text') or '').strip() for seg in conversation.get('segments') or []).strip()


def transcript_key(conversation: Mapping[str, Any]) -> str:
    return content_key('transcript', transcript_text(conversation))


def speaker_key(conversation: Mapping[str, Any]) -> str:
    turns = [
        [seg.get('speaker_name') or seg.get('speaker') or '', bool(seg.get('is_user'))]
        for seg in conversation.get('segments') or []
    ]
    return content_key('speaker', turns)


def boundary_key(conversation: Mapping[str, Any]) -> str:
    return content_key(
        'boundary',
        {'started_at': conversation.get('started_at') or '', 'finished_at': conversation.get('finished_at') or ''},
    )


def daily_summary_key(value: Any) -> str:
    return content_key('daily_summary', value if value is not None else '')


# ---- time ----------------------------------------------------------------------------------


def parse_utc(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def utc_iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def day_window(date: Optional[str], tz_name: Optional[str]) -> Optional[dict[str, str]]:
    """UTC instants of local midnight to next local midnight (23 or 25 h across DST changes)."""
    if not date:
        return None
    try:
        from zoneinfo import ZoneInfo  # stdlib; imported lazily so a missing tz database degrades to UTC

        zone: Any = ZoneInfo(tz_name or 'UTC')
    except Exception:  # noqa: BLE001 - unknown zone or no tz database: show the day in UTC
        zone = timezone.utc
    try:
        local = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return None
    start = local.replace(tzinfo=zone)
    end = (local + timedelta(days=1)).replace(tzinfo=zone)
    return {'start': utc_iso(start), 'end': utc_iso(end)}


def seconds_between(start: Optional[str], end: Optional[str]) -> Optional[float]:
    a, b = parse_utc(start), parse_utc(end)
    if a is None or b is None:
        return None
    return (b - a).total_seconds()


# ---- pairing and status ----------------------------------------------------------------


def _words(text: str) -> set[str]:
    return set(_WORD.findall(normalize_text(text or '')))


def similarity(a: str, b: str) -> float:
    left, right = _words(a), _words(b)
    if not left and not right:
        return 1.0
    return len(left & right) / max(1, len(left | right))


def pair_items(
    replay: Iterable[Mapping[str, Any]],
    baseline: Iterable[Mapping[str, Any]],
    key_of: Callable[[Mapping[str, Any]], str],
    text_of: Callable[[Mapping[str, Any]], str],
) -> list[dict[str, Any]]:
    """Diff-ready pairs: ``same`` (same key), ``changed`` (near match), ``added`` (replay only), ``removed``."""
    replay = list(replay or [])
    baseline = list(baseline or [])
    used: set[int] = set()
    out: list[Optional[dict[str, Any]]] = [None] * len(replay)
    keys = [key_of(item) for item in baseline]
    for i, item in enumerate(replay):
        key = key_of(item)
        for j, other in enumerate(keys):
            if j not in used and other == key:
                used.add(j)
                out[i] = {'state': 'same', 'key': key, 'replay': item, 'baseline': baseline[j], 'similarity': 1.0}
                break
    candidates = []
    for i, item in enumerate(replay):
        if out[i] is not None:
            continue
        for j, other in enumerate(baseline):
            if j in used:
                continue
            score = similarity(text_of(item), text_of(other))
            if score >= NEAR_MATCH:
                candidates.append((score, i, j))
    for score, i, j in sorted(candidates, key=lambda c: (-c[0], c[1], c[2])):
        if out[i] is not None or j in used:
            continue
        used.add(j)
        out[i] = {
            'state': 'changed',
            'key': key_of(replay[i]),
            'replay': replay[i],
            'baseline': baseline[j],
            'similarity': round(score, 3),
        }
    pairs: list[dict[str, Any]] = []
    for i, item in enumerate(replay):
        pairs.append(out[i] or {'state': 'added', 'key': key_of(item), 'replay': item, 'baseline': None})
    for j, item in enumerate(baseline):
        if j not in used:
            pairs.append({'state': 'removed', 'key': keys[j], 'replay': None, 'baseline': item})
    return pairs


def _task_text(item: Mapping[str, Any]) -> str:
    return item.get('description') or ''


def _memory_text(item: Mapping[str, Any]) -> str:
    return item.get('content') or ''


def _push_text(item: Mapping[str, Any]) -> str:
    return f"{item.get('title') or ''} {item.get('body') or ''}"


def pipeline_of(run: Optional[Mapping[str, Any]]) -> str:
    """``v3`` for a conversations-v3 run (``run.json`` ``pipeline``), else ``classic``."""
    return 'v3' if (run or {}).get('pipeline') == 'v3' else 'classic'


def home_hidden(conversation: Optional[Mapping[str, Any]]) -> Optional[bool]:
    """v3 only: hidden from the phone's Home list. ``None`` for classic rows."""
    block = (conversation or {}).get('v3')
    return None if not isinstance(block, Mapping) else not block.get('visible', True)


def baseline_ids_of(conversation: Mapping[str, Any]) -> list[str]:
    ids = conversation.get('baseline_ids')
    if isinstance(ids, list) and ids:
        return [i for i in ids if isinstance(i, str)]
    single = conversation.get('baseline_id')
    return [single] if isinstance(single, str) and single else []


def conversation_pairs(replay: Mapping[str, Any], baseline: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Every diff-ready pair the conversation page renders, in one object agents can read too."""
    replay = replay or {}
    baseline = baseline or {}
    return {
        'summary': {
            'key': summary_key(replay.get('structured')) if replay else None,
            'replay': replay.get('structured'),
            'baseline': baseline.get('structured'),
        },
        'tasks': pair_items(replay.get('action_items'), baseline.get('action_items'), task_key, _task_text),
        'memories': pair_items(replay.get('memories'), baseline.get('memories'), memory_key, _memory_text),
        'pushes': pair_items(replay.get('notifications'), baseline.get('notifications'), notification_key, _push_text),
    }


# ---- json io ---------------------------------------------------------------------------


class _FileCache:
    """Parsed-file cache keyed by (path, mtime, size): a re-run rewrites files and invalidates itself."""

    def __init__(self, limit: int = 2048):
        self._items: dict[Path, tuple[tuple[int, int], Any]] = {}
        self._limit = limit

    def get(self, path: Path, parse: Callable[[bytes], Any]) -> Any:
        try:
            info = path.stat()
        except FileNotFoundError:
            return None
        sig = (info.st_mtime_ns, info.st_size)
        hit = self._items.get(path)
        if hit and hit[0] == sig:
            return hit[1]
        value = parse(path.read_bytes())
        if len(self._items) >= self._limit:
            self._items.clear()
        self._items[path] = (sig, value)
        return value


def _parse_json(body: bytes) -> Any:
    return json.loads(body.decode('utf-8'))


def _parse_jsonl(body: bytes) -> list[Any]:
    rows = []
    for line in body.decode('utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a torn final line from a concurrent append; the next read sees it whole
    return rows


class Reader:
    """The run store at ``root`` and the verdict file under ``verdicts_root``."""

    def __init__(self, root: Path, verdicts_root: Path):
        self.root = Path(root).expanduser().resolve()
        self.verdicts_root = Path(verdicts_root).expanduser()
        self._cache = _FileCache()
        self._computed: dict[str, tuple[Any, dict[str, Any]]] = {}

    # -- raw reads

    def _json(self, *parts: str) -> Any:
        return self._cache.get(inside(self.root, *parts), _parse_json)

    def _jsonl(self, *parts: str) -> list[Any]:
        return self._cache.get(inside(self.root, *parts), _parse_jsonl) or []

    def run_ids(self) -> list[str]:
        runs = inside(self.root, 'runs')
        if not runs.is_dir():
            return []
        return sorted(p.name for p in runs.iterdir() if ID_PATTERN.fullmatch(p.name) and (p / 'run.json').is_file())

    def run(self, run_id: str) -> dict[str, Any]:
        data = self._json('runs', safe_id(run_id, 'run id'), 'run.json')
        if not isinstance(data, dict):
            raise NotFound('run not found')
        return data

    def corpus_day(self, day_id: str) -> dict[str, Any]:
        data = self._json('corpus', safe_id(day_id, 'day id'), 'day.json')
        return data if isinstance(data, dict) else {'day_id': day_id}

    def conversations(self, run_id: str) -> list[dict[str, Any]]:
        folder = inside(self.root, 'runs', safe_id(run_id, 'run id'), 'conversations')
        if not folder.is_dir():
            return []
        rows = []
        for path in sorted(folder.glob('*.json')):
            if not ID_PATTERN.fullmatch(path.stem):
                continue
            row = self._cache.get(path, _parse_json)
            if isinstance(row, dict) and row.get('id'):
                rows.append(row)
        rows.sort(key=lambda c: (c.get('started_at') or '', c.get('id')))
        return rows

    def conversation(self, run_id: str, conversation_id: str) -> dict[str, Any]:
        data = self._json('runs', safe_id(run_id, 'run id'), 'conversations', safe_id(conversation_id) + '.json')
        if not isinstance(data, dict):
            raise NotFound('conversation not found')
        return data

    def baseline(self, day_id: str, name: str) -> list[dict[str, Any]]:
        return [r for r in self._jsonl('corpus', safe_id(day_id, 'day id'), 'baseline', name) if isinstance(r, dict)]

    def baseline_conversations(self, day_id: str, pipeline: Optional[str] = None) -> list[dict[str, Any]]:
        """Production conversations of the day; for a v3 run, production's v3 conversations."""
        name = 'v3_conversations.jsonl' if pipeline == 'v3' else 'conversations.jsonl'
        rows = self.baseline(day_id, name)
        rows.sort(key=lambda c: (c.get('started_at') or '', c.get('id') or ''))
        return rows

    def baseline_daily_summary(self, day_id: str) -> Any:
        return self._json('corpus', safe_id(day_id, 'day id'), 'baseline', 'daily_summary.json')

    def run_day(self, run_id: str) -> dict[str, Any]:
        data = self._json('runs', safe_id(run_id, 'run id'), 'day.json')
        return data if isinstance(data, dict) else {}

    def llm_calls(self, run_id: str, conversation_id: Optional[str] = None, ids: Iterable[str] = ()) -> list[dict]:
        rows = [r for r in self._jsonl('runs', safe_id(run_id, 'run id'), 'llm_calls.jsonl') if isinstance(r, dict)]
        if conversation_id is None:
            return rows
        wanted = set(ids)
        return [r for r in rows if r.get('conversation_id') == conversation_id or r.get('id') in wanted]

    def audio_index(self, day_id: str) -> list[dict[str, Any]]:
        data = self._json('corpus', safe_id(day_id, 'day id'), 'audio', 'index.json')
        if isinstance(data, dict):  # tolerate {"entries": [...]}
            data = data.get('entries')
        return [e for e in data or [] if isinstance(e, dict)]

    def audio_file(self, day_id: str, conversation_id: str) -> tuple[Path, dict[str, Any]]:
        safe_id(conversation_id)
        audio_dir = inside(self.root, 'corpus', safe_id(day_id, 'day id'), 'audio')
        for entry in self.audio_index(day_id):
            if entry.get('conversation_id') != conversation_id:
                continue
            relative = entry.get('path')
            if not isinstance(relative, str) or not relative or os.path.isabs(relative):
                break
            path = inside(audio_dir, *Path(relative).parts)
            if path.is_file():
                return path, entry
            break
        raise NotFound('audio not found')

    # -- composed views

    def baseline_view(self, run_id: str) -> Optional[dict[str, Any]]:
        """``runs/<id>/baseline.json`` from the chain's baseline stage (the one pairing implementation)."""
        data = self._json('runs', safe_id(run_id, 'run id'), 'baseline.json')
        return data if isinstance(data, dict) and isinstance(data.get('conversations'), list) else None

    def comparison(self, run: Mapping[str, Any]) -> dict[str, Any]:
        """Pairs, groups and the digest for a run: ``baseline/compare.py``'s view (RULINGS 10).

        ``baseline.json`` is used when it was written by the current compare (``version`` 2 and
        it covers every replay conversation); otherwise (older runs, the synthetic sample) the same
        :func:`compare.baseline_view` runs here over the run's files, so there is one implementation.
        """
        run_id = run['run_id']
        replay = self.conversations(run_id)
        production = self.baseline_conversations(run['day_id'], pipeline_of(run))
        view = self.baseline_view(run_id)
        if view is not None and view.get('version') == compare.VERSION and isinstance(view.get('groups'), list):
            listed = {i for g in view['groups'] for i in g.get('replay') or []}
            if listed == {c['id'] for c in replay}:
                return view
        stamp = (run_id, tuple((c['id'], c.get('finished_at')) for c in replay), len(production))
        cached = self._computed.get(run_id)
        if cached is None or cached[0] != stamp:
            cached = (stamp, compare.baseline_view(replay, production))
            self._computed[run_id] = cached
        return cached[1]

    def audio_for(self, day_id: str, conv: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        start, end = parse_utc(conv.get('started_at')), parse_utc(conv.get('finished_at'))
        if start is None:
            return None
        end = end or start
        own = {conv.get('id'), *baseline_ids_of(conv), *(conv.get('recordings') or [])}
        best, best_score = None, (False, 0.0)
        for entry in self.audio_index(day_id):
            a, b = parse_utc(entry.get('start')), parse_utc(entry.get('end'))
            if a is None or b is None:
                continue
            overlap = (min(b, end) - max(a, start)).total_seconds()
            named = entry.get('conversation_id') in own
            if overlap <= 0 and not named:
                continue
            score = (named, overlap)  # the clip filed under this conversation wins, then the widest overlap
            if best is None or score > best_score:
                best, best_score = entry, score
        if best is None:
            return None
        clip_id = best.get('conversation_id')
        if not isinstance(clip_id, str) or not ID_PATTERN.fullmatch(clip_id):
            return None
        return {
            'url': f'/audio/{day_id}/{clip_id}',
            'clip_id': clip_id,
            'offset': (start - parse_utc(best['start'])).total_seconds(),
            'start': best.get('start'),
            'end': best.get('end'),
            'codec': best.get('codec'),
            'sample_rate': best.get('sample_rate'),
        }

    # -- verdicts

    @property
    def verdicts_path(self) -> Path:
        return self.verdicts_root / 'verdicts.jsonl'

    def verdicts(self, *, latest: bool = True, **filters: Optional[str]) -> list[dict[str, Any]]:
        path = self.verdicts_path
        if not path.is_file():
            return []
        rows = [r for r in _parse_jsonl(path.read_bytes()) if isinstance(r, dict)]
        if latest:
            newest: dict[tuple, dict] = {}
            for row in rows:
                newest[_verdict_target(row)] = row
            rows = [row for row in rows if newest[_verdict_target(row)] is row and row.get('mark') != 'clear']
        for name, value in filters.items():
            if not value:
                continue
            if name == 'conversation_id':  # either the stored (production) id or the replay id it was made on
                rows = [r for r in rows if value in (r.get('conversation_id'), r.get('replay_conversation_id'))]
            else:
                rows = [r for r in rows if r.get(name) == value]
        return rows

    def append_verdict(self, row: Mapping[str, Any]) -> None:
        root = self.verdicts_root
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = root.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise BadRequest('verdict root must be a directory')
        line = (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
        fd = os.open(self.verdicts_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, line)
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _verdict_target(row: Mapping[str, Any]) -> tuple:
    return (row.get('day_id'), row.get('conversation_id'), row.get('item_kind'), row.get('item_key'))


def new_verdict_id() -> str:
    return 'v-' + secrets.token_hex(8)
