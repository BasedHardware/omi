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
API_KEYS_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'api_keys_wire.g.dart'
AGENT_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'agent_wire.g.dart'
PHONE_CALLS_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'phone_calls_wire.g.dart'
PEOPLE_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'people_wire.g.dart'
IMPORTS_INTEGRATIONS_DART_PATH = (
    ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'imports_integrations_wire.g.dart'
)
WRAPPED_TASK_INTEGRATIONS_DART_PATH = (
    ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'wrapped_task_integrations_wire.g.dart'
)
SUBSCRIPTION_USAGE_DART_PATH = (
    ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'subscription_usage_wire.g.dart'
)
PRIVACY_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'privacy_wire.g.dart'
ANNOUNCEMENTS_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'announcements_wire.g.dart'
AUDIO_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'audio_wire.g.dart'
PAYMENTS_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'payments_wire.g.dart'
MEMORIES_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'memories_wire.g.dart'
GOALS_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'goals_wire.g.dart'
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
    assert 'class GeneratedBatchMutationResponse' in generated
    assert 'class GeneratedBatchDeleteActionItemsResponse' in generated
    assert 'class GeneratedBatchCreateActionItemsResponse' in generated
    assert 'class GeneratedShareActionItemsResponse' in generated
    assert 'class GeneratedSharedActionItemsResponse' in generated
    assert 'class GeneratedAcceptSharedActionItemsResponse' in generated
    assert 'class GeneratedFolder' in generated
    assert 'class GeneratedFolderMutationResponse' in generated
    assert 'class GeneratedBulkMoveConversationsResponse' in generated
    assert 'exported: _readBool(_readAny(json, const ["exported"])) ?? false' in generated
    assert 'color: _readString(_readAny(json, const ["color"])) ?? "#6B7280"' in generated
    assert 'deletedIds: _required(_readStringList(_readAny(json, const ["deleted_ids"])), "deleted_ids")' in generated


def test_action_items_adapter_coalesces_optional_envelope_defaults():
    adapter = (ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'action_item.dart').read_text()

    assert 'hasMore: generated.hasMore ?? false' in adapter


def test_api_keys_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'api_keys')

    assert API_KEYS_DART_PATH.read_text() == generated
    assert 'class GeneratedDevApiKey' in generated
    assert 'class GeneratedDevApiKeyCreated' in generated
    assert 'class GeneratedMcpApiKey' in generated
    assert 'class GeneratedMcpApiKeyCreated' in generated
    assert 'final List<String>? scopes;' in generated
    assert 'final String? appId;' in generated
    assert 'createdAt: _required(_readDateTime(_readAny(json, const ["created_at"])), "created_at")' in generated


def test_agent_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'agent')

    assert AGENT_DART_PATH.read_text() == generated
    assert 'class GeneratedAgentVmInfo' in generated
    assert 'class GeneratedAgentKeepaliveResponse' in generated
    assert 'hasVm: _required(_readBool(_readAny(json, const ["has_vm"])), "has_vm")' in generated


def test_phone_calls_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'phone_calls')

    assert PHONE_CALLS_DART_PATH.read_text() == generated
    assert 'class GeneratedPhoneNumberResponse' in generated
    assert 'class GeneratedPhoneNumbersResponse' in generated
    assert 'class GeneratedTokenResponse' in generated
    assert 'accessToken: _required(_readString(_readAny(json, const ["access_token"])), "access_token")' in generated


def test_people_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'people')

    assert PEOPLE_DART_PATH.read_text() == generated
    assert 'class GeneratedPerson' in generated
    assert 'speechSamplesVersion: _readInt(_readAny(json, const ["speech_samples_version"])) ?? 3' in generated


def test_person_adapter_preserves_required_timestamp_behavior():
    adapter = (ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'person.dart').read_text()

    assert "FormatException('Missing required field: created_at')" in adapter
    assert "FormatException('Missing required field: updated_at')" in adapter


def test_imports_integrations_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'imports_integrations')

    assert IMPORTS_INTEGRATIONS_DART_PATH.read_text() == generated
    assert 'class GeneratedImportJobResponse' in generated
    assert 'class GeneratedIntegrationResponse' in generated
    assert 'jobId: _required(_readString(_readAny(json, const ["job_id"])), "job_id")' in generated
    assert 'connected: _required(_readBool(_readAny(json, const ["connected"])), "connected")' in generated


def test_wrapped_task_integrations_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'wrapped_task_integrations')

    assert WRAPPED_TASK_INTEGRATIONS_DART_PATH.read_text() == generated
    assert 'class GeneratedWrappedStatusResponse' in generated
    assert 'class GeneratedGenerateWrappedResponse' in generated
    assert 'class GeneratedTaskIntegrationsResponse' in generated
    assert 'class GeneratedDefaultTaskIntegrationResponse' in generated
    assert 'status: _required(_readString(_readAny(json, const ["status"])), "status")' in generated
    assert 'integrations: _required(_readMap(_readAny(json, const ["integrations"])), "integrations")' in generated


def test_subscription_usage_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'subscription_usage')

    assert SUBSCRIPTION_USAGE_DART_PATH.read_text() == generated
    assert 'class GeneratedUserSubscriptionResponse' in generated
    assert 'class GeneratedUserUsageResponse' in generated
    assert 'final List<String> features;' in generated
    assert 'limits: _readObject(_readAny(json, const ["limits"]), GeneratedPlanLimits.fromJson)' in generated
    assert 'GeneratedPlanLimits.fromJson(const {})' in generated
    assert 'transcriptionSeconds: _readInt(_readAny(json, const ["transcription_seconds"])) ?? 0' in generated


