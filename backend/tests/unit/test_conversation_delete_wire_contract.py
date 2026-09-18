"""Released-client wire contract for DELETE /v1/conversations/{conversation_id}.

The 2026-07-04 response_model backfill (e22938ac78) silently converted this
route from ``status_code=204`` to a 200-with-body. The released mobile client
(``app/lib/backend/http/api/conversations.dart::deleteConversationServer``)
gates delete success on exactly 204, so every conversation delete read as a
failure there: the optimistic tombstone was dropped, the server-cursor bookkeeping
skipped the rebase, and once the server delete itself could not complete the
conversation resurfaced on the next refresh (#10446 recurrence class).

Two layers assert the same contract so one layer failing alone cannot hide the
drift: the router declaration and the generated app-client OpenAPI spec.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.routing import APIRoute

from routers import conversations

ROOT_DIR = Path(__file__).resolve().parents[3]
APP_CLIENT_SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'

CONVERSATION_DELETE_PATH = '/v1/conversations/{conversation_id}'


def _conversation_delete_route() -> APIRoute:
    matches = [
        route
        for route in conversations.router.routes
        if isinstance(route, APIRoute) and route.path == CONVERSATION_DELETE_PATH and 'DELETE' in route.methods
    ]
    assert matches, 'conversation delete route must stay registered'
    return matches[0]


def test_conversation_delete_declares_released_204_contract():
    route = _conversation_delete_route()

    assert route.status_code == 204
    # A 204 route has no body; a response_model forces FastAPI to serialize one.
    assert route.response_model is None


def test_app_client_spec_declares_204_not_200_for_conversation_delete():
    spec = json.loads(APP_CLIENT_SPEC_PATH.read_text())
    responses = spec['paths'][CONVERSATION_DELETE_PATH]['delete']['responses']

    assert '204' in responses
    # The released mobile client treats a 200 body as a failed DELETE.
    assert '200' not in responses
