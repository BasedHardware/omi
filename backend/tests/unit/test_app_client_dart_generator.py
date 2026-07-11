from __future__ import annotations

import json
from pathlib import Path

from models.conversation import Conversation
from scripts import generate_dart_models

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
GENERATED_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'conversation_wire.g.dart'
MESSAGES_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'messages_wire.g.dart'
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
DEVICE_SPEECH_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'device_speech_wire.g.dart'
MISC_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'misc_wire.g.dart'
WRAPPED_TASK_INTEGRATIONS_DART_PATH = (
    ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'wrapped_task_integrations_wire.g.dart'
)
APPS_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'apps_wire.g.dart'
USERS_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'users_wire.g.dart'
SUBSCRIPTION_USAGE_DART_PATH = (
    ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'subscription_usage_wire.g.dart'
)
PRIVACY_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'privacy_wire.g.dart'
ANNOUNCEMENTS_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'announcements_wire.g.dart'
AUDIO_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'audio_wire.g.dart'
PAYMENTS_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'payments_wire.g.dart'
MEMORIES_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'memories_wire.g.dart'
GOALS_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'goals_wire.g.dart'
TASK_INTELLIGENCE_DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'task_intelligence_wire.g.dart'
CONVERSATION_FIXTURE_PATH = ROOT_DIR / 'backend' / 'testing' / 'e2e' / 'fixtures' / 'conversations.json'


def test_conversation_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'conversation')

    assert GENERATED_DART_PATH.read_text() == generated
    for schema_name in generate_dart_models.SCHEMA_GROUPS['conversation']['schemas']:
        assert f'class Generated{schema_name}' in generated
    assert 'items: _required(_readFieldValue<List<GeneratedConversation>>' in generated
    assert 'class GeneratedSyncJobStartResponse' in generated
    assert 'class GeneratedSyncJobStatusResponse' in generated
    assert 'result: _readFieldValue<GeneratedSyncLocalFilesResultResponse>' in generated


def test_messages_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'messages')

    assert MESSAGES_DART_PATH.read_text() == generated
    assert 'class GeneratedMessage' in generated
    assert 'class GeneratedResponseMessage' in generated
    assert 'class GeneratedMessageReportResponse' in generated
    assert 'class GeneratedFileChat' in generated
    assert 'class GeneratedChartData' in generated
    assert 'class GeneratedVoiceMessageTranscriptionResponse' in generated
    assert 'final Map<String, dynamic>? chartData;' in generated
    assert 'chartData: _readFieldValue<Map<String, dynamic>>' in generated
    assert 'this.askForNps = false' in generated
    assert 'this.files = const []' in generated
    assert 'transcript: _required(_readFieldValue<String>' in generated


def test_message_adapter_preserves_arbitrary_chart_data_union_payloads():
    adapter = (ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'message.dart').read_text()

    assert 'Map<String, dynamic>? rawChartData;' in adapter
    assert "const requiredKeys = {'chart_type', 'title', 'datasets'};" in adapter
    assert "return (chartType == 'line' || chartType == 'bar') && requiredKeys.every(json.containsKey);" in adapter
    assert 'static ServerMessage fromResponseJson(Map<String, dynamic> json)' in adapter
    assert 'wire.GeneratedResponseMessage.fromJson(json)' in adapter
    assert 'askForNps: generated.askForNps ?? false' in adapter
    assert 'final parsedChartData = chartData ?? ChartData.tryFromJson(rawChartData);' in adapter
    assert 'rawChartData: rawChartData' in adapter
    assert 'final chartJson = rawChartData ?? chartData?.toJson();' in adapter
    assert "'chart_data': chartJson" in adapter


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
    assert 'this.exported = false' in generated
    assert 'this.color = "#6B7280"' in generated
    assert 'deletedIds: _required(_readFieldValue<List<String>>' in generated


