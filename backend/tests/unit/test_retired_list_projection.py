"""Released list readers and account erasure after list projection retirement."""

import copy
from types import SimpleNamespace

import pytest
from fastapi import Request, Response

from database import batch_pipeline_purge, user_data_deletion
from routers import conversations as conversation_routes


def test_account_erasure_clears_retired_list_data_even_when_user_root_is_missing(monkeypatch):
    rows = {
        'list_serving_versions': {'conversations': {}, 'action_items': {}},
        'conversation_list_rows': {'one': {}},
        'action_item_list_rows': {'one': {}},
        'conversations': {'one': {}},
        'action_items': {'one': {}},
    }

    deleted = []

    def delete(name, key):
        deleted.append((name, key))
        rows.get(name, {}).pop(key, None)

    def collection(name):
        return SimpleNamespace(document=lambda key: SimpleNamespace(delete=lambda: delete(name, key)))

    root = SimpleNamespace(
        get=lambda: SimpleNamespace(exists=False),
        collection=collection,
        collections=lambda: [SimpleNamespace(id=name) for name in rows],
    )
    client = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda key: root))
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', lambda uid: None)
    monkeypatch.setattr(user_data_deletion, 'search_apps_db', lambda _uid, my_apps: [])
    monkeypatch.setattr(
        user_data_deletion,
        'get_data_plane_firestore_client',
        lambda: SimpleNamespace(
            collection=lambda name: SimpleNamespace(
                document=lambda key: SimpleNamespace(
                    collections=lambda: [],
                    delete=lambda: None,
                    collection=lambda _: SimpleNamespace(list_documents=lambda: []),
                )
            )
        ),
    )

    def recursive(subcollection, **kwargs):
        rows[subcollection.id].clear()

    retirements = []
    monkeypatch.setattr(
        user_data_deletion,
        'stop_quiet_checks_for_account',
        lambda uid, **kwargs: retirements.append((uid, kwargs['firestore_client'])),
    )
    assert user_data_deletion.purge_user_subtree('owner', client, recursive)['status'] == 'ok'
    assert retirements == [('owner', client)]
    assert all(not values for values in rows.values())
    assert ('list_serving_versions', 'conversations') in deleted
    assert ('list_serving_versions', 'action_items') in deleted


@pytest.mark.parametrize('gate', ['on', 'off'])
@pytest.mark.parametrize('home_gate', ['on', 'off'])
def test_real_conversation_route_preserves_locked_allowance_recovery(monkeypatch, gate, home_gate):
    monkeypatch.setenv('HOME_TRANSCRIPTION_PRESENTATION_GATE', gate)
    monkeypatch.setenv('HOME_STEP_PROJECTION', home_gate)
    rows = [{'id': 'locked', 'is_locked': True, 'status': 'completed'}]

    def wire(source_rows):
        # The default-on Home row contract stamps the wire copy (both gate
        # modes). This bare completed capture has no title, transcript, batch
        # receipt, or 2h bound, so it reads as still transcribing.
        return [{**row, 'home_step': 'transcribing'} for row in source_rows] if home_gate == 'on' else source_rows

    calls = []

    def source(*args, **kwargs):
        calls.append('source')
        return copy.deepcopy(rows)

    def heal(uid, page):
        calls.append('heal')

    monkeypatch.setattr(conversation_routes.conversations_db, 'get_conversations_without_photos', source)
    monkeypatch.setattr(conversation_routes, '_heal_locked_conversations_if_eligible', heal)
    monkeypatch.setattr(conversation_routes, 'redact_conversations_for_list', lambda page: None)
    monkeypatch.setattr(
        conversation_routes,
        'list_read_budget_for_request',
        lambda *a, **k: SimpleNamespace(
            truncated=False,
            observe=lambda outcome: None,
        ),
    )
    request = Request(
        {
            'type': 'http',
            'path': '/v1/conversations',
            'headers': [(b'if-none-match', b'W/"lp1-retired-validator"')],
            'query_string': b'',
        }
    )
    params = dict(
        request=request,
        uid='owner',
        limit=100,
        offset=0,
        statuses='completed',
        sources=None,
        start_date=None,
        end_date=None,
        folder_id=None,
        starred=None,
    )
    first = Response()
    assert conversation_routes.get_conversations(response=first, **params) == wire(rows)
    assert 'etag' not in first.headers  # monthly rollover must still reach heal
    assert conversation_routes.get_conversations(response=Response(), **params) == wire(rows)
    assert calls == ['source', 'heal', 'source', 'heal']
    rows[0]['is_locked'] = False
    fresh = Response()
    assert conversation_routes.get_conversations(response=fresh, **params) == wire(rows)
    assert 'etag' not in fresh.headers
    assert calls == ['source', 'heal'] * 3
