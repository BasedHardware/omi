"""Regression: integration conversation search must hydrate with the same include_discarded.

POST /v2/integrations/{app_id}/search/conversations forwards include_discarded to
search_conversations, but hydrated the matched ids with conversations_db.get_conversations_by_id
and no flag. That helper defaults include_discarded=False and skips discarded documents, so a
discarded conversation could match the search and then be dropped during hydration. The search
window has already advanced past it, so the row is unreachable on any page.

SearchRequest.include_discarded defaults to True (models/conversation.py), so the two gates
disagree by default rather than only in an unusual configuration.

The sibling desktop endpoint had the same defect and a maintainer fixed it the same way in #9175
(routers/conversations.py now passes include_discarded into its hydration call); the integration
endpoint was not updated at the time.

Seam: the handler is a plain def, so this calls it directly with its collaborators patched via
monkeypatch.setattr on module attributes. No sys.modules mutation.
"""

from unittest.mock import MagicMock

import routers.integration as integration


def _patch_auth(monkeypatch):
    monkeypatch.setattr(integration, 'verify_api_key', lambda app_id, api_key: True)
    monkeypatch.setattr(integration.apps_db, 'get_app_by_id_db', lambda app_id: {'id': app_id, 'name': 'test'})
    monkeypatch.setattr(integration.redis_db, 'get_enabled_apps', lambda uid: ['app-1'])
    apps_utils_stub = MagicMock()
    apps_utils_stub.app_can_read_conversations.return_value = True
    monkeypatch.setattr(integration, 'apps_utils', apps_utils_stub)


def _run_search(monkeypatch, include_discarded):
    captured: dict = {}

    def fake_get_conversations_by_id(uid, conversation_ids, **kwargs):
        captured.update(kwargs)
        return []

    _patch_auth(monkeypatch)
    monkeypatch.setattr(integration.conversations_db, 'get_conversations_by_id', fake_get_conversations_by_id)
    monkeypatch.setattr(
        integration,
        'search_conversations',
        lambda **kwargs: {'items': [{'id': 'c1'}], 'total_pages': 1, 'current_page': 1, 'per_page': 10},
    )

    integration.search_conversations_via_integration(
        request=MagicMock(),
        app_id='app-1',
        uid='test-uid',
        search_request=MagicMock(
            query='test',
            page=1,
            per_page=10,
            include_discarded=include_discarded,
            start_date=None,
            end_date=None,
        ),
        max_transcript_segments=100,
        authorization='Bearer test-key',
    )
    return captured


def test_hydration_requests_discarded_when_search_did(monkeypatch):
    captured = _run_search(monkeypatch, include_discarded=True)

    # Without the flag the helper defaults to False and silently drops discarded matches.
    assert captured.get('include_discarded') is True


def test_hydration_excludes_discarded_when_search_did(monkeypatch):
    captured = _run_search(monkeypatch, include_discarded=False)

    assert captured.get('include_discarded') is False