def test_action_items_adapter_uses_generated_envelope_defaults():
    adapter = (ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'action_item.dart').read_text()

    # Phase 4.1 collapsed the hand-written wrappers into typedefs over the
    # generated wire types, so JSON encode/decode is provided by GeneratedX.
    assert 'typedef ActionItemsResponse = wire.GeneratedActionItemsResponse' in adapter
    assert 'typedef PendingSyncResponse = wire.GeneratedPendingSyncResponse' in adapter
    assert 'typedef ActionItemWithMetadata = wire.GeneratedActionItemResponse' in adapter


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
    assert 'createdAt: _required(_readFieldValue<DateTime>' in generated


def test_agent_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'agent')

    assert AGENT_DART_PATH.read_text() == generated
    assert 'class GeneratedAgentVmInfo' in generated
    assert 'class GeneratedAgentKeepaliveResponse' in generated
    assert 'hasVm: _required(_readFieldValue<bool>' in generated


def test_phone_calls_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'phone_calls')

    assert PHONE_CALLS_DART_PATH.read_text() == generated
    assert 'class GeneratedPhoneNumberResponse' in generated
    assert 'class GeneratedPhoneNumbersResponse' in generated
    assert 'class GeneratedTokenResponse' in generated
    assert 'accessToken: _required(_readFieldValue<String>' in generated


def test_people_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'people')

    assert PEOPLE_DART_PATH.read_text() == generated
    assert 'class GeneratedPerson' in generated
    assert 'this.speechSamplesVersion = 3' in generated


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
    assert 'class GeneratedOAuthUrlResponse' in generated
    assert 'class GeneratedDeleteLimitlessConversationsResponse' in generated
    assert 'class GeneratedAppleHealthSyncResponse' in generated
    assert 'jobId: _required(_readFieldValue<String>' in generated
    assert 'connected: _required(_readFieldValue<bool>' in generated
    assert 'deletedCount: _required(_readFieldValue<int>' in generated


def test_device_speech_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'device_speech')

    assert DEVICE_SPEECH_DART_PATH.read_text() == generated
    assert 'class GeneratedFirmwareVersionResponse' in generated
    assert 'class GeneratedHasSpeechProfileResponse' in generated
    assert 'class GeneratedSpeechProfileResponse' in generated
    assert 'class GeneratedSpeechProfileUploadResponse' in generated
    assert 'class GeneratedSpeechProfileMutationResponse' in generated
    assert 'class GeneratedExpandedSpeechProfileSamplesResponse' in generated
    assert 'factory GeneratedExpandedSpeechProfileSamplesResponse.fromJsonList' in generated
    assert 'this.isLegacySecureDfu = true' in generated
    assert 'hasProfile: _required(_readFieldValue<bool>' in generated


def test_misc_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'misc')

    assert MISC_DART_PATH.read_text() == generated
    assert 'class GeneratedFcmTokenResponse' in generated
    assert 'class GeneratedDeleteKnowledgeGraphResponse' in generated
    assert 'class GeneratedKnowledgeGraphResponse' in generated
    assert 'class GeneratedRebuildResponse' in generated
    assert 'class GeneratedErrorResponse' in generated
    assert 'status: _required(_readFieldValue<String>' in generated
    assert 'detail: _required(_readFieldValue<dynamic>' in generated


def test_wrapped_task_integrations_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'wrapped_task_integrations')

    assert WRAPPED_TASK_INTEGRATIONS_DART_PATH.read_text() == generated
    assert 'class GeneratedWrappedStatusResponse' in generated
    assert 'class GeneratedGenerateWrappedResponse' in generated
    assert 'class GeneratedTaskIntegrationsResponse' in generated
    assert 'class GeneratedOAuthUrlResponse' in generated
    assert 'class GeneratedCreateTaskResponse' in generated
    assert 'class GeneratedDefaultTaskIntegrationResponse' in generated
    assert 'class GeneratedAsanaWorkspacesResponse' in generated
    assert 'class GeneratedAsanaProjectsResponse' in generated
    assert 'class GeneratedClickUpTeamsResponse' in generated
    assert 'class GeneratedClickUpSpacesResponse' in generated
    assert 'class GeneratedClickUpListsResponse' in generated
    assert 'status: _required(_readFieldValue<String>' in generated
    assert 'integrations: _required(_readFieldValue<Map<String, dynamic>>' in generated
    assert 'workspaces: _readFieldValue<List<Map<String, dynamic>>' in generated
    assert 'List<Map<String, dynamic>>? _readMapList(dynamic value)' in generated


