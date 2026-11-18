"""Lab root, private directories and atomic JSON IO for the ingest lane.

Lane ``core`` owns the shared store (``pipeline_lab/store.py``). Until the lead
integrates it, the ingest lane keeps this small private copy of the parts it
needs and follows the DESIGN store contract (L11) exactly: the root comes from
``OMI_PIPELINE_LAB_ROOT`` and every directory is created mode 0700.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

DEFAULT_ROOT = '/Volumes/Ephemeral/pipeline-lab'


def lab_root(root: str | os.PathLike | None = None) -> Path:
    return Path(root or os.environ.get('OMI_PIPELINE_LAB_ROOT') or DEFAULT_ROOT)


def private_dir(path: str | os.PathLike) -> Path:
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def atomic_write_json(path: str | os.PathLike, value: Any) -> Path:
    path = Path(path)
    private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=1, sort_keys=True)
            handle.write('\n')
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return path


def append_jsonl(path: str | os.PathLike, rows: Iterable[dict]) -> None:
    path = Path(path)
    private_dir(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'a', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')


def read_json(path: str | os.PathLike, default: Any = None) -> Any:
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def read_jsonl(path: str | os.PathLike) -> Iterator[dict]:
    try:
        handle = open(path, encoding='utf-8')
    except FileNotFoundError:
        return
    with handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def parse_time(value: Any) -> datetime | None:
    """ISO-8601 (``Z`` allowed) or epoch seconds -> aware UTC datetime."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
