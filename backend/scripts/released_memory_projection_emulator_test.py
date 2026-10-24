"""Real Firestore atomicity/retry/delete coverage. Emulator only; no prod access."""

import asyncio
import os
import uuid

from google.api_core.exceptions import Aborted, NotFound
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database.memory_change_head import HEAD_DOCUMENT, install_write_heads
from database.released_memory_projection import projected_stream_list


def main() -> None:
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):
        raise RuntimeError('FIRESTORE_EMULATOR_HOST required')
    project = 'demo-fs-p2'
    client = firestore.Client(project=project, credentials=AnonymousCredentials())
    uid = f'fs-p2-{uuid.uuid4().hex}'
    install_write_heads()
    os.environ['MEMORY_RELEASED_WRITERS_COVERED'] = 'v1:emulator-test'
    os.environ['MEMORY_RELEASED_PROJECTION'] = 'on'
    root = f'users/{uid}'
    item = client.document(f'{root}/memory_items/a')
    marker = client.document(f'{root}/memory_state/{HEAD_DOCUMENT}')
    query = client.collection(f'{root}/memory_items').order_by('n')

    def token():
        return marker.get().to_dict()['token']

    def read():
        return [row.to_dict() for row in projected_stream_list(query, surface='canonical_scan')]

    item.set({'n': 1})
    first = token()
    assert read() == read() == [{'n': 1}]
    batch = client.batch()
    batch.update(item, {'n': 2})
    result = batch.commit()
    assert len(result) == 1 and token() != first
    assert read() == [{'n': 2}]

    before = token()
    failed = client.batch()
    failed.update(item, {'n': 99})
    failed.update(client.document(f'{root}/memories/missing'), {'n': 1})
    try:
        failed.commit()
        raise AssertionError('invalid batch unexpectedly committed')
    except NotFound:
        pass
    assert item.get().to_dict() == {'n': 2} and token() == before

    attempts = []
    transport = client._firestore_api._transport
    real_rpc = transport._wrapped_methods[transport.commit]

    def abort_once(request, **kwargs):
        attempts.append(request)
        if len(attempts) == 1:
            # A real server abort releases its transaction locks. An injected
            # transport exception must release them too before the SDK retries.
            client._firestore_api.rollback(request={'database': request.database, 'transaction': request.transaction})
            raise Aborted('injected first-attempt RPC abort')
        return real_rpc(request, **kwargs)

    @firestore.transactional
    def retried(transaction):
        value = item.get(transaction=transaction).to_dict()['n']
        transaction.update(item, {'n': value + 1})

    transport._wrapped_methods[transport.commit] = abort_once
    try:
        retried(client.transaction())
    finally:
        transport._wrapped_methods[transport.commit] = real_rpc
    assert len(attempts) == 2 and read() == [{'n': 3}]
    assert all(len(request.writes) == 2 for request in attempts)
    assert token() != before
    item.delete()
    assert read() == []

    async def async_writes():
        async_client = firestore.AsyncClient(project=project, credentials=AnonymousCredentials())
        ref = async_client.document(f'{root}/memories/legacy')
        await ref.set({'n': 1})
        before_async = token()
        await ref.delete()
        assert token() != before_async
        async_client.close()

    asyncio.run(async_writes())

    bulk = client.bulk_writer()
    bulk.set(client.document(f'{root}/memories/bulk'), {'n': 1})
    bulk.close()
    assert client.document(f'{root}/memories/bulk').get().exists
    assert marker.get().to_dict()['blocked'] is True
    item.set({'n': 4})
    assert marker.get().to_dict()['blocked'] is True
    print(
        'PASS: atomic batch failure, transaction retry, source result parity, sync/async deletes, bulk exclusion, raw read parity'
    )


if __name__ == '__main__':
    main()