def test_apps_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'apps')

    assert APPS_DART_PATH.read_text() == generated
    assert 'class GeneratedAppSelectOption' in generated
    assert 'class GeneratedAppCapabilityResponse' in generated
    assert 'class GeneratedAppThumbnailUploadResponse' in generated
    assert 'class GeneratedAppMutationResponse' in generated
    assert 'class GeneratedAppCreateResponse' in generated
    assert 'class GeneratedAppMigrationResponse' in generated
    assert 'class GeneratedMcpAddServerResponse' in generated
    assert 'class GeneratedAppDescriptionGenerationResponse' in generated
    assert 'class GeneratedAppDescriptionEmojiGenerationResponse' in generated
    assert 'class GeneratedAppPromptsGenerationResponse' in generated
    assert 'class GeneratedAppGenerationResponse' in generated
    assert 'class GeneratedAppIconGenerationResponse' in generated
    assert 'class GeneratedAppReview' in generated
    assert 'class GeneratedAppBaseModel' in generated
    assert 'class GeneratedApp' in generated
    assert 'class GeneratedAppCatalogResponse' in generated
    assert 'class GeneratedAppSearchResponse' in generated
    assert 'class GeneratedConversationSuggestedAppsResponse' in generated
    assert 'class GeneratedEnabledAppsResponse' in generated
    assert 'factory GeneratedEnabledAppsResponse.fromJsonList' in generated
    assert 'class GeneratedAppApiKeyResponse' in generated
    assert 'id: _required(_readFieldValue<String>' in generated
    assert 'app: _required(_readFieldValue<GeneratedAppDraftGenerationResponse>' in generated
    assert 'requiresOauth: _required(_readFieldValue<bool>' in generated
    assert 'data: _readFieldValue<List<GeneratedAppCatalogItem>>' in generated
    assert 'createdAt: _readFieldValue<DateTime>' in generated


def test_users_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'users')

    assert USERS_DART_PATH.read_text() == generated
    assert 'class GeneratedUserStatusResponse' in generated
    assert 'class GeneratedUserWebhooksStatusResponse' in generated
    assert 'class GeneratedStoreRecordingPermissionResponse' in generated
    assert 'class GeneratedPrivateCloudSyncResponse' in generated
    assert 'class GeneratedOnboardingStateResponse' in generated
    assert 'class GeneratedUserLanguageResponse' in generated
    assert 'class GeneratedUserLanguageUpdateResponse' in generated
    assert 'class GeneratedMemorySummaryRatingResponse' in generated
    assert 'class GeneratedTrainingDataOptInResponse' in generated
    assert 'class GeneratedTranscriptionPreferencesResponse' in generated
    assert 'class GeneratedUserWebhookUrlResponse' in generated
    assert 'class GeneratedDailySummarySettingsResponse' in generated
    assert 'class GeneratedDailySummaryTestResponse' in generated
    assert 'class GeneratedMentorNotificationSettingsResponse' in generated
    assert 'class GeneratedDailySummaryResponse' in generated
    assert 'class GeneratedDailySummariesResponse' in generated
    assert 'class GeneratedDailySummaryDayStats' in generated
    assert 'class GeneratedFairUseStatusResponse' in generated
    assert 'class GeneratedFairUseLimitsResponse' in generated
    assert 'class GeneratedFairUseUsagePctResponse' in generated
    assert 'storeRecordingPermission: _required(_readFieldValue<bool>' in generated
    assert 'summaryId: _required(_readFieldValue<String>' in generated
    assert 'summaries: _readFieldValue<List<GeneratedDailySummaryResponse>>' in generated
    assert 'createdAt: _readFieldValue<DateTime>' in generated
    assert 'audioBytes: _required(_readFieldValue<bool>' in generated
    assert 'limits: _required(_readFieldValue<GeneratedFairUseLimitsResponse>' in generated


