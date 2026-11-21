"""Ambiguous-success retries must not make an older raw projection current again."""

import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from google.api_core.exceptions import ServiceUnavailable
from google.api_core.gapic_v1.method import wrap_method
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import _client
from database.memory_change_head import HEAD_DOCUMENT
from database.released_memory_projection import projected_stream_list

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('interleaved_delete', [True, False])
def test_ambiguous_success_retry_invalidates_projection(monkeypatch, interleaved_delete):
    endpoint = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not endpoint:
        pytest.skip('requires the dedicated local Firestore emulator')
    assert urlsplit('http://' + endpoint).hostname in {'127.0.0.1', 'localhost', '::1'}
    assert os.getenv('GCLOUD_PROJECT') == 'demo-fs-p2-retry'
    monkeypatch.setenv('MEMORY_RELEASED_WRITERS_COVERED', 'v2:retry-emulator')
    monkeypatch.setenv('MEMORY_RELEASED_PROJECTION', 'on')
    _client._install_memory_change_heads()
    _client._install_list_projection_writer()
    client = firestore.Client(project='demo-fs-p2-retry', credentials=AnonymousCredentials())
    root = f'users/retry-{uuid4().hex}'
    refs = {key: client.document(f'{root}/memory_items/{key}') for key in 'abc'}
    marker = client.document(f'{root}/memory_state/{HEAD_DOCUMENT}')
    query = client.collection(f'{root}/memory_items').order_by('n')
    transport = client._firestore_api._transport
    real_rpc = transport._wrapped_methods[transport.commit]
    attempts = []
    first_head = []

    def read():
        return {row.id: row.to_dict()['n'] for row in projected_stream_list(query, surface='canonical_scan')}

    def ambiguous_success(request, **kwargs):
        result = real_rpc(request, **kwargs)
        if any(write.update.name == refs['a']._document_path for write in request.writes):
            attempts.append(request)
            if len(attempts) == 1:
                assert read() == {'a': 1, 'b': 2, 'c': 3}
                first_head.append(marker.get())
                if interleaved_delete:
                    refs['b'].delete()
                # The server applied A; only its acknowledgement was lost.
                raise ServiceUnavailable('synthetic lost Commit acknowledgement')
        return result

    try:
        for index, ref in enumerate(refs.values()):
            ref.set({'n': index + 1 if index else 0})
        assert real_rpc._retry is not None  # Preserve the pinned SDK's actual retry policy.
        transport._wrapped_methods[transport.commit] = wrap_method(
            ambiguous_success, default_retry=real_rpc._retry, default_timeout=real_rpc._timeout
        )
        if interleaved_delete:
            refs['a'].set({'n': 1})
        else:
            refs['a'].update({'n': firestore.Increment(1)})
        assert len(attempts) == 2
        # The same prepared head token really is replayed by GAPIC, rather than
        # re-entering our outer writer hook and accidentally making a fresh UUID.
        assert attempts[0].writes[-1].update.fields['token'] == attempts[1].writes[-1].update.fields['token']
        expected = {'a': 1, 'c': 3} if interleaved_delete else {'a': 2, 'b': 2, 'c': 3}
        assert read() == expected
        final_head = marker.get()
        assert final_head.update_time > first_head[0].update_time
        assert final_head.to_dict()['commit_generation'] > first_head[0].to_dict()['commit_generation']
    finally:
        transport._wrapped_methods[transport.commit] = real_rpc
        for ref in refs.values():
            ref.delete()
        marker.delete()
        client.close()
