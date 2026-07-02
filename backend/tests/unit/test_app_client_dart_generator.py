from __future__ import annotations

import json
from pathlib import Path

from models.conversation import Conversation
from scripts import generate_dart_models

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
GENERATED_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'conversation_wire.g.dart'
ACTION_ITEMS_FOLDERS_DART_PATH = (
    ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'action_items_folders_wire.g.dart'
)
CONVERSATION_FIXTURE_PATH = ROOT_DIR / 'backend' / 'testing' / 'e2e' / 'fixtures' / 'conversations.json'


def test_conversation_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'conversation')

    assert GENERATED_DART_PATH.read_text() == generated
    for schema_name in generate_dart_models.SCHEMA_GROUPS['conversation']['schemas']:
        assert f'class Generated{schema_name}' in generated


def test_action_items_folders_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'action_items_folders')

    assert ACTION_ITEMS_FOLDERS_DART_PATH.read_text() == generated
    assert 'class GeneratedActionItemResponse' in generated
    assert 'class GeneratedActionItemsResponse' in generated
    assert 'class GeneratedActionItemsSearchResponse' in generated
    assert 'class GeneratedPendingSyncResponse' in generated
    assert 'class GeneratedFolder' in generated
    assert 'class GeneratedFolderMutationResponse' in generated
    assert 'class GeneratedBulkMoveConversationsResponse' in generated
    assert 'exported: _readBool(_readAny(json, const ["exported"])) ?? false' in generated
    assert 'color: _readString(_readAny(json, const ["color"])) ?? "#6B7280"' in generated


def test_conversation_wire_dart_preserves_known_client_aliases():
    generated = GENERATED_DART_PATH.read_text()

    assert 'const ["action_items", "actionItems"]' in generated
    assert 'const ["start", "startsAt"]' in generated
    assert 'const ["app_id", "appId"]' in generated
    assert 'const ["google_place_id", "googlePlaceId"]' in generated
    assert "'apps_results': appsResults" in generated
    assert "'plugins_results': pluginsResults" in generated
    assert 'category: _readString(_readAny(json, const ["category"])) ?? "other"' in generated
    assert 'source: _readString(_readAny(json, const ["source"])) ?? "omi"' in generated
    assert 'visibility: _readString(_readAny(json, const ["visibility"])) ?? "private"' in generated
    assert 'DateTime.fromMillisecondsSinceEpoch(value * 1000).toLocal()' in generated
    assert 'final List<GeneratedTranslation>? translations;' in generated
    assert 'translations: _readAny(json, const ["translations"]) == null ? null : _readObjectList' in generated


def test_conversation_fixtures_validate_against_python_schema_authority():
    fixtures = json.loads(CONVERSATION_FIXTURE_PATH.read_text())

    for name, payload in fixtures.items():
        conversation = Conversation.model_validate(payload)
        assert conversation.id, name
        assert conversation.structured is not None, name
