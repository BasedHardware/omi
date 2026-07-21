"""GET /v2/integrations/{app_id}/conversations must cap the `statuses` filter length.

`statuses` flows straight from the query string into
`conversations_db.get_conversations(..., statuses=statuses, ...)`, which applies it as a
single Firestore `in` filter (`FieldFilter('status', 'in', statuses)`). Firestore hard-rejects
`in` filters with more than 30 values - a limit this codebase already respects elsewhere
(see `database/apps.py` "Firestore 'in' limited to 30 items" and the chunking in
`database/chat.py`). Before the fix, nothing capped `statuses` on this route, so a caller
that supplied more than 30 values turned a client error into an unhandled exception from the
Firestore client (surfaced to the caller as a 500) instead of a clean 400. The real
`ConversationStatus` enum only has 5 members, so no legitimate integration caller needs more
than a handful of values - the cap here cannot reject any real request shape.

Test isolation: routers.integration pulls in routers.conversations -> speaker_identification
-> av/langchain transitively, so the import is heavy (tens of seconds). Per AGENTS.md test
isolation guidance this is done as a plain top-level import (paid once for the file, at
collection time) rather than inside a test body, and without any sys.modules mutation -
collaborators are patched with monkeypatch.setattr and the handler is called directly.
"""

import os
from unittest.mock import MagicMock

from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('PINECONE_API_KEY', 'fake')

from routers import integration as integ  # noqa: E402


class _SpyGetConversations:
    """Stand-in for conversations_db.get_conversations.

    Records every call it receives (the real seam the router hands `statuses` to) and
    mirrors Firestore's actual behavior: an `in` filter with more than 30 values blows up
    instead of returning results.
    """

    def __init__(self):
        self.calls = []

    def __call__(self, uid, **kwargs):
        self.calls.append(kwargs.get('statuses'))
        statuses = kwargs.get('statuses') or []
        if len(statuses) > 30:
            raise Exception("400 Bad Request: 'in' filters support a maximum of 30 elements.")
        return []


def _setup_gates(monkeypatch):
    monkeypatch.setattr(integ, 'verify_api_key', lambda app_id, api_key: True)
    monkeypatch.setattr(integ.apps_db, 'get_app_by_id_db', lambda app_id: {'id': app_id, 'name': 'test-app'})
    monkeypatch.setattr(integ.redis_db, 'get_enabled_apps', lambda uid: ['app-1'])
    monkeypatch.setattr(integ.apps_utils, 'app_can_read_conversations', lambda app: True)


def _call(statuses, monkeypatch, spy):
    _setup_gates(monkeypatch)
    monkeypatch.setattr(integ.conversations_db, 'get_conversations', spy)
    return integ.get_conversations_via_integration(
        request=MagicMock(),
        app_id='app-1',
        uid='test-uid',
        limit=100,
        offset=0,
        include_discarded=False,
        statuses=statuses,
        start_date=None,
        end_date=None,
        max_transcript_segments=100,
        authorization='Bearer test-key',
    )


def test_oversized_statuses_filter_rejected_before_reaching_db(monkeypatch):
    """35 values (more than Firestore's 30-value 'in' cap) must be a clean 400 that never
    reaches the db seam - not an unhandled exception from the Firestore client."""
    spy = _SpyGetConversations()
    too_many = [f'status-{i}' for i in range(35)]

    raised = None
    try:
        _call(too_many, monkeypatch, spy)
    except Exception as exc:  # noqa: BLE001 - capture whatever the handler actually raises
        raised = exc

    assert isinstance(raised, HTTPException), f'expected a clean HTTPException(400), got {raised!r}'
    assert raised.status_code == 400
    assert spy.calls == [], f'db seam must never see an oversized statuses list, got {spy.calls}'


def test_normal_statuses_filter_reaches_db_unmodified(monkeypatch):
    """A couple of real status values are unaffected by the cap and reach the db as-is."""
    spy = _SpyGetConversations()

    result = _call(['processing', 'completed'], monkeypatch, spy)

    assert spy.calls == [['processing', 'completed']]
    assert result == {'conversations': []}
