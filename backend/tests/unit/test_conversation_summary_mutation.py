"""Atomic user summary edits and stale structured-section invalidation."""

from __future__ import annotations

import json
import zlib
from datetime import datetime, timezone

import pytest

from database import conversations as conversations_db

UID = 'summary-user'
CONVERSATION_ID = 'summary-conversation'


class _Snapshot:
    def __init__(self, data: dict | None):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


class _Ref:
    def __init__(self, snapshot: _Snapshot):
        self.snapshot = snapshot
        self.update_calls: list[dict] = []
        self.get_transactions: list[object] = []

    def get(self, transaction=None):
        self.get_transactions.append(transaction)
        return self.snapshot


class _Transaction:
    def update(self, ref: _Ref, payload: dict):
        assert ref.get_transactions == [self], "Writes require a transactional read first"
        ref.update_calls.append(payload)


class _DB:
    def __init__(self, ref: _Ref):
        self.ref = ref
        self.tx = _Transaction()
        self._document_calls = 0

    def collection(self, _name):
        return self

    def document(self, _name):
        self._document_calls += 1
        return self.ref if self._document_calls == 2 else self

    def transaction(self):
        return self.tx


def _install_db(monkeypatch, data: dict | None):
    ref = _Ref(_Snapshot(data))
    monkeypatch.setattr(conversations_db, 'db', _DB(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_args: None)
    return ref


def test_first_party_edit_atomically_replaces_overview_and_removes_stale_sections(monkeypatch):
    ref = _install_db(
        monkeypatch,
        {
            'structured': {
                'overview': 'Generated overview',
                'sections': [{'heading': 'Old evidence', 'body_markdown': 'Old body'}],
                'action_items': [{'description': 'Keep this action'}],
                'events': [{'title': 'Keep this event'}],
            },
            'apps_results': [{'app_id': 'other', 'content': 'Keep this app result'}],
        },
    )

    assert conversations_db.update_conversation_summary(UID, CONVERSATION_ID, None, 'User corrected text') == 'ok'

    assert len(ref.update_calls) == 1
    payload = ref.update_calls[0]
    assert payload['structured.overview'] == 'User corrected text'
    assert payload['structured.sections'] is conversations_db.firestore.DELETE_FIELD
    assert isinstance(payload['updated_at'], datetime)
    assert payload['updated_at'].tzinfo == timezone.utc
    assert set(payload) == {'structured.overview', 'structured.sections', 'updated_at'}


def test_app_edit_preserves_other_results_and_advances_freshness(monkeypatch):
    ref = _install_db(
        monkeypatch,
        {
            'structured': {
                'overview': 'Generated overview',
                'sections': [{'heading': 'Evidence', 'body_markdown': 'Body'}],
                'action_items': [{'description': 'Keep this action'}],
            },
            'apps_results': [
                {'app_id': 'first', 'content': 'First'},
                {'app_id': 'selected', 'content': 'Old selected'},
                {'app_id': 'third', 'content': 'Third'},
            ],
        },
    )

    assert conversations_db.update_conversation_summary(UID, CONVERSATION_ID, 'selected', 'New selected') == 'ok'

    payload = ref.update_calls[0]
    assert payload['apps_results'] == [
        {'app_id': 'first', 'content': 'First'},
        {'app_id': 'selected', 'content': 'New selected'},
        {'app_id': 'third', 'content': 'Third'},
    ]
    assert isinstance(payload['updated_at'], datetime)
    assert 'structured.overview' not in payload
    assert 'structured.sections' not in payload


def test_missing_app_edit_does_not_write(monkeypatch):
    ref = _install_db(monkeypatch, {'apps_results': [{'app_id': 'known', 'content': 'Known'}]})

    assert (
        conversations_db.update_conversation_summary(UID, CONVERSATION_ID, 'missing', 'New') == 'app_result_not_found'
    )
    assert ref.update_calls == []


def test_segment_edit_invalidates_affected_summary_evidence_in_same_transaction(monkeypatch):
    ref = _install_db(
        monkeypatch,
        {
            'data_protection_level': 'standard',
            'transcript_segments': [
                {'id': 's1', 'text': 'Old source text'},
                {'id': 's2', 'text': 'Unaffected source text'},
            ],
            'structured': {
                'overview': 'Keep this user-visible overview',
                'sections': [
                    {
                        'heading': 'Affected section',
                        'body_markdown': '- Preserve this body',
                        'source_segment_ids': ['s1', 's2'],
                    },
                    {
                        'heading': 'Unaffected section',
                        'body_markdown': '- Still authoritative',
                        'source_segment_ids': ['s2'],
                    },
                ],
                'action_items': [
                    {
                        'description': 'Preserve affected action',
                        'completed': False,
                        'source_segment_ids': ['s1', 's2'],
                    },
                    {
                        'description': 'Preserve unaffected action',
                        'completed': True,
                        'source_segment_ids': ['s2'],
                    },
                ],
                'events': [{'title': 'Keep this event'}],
            },
        },
    )

    assert conversations_db.update_conversation_segment_text(UID, CONVERSATION_ID, 's1', 'New source text') == 'ok'

    assert ref.get_transactions == [conversations_db.db.tx]
    assert len(ref.update_calls) == 1
    payload = ref.update_calls[0]
    assert payload['updated_at'].tzinfo == timezone.utc
    assert payload['structured.sections'] == [
        {
            'heading': 'Affected section',
            'body_markdown': '- Preserve this body',
            'source_segment_ids': [],
        },
        {
            'heading': 'Unaffected section',
            'body_markdown': '- Still authoritative',
            'source_segment_ids': ['s2'],
        },
    ]
    assert payload['structured.action_items'] == [
        {
            'description': 'Preserve affected action',
            'completed': False,
            'source_segment_ids': [],
        },
        {
            'description': 'Preserve unaffected action',
            'completed': True,
            'source_segment_ids': ['s2'],
        },
    ]
    # The partial transaction update leaves unrelated structured fields intact.
    assert 'structured.overview' not in payload
    assert 'structured.events' not in payload

    stored_segments = json.loads(zlib.decompress(payload['transcript_segments']).decode('utf-8'))
    assert stored_segments == [
        {'id': 's1', 'text': 'New source text'},
        {'id': 's2', 'text': 'Unaffected source text'},
    ]


def test_missing_conversation_summary_edit_does_not_write(monkeypatch):
    ref = _install_db(monkeypatch, None)
    assert conversations_db.update_conversation_summary(UID, CONVERSATION_ID, None, 'New') == 'not_found'
    assert ref.update_calls == []


@pytest.fixture
def summary_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import conversations as routes

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: UID
    with TestClient(app) as client:
        yield client


def test_duplicate_app_id_is_rejected_by_summary_endpoint_without_mutation(monkeypatch, summary_client):
    ref = _install_db(
        monkeypatch,
        {
            'apps_results': [
                {'app_id': 'duplicate', 'content': ''},
                {'app_id': 'duplicate', 'content': 'Selected useful result'},
            ]
        },
    )
    response = summary_client.patch(
        f'/v1/conversations/{CONVERSATION_ID}/summary',
        json={'app_id': 'duplicate', 'content': 'User edit'},
    )
    assert response.status_code == 409
    assert ref.update_calls == []
