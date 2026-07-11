#!/usr/bin/env python3
"""Generate Dart wire DTOs from the app-client OpenAPI contract."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
DEFAULT_OUTPUT_DIR = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen'

SCHEMA_GROUPS = {
    'conversation': {
        'output': DEFAULT_OUTPUT_DIR / 'conversation_wire.g.dart',
        'schemas': (
            'Translation',
            'TranscriptSegment',
            'ActionItem',
            'AppResult',
            'PluginResult',
            'Event',
            'Structured',
            'Geolocation',
            'ConversationPhoto',
            'AudioFile',
            'ConversationAudioSpan',
            'ConversationAudio',
            'CalendarEventLink',
            'Conversation',
            'ConversationTestPromptResponse',
            'MergeConversationsResponse',
            'SearchConversationsResponse',
            'SyncLocalFilesResultResponse',
            'SyncJobStartResponse',
            'SyncJobStatusResponse',
            'SyncCaptureManifestFile',
            'SyncCaptureManifestRequest',
            'SyncCaptureManifestResponse',
        ),
    },
    'messages': {
        'output': DEFAULT_OUTPUT_DIR / 'messages_wire.g.dart',
        'schemas': (
            'MessageConversationStructured',
            'MessageConversation',
            'FileChat',
            'ChartDataPoint',
            'ChartDataset',
            'ChartData',
            'Message',
            'ResponseMessage',
            'MessageReportResponse',
            'VoiceMessageTranscriptionResponse',
        ),
    },
    'action_items_folders': {
        'output': DEFAULT_OUTPUT_DIR / 'action_items_folders_wire.g.dart',
        'schemas': (
            'EvidenceRef',
            'ActionItemResponse',
            'ActionItemCreateRequest',
            'ActionItemUpdateRequest',
            'ActionItemsResponse',
            'ActionItemsCountResponse',
            'ActionItemsSearchResponse',
            'PendingSyncResponse',
            'BatchMutationResponse',
            'BatchDeleteActionItemsResponse',
            'BatchCreateActionItemsResponse',
            'ShareActionItemsResponse',
            'SharedActionItemPreview',
            'SharedActionItemsResponse',
            'AcceptSharedActionItemsResponse',
            'Folder',
            'FolderMutationResponse',
            'BulkMoveConversationsResponse',
        ),
    },
    'task_intelligence': {
        'output': DEFAULT_OUTPUT_DIR / 'task_intelligence_wire.g.dart',
        'schemas': (
            'EvidenceRef',
            'ActionItemResponse',
            'TaskCreatePayload',
            'TaskChangePayload',
            'GoalMetric',
            'CandidateRecord',
            'CandidateListResponse',
            'CandidateResolutionReceipt',
            'CandidateCreate',
            'TaskCreateCandidate',
            'TaskUpdateCandidate',
            'TaskCompleteCandidate',
            'TaskCancelCandidate',
            'TaskSupersedeCandidate',
            'CandidateResolutionRequest',
            'WorkstreamProposal',
            'WorkstreamProposal-Output',
            'GoalResponse',
            'GoalUpdate',
            'GoalDetailProjection',
            'GoalProgressEvent',
            'Workstream',
            'WorkstreamCreateCandidate',
            'WorkstreamUpdate',
            'WorkstreamDetailProjection',
            'WorkstreamEvent',
            'WorkstreamEventCreate',
            'ArtifactDescriptor',
            'ArtifactDescriptorCreate',
            'ArtifactStatusTransitionRequest',
            'ContinuationCheckpoint',
            'ContinuationCheckpointUpsert',
            'WhatMattersNowProjection',
            'EvaluationRequest',
            'FeedbackCreate',
            'FeedbackRecord',
            'InterventionCreate',
            'InterventionRecord',
            'OutcomeCreate',
            'OutcomeRecord',
            'NormalizedContextSnapshot',
            'OpenLoopSnapshot',
            'SnapshotReceipt',
            'DecisionDebugProjection',
            'Recommendation',
            'RecommendationSubjectKind',
            'DeterministicFacts',
            'ShortlistEligibility',
            'DecisionRecord',
            'ContextMatchSignal',
            'FeedbackSubjectKind',
            'InterventionSurface',
            'NormalizedContextMatch',
            'OpenLoopDescriptor',
            'OpenLoopKind',
            'OpenLoopStatus',
            'TaskIntelligenceFeedbackAction',
            'TaskIntelligenceFeedbackReason',
            'TaskIntelligenceOutcomeCode',
        ),
    },
    'api_keys': {
        'output': DEFAULT_OUTPUT_DIR / 'api_keys_wire.g.dart',
        'schemas': (
            'DevApiKey',
            'DevApiKeyCreated',
            'McpApiKey',
            'McpApiKeyCreated',
        ),
    },
    'agent': {
        'output': DEFAULT_OUTPUT_DIR / 'agent_wire.g.dart',
        'schemas': (
            'AgentVmInfo',
            'AgentKeepaliveResponse',
        ),
    },
    'phone_calls': {
        'output': DEFAULT_OUTPUT_DIR / 'phone_calls_wire.g.dart',
        'schemas': (
            'VerifyPhoneNumberResponse',
            'CheckVerificationResponse',
            'PhoneNumberResponse',
            'PhoneNumbersResponse',
            'PhoneMutationResponse',
            'TokenResponse',
        ),
    },
    'people': {
        'output': DEFAULT_OUTPUT_DIR / 'people_wire.g.dart',
        'schemas': ('Person',),
    },
    'imports_integrations': {
        'output': DEFAULT_OUTPUT_DIR / 'imports_integrations_wire.g.dart',
        'schemas': (
            'ImportJobResponse',
            'IntegrationResponse',
            'OAuthUrlResponse',
            'DeleteLimitlessConversationsResponse',
            'AppleHealthSyncResponse',
        ),
    },
    'device_speech': {
        'output': DEFAULT_OUTPUT_DIR / 'device_speech_wire.g.dart',
        'schemas': (
            'FirmwareVersionResponse',
            'HasSpeechProfileResponse',
            'SpeechProfileResponse',
            'SpeechProfileUploadResponse',
            'SpeechProfileMutationResponse',
        ),
        'operation_wrappers': (
            (
                'ExpandedSpeechProfileSamplesResponse',
                'get_extra_speech_profile_samples_v3_speech_profile_expand_get',
                'items',
            ),
        ),
    },
    'misc': {
        'output': DEFAULT_OUTPUT_DIR / 'misc_wire.g.dart',
        'schemas': (
            'FcmTokenResponse',
            'DeleteKnowledgeGraphResponse',
            'KnowledgeGraphResponse',
            'RebuildResponse',
            'ErrorResponse',
        ),
    },
    'wrapped_task_integrations': {
        'output': DEFAULT_OUTPUT_DIR / 'wrapped_task_integrations_wire.g.dart',
        'schemas': (
            'WrappedStatusResponse',
            'GenerateWrappedResponse',
            'TaskIntegrationsResponse',
            'OAuthUrlResponse',
            'CreateTaskResponse',
            'DefaultTaskIntegrationResponse',
            'AsanaWorkspacesResponse',
            'AsanaProjectsResponse',
            'ClickUpTeamsResponse',
            'ClickUpSpacesResponse',
            'ClickUpListsResponse',
        ),
    },
    'apps': {
        'output': DEFAULT_OUTPUT_DIR / 'apps_wire.g.dart',
        'schemas': (
            'AppSelectOption',
            'AppCapabilityAction',
            'AppCapabilityResponse',
            'AppThumbnailUploadResponse',
            'AppMutationResponse',
            'AppCreateResponse',
            'AppMigrationResponse',
            'McpAddServerResponse',
            'AppDescriptionGenerationResponse',
            'AppDescriptionEmojiGenerationResponse',
            'AppPromptsGenerationResponse',
            'AppDraftGenerationResponse',
            'AppGenerationResponse',
            'AppIconGenerationResponse',
            'AppReview',
            'AuthStep',
            'Action',
            'ExternalIntegration',
            'ProactiveNotification',
            'ChatTool',
            'AppBaseModel',
            'AppCatalogItem',
            'App',
            'AppPaginationLinks',
            'AppPagination',
            'AppCatalogGroup',
            'AppCatalogMeta',
            'AppCatalogResponse',
            'AppSearchFilters',
            'AppSearchResponse',
            'ConversationSuggestedAppsResponse',
            'AppApiKeyResponse',
        ),
        'operation_wrappers': (
            (
                'EnabledAppsResponse',
                'get_user_enabled_apps_v1_apps_enabled_get',
                'items',
            ),
        ),
    },
    'users': {
        'output': DEFAULT_OUTPUT_DIR / 'users_wire.g.dart',
        'schemas': (
            'UserStatusResponse',
            'UserWebhooksStatusResponse',
            'StoreRecordingPermissionResponse',
            'PrivateCloudSyncResponse',
            'OnboardingStateResponse',
            'UserLanguageResponse',
            'UserLanguageUpdateResponse',
            'MemorySummaryRatingResponse',
            'TrainingDataOptInResponse',
            'TranscriptionPreferencesResponse',
            'TranscriptionPreferencesUpdate',
            'UserWebhookUrlResponse',
            'DailySummarySettingsResponse',
            'DailySummaryTestResponse',
            'MentorNotificationSettingsResponse',
            'DailySummaryActionItem',
            'DailySummaryTopicHighlight',
            'DailySummaryUnresolvedQuestion',
            'DailySummaryDecisionMade',
            'DailySummaryKnowledgeNugget',
            'DailySummaryDayStats',
            'DailySummaryLocationPin',
            'DailySummaryResponse',
            'DailySummariesResponse',
            'FairUseDailyGenerationsBudgetResponse',
            'FairUseLimitsResponse',
            'FairUseUsagePctResponse',
            'FairUseStatusResponse',
        ),
    },
    'subscription_usage': {
        'output': DEFAULT_OUTPUT_DIR / 'subscription_usage_wire.g.dart',
        'schemas': (
            'PlanLimits',
            'Subscription',
            'PricingOption',
            'SubscriptionPlan',
            'PhoneCallQuota',
            'UserSubscriptionResponse',
            'UsageStats',
            'UsageHistoryPoint',
            'UserUsageResponse',
        ),
    },
    'privacy': {
        'output': DEFAULT_OUTPUT_DIR / 'privacy_wire.g.dart',
        'schemas': (
            'MigrationRequest',
            'BatchMigrationRequest',
            'MigrationTargetRequest',
            'MigrationStatusResponse',
            'MigrationRequestsResponse',
            'UserProfileResponse',
        ),
    },
    'announcements': {
        'output': DEFAULT_OUTPUT_DIR / 'announcements_wire.g.dart',
        'schemas': (
            'Targeting',
            'Display',
            'Announcement',
        ),
    },
    'audio': {
        'output': DEFAULT_OUTPUT_DIR / 'audio_wire.g.dart',
        'schemas': (
            'AudioPrecacheResponse',
            'AudioFileUrlInfo',
            'ConversationAudioSpanInfo',
            'ConversationAudioUrlInfo',
            'AudioUrlsResponse',
        ),
    },
    'payments': {
        'output': DEFAULT_OUTPUT_DIR / 'payments_wire.g.dart',
        'schemas': (
            'PaymentMutationResponse',
            'StripeConnectAccountResponse',
            'StripeOnboardingStatusResponse',
            'StripeSupportedCountryResponse',
            'PayPalPaymentDetailsResponse',
            'PaymentMethodStatusResponse',
            'PaymentSubscriptionResponse',
            'PaymentStatusMessageResponse',
            'PaymentCheckoutSessionResponse',
            'PaymentUpgradeSubscriptionResponse',
            'CustomerPortalSessionResponse',
            'PlanLimits',
            'routers__payment__PricingOption',
            'AvailablePlansResponse',
            'AppSubscriptionDetails',
            'AppSubscriptionResponse',
            'AppSubscriptionCancelResponse',
        ),
    },
    'memories': {
        'output': DEFAULT_OUTPUT_DIR / 'memories_wire.g.dart',
        'schemas': (
            'Evidence',
            'MemoryDB',
        ),
    },
    'goals': {
        'output': DEFAULT_OUTPUT_DIR / 'goals_wire.g.dart',
        'schemas': (
            'GoalMetric',
            'GoalResponse',
            'GoalSuggestionResponse',
            'AdviceResponse',
            'GoalHistoryEntryResponse',
            'GoalDeleteResponse',
        ),
    },
}
ALIASES = {
    'Structured': {'action_items': ('actionItems',)},
    'Event': {'start': ('startsAt',)},
    'AppResult': {'app_id': ('appId',)},
    'Geolocation': {'google_place_id': ('googlePlaceId',), 'location_type': ('locationType',)},
}
DART_FIELD_NAME_OVERRIDES = {
    'default': 'defaultValue',
}
DART_CLASS_NAME_OVERRIDES = {
    'routers__payment__PricingOption': 'PaymentPricingOption',
}
PRESENCE_AWARE_PATCH_SCHEMAS = {
    'ActionItemUpdateRequest',
    'GoalUpdate',
    'WorkstreamUpdate',
}


@dataclass(frozen=True)
class DartType:
    name: str
    nullable: bool = False
    list_item: 'DartType | None' = None
    ref_schema: str | None = None
    is_date_time: bool = False
    is_map: bool = False
    is_dynamic: bool = False
    is_string_wrapper: bool = False

    @property
    def annotation(self) -> str:
        suffix = '?' if self.nullable else ''
        return f'{self.name}{suffix}'


@dataclass(frozen=True)
class Field:
    wire_name: str
    dart_name: str
    dart_type: DartType
    required: bool
    default: Any
    aliases: tuple[str, ...]


def snake_to_camel(value: str) -> str:
    parts = value.split('_')
    return parts[0] + ''.join(part[:1].upper() + part[1:] for part in parts[1:])


def dart_field_name(wire_name: str) -> str:
    name = snake_to_camel(wire_name)
    return DART_FIELD_NAME_OVERRIDES.get(name, name)


def generated_class_name(schema_name: str) -> str:
    raw_name = DART_CLASS_NAME_OVERRIDES.get(schema_name, schema_name)
    return f"Generated{re.sub(r'[^A-Za-z0-9_]', '', raw_name)}"


def unwrap_nullable(schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    any_of = schema.get('anyOf')
    if not isinstance(any_of, list):
        return schema, False
    non_null = [item for item in any_of if item.get('type') != 'null']
    if len(non_null) == 1 and len(non_null) != len(any_of):
        return non_null[0], True
    return schema, False


def schema_debug_name(schema: dict[str, Any]) -> str:
    title = schema.get('title')
    if isinstance(title, str) and title:
        return title
    ref = schema.get('$ref')
    if isinstance(ref, str):
        return ref.rsplit('/', 1)[-1]
    return json.dumps(schema, sort_keys=True)[:200]


def is_untyped_object_schema(schema: dict[str, Any]) -> bool:
    return schema.get('type') == 'object' or schema.get('additionalProperties') is not None


def dart_type_for(
    schema: dict[str, Any],
    required: bool,
    target_schemas: tuple[str, ...],
    all_schemas: dict[str, Any],
) -> DartType:
    if 'oneOf' in schema or 'allOf' in schema:
        raise ValueError(f'unsupported composed schema: {schema_debug_name(schema)}')
    any_of = schema.get('anyOf')
    if isinstance(any_of, list):
        non_null = [item for item in any_of if item.get('type') != 'null']
        ref_names = {item['$ref'].rsplit('/', 1)[-1] for item in non_null if item.get('$ref')}
        if ref_names == {'TaskCreatePayload', 'TaskChangePayload'}:
            nullable = any(item.get('type') == 'null' for item in any_of) or not required
            return DartType(
                'GeneratedCandidateTaskChange',
                nullable=nullable,
                ref_schema='CandidateTaskChange',
            )
        if len(non_null) == 1 and len(non_null) != len(any_of):
            unwrapped = non_null[0]
            nullable = True
        elif (
            len(non_null) == 2
            and any(item.get('$ref') for item in non_null)
            and any(is_untyped_object_schema(item) and not item.get('properties') for item in non_null)
        ):
            nullable = any(item.get('type') == 'null' for item in any_of) or not required
            return DartType('Map<String, dynamic>', nullable=nullable, is_map=True)
        elif non_null and all(
            item.get('$ref') and all_schemas.get(item['$ref'].rsplit('/', 1)[-1], {}).get('type') == 'object'
            for item in non_null
        ):
            nullable = any(item.get('type') == 'null' for item in any_of) or not required
            return DartType('Map<String, dynamic>', nullable=nullable, is_map=True)
        elif any(item.get('type') in {'array', 'object'} for item in non_null) and all(
            item.get('type') in {'array', 'boolean', 'integer', 'number', 'object', 'string'} for item in non_null
        ):
            nullable = any(item.get('type') == 'null' for item in any_of) or not required
            return DartType('dynamic', nullable=nullable, is_dynamic=True)
        else:
            raise ValueError(f'unsupported anyOf schema: {schema_debug_name(schema)}')
    else:
        unwrapped, nullable = unwrap_nullable(schema)
    nullable = nullable or not required
    ref = unwrapped.get('$ref')
    if isinstance(ref, str):
        schema_name = ref.rsplit('/', 1)[-1]
        if schema_name in target_schemas:
            ref_schema = all_schemas.get(schema_name, {})
            return DartType(
                generated_class_name(schema_name),
                nullable=nullable,
                ref_schema=schema_name,
                is_string_wrapper=ref_schema.get('type') == 'string',
            )
        ref_schema = all_schemas.get(schema_name, {})
        if ref_schema.get('type') == 'string':
            return DartType('String', nullable=nullable)
        raise ValueError(f'$ref target {schema_name} is not in selected Dart schema group')

    schema_type = unwrapped.get('type')
    if unwrapped.get('format') == 'date-time':
        return DartType('DateTime', nullable=nullable, is_date_time=True)
    if schema_type == 'array':
        item_type = dart_type_for(unwrapped.get('items', {'type': 'object'}), True, target_schemas, all_schemas)
        return DartType(f'List<{item_type.name}>', nullable=nullable, list_item=item_type)
    if schema_type == 'integer':
        return DartType('int', nullable=nullable)
    if schema_type == 'number':
        return DartType('double', nullable=nullable)
    if schema_type == 'boolean':
        return DartType('bool', nullable=nullable)
    if schema_type == 'object' or unwrapped.get('additionalProperties') is not None:
        return DartType('Map<String, dynamic>', nullable=nullable, is_map=True)
    if schema_type == 'string' or 'enum' in unwrapped or 'const' in unwrapped:
        return DartType('String', nullable=nullable)
    raise ValueError(f'unsupported schema shape: {schema_debug_name(schema)}')


def default_for(field: Field) -> str:
    if field.dart_type.ref_schema and isinstance(field.default, dict):
        return f'{field.dart_type.name}.fromJson(const {{}})'
    if field.default is not None:
        return dart_literal(field.default)
    if field.dart_type.list_item:
        return 'null' if field.dart_type.nullable else 'const []'
    if field.dart_type.name == 'String' and not field.dart_type.nullable:
        return "''"
    if field.dart_type.name == 'int' and not field.dart_type.nullable:
        return '0'
    if field.dart_type.name == 'double' and not field.dart_type.nullable:
        return '0.0'
    if field.dart_type.name == 'bool' and not field.dart_type.nullable:
        return 'false'
    if field.dart_type.is_date_time and not field.dart_type.nullable:
        return 'DateTime.fromMillisecondsSinceEpoch(0)'
    if field.dart_type.ref_schema and not field.dart_type.nullable:
        if field.dart_type.ref_schema == 'Structured':
            return 'GeneratedStructured.fromJson(const {})'
    return 'null'


def dart_literal(value: Any) -> str:
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if value is None:
        return 'null'
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return 'const []'
    return str(value)


def read_key_expr(field: Field) -> str:
    names = (field.wire_name,) + field.aliases
    quoted = ', '.join(json.dumps(name) for name in names)
    return f'_readField(json, const [{quoted}])'


def converter_name(typ: DartType) -> str:
    if typ.list_item:
        item = typ.list_item
        if item.ref_schema:
            if item.is_string_wrapper:
                return f'(value) => _readValueList(value, {item.name}.fromJson)'
            return f'(value) => _readObjectList(value, {item.name}.fromJson)'
        if item.is_date_time:
            return '_readDateTimeList'
        if item.name == 'String':
            return '_readStringList'
        if item.name == 'double':
            return '_readDoubleList'
        if item.name == 'int':
            return '_readIntList'
        if item.is_map:
            return '_readMapList'
        return '_readDynamicList'
    if typ.ref_schema:
        if typ.is_string_wrapper:
            return f'{typ.name}.fromJson'
        return f'(value) => _readObject(value, {typ.name}.fromJson)'
    if typ.is_date_time:
        return '_readDateTime'
    if typ.is_map:
        return '_readMap'
    if typ.name == 'String':
        return '_readString'
    if typ.name == 'int':
        return '_readInt'
    if typ.name == 'double':
        return '_readDouble'
    if typ.name == 'bool':
        return '_readBool'
    return '(value) => value'


def read_value_expr(field: Field) -> str:
    default = ''
    if field.default is not None:
        default = f', defaultValue: {default_for(field)}'
    return (
        f'_readFieldValue<{field.dart_type.name}>('
        f'{read_key_expr(field)}, '
        f'{json.dumps(field.wire_name)}, '
        f'{converter_name(field.dart_type)}, '
        f'requiredField: {str(field.required).lower()}, '
        f'nullable: {str(field.dart_type.nullable).lower()}'
        f'{default})'
    )


def read_expr(field: Field) -> str:
    typ = field.dart_type
    expr = read_value_expr(field)
    if typ.nullable:
        return expr
    return f'_required({expr}, {json.dumps(field.wire_name)})'


def constructor_default_for(field: Field) -> str | None:
    if field.required or field.default is None:
        return None
    if field.dart_type.ref_schema and isinstance(field.default, dict):
        return None
    return default_for(field)


def to_json_expr(field: Field) -> str:
    name = field.dart_name
    typ = field.dart_type
    if typ.list_item:
        item = typ.list_item
        if item.ref_schema:
            mapper = '(value) => value.toJson()'
        elif item.is_date_time:
            # DateTime is not JSON-native; encode each element as an ISO-8601 string.
            mapper = '(value) => value.toUtc().toIso8601String()'
        else:
            # Primitives, maps, and dynamic values are JSON-native and pass through unchanged.
            return name
        access = f'{name}?' if typ.nullable else name
        return f'{access}.map({mapper}).toList()'
    if typ.ref_schema:
        return f'{name}?.toJson()' if typ.nullable else f'{name}.toJson()'
    if typ.is_date_time:
        return f'{name}?.toUtc().toIso8601String()' if typ.nullable else f'{name}.toUtc().toIso8601String()'
    return name


def fields_for_schema(
    schema_name: str,
    schema: dict[str, Any],
    target_schemas: tuple[str, ...],
    all_schemas: dict[str, Any],
) -> list[Field]:
    required = set(schema.get('required', []))
    fields: list[Field] = []
    for wire_name, prop_schema in schema.get('properties', {}).items():
        is_required = wire_name in required
        is_non_null_default = prop_schema.get('default') is not None
        fields.append(
            Field(
                wire_name=wire_name,
                dart_name=dart_field_name(wire_name),
                dart_type=dart_type_for(prop_schema, is_required or is_non_null_default, target_schemas, all_schemas),
                required=is_required,
                default=prop_schema.get('default'),
                aliases=ALIASES.get(schema_name, {}).get(wire_name, ()),
            )
        )
    return fields


def emit_class(schema_name: str, fields: list[Field], *, emit_list_factory: bool = False) -> str:
    class_name = generated_class_name(schema_name)
    lines = [f'class {class_name} {{']
    for field in fields:
        lines.append(f'  final {field.dart_type.annotation} {field.dart_name};')
    lines.append('')
    initializers: list[str] = []
    constructor_is_const = True
    for field in fields:
        if field.required:
            continue
        if field.default is None:
            continue
        if constructor_default_for(field) is None:
            initializers.append(f'{field.dart_name} = {field.dart_name} ?? {default_for(field)}')
            constructor_is_const = False

    const_prefix = 'const ' if constructor_is_const else ''
    lines.append(f'  {const_prefix}{class_name}({{')
    for field in fields:
        required = 'required ' if field.required else ''
        default = ''
        if not required:
            constructor_default = constructor_default_for(field)
            if constructor_default is not None:
                default = f' = {constructor_default}'
        if initializers and field.dart_name in {item.split(' = ', 1)[0] for item in initializers}:
            lines.append(f'    {field.dart_type.name}? {field.dart_name},')
        else:
            lines.append(f'    {required}this.{field.dart_name}{default},')
    if initializers:
        lines.append('  }) :')
        for index, initializer in enumerate(initializers):
            suffix = ';' if index == len(initializers) - 1 else ','
            lines.append(f'       {initializer}{suffix}')
    else:
        lines.append('  });')
    lines.append('')
    lines.append(f'  factory {class_name}.fromJson(Map<String, dynamic> json) {{')
    lines.append(f'    return {class_name}(')
    for field in fields:
        if schema_name == 'CandidateRecord' and field.wire_name == 'task_change':
            lines.append('      taskChange: GeneratedCandidateTaskChange.fromCandidateJson(json),')
        else:
            lines.append(f'      {field.dart_name}: {read_expr(field)},')
    lines.append('    );')
    lines.append('  }')
    if emit_list_factory and len(fields) == 1 and fields[0].dart_type.list_item:
        field = fields[0]
        lines.append('')
        lines.append(f'  factory {class_name}.fromJsonList(List<dynamic> json) {{')
        lines.append(f'    return {class_name}(')
        lines.append(
            f'      {field.dart_name}: _required({converter_name(field.dart_type)}(json), {json.dumps(field.wire_name)}),'
        )
        lines.append('    );')
        lines.append('  }')
    lines.append('')
    lines.append('  Map<String, dynamic> toJson() {')
    lines.append('    return {')
    for field in fields:
        lines.append(f"      '{field.wire_name}': {to_json_expr(field)},")
    lines.append('    };')
    lines.append('  }')
    lines.append('}')
    return '\n'.join(lines)


def emit_string_wrapper(schema_name: str, schema: dict[str, Any]) -> str:
    class_name = generated_class_name(schema_name)
    values = [value for value in schema.get('enum', []) if isinstance(value, str)]
    lines = [f'class {class_name} {{', '  final String value;', '', f'  const {class_name}._(this.value);']
    for value in values:
        constant = dart_field_name(re.sub(r'[^A-Za-z0-9_]', '_', value))
        lines.append(f'  static const {constant} = {class_name}._({json.dumps(value)});')
    lines.extend(
        [
            '',
            f'  factory {class_name}.fromJson(dynamic value) {{',
            '    if (value is! String) {',
            f"      throw const FormatException('Invalid {schema_name}: expected string');",
            '    }',
        ]
    )
    if values:
        lines.extend(
            [
                '    switch (value) {',
                *[
                    f'      case {json.dumps(value)}: return {constant_name};'
                    for value, constant_name in (
                        (value, dart_field_name(re.sub(r'[^A-Za-z0-9_]', '_', value))) for value in values
                    )
                ],
                '      default:',
                f"        throw FormatException('Invalid {schema_name}: $value');",
                '    }',
            ]
        )
    else:
        lines.append(f'    return {class_name}._(value);')
    lines.extend(
        [
            '  }',
            '',
            '  String toJson() => value;',
            '',
            '  @override',
            '  bool operator ==(Object other) =>',
            f'      identical(this, other) || other is {class_name} && other.value == value;',
            '',
            '  @override',
            '  int get hashCode => value.hashCode;',
            '',
            '  @override',
            '  String toString() => value;',
            '}',
        ]
    )
    return '\n'.join(lines)


def emit_candidate_task_change() -> str:
    return '''class GeneratedCandidateTaskChange {
  final GeneratedTaskCreatePayload? create;
  final GeneratedTaskChangePayload? change;

  const GeneratedCandidateTaskChange.create(GeneratedTaskCreatePayload value)
      : create = value,
        change = null;
  const GeneratedCandidateTaskChange.change(GeneratedTaskChangePayload value)
      : create = null,
        change = value;

  static GeneratedCandidateTaskChange? fromCandidateJson(Map<String, dynamic> json) {
    final value = _readMap(json['task_change']);
    if (value == null) return null;
    final action = _readString(json['proposed_action']);
    final subjectKind = _readString(json['subject_kind']);
    if (action == 'create' && subjectKind == 'task') {
      return GeneratedCandidateTaskChange.create(GeneratedTaskCreatePayload.fromJson(value));
    }
    if (const {'update', 'complete', 'cancel', 'supersede'}.contains(action)) {
      return GeneratedCandidateTaskChange.change(GeneratedTaskChangePayload.fromJson(value));
    }
    return null;
  }

  Map<String, dynamic> toJson() => create?.toJson() ?? change?.toJson() ?? const {};
}'''


def emit_candidate_create() -> str:
    return '''class GeneratedCandidateCreate {
  final GeneratedTaskCreateCandidate? taskCreate;
  final GeneratedTaskUpdateCandidate? taskUpdate;
  final GeneratedTaskCompleteCandidate? taskComplete;
  final GeneratedTaskCancelCandidate? taskCancel;
  final GeneratedTaskSupersedeCandidate? taskSupersede;
  final GeneratedWorkstreamCreateCandidate? workstreamCreate;

  const GeneratedCandidateCreate.taskCreate(GeneratedTaskCreateCandidate value)
      : taskCreate = value, taskUpdate = null, taskComplete = null, taskCancel = null,
        taskSupersede = null, workstreamCreate = null;
  const GeneratedCandidateCreate.taskUpdate(GeneratedTaskUpdateCandidate value)
      : taskCreate = null, taskUpdate = value, taskComplete = null, taskCancel = null,
        taskSupersede = null, workstreamCreate = null;
  const GeneratedCandidateCreate.taskComplete(GeneratedTaskCompleteCandidate value)
      : taskCreate = null, taskUpdate = null, taskComplete = value, taskCancel = null,
        taskSupersede = null, workstreamCreate = null;
  const GeneratedCandidateCreate.taskCancel(GeneratedTaskCancelCandidate value)
      : taskCreate = null, taskUpdate = null, taskComplete = null, taskCancel = value,
        taskSupersede = null, workstreamCreate = null;
  const GeneratedCandidateCreate.taskSupersede(GeneratedTaskSupersedeCandidate value)
      : taskCreate = null, taskUpdate = null, taskComplete = null, taskCancel = null,
        taskSupersede = value, workstreamCreate = null;
  const GeneratedCandidateCreate.workstreamCreate(GeneratedWorkstreamCreateCandidate value)
      : taskCreate = null, taskUpdate = null, taskComplete = null, taskCancel = null,
        taskSupersede = null, workstreamCreate = value;

  factory GeneratedCandidateCreate.fromJson(Map<String, dynamic> json) {
    final subjectKind = _readString(json['subject_kind']);
    final action = _readString(json['proposed_action']);
    if (subjectKind == 'task') {
      switch (action) {
        case 'create': return GeneratedCandidateCreate.taskCreate(GeneratedTaskCreateCandidate.fromJson(json));
        case 'update': return GeneratedCandidateCreate.taskUpdate(GeneratedTaskUpdateCandidate.fromJson(json));
        case 'complete': return GeneratedCandidateCreate.taskComplete(GeneratedTaskCompleteCandidate.fromJson(json));
        case 'cancel': return GeneratedCandidateCreate.taskCancel(GeneratedTaskCancelCandidate.fromJson(json));
        case 'supersede': return GeneratedCandidateCreate.taskSupersede(GeneratedTaskSupersedeCandidate.fromJson(json));
      }
    }
    if (subjectKind == 'workstream' && action == 'create') {
      return GeneratedCandidateCreate.workstreamCreate(GeneratedWorkstreamCreateCandidate.fromJson(json));
    }
    throw FormatException('Unsupported Candidate discriminator: $subjectKind/$action');
  }

  Map<String, dynamic> toJson() =>
      taskCreate?.toJson() ?? taskUpdate?.toJson() ?? taskComplete?.toJson() ??
      taskCancel?.toJson() ?? taskSupersede?.toJson() ?? workstreamCreate?.toJson() ?? const {};
}'''


def emit_patch_field() -> str:
    return '''class GeneratedPatchField<T> {
  final bool isPresent;
  final T? value;

  const GeneratedPatchField.omitted() : isPresent = false, value = null;
  const GeneratedPatchField.value(this.value) : isPresent = true;
}'''


def emit_patch_reader() -> str:
    return '''GeneratedPatchField<T> _readPatchField<T>(
  Map<String, dynamic> json,
  String name,
  T? Function(dynamic) converter,
) {
  if (!json.containsKey(name)) return const GeneratedPatchField.omitted();
  final raw = json[name];
  if (raw == null) return const GeneratedPatchField.value(null);
  final value = converter(raw);
  if (value == null) throw FormatException('Invalid field: $name');
  return GeneratedPatchField.value(value);
}'''


def patch_to_json_expr(field: Field) -> str:
    value = f'{field.dart_name}.value'
    typ = field.dart_type
    if typ.list_item:
        item = typ.list_item
        if item.ref_schema:
            return f'{value}?.map((value) => value.toJson()).toList()'
        if item.is_date_time:
            return f'{value}?.map((value) => value.toUtc().toIso8601String()).toList()'
        return value
    if typ.ref_schema:
        return f'{value}?.toJson()'
    if typ.is_date_time:
        return f'{value}?.toUtc().toIso8601String()'
    return value


def emit_patch_class(schema_name: str, fields: list[Field]) -> str:
    class_name = generated_class_name(schema_name)
    lines = [f'class {class_name} {{']
    for field in fields:
        lines.append(f'  final GeneratedPatchField<{field.dart_type.name}> {field.dart_name};')
    lines.append('')
    lines.append(f'  const {class_name}({{')
    for field in fields:
        lines.append(f'    this.{field.dart_name} = const GeneratedPatchField.omitted(),')
    lines.append('  });')
    lines.append('')
    lines.append(f'  factory {class_name}.fromJson(Map<String, dynamic> json) {{')
    lines.append(f'    return {class_name}(')
    for field in fields:
        lines.append(
            f'      {field.dart_name}: _readPatchField<{field.dart_type.name}>('
            f'json, {json.dumps(field.wire_name)}, {converter_name(field.dart_type)}),'
        )
    lines.append('    );')
    lines.append('  }')
    lines.append('')
    lines.append('  Map<String, dynamic> toJson() {')
    lines.append('    final json = <String, dynamic>{};')
    for field in fields:
        lines.append(f'    if ({field.dart_name}.isPresent) {{')
        lines.append(f"      json['{field.wire_name}'] = {patch_to_json_expr(field)};")
        lines.append('    }')
    lines.append('    return json;')
    lines.append('  }')
    lines.append('}')
    return '\n'.join(lines)


def emit_helpers(*, include_value_list: bool = False) -> str:
    helpers = r'''
class _WireField {
  final bool present;
  final dynamic value;

  const _WireField(this.present, this.value);
}

_WireField _readField(Map<String, dynamic> json, List<String> names) {
  for (final name in names) {
    if (json.containsKey(name)) return _WireField(true, json[name]);
  }
  return const _WireField(false, null);
}

String? _readString(dynamic value) => value is String ? value : null;

int? _readInt(dynamic value) {
  if (value is int) return value;
  if (value is String) return int.tryParse(value);
  return null;
}

double? _readDouble(dynamic value) {
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value);
  return null;
}

bool? _readBool(dynamic value) {
  if (value is bool) return value;
  return null;
}

T _required<T>(T? value, String name) {
  if (value == null) {
    throw FormatException('Missing required field: $name');
  }
  return value;
}

T? _readFieldValue<T>(
  _WireField field,
  String name,
  T? Function(dynamic) read, {
  required bool requiredField,
  required bool nullable,
  T? defaultValue,
}) {
  if (!field.present) {
    if (requiredField) {
      throw FormatException('Missing required field: $name');
    }
    return defaultValue;
  }
  if (field.value == null) {
    if (nullable) return null;
    throw FormatException('Null field: $name');
  }
  final value = read(field.value);
  if (value == null) {
    throw FormatException('Invalid field: $name');
  }
  return value;
}

DateTime? _readDateTime(dynamic value) {
  if (value == null) return null;
  if (value is String) return DateTime.tryParse(value)?.toLocal();
  return null;
}

List<DateTime>? _readDateTimeList(dynamic value) {
  if (value is! List) return null;
  return [
    for (final item in value) _required(_readDateTime(item), 'list item')
  ];
}

Map<String, dynamic>? _readMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return null;
}

T? _readObject<T>(dynamic value, T Function(Map<String, dynamic>) fromJson) {
  final map = _readMap(value);
  return map == null ? null : fromJson(map);
}

List<T>? _readObjectList<T>(dynamic value, T Function(Map<String, dynamic>) fromJson) {
  if (value is! List) return null;
  return [
    for (final item in value) fromJson(_required(_readMap(item), 'list item'))
  ];
}

List<String>? _readStringList(dynamic value) {
  if (value is! List) return null;
  return [
    for (final item in value) _required(_readString(item), 'list item')
  ];
}

List<double>? _readDoubleList(dynamic value) {
  if (value is! List) return null;
  return [
    for (final item in value) _required(_readDouble(item), 'list item')
  ];
}

List<int>? _readIntList(dynamic value) {
  if (value is! List) return null;
  return [
    for (final item in value) _required(_readInt(item), 'list item')
  ];
}

List<Map<String, dynamic>>? _readMapList(dynamic value) {
  if (value is! List) return null;
  return [
    for (final item in value) _required(_readMap(item), 'list item')
  ];
}

List<dynamic>? _readDynamicList(dynamic value) => value is List ? value : null;
'''.strip()
    if include_value_list:
        value_list = '''List<T>? _readValueList<T>(dynamic value, T Function(dynamic) fromJson) {
  if (value is! List) return null;
  return [for (final item in value) fromJson(item)];
}'''
        anchor = '\n\nList<String>? _readStringList'
        helpers = helpers.replace(anchor, f'\n\n{value_list}{anchor}')
    return helpers


def response_schema_for_operation(spec: dict[str, Any], operation_id: str) -> dict[str, Any]:
    for methods in spec.get('paths', {}).values():
        for operation in methods.values():
            if not isinstance(operation, dict) or operation.get('operationId') != operation_id:
                continue
            schema = (
                operation.get('responses', {})
                .get('200', {})
                .get('content', {})
                .get('application/json', {})
                .get('schema')
            )
            if not isinstance(schema, dict):
                raise ValueError(f'operation {operation_id} does not have an object response schema')
            return schema
    raise ValueError(f'operation not found in OpenAPI spec: {operation_id}')


def operation_wrapper_schemas(spec: dict[str, Any], group: str) -> dict[str, dict[str, Any]]:
    wrappers: dict[str, dict[str, Any]] = {}
    for schema_name, operation_id, field_name in SCHEMA_GROUPS[group].get('operation_wrappers', ()):
        wrappers[schema_name] = {
            'type': 'object',
            'required': [field_name],
            'properties': {
                field_name: response_schema_for_operation(spec, operation_id),
            },
        }
    return wrappers


def build_output(spec: dict[str, Any], group: str = 'conversation') -> str:
    if group not in SCHEMA_GROUPS:
        raise ValueError(f'unknown Dart generation group: {group}')
    wrapper_schemas = operation_wrapper_schemas(spec, group)
    wrapper_schema_names = set(wrapper_schemas)
    target_schemas = (*SCHEMA_GROUPS[group]['schemas'], *wrapper_schemas)
    schemas = spec.get('components', {}).get('schemas', {})
    schemas = {**schemas, **wrapper_schemas}
    missing = [name for name in SCHEMA_GROUPS[group]['schemas'] if name not in schemas]
    if missing:
        raise ValueError('missing OpenAPI schemas: ' + ', '.join(missing))

    chunks = [
        '// GENERATED CODE - DO NOT EDIT.',
        '// ignore_for_file: unused_element',
        f'// Generated by backend/scripts/generate_dart_models.py --group {group} from docs/api-reference/app-client-openapi.json.',
        '',
    ]
    if group in {'action_items_folders', 'task_intelligence'}:
        chunks.extend([emit_patch_field(), ''])
    if group == 'task_intelligence':
        chunks.extend([emit_candidate_task_change(), ''])
    for schema_name in target_schemas:
        if schema_name == 'CandidateCreate':
            chunks.extend([emit_candidate_create(), ''])
            continue
        if schema_name in PRESENCE_AWARE_PATCH_SCHEMAS:
            chunks.extend(
                [
                    emit_patch_class(
                        schema_name,
                        fields_for_schema(schema_name, schemas[schema_name], target_schemas, schemas),
                    ),
                    '',
                ]
            )
            continue
        if schemas[schema_name].get('type') == 'string':
            chunks.extend([emit_string_wrapper(schema_name, schemas[schema_name]), ''])
            continue
        chunks.append(
            emit_class(
                schema_name,
                fields_for_schema(schema_name, schemas[schema_name], target_schemas, schemas),
                emit_list_factory=schema_name in wrapper_schema_names,
            )
        )
        chunks.append('')
    if group in {'action_items_folders', 'task_intelligence'}:
        chunks.extend([emit_patch_reader(), ''])
    chunks.append(
        emit_helpers(include_value_list=any(schemas[name].get('type') == 'string' for name in target_schemas))
    )
    chunks.append('')
    return '\n'.join(chunks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate Dart app-client wire DTOs.')
    parser.add_argument('--spec', default=str(DEFAULT_SPEC_PATH), help='app-client OpenAPI spec path')
    parser.add_argument(
        '--group',
        choices=tuple(SCHEMA_GROUPS),
        default='conversation',
        help='schema group to generate',
    )
    parser.add_argument('--all', action='store_true', help='generate or check every schema group')
    parser.add_argument('--output', default=None, help='Dart output path; defaults to the selected group output')
    parser.add_argument('--check', action='store_true', help='fail if generated output is stale')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.all and args.output:
        raise SystemExit('--output cannot be used with --all')

    spec = json.loads(Path(args.spec).read_text())
    groups = tuple(SCHEMA_GROUPS) if args.all else (args.group,)
    for group in groups:
        output_path = Path(args.output) if args.output else SCHEMA_GROUPS[group]['output']
        generated = build_output(spec, group)
        if args.check:
            if not output_path.exists() or output_path.read_text() != generated:
                raise SystemExit(f'{output_path} is stale; run backend/scripts/generate_dart_models.py --group {group}')
            print(f'{output_path} is up to date')
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generated)
        print(f'wrote {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
