"""Read-only export of one consenting owner's conversations-v3 rows, beside an owner snapshot.

The ``fetch-owner-audio`` snapshot reads conversations through the Home reader, which hides
v3 *recordings* (the builder's inputs) and keeps no Firestore create/update times. This tool
adds what the v3 replay needs, for the snapshot's own window, into ``<snapshot>/v3/``:

- ``recordings.jsonl``: every ``recording`` row (decoded with the v3 loader's own decoder);
- ``derived.jsonl``: every ``v3_derived`` row, hidden, discarded and deleted ones included;
- ``other.jsonl``: the remaining rows of the window (legacy conversations), raw-decoded;
- ``leases.jsonl``: the owner's v3 lease documents (builder state: ``open_id``, backoff, the
  decrypted outline cache); lease tokens are dropped;
- ``manifest.json``: counts and the window. Never the uid.

Every row carries ``_create_time`` / ``_update_time`` (the Firestore document times), which
the replay uses to order recordings the way production saw them.

    cd backend
    python -m testing.pipeline_lab.v3.prod_export --guard <path to guard.py> \\
        --uid-file <0600 file> --secret-file <0600 file> --snapshot <snapshot dir>

Safety: the guard module is **injected by path** (it holds the owner pin and is never in this
repository); its ``owner_uid`` refuses any other account and ``load_secret`` puts
``ENCRYPTION_SECRET`` into this process only. Output is refused outside ``/Volumes/Ephemeral``
or inside a Git work tree. Firestore, Storage and Redis writes are refused for the whole run
(:func:`read_only_fence`). The uid is never printed or written.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable, Iterator, Mapping
from unittest.mock import patch

ALLOWED_ROOT = Path('/Volumes/Ephemeral')
PAGE = 200
LEASE_COLLECTION = 'conversation_v3_leases'
REDIS_READ_COMMANDS = frozenset(
    {'GET', 'MGET', 'EXISTS', 'TTL', 'PTTL', 'HGET', 'HGETALL', 'HMGET', 'SMEMBERS', 'SISMEMBER', 'TYPE', 'PING'}
)


class WriteRefused(RuntimeError):
    pass


def load_guard(path: str | Path) -> ModuleType:
    """The owner guard, loaded from a file outside the repository. It must define
    ``owner_uid(path) -> str`` and ``load_secret(path) -> None``."""
    location = Path(path).expanduser().resolve()
    spec = importlib.util.spec_from_file_location('pipeline_lab_owner_guard', location)
    if spec is None or spec.loader is None:
        raise SystemExit('refusing: guard module not loadable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ('owner_uid', 'load_secret'):
        if not callable(getattr(module, name, None)):
            raise SystemExit(f'refusing: guard module has no {name}()')
    return module


def _inside_git_worktree(path: Path) -> bool:
    probe = path if path.exists() else path.parent
    result = subprocess.run(
        ['git', '-C', str(probe), 'rev-parse', '--is-inside-work-tree'], capture_output=True, text=True
    )
    return result.returncode == 0 and result.stdout.strip() == 'true'


def resolve_output(snapshot: str | Path, *, allowed_root: Path = ALLOWED_ROOT) -> Path:
    root = Path(snapshot).expanduser().resolve()
    if allowed_root not in root.parents:
        raise SystemExit(f'refusing: the snapshot must live under {allowed_root}')
    if not (root / 'manifest.json').is_file():
        raise SystemExit('refusing: not a snapshot directory (no manifest.json)')
    if _inside_git_worktree(root):
        raise SystemExit('refusing: the snapshot is inside a Git work tree')
    out = root / 'v3'
    out.mkdir(mode=0o700, exist_ok=True)
    return out


def snapshot_window(snapshot: Path) -> tuple[datetime, datetime]:
    manifest = json.loads((snapshot / 'manifest.json').read_text())
    window = manifest.get('window') or {}
    start = datetime.fromisoformat(str(window['start']))
    end = datetime.fromisoformat(str(window['end']))
    return start, end


def _refuse(what: str) -> Callable[..., Any]:
    def refused(*args: Any, **kwargs: Any) -> Any:
        raise WriteRefused(f'read-only export: {what} refused')

    return refused


@contextmanager
def read_only_fence() -> Iterator[None]:
    """Refuse every Firestore, Cloud Storage and Redis write in this process."""
    with ExitStack() as stack:
        from google.cloud.firestore_v1 import batch, bulk_writer, collection, document, transaction

        for cls, names in (
            (document.DocumentReference, ('set', 'update', 'delete', 'create')),
            (collection.CollectionReference, ('add',)),
            (batch.WriteBatch, ('commit',)),
            (transaction.Transaction, ('_commit', 'commit')),
            (bulk_writer.BulkWriter, ('create', 'set', 'update', 'delete')),
        ):
            for name in names:
                if hasattr(cls, name):
                    stack.enter_context(patch.object(cls, name, _refuse(f'firestore {cls.__name__}.{name}')))
        try:
            from google.cloud.storage import blob as storage_blob

            for name in (
                'upload_from_string',
                'upload_from_file',
                'upload_from_filename',
                'delete',
                'compose',
                'rewrite',
                'patch',
            ):
                if hasattr(storage_blob.Blob, name):
                    stack.enter_context(patch.object(storage_blob.Blob, name, _refuse(f'storage {name}')))
        except ImportError:  # pragma: no cover - storage is a backend dependency
            pass
        try:
            import redis

            original = redis.Redis.execute_command

            def read_only(self: Any, *args: Any, **kwargs: Any) -> Any:
                command = str(args[0]).upper() if args else ''
                if command not in REDIS_READ_COMMANDS:
                    raise WriteRefused(f'read-only export: redis {command} refused')
                return original(self, *args, **kwargs)

            stack.enter_context(patch.object(redis.Redis, 'execute_command', read_only))
        except ImportError:  # pragma: no cover
            pass
        yield


def _default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return {'_bytes': len(value)}
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if hasattr(value, 'value'):
        return value.value
    return str(value)


def plain(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_default))


def classify(row: Mapping[str, Any]) -> str:
    if row.get('recording') is True:
        return 'recordings'
    if row.get('v3_derived') is True:
        return 'derived'
    return 'other'


def decode(uid: str, snapshot: Any) -> dict[str, Any]:
    """A row as the v3 loader reads it; an undecodable row is kept raw, marked, without speech."""
    raw = snapshot.to_dict() or {}
    row: dict[str, Any] | None = None
    try:
        from database import conversations_v3 as v3_store

        row = v3_store.decode_row(uid, snapshot)
    except Exception as error:  # noqa: BLE001 - the export keeps going and counts it
        row = {k: v for k, v in raw.items() if k != 'transcript_segments'}
        row['_export_unreadable'] = type(error).__name__
    if row is None:
        row = {k: v for k, v in raw.items() if k != 'transcript_segments'}
        row['_export_unreadable'] = 'absent'
    row.pop('_v3_revision', None)
    row['id'] = snapshot.id
    row['_create_time'] = getattr(snapshot, 'create_time', None)
    row['_update_time'] = getattr(snapshot, 'update_time', None)
    return row


def window_documents(client: Any, uid: str, start: datetime, end: datetime, *, page: int = PAGE) -> Iterator[Any]:
    """Every conversation document created in [start, end], oldest first, paged by cursor."""
    from google.cloud.firestore_v1 import FieldFilter

    coll = client.collection('users').document(uid).collection('conversations')
    cursor = None
    while True:
        query = (
            coll.where(filter=FieldFilter('created_at', '>=', start))
            .where(filter=FieldFilter('created_at', '<=', end))
            .order_by('created_at')
            .limit(page)
        )
        if cursor is not None:
            query = query.start_after(cursor)
        docs = list(query.stream())
        yield from docs
        if len(docs) < page:
            return
        cursor = docs[-1]


def lease_rows(client: Any, uid: str) -> list[dict[str, Any]]:
    from utils.encryption import decrypt

    rows = []
    for doc in client.collection('users').document(uid).collection(LEASE_COLLECTION).stream():
        data = doc.to_dict() or {}
        data.pop('token', None)
        cache = data.pop('outline_cache', None)
        if cache:
            try:
                data['outline_cache'] = json.loads(decrypt(cache, uid))
            except Exception as error:  # noqa: BLE001
                data['outline_cache_unreadable'] = type(error).__name__
        data['_key'] = doc.id
        data['_update_time'] = getattr(doc, 'update_time', None)
        rows.append(data)
    return rows


def _write_jsonl(path: Path, rows: Iterable[Any]) -> int:
    count = 0
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as fp:
        for row in rows:
            fp.write(json.dumps(plain(row), ensure_ascii=False))
            fp.write('\n')
            count += 1
    return count


def export(uid: str, client: Any, snapshot: Path, out: Path, *, margin: timedelta = timedelta(hours=6)) -> dict:
    start, end = snapshot_window(snapshot)
    # A margin before the window: a recording created just before it can still feed its first day.
    start = start - margin
    buckets: dict[str, list[dict[str, Any]]] = {'recordings': [], 'derived': [], 'other': []}
    unreadable = 0
    for doc in window_documents(client, uid, start, end):
        row = decode(uid, doc)
        unreadable += 1 if row.get('_export_unreadable') else 0
        buckets[classify(row)].append(row)
    counts = {name: _write_jsonl(out / f'{name}.jsonl', rows) for name, rows in buckets.items()}
    counts['leases'] = _write_jsonl(out / 'leases.jsonl', lease_rows(client, uid))
    counts['unreadable'] = unreadable
    manifest = {
        'window': {'start': start.isoformat(), 'end': end.isoformat(), 'margin_hours': margin.total_seconds() / 3600},
        'exported_at': datetime.now().astimezone().isoformat(),
        'counts': counts,
        'tool': 'testing.pipeline_lab.v3.prod_export',
    }
    fd = os.open(out / 'manifest.json', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as fp:
        json.dump(manifest, fp, indent=1)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--guard', required=True, help='path to the owner guard module (outside the repo)')
    parser.add_argument('--uid-file', required=True, help='0600 file holding the owner uid')
    parser.add_argument('--secret-file', required=True, help='0600 file holding ENCRYPTION_SECRET')
    parser.add_argument('--snapshot', required=True, help='owner snapshot directory under /Volumes/Ephemeral')
    parser.add_argument('--margin-hours', type=float, default=6.0)
    args = parser.parse_args(argv)
    guard = load_guard(args.guard)
    uid = guard.owner_uid(args.uid_file)
    guard.load_secret(args.secret_file)
    os.umask(0o077)
    snapshot = Path(args.snapshot).expanduser().resolve()
    out = resolve_output(snapshot)
    with read_only_fence():
        from database._client import get_firestore_client

        manifest = export(uid, get_firestore_client(), snapshot, out, margin=timedelta(hours=args.margin_hours))
    print(json.dumps({'out': str(out), 'counts': manifest['counts']}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