def test_subscription_usage_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'subscription_usage')

    assert SUBSCRIPTION_USAGE_DART_PATH.read_text() == generated
    assert 'class GeneratedUserSubscriptionResponse' in generated
    assert 'class GeneratedUserUsageResponse' in generated
    assert 'final List<String> features;' in generated
    assert 'GeneratedPlanLimits? limits,' in generated
    assert 'GeneratedPlanLimits.fromJson(const {})' in generated
    assert 'this.transcriptionSeconds = 0' in generated


def test_privacy_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'privacy')

    assert PRIVACY_DART_PATH.read_text() == generated
    assert 'class GeneratedMigrationRequest' in generated
    assert 'class GeneratedBatchMigrationRequest' in generated
    assert 'class GeneratedMigrationTargetRequest' in generated
    assert 'class GeneratedMigrationStatusResponse' in generated
    assert 'class GeneratedMigrationRequestsResponse' in generated
    assert 'class GeneratedUserProfileResponse' in generated
    assert 'targetLevel: _required(_readFieldValue<String>' in generated
    assert 'needsMigration: _readFieldValue<List<Map<String, dynamic>>' in generated
    assert 'migrationStatus: _readFieldValue<Map<String, dynamic>>' in generated


def test_announcements_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'announcements')

    assert ANNOUNCEMENTS_DART_PATH.read_text() == generated
    assert 'class GeneratedTargeting' in generated
    assert 'class GeneratedDisplay' in generated
    assert 'class GeneratedAnnouncement' in generated
    assert 'createdAt: _required(_readFieldValue<DateTime>' in generated
    assert 'this.trigger = "version_upgrade"' in generated
    assert 'deviceModels: _readFieldValue<List<String>>' in generated


def test_audio_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'audio')

    assert AUDIO_DART_PATH.read_text() == generated
    assert 'class GeneratedAudioPrecacheResponse' in generated
    assert 'class GeneratedAudioFileUrlInfo' in generated
    assert 'class GeneratedAudioUrlsResponse' in generated
    assert 'this.duration = 0' in generated
    assert 'audioFiles: _required(_readFieldValue<List<GeneratedAudioFileUrlInfo>>' in generated
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
    assert 'class GeneratedAvailablePlansResponse' in generated
    assert 'class GeneratedAppSubscriptionResponse' in generated
    assert 'class GeneratedAppSubscriptionCancelResponse' in generated
    assert 'final String? defaultValue;' in generated
    assert 'defaultValue: _readFieldValue<String>' in generated
    assert "'default': defaultValue" in generated
    assert 'nextBillingDate: _readFieldValue<int>' in generated


def test_memories_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'memories')

    assert MEMORIES_DART_PATH.read_text() == generated
    assert 'class GeneratedEvidence' in generated
    assert 'class GeneratedMemoryDB' in generated
    assert 'final String? layer;' in generated
    assert 'final String? memoryTier;' in generated
    assert 'layer: _readFieldValue<String>' in generated
    assert 'captureDeviceIds: _readFieldValue<List<String>>' in generated


def test_goals_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'goals')

    assert GOALS_DART_PATH.read_text() == generated
    assert 'class GeneratedGoalResponse' in generated
    assert 'class GeneratedGoalSuggestionResponse' in generated
    assert 'class GeneratedAdviceResponse' in generated
    assert 'class GeneratedGoalHistoryEntryResponse' in generated
    assert 'class GeneratedGoalDeleteResponse' in generated
    assert 'goalType: _required(_readFieldValue<String>' in generated
    assert 'this.suggestedMax = 10' in generated


