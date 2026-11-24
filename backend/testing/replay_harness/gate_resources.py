"""Private gate resources and timeout recovery; all RPCs are emulator-only."""

from contextvars import ContextVar
from contextlib import contextmanager
import json
from http.client import HTTPConnection
import os
from pathlib import Path
import stat
import threading
from unittest.mock import patch

CURRENT_SCOPE = ContextVar('replay_gate_scope', default=None)
DOCUMENT_PREFIX = 'projects/demo-omi-isolated-tests/databases/(default)/documents/'


def private_write(path, data):
    """Replace only the named receipt; never follow a preexisting symlink."""
    path.unlink(missing_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)


def prepare_output(output):
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = output.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('OUTPUT must be an owned directory with mode 0700')


@contextmanager
def journal_writes(client, scope):
    """Journal document *names* before commit, never request bodies or captured values.

    Seeders remap captured identities to synthetic identities. A dedicated ledger
    per environment covers namespace, user subcollections and global outbox rows,
    including transaction commits that have not returned when a worker is killed.
    """
    ledger = Path(scope['root']) / 'documents.jsonl'
    descriptor = os.open(ledger, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    lock = threading.Lock()
    seen = set()

    def intercept(original):
        def commit(*args, **kwargs):
            request = kwargs.get('request', args[0] if args else None)
            writes = request.get('writes', ()) if isinstance(request, dict) else request.writes
            names = []
            for write in writes:
                if isinstance(write, dict):
                    name = (
                        (write.get('update') or {}).get('name')
                        or write.get('delete')
                        or (write.get('transform') or {}).get('document')
                    )
                else:
                    name = write.update.name or write.delete or write.transform.document
                if not name or not name.startswith(DOCUMENT_PREFIX):
                    raise RuntimeError('gate journal refuses non-emulator document')
                names.append(name)
            with lock:
                for name in names:
                    if name not in seen:
                        os.write(descriptor, (json.dumps(name) + '\n').encode())
                        seen.add(name)
                os.fsync(descriptor)
            return original(*args, **kwargs)

        return commit

    try:
        api = client._firestore_api
        with patch.object(api, 'commit', intercept(api.commit)), patch.object(
            api, 'batch_write', intercept(api.batch_write)
        ):
            yield
    finally:
        os.close(descriptor)


def cleanup_scopes(root, endpoint):
    """Recover only journaled documents, after the worker has fully exited.

    No emulator-wide deletion and no ADC/client construction. Scratch lives
    below the parent's owned temporary tree and is removed by its context.
    """
    from testing.replay_harness.env import validate_emulator_endpoint

    validate_emulator_endpoint(endpoint)
    for ledger in sorted(root.glob('*/documents.jsonl')):
        names = {json.loads(line) for line in ledger.read_text().splitlines()}
        for name in sorted(names, key=lambda name: (-name.count('/'), name)):
            if not isinstance(name, str) or not name.startswith(DOCUMENT_PREFIX):
                raise RuntimeError('invalid gate cleanup document')
            host, port = endpoint.rsplit(':', 1)
            # Match the SDK's emulator-only admin identity. Use a direct local
            # socket so ambient HTTP proxies and redirects cannot route cleanup.
            connection = HTTPConnection(host, int(port), timeout=10)
            try:
                connection.request('DELETE', f'/v1/{name}', headers={'Authorization': 'Bearer owner'})
                response = connection.getresponse()
                if response.status not in (200, 404):
                    raise RuntimeError('emulator cleanup rejected document deletion')
            finally:
                connection.close()
