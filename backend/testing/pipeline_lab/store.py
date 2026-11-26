"""Private on-disk run store for the pipeline lab (DESIGN L11 and "Store contract").

Two roots, both owner-only and both outside every git worktree:

- the run store, ``$OMI_PIPELINE_LAB_ROOT`` (default ``/Volumes/Ephemeral/pipeline-lab``):
  ``corpus/``, ``cache/`` and ``runs/``;
- the verdict root, ``$OMI_PIPELINE_LAB_VERDICTS`` (default
  ``~/.local/share/pipeline-lab/verdicts``): ``verdicts.jsonl``. Verdicts are a
  record, so they never live beside disposable runs.

Directories are created ``0700`` and files ``0600``. JSON documents are replaced
atomically (temp file, fsync, rename); JSONL logs are appended under an exclusive
``flock`` so the LLM proxy's threads and stage subprocesses can share one file.
Path segments (day, run, conversation, stage ids) are validated, so no id can
escape its directory.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional, Sequence

from testing.pipeline_lab.contracts import (
    AudioIndexEntry,
    ConversationRecord,
    CorpusDay,
    Decision,
    LlmCall,
    RunDay,
    RunRecord,
    VendorLogEntry,
    Verdict,
    canonical_json,
    utc_iso,
)

ROOT_ENV = 'OMI_PIPELINE_LAB_ROOT'
VERDICTS_ENV = 'OMI_PIPELINE_LAB_VERDICTS'
DEFAULT_ROOT = '/Volumes/Ephemeral/pipeline-lab'
DEFAULT_VERDICTS = '~/.local/share/pipeline-lab/verdicts'

# ``conversations.jsonl`` holds ConversationRecord-shaped rows; ``raw_conversations.jsonl`` the same day's
# production rows in snapshot shape (uid remapped to the lab uid), which the chain replays from (RULINGS 1).
BASELINE_FILES = (
    'conversations.jsonl',
    'raw_conversations.jsonl',
    'memories.jsonl',
    'action_items.jsonl',
    'notifications.jsonl',
)
_SEGMENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}')
SEGMENT_PATTERN = _SEGMENT  # the id pattern every run/day/conversation id must match


class StoreRefused(PermissionError):
    """A path or permission check failed. Messages name the policy, not private values."""


def safe_segment(value: str, what: str = 'id') -> str:
    if not isinstance(value, str) or not _SEGMENT.fullmatch(value) or '..' in value:
        raise StoreRefused(f'invalid {what}: must match {_SEGMENT.pattern} without ".."')
    return value


def _inside_git(path: Path) -> bool:
    return any((parent / '.git').exists() for parent in (path, *path.parents))


def ensure_private_dir(path: Path) -> Path:
    """Create ``path`` (and missing parents) owner-only; refuse git trees and foreign/open dirs.

    Existing parents above the first created directory are left alone; every
    directory this call creates is ``0700``. The leaf must be an owned directory
    with no group/other access.
    """
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if _inside_git(path.resolve()):
        raise StoreRefused('lab data must live outside every git worktree')
    missing = []
    probe = path
    while not probe.exists():
        missing.append(probe)
        probe = probe.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        os.chmod(directory, 0o700)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise StoreRefused('lab directory cannot be a symlink')
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise StoreRefused('lab directory must be a directory owned by this user')
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise StoreRefused('lab directory must not be group/other accessible (expected 0700)')
    return path


def _subdir(path: Path) -> Path:
    """A directory below an already-validated root: create it and every missing parent 0700 (``mkdir -p``
    would give the parents the umask's default mode), without re-validating existing ones."""
    path = Path(path)
    missing = []
    probe = path
    while not probe.exists():
        missing.append(probe)
        probe = probe.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            continue
        os.chmod(directory, 0o700)  # mkdir's mode is masked by the umask
    return path


private_subdir = _subdir


def private_dir(path: Path, what: str = 'lab output') -> Path:
    """``ensure_private_dir`` for a directory a command was told to write into (``--keep``, ``--out``).

    An existing directory that is group/other accessible, foreign or a symlink is refused, not
    chmod-ed: it may be someone else's tree. The message names the policy and the path only."""
    try:
        return ensure_private_dir(Path(path))
    except StoreRefused as refused:
        raise StoreRefused(f'{what} {path}: {refused} (use a new path or chmod 700 it yourself)') from None


@contextlib.contextmanager
def private_tempdir(root: Path) -> Iterator[Path]:
    """``tempfile`` and ``$TMPDIR`` point at ``<root>/tmp/product`` (owner-only) for the block, then back.

    Product code the lab runs on owner data makes its own temp files (``utils/batch_pipeline``, ``utils/sync``)
    in the system temp directory; under this they land inside the private lab root instead. ``TMPDIR`` is
    inherited by the lab environment (``stack/env.py``) and by child processes."""
    import tempfile

    directory = ensure_private_dir(Path(root) / 'tmp' / 'product')
    previous_env, previous_dir = os.environ.get('TMPDIR'), tempfile.tempdir
    os.environ['TMPDIR'] = str(directory)
    tempfile.tempdir = str(directory)
    try:
        yield directory
    finally:
        tempfile.tempdir = previous_dir
        if previous_env is None:
            os.environ.pop('TMPDIR', None)
        else:
            os.environ['TMPDIR'] = previous_env


def private_write_text(path: Path, text: str) -> Path:
    """Replace ``path`` atomically with ``text``, created 0600 (parents 0700)."""
    atomic_write_bytes(Path(path), text.encode('utf-8'))
    return Path(path)


def private_open(path: Path, mode: str = 'wb') -> Any:
    """A file object on ``path`` created 0600 and never through a symlink: ``wb`` truncates, ``ab`` appends.

    For streams another process writes (an emulator's log), where an atomic replace cannot work."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_APPEND if mode.startswith('a') else os.O_TRUNC)
    _subdir(Path(path).parent)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)  # an existing file keeps its mode through O_CREAT
    return os.fdopen(fd, mode)


def atomic_write_bytes(path: Path, body: bytes) -> None:
    path = Path(path)
    _subdir(path.parent)
    temp = path.with_name(f'.{path.name}.{secrets.token_hex(6)}.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp.unlink()


def atomic_write_json(path: Path, value: Any) -> Path:
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False, default=str) + '\n'
    atomic_write_bytes(Path(path), text.encode('utf-8'))
    return Path(path)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default


@contextlib.contextmanager
def locked(path: Path) -> Iterator[None]:
    """An exclusive advisory lock on ``path`` (created 0600), across threads and processes."""
    _subdir(path.parent)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def append_jsonl(path: Path, rows: Iterable[Any]) -> None:
    lines = ''.join(canonical_json(row.to_json() if hasattr(row, 'to_json') else row) + '\n' for row in rows)
    if not lines:
        return
    _subdir(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, lines.encode('utf-8'))
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Rows of a JSONL file; a torn final line (crash mid-append) is skipped, not fatal."""
    try:
        text = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return []
    rows = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                continue
            raise
    return rows


def default_root() -> Path:
    return Path(os.environ.get(ROOT_ENV) or DEFAULT_ROOT).expanduser()


def lab_root(root: Any = None) -> Path:
    """``root`` when given, else ``$OMI_PIPELINE_LAB_ROOT`` (no permission checks: use ``Store.open`` for those)."""
    return Path(root).expanduser() if root else default_root()


def default_verdicts_root() -> Path:
    return Path(os.environ.get(VERDICTS_ENV) or DEFAULT_VERDICTS).expanduser()


def new_run_id(day_id: str, ref: str, now: Optional[datetime] = None) -> str:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    short = re.sub(r'[^A-Za-z0-9]', '', ref)[:12] or 'ref'
    return safe_segment(f'{moment:%Y%m%dT%H%M%SZ}-{safe_segment(day_id, "day id")}-{short}-{secrets.token_hex(3)}')


@dataclass
class Store:
    """The run store plus the separate verdict root. Construct, then use; nothing happens at import."""

    root: Path
    verdicts_root: Path

    @classmethod
    def open(cls, root: Optional[Path] = None, verdicts_root: Optional[Path] = None) -> 'Store':
        store = cls(
            root=ensure_private_dir(Path(root) if root else default_root()),
            verdicts_root=ensure_private_dir(Path(verdicts_root) if verdicts_root else default_verdicts_root()),
        )
        for name in ('corpus', 'cache', 'runs'):
            _subdir(store.root / name)
        return store

    # ---- corpus ----------------------------------------------------------------

    def day_dir(self, day_id: str) -> Path:
        return self.root / 'corpus' / safe_segment(day_id, 'day id')

    def write_day(self, day: CorpusDay) -> Path:
        path = self.day_dir(day.day_id) / 'day.json'
        atomic_write_json(path, day.to_json())
        return path

    def read_day(self, day_id: str) -> CorpusDay:
        data = read_json(self.day_dir(day_id) / 'day.json')
        if data is None:
            raise FileNotFoundError(f'corpus day not found: {day_id}')
        return CorpusDay.from_json(data)

    def list_days(self) -> list[CorpusDay]:
        days = []
        for path in sorted((self.root / 'corpus').glob('*/day.json')):
            days.append(CorpusDay.from_json(read_json(path)))
        return sorted(days, key=lambda day: (day.date, day.day_id))

    def baseline_dir(self, day_id: str) -> Path:
        return self.day_dir(day_id) / 'baseline'

    def write_baseline(self, day_id: str, name: str, rows: Sequence[Any]) -> Path:
        if name not in BASELINE_FILES:
            raise StoreRefused(f'unknown baseline file; expected one of {", ".join(BASELINE_FILES)}')
        path = self.baseline_dir(day_id) / name
        text = ''.join(canonical_json(r.to_json() if hasattr(r, 'to_json') else r) + '\n' for r in rows)
        atomic_write_bytes(path, text.encode('utf-8'))
        return path

    def read_baseline(self, day_id: str, name: str) -> list[dict[str, Any]]:
        if name not in BASELINE_FILES:
            raise StoreRefused(f'unknown baseline file; expected one of {", ".join(BASELINE_FILES)}')
        return read_jsonl(self.baseline_dir(day_id) / name)

    def baseline_conversations(self, day_id: str) -> list[ConversationRecord]:
        return [ConversationRecord.from_json(row) for row in self.read_baseline(day_id, 'conversations.jsonl')]

    def write_baseline_daily_summary(self, day_id: str, value: Any) -> Path:
        path = self.baseline_dir(day_id) / 'daily_summary.json'
        atomic_write_json(path, value)
        return path

    def read_baseline_daily_summary(self, day_id: str) -> Any:
        return read_json(self.baseline_dir(day_id) / 'daily_summary.json')

    def audio_dir(self, day_id: str) -> Path:
        return self.day_dir(day_id) / 'audio'

    def write_audio_index(self, day_id: str, entries: Sequence[AudioIndexEntry]) -> Path:
        for entry in entries:
            self.audio_path(day_id, entry.path)  # validates
        path = self.audio_dir(day_id) / 'index.json'
        atomic_write_json(path, [entry.to_json() for entry in entries])
        return path

    def read_audio_index(self, day_id: str) -> list[AudioIndexEntry]:
        return [AudioIndexEntry.from_json(row) for row in read_json(self.audio_dir(day_id) / 'index.json', [])]

    def audio_path(self, day_id: str, relative: str) -> Path:
        """Resolve an index ``path`` strictly inside the day's audio directory."""
        base = self.audio_dir(day_id)
        parts = Path(relative).parts
        if not parts or Path(relative).is_absolute():
            raise StoreRefused('audio path must be relative to the audio directory')
        for part in parts:
            safe_segment(part, 'audio path segment')
        return base.joinpath(*parts)

    # ---- cache -----------------------------------------------------------------

    def cache_path(self, stage: str, key: str) -> Path:
        safe_segment(stage, 'cache namespace')
        if not re.fullmatch(r'[0-9a-f]{16,128}', key):
            raise StoreRefused('cache key must be lowercase hex')
        return self.root / 'cache' / stage / key[:2] / f'{key}.json'

    def cache_get(self, stage: str, key: str) -> Optional[dict[str, Any]]:
        entry = read_json(self.cache_path(stage, key))
        if entry is None or entry.get('key') != key:
            return None
        return entry

    def cache_put(self, stage: str, key: str, value: dict[str, Any]) -> Path:
        path = self.cache_path(stage, key)
        atomic_write_json(path, {**value, 'key': key, 'stage': stage, 'stored_at': utc_iso()})
        return path

    def cache_files_dir(self, stage: str, key: str) -> Path:
        """Where a cache entry's stored artifacts live (run files, by path relative to the run dir)."""
        return self.cache_path(stage, key).with_suffix('.files')

    @staticmethod
    def _artifact_parts(relative: str) -> tuple[str, ...]:
        parts = Path(relative).parts
        if not parts or Path(relative).is_absolute():
            raise StoreRefused('artifact path must be relative to the run directory')
        for part in parts:
            safe_segment(part, 'artifact path segment')
        return parts

    def cache_put_files(self, stage: str, key: str, source_dir: Path, relatives: Sequence[str]) -> dict[str, str]:
        """Copy run files into the entry's artifact directory; returns ``{relative: sha256}``."""
        import hashlib

        base = self.cache_files_dir(stage, key)
        digests: dict[str, str] = {}
        for relative in relatives:
            parts = self._artifact_parts(relative)
            body = Path(source_dir).joinpath(*parts).read_bytes()
            atomic_write_bytes(base.joinpath(*parts), body)
            digests[relative] = hashlib.sha256(body).hexdigest()
        return digests

    def cache_files_present(self, stage: str, key: str, relatives: Sequence[str]) -> bool:
        base = self.cache_files_dir(stage, key)
        try:
            return all(base.joinpath(*self._artifact_parts(r)).is_file() for r in relatives)
        except StoreRefused:
            return False

    def cache_restore_files(self, stage: str, key: str, target_dir: Path, relatives: Sequence[str]) -> None:
        """Write an entry's artifacts back into a run directory (same relative paths)."""
        base = self.cache_files_dir(stage, key)
        for relative in relatives:
            parts = self._artifact_parts(relative)
            atomic_write_bytes(Path(target_dir).joinpath(*parts), base.joinpath(*parts).read_bytes())

    # ---- runs ------------------------------------------------------------------

    def run_dir(self, run_id: str) -> Path:
        return self.root / 'runs' / safe_segment(run_id, 'run id')

    def create_run(self, run: RunRecord) -> Path:
        directory = self.run_dir(run.run_id)
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            raise StoreRefused('run id already exists') from None
        _subdir(directory / 'conversations')
        atomic_write_json(directory / 'run.json', run.to_json())
        return directory

    def read_run(self, run_id: str) -> RunRecord:
        data = read_json(self.run_dir(run_id) / 'run.json')
        if data is None:
            raise FileNotFoundError(f'run not found: {run_id}')
        return RunRecord.from_json(data)

    def write_run(self, run: RunRecord) -> None:
        directory = self.run_dir(run.run_id)
        if not directory.is_dir():
            raise FileNotFoundError(f'run not found: {run.run_id}')
        atomic_write_json(directory / 'run.json', run.to_json())

    def update_run(self, run_id: str, mutate: Callable[[RunRecord], Optional[RunRecord]]) -> RunRecord:
        """Read-modify-write ``run.json`` under the run lock (safe across processes)."""
        with locked(self.run_dir(run_id) / '.run.lock'):
            run = self.read_run(run_id)
            run = mutate(run) or run
            self.write_run(run)
            return run

    def list_runs(self, day_id: Optional[str] = None) -> list[RunRecord]:
        runs = []
        for path in (self.root / 'runs').glob('*/run.json'):
            data = read_json(path)
            if data is None:
                continue
            run = RunRecord.from_json(data)
            if day_id is None or run.day_id == day_id:
                runs.append(run)
        return sorted(runs, key=lambda run: (run.started_at or '', run.run_id), reverse=True)

    def write_conversation(self, run_id: str, conversation: ConversationRecord) -> Path:
        path = self.run_dir(run_id) / 'conversations' / f'{safe_segment(conversation.id, "conversation id")}.json'
        atomic_write_json(path, conversation.to_json())
        return path

    def read_conversation(self, run_id: str, conversation_id: str) -> ConversationRecord:
        path = self.run_dir(run_id) / 'conversations' / f'{safe_segment(conversation_id, "conversation id")}.json'
        data = read_json(path)
        if data is None:
            raise FileNotFoundError(f'conversation not found in run: {conversation_id}')
        return ConversationRecord.from_json(data)

    def list_conversations(self, run_id: str) -> list[ConversationRecord]:
        rows = [
            ConversationRecord.from_json(read_json(path))
            for path in (self.run_dir(run_id) / 'conversations').glob('*.json')
        ]
        return sorted(rows, key=lambda row: (row.started_at or '', row.id))

    def write_run_day(self, run_id: str, day: RunDay) -> Path:
        path = self.run_dir(run_id) / 'day.json'
        atomic_write_json(path, day.to_json())
        return path

    def read_run_day(self, run_id: str) -> Optional[RunDay]:
        data = read_json(self.run_dir(run_id) / 'day.json')
        return RunDay.from_json(data) if data is not None else None

    def llm_calls_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / 'llm_calls.jsonl'

    def append_llm_calls(self, run_id: str, calls: Sequence[LlmCall]) -> None:
        append_jsonl(self.llm_calls_path(run_id), calls)

    def read_llm_calls(self, run_id: str) -> list[LlmCall]:
        return [LlmCall.from_json(row) for row in read_jsonl(self.llm_calls_path(run_id))]

    def append_vendor_log(self, run_id: str, rows: Sequence[VendorLogEntry]) -> None:
        append_jsonl(self.run_dir(run_id) / 'vendor_log.jsonl', rows)

    def read_vendor_log(self, run_id: str) -> list[VendorLogEntry]:
        return [VendorLogEntry.from_json(row) for row in read_jsonl(self.run_dir(run_id) / 'vendor_log.jsonl')]

    def append_decisions(self, run_id: str, rows: Sequence[Decision]) -> None:
        append_jsonl(self.run_dir(run_id) / 'decisions.jsonl', rows)

    def read_decisions(self, run_id: str) -> list[Decision]:
        return [Decision.from_json(row) for row in read_jsonl(self.run_dir(run_id) / 'decisions.jsonl')]

    def ledger_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / 'ledger.json'

    # ---- verdicts --------------------------------------------------------------

    @property
    def verdicts_path(self) -> Path:
        return self.verdicts_root / 'verdicts.jsonl'

    def append_verdict(self, verdict: Verdict) -> Verdict:
        verdict.validate()
        append_jsonl(self.verdicts_path, [verdict])
        return verdict

    def read_verdicts(
        self,
        *,
        run_id: Optional[str] = None,
        day_id: Optional[str] = None,
        item_kind: Optional[str] = None,
        mark: Optional[str] = None,
        latest: bool = False,
    ) -> list[Verdict]:
        """Verdict rows in file order, filtered; ``latest`` keeps the newest row per target and drops
        targets whose newest row is a ``clear``."""
        rows = [Verdict.from_json(row) for row in read_jsonl(self.verdicts_path)]
        if latest:
            newest: dict[tuple, Verdict] = {}
            for row in rows:
                newest[row.target] = row
            rows = [row for row in rows if newest[row.target] is row and row.mark != 'clear']
        return [
            row
            for row in rows
            if (run_id is None or row.run_id == run_id)
            and (day_id is None or row.day_id == day_id)
            and (item_kind is None or row.item_kind == item_kind)
            and (mark is None or row.mark == mark)
        ]


def new_verdict_id() -> str:
    return 'v-' + secrets.token_hex(8)
