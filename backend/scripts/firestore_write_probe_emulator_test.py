"""Verify write attribution through the real Firestore SDK and local emulator."""

import os
from pathlib import Path
import sys
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import _client  # noqa: E402,F401 - installs the production SDK probes
from database.firestore_read_origin import read_origin  # noqa: E402
from database.firestore_write_probe import (  # noqa: E402
    FIRESTORE_BILLED_WRITES_BY_CALLER,
    FIRESTORE_BILLED_WRITES_BY_ORIGIN,
)


def main() -> None:
    host, separator, port = os.getenv('FIRESTORE_EMULATOR_HOST', '').rpartition(':')
    if host != '127.0.0.1' or not separator or not port.isdigit():
        raise SystemExit('Run with npm run test:firestore-write-probe:emulator')

    client = firestore.Client(project='demo-write-probe', credentials=AnonymousCredentials())
    collection = client.collection('write_probe_emulator')
    run_id = uuid4().hex
    origin = 'job:write_probe_emulator'
    caller = f'{__name__}:main'
    caller_counter = FIRESTORE_BILLED_WRITES_BY_CALLER.labels(collection='other', op='set', caller=caller)
    origin_counter = FIRESTORE_BILLED_WRITES_BY_ORIGIN.labels(collection='other', op='set', origin=origin)
    before_caller = caller_counter._value.get()
    before_origin = origin_counter._value.get()
    documents = 7

    batch = client.batch()
    for index in range(documents):
        batch.set(collection.document(f'{run_id}-{index}'), {'n': index})
    assert caller_counter._value.get() == before_caller
    with read_origin(origin):
        assert len(batch.commit()) == documents
    assert caller_counter._value.get() - before_caller == documents
    assert origin_counter._value.get() - before_origin == documents
    print(
        f'Firestore emulator acknowledged {documents} document writes; both attribution counters recorded {documents}'
    )


if __name__ == '__main__':
    main()