def test_privacy_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'privacy')

    assert PRIVACY_DART_PATH.read_text() == generated
    assert 'class GeneratedMigrationRequest' in generated
    assert 'class GeneratedBatchMigrationRequest' in generated
    assert 'class GeneratedMigrationTargetRequest' in generated
    assert 'targetLevel: _required(_readString(_readAny(json, const ["target_level"])), "target_level")' in generated


def test_announcements_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'announcements')

    assert ANNOUNCEMENTS_DART_PATH.read_text() == generated
    assert 'class GeneratedTargeting' in generated
    assert 'class GeneratedDisplay' in generated
    assert 'class GeneratedAnnouncement' in generated
    assert 'createdAt: _required(_readDateTime(_readAny(json, const ["created_at"])), "created_at")' in generated
    assert 'trigger: _readString(_readAny(json, const ["trigger"])) ?? "version_upgrade"' in generated
    assert 'deviceModels: _readAny(json, const ["device_models"]) == null ? null : _readStringList' in generated


def test_audio_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'audio')

    assert AUDIO_DART_PATH.read_text() == generated
    assert 'class GeneratedAudioPrecacheResponse' in generated
    assert 'class GeneratedAudioFileUrlInfo' in generated
    assert 'class GeneratedAudioUrlsResponse' in generated
    assert 'duration: _readDouble(_readAny(json, const ["duration"])) ?? 0' in generated
    assert 'audioFiles: _required(_readObjectList(_readAny(json, const ["audio_files"])' in generated
    assert 'List<T>? _readObjectList<T>' in generated
    assert 'if (value is! List) return null;' in generated


def test_payments_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'payments')

    assert PAYMENTS_DART_PATH.read_text() == generated
    assert 'class GeneratedStripeConnectAccountResponse' in generated
    assert 'class GeneratedStripeOnboardingStatusResponse' in generated
    assert 'class GeneratedStripeSupportedCountryResponse' in generated
    assert 'class GeneratedPayPalPaymentDetailsResponse' in generated
    assert 'class GeneratedPaymentMethodStatusResponse' in generated
    assert 'class GeneratedPaymentCheckoutSessionResponse' in generated
    assert 'class GeneratedPaymentUpgradeSubscriptionResponse' in generated
    assert 'class GeneratedCustomerPortalSessionResponse' in generated
    assert 'class GeneratedPaymentStatusMessageResponse' in generated
    assert 'class GeneratedPaymentSubscriptionResponse' in generated
    assert 'final String? defaultValue;' in generated
    assert 'defaultValue: _readString(_readAny(json, const ["default"]))' in generated
    assert "'default': defaultValue" in generated
    assert 'nextBillingDate: _readInt(_readAny(json, const ["next_billing_date"]))' in generated


def test_memories_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'memories')

    assert MEMORIES_DART_PATH.read_text() == generated
    assert 'class GeneratedEvidence' in generated
    assert 'class GeneratedMemoryDB' in generated
    assert 'layer: _required(_readString(_readAny(json, const ["layer"])), "layer")' in generated
    assert 'memoryTier: _readString(_readAny(json, const ["memory_tier"])) ?? "long_term"' in generated
    assert (
        'captureDeviceIds: _readAny(json, const ["capture_device_ids"]) == null ? null : _readStringList' in generated
    )


def test_goals_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'goals')

    assert GOALS_DART_PATH.read_text() == generated
    assert 'class GeneratedGoalResponse' in generated
    assert 'class GeneratedGoalSuggestionResponse' in generated
    assert 'class GeneratedAdviceResponse' in generated
    assert 'class GeneratedGoalHistoryEntryResponse' in generated
    assert 'class GeneratedGoalDeleteResponse' in generated
    assert 'goalType: _readString(_readAny(json, const ["goal_type"])) ?? "scale"' in generated
    assert 'suggestedMax: _readDouble(_readAny(json, const ["suggested_max"])) ?? 10' in generated


def test_conversation_wire_dart_preserves_known_client_aliases():
    generated = GENERATED_DART_PATH.read_text()

    assert 'const ["action_items", "actionItems"]' in generated
    assert 'const ["start", "startsAt"]' in generated
    assert 'const ["app_id", "appId"]' in generated
    assert 'const ["google_place_id", "googlePlaceId"]' in generated
    assert "'apps_results': appsResults" in generated
    assert "'plugins_results': pluginsResults" in generated
    assert (
        'appsResults: _readObjectList(_readAny(json, const ["apps_results"]), GeneratedAppResult.fromJson) ?? const []'
        in generated
    )
    assert 'category: _readString(_readAny(json, const ["category"])) ?? "other"' in generated
    assert 'source: _readString(_readAny(json, const ["source"])) ?? "omi"' in generated
    assert 'visibility: _readString(_readAny(json, const ["visibility"])) ?? "private"' in generated
    assert 'DateTime.fromMillisecondsSinceEpoch(value * 1000).toLocal()' in generated
    assert 'final List<GeneratedTranslation>? translations;' in generated
    assert 'translations: _readAny(json, const ["translations"]) == null ? null : _readObjectList' in generated
    assert 'List<T>? _readObjectList<T>' in generated
    assert 'if (value is! List) return null;' in generated


def test_conversation_fixtures_validate_against_python_schema_authority():
    fixtures = json.loads(CONVERSATION_FIXTURE_PATH.read_text())

    for name, payload in fixtures.items():
        conversation = Conversation.model_validate(payload)
        assert conversation.id, name
        assert conversation.structured is not None, name