def test_task_intelligence_wire_dart_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_dart_models.build_output(spec, 'task_intelligence')

    assert TASK_INTELLIGENCE_DART_PATH.read_text() == generated
    for name in (
        'GeneratedCandidateRecord',
        'GeneratedGoalDetailProjection',
        'GeneratedWorkstreamDetailProjection',
        'GeneratedArtifactDescriptor',
        'GeneratedContinuationCheckpoint',
    ):
        assert f'class {name}' in generated
    assert 'final List<GeneratedEvidenceRef>? provenance;' in generated
    assert 'final GeneratedWorkstreamProposalOutput? workstreamProposal;' in generated
    assert 'final GeneratedCandidateTaskChange? taskChange;' in generated
    assert 'GeneratedCandidateTaskChange.fromCandidateJson(json)' in generated
    assert 'class GeneratedCandidateCreate {' in generated
    assert 'GeneratedCandidateCreate.taskSupersede' in generated
    assert 'class GeneratedGoalUpdate {' in generated
    assert 'final GeneratedPatchField<String> desiredOutcome;' in generated
    assert 'final GeneratedPatchField<DateTime> nextReviewAt;' in generated
    assert 'class GeneratedContextMatchSignal {' in generated
    assert 'static const dependency = GeneratedContextMatchSignal._("dependency");' in generated
    assert 'factory GeneratedContextMatchSignal.fromJson(dynamic value)' in generated
    assert '_readValueList(value, GeneratedContextMatchSignal.fromJson)' in generated
    action_items_generated = ACTION_ITEMS_FOLDERS_DART_PATH.read_text()
    assert 'class GeneratedActionItemCreateRequest' in action_items_generated
    assert 'class GeneratedActionItemUpdateRequest' in action_items_generated
    assert 'final GeneratedPatchField<String> goalId;' in action_items_generated
    assert 'if (goalId.isPresent) {' in action_items_generated


def test_conversation_wire_dart_preserves_known_client_aliases():
    generated = GENERATED_DART_PATH.read_text()

    assert 'const ["action_items", "actionItems"]' in generated
    assert 'const ["start", "startsAt"]' in generated
    assert 'const ["app_id", "appId"]' in generated
    assert 'const ["google_place_id", "googlePlaceId"]' in generated
    assert "'apps_results': appsResults" in generated
    assert "'plugins_results': pluginsResults" in generated
    assert 'appsResults: _required(_readFieldValue<List<GeneratedAppResult>>' in generated
    assert 'this.category = "other"' in generated
    assert 'source: _readFieldValue<String>' in generated
    assert 'defaultValue: "omi"' in generated
    assert 'this.visibility = "private"' in generated
    assert 'if (value is String) return DateTime.tryParse(value)?.toLocal();' in generated
    assert 'final List<GeneratedTranslation>? translations;' in generated
    assert 'translations: _readFieldValue<List<GeneratedTranslation>>' in generated
    assert 'List<T>? _readObjectList<T>' in generated
    assert "for (final item in value) fromJson(_required(_readMap(item), 'list item'))" in generated


def test_generator_rejects_unsupported_schema_shapes_without_string_fallback():
    spec = {
        'components': {
            'schemas': {
                'UnsupportedUnion': {
                    'type': 'object',
                    'properties': {
                        'value': {
                            'anyOf': [
                                {'type': 'string'},
                                {'type': 'integer'},
                                {'type': 'null'},
                            ]
                        }
                    },
                }
            }
        }
    }

    original = generate_dart_models.SCHEMA_GROUPS['messages']
    generate_dart_models.SCHEMA_GROUPS['messages'] = {
        **original,
        'schemas': ('UnsupportedUnion',),
    }
    try:
        try:
            generate_dart_models.build_output(spec, 'messages')
        except ValueError as exc:
            assert 'unsupported anyOf schema' in str(exc)
        else:
            raise AssertionError('expected unsupported anyOf to fail generation')
    finally:
        generate_dart_models.SCHEMA_GROUPS['messages'] = original


def test_conversation_fixtures_validate_against_python_schema_authority():
    fixtures = json.loads(CONVERSATION_FIXTURE_PATH.read_text())

    for name, payload in fixtures.items():
        conversation = Conversation.model_validate(payload)
        assert conversation.id, name
        assert conversation.structured is not None, name
