"""JSON helpers for product-shaped values (datetimes, pydantic models, bytes markers).

Times and content keys come from ``contracts`` (the single source); writes are atomic
and private (0600) like ``store``'s.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
import threading
from typing import Any, Iterable, Iterator

from testing.pipeline_lab.contracts import parse_time, utc_iso  # noqa: F401 - re-exported for lane modules
from testing.pipeline_lab.store import private_subdir

_APPEND_LOCK = threading.Lock()


def iso(value: Any) -> Any:
    """ISO-8601 UTC for datetimes; everything else unchanged."""
    if isinstance(value, datetime):
        return utc_iso(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return iso(value)
    if isinstance(value, bytes):
        return {'_bytes': len(value)}
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return str(value)


def dumps(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(value, default=_default, ensure_ascii=False, sort_keys=True, indent=indent)


def plain(value: Any) -> Any:
    """JSON round trip: datetimes become ISO strings, models become dicts."""
    return json.loads(dumps(value))


def write_json(path: Path, value: Any) -> Path:
    path = Path(path)
    private_subdir(path.parent)
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(dumps(value, indent=1))
        stream.write('\n')
    os.replace(tmp, path)
    return path


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def append_jsonl(path: Path, row: Any) -> None:
    path = Path(path)
    private_subdir(path.parent)
    line = dumps(row) + '\n'
    with _APPEND_LOCK:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'a', encoding='utf-8') as stream:
            stream.write(line)


def read_jsonl(path: Path) -> Iterator[dict]:
    path = Path(path)
    if not path.exists():
        return
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[Any]) -> int:
    path = Path(path)
    private_subdir(path.parent)
    count = 0
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(dumps(row) + '\n')
            count += 1
    os.replace(tmp, path)
    return count
