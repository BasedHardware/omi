from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts import inventory_app_client_schemas

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'


def test_inventory_separates_generated_backed_adapters_from_raw_manual_dtos():
    report = inventory_app_client_schemas.build_report(SPEC_PATH)

    generated_backed_paths = {item['path'] for item in report['generated_backed_adapter_files']}
    remaining_manual_paths = {item['path'] for item in report['remaining_manual_dart_json_schema_files']}
    local_non_rest_paths = {item['path'] for item in report['local_non_rest_schema_files']}
    unmodeled_operations = {
        (item['method'], item['path'], item['operation_id']) for item in report['app_used_unmodeled_success_responses']
    }
    all_unmodeled_operations = {
        (item['method'], item['path'], item['operation_id']) for item in report['unmodeled_success_responses']
    }

    assert 'app/lib/backend/schema/conversation.dart' in generated_backed_paths
    # action_item.dart was fully migrated to typedefs (no fromJson/toJson), so it's
    # correctly absent from manual_files entirely — neither generated_backed nor remaining.
    assert 'app/lib/backend/schema/folder.dart' in generated_backed_paths
    assert 'app/lib/backend/http/api/apps.dart' in generated_backed_paths
    assert 'app/lib/backend/http/api/users.dart' in generated_backed_paths
    assert 'app/lib/backend/schema/action_item.dart' not in remaining_manual_paths
    assert 'app/lib/backend/schema/folder.dart' not in remaining_manual_paths
    assert 'app/lib/backend/schema/bt_device/bt_device.dart' in local_non_rest_paths
    assert (
        'POST',
        '/v1/conversations/search',
        'search_conversations_endpoint_v1_conversations_search_post',
    ) not in unmodeled_operations
    assert ('GET', '/v1/app-categories', 'get_app_categories_v1_app_categories_get') not in unmodeled_operations
    assert ('POST', '/v1/app/generate', 'generate_app_endpoint_v1_app_generate_post') not in unmodeled_operations
    assert ('GET', '/v2/apps', 'get_apps_v2_v2_apps_get') not in unmodeled_operations
    assert (
        'GET',
        '/v1/apps/{app_id}/reviews',
        'app_reviews_v1_apps__app_id__reviews_get',
    ) not in all_unmodeled_operations
    assert ('GET', '/v2/apps/search', 'search_apps_v2_apps_search_get') not in unmodeled_operations
    assert (
        'DELETE',
        '/v1/import/limitless/conversations',
        'delete_limitless_conversations_v1_import_limitless_conversations_delete',
    ) not in unmodeled_operations
    assert (
        'PUT',
        '/v1/integrations/apple-health/sync',
        'sync_apple_health_data_v1_integrations_apple_health_sync_put',
    ) not in unmodeled_operations
    assert (
        'DELETE',
        '/v1/knowledge-graph',
        'delete_knowledge_graph_v1_knowledge_graph_delete',
    ) not in unmodeled_operations
    assert ('POST', '/v1/users/fcm-token', 'save_token_v1_users_fcm_token_post') not in unmodeled_operations
    assert ('GET', '/v1/fair-use/status', 'get_my_fair_use_status_v1_fair_use_status_get') not in unmodeled_operations
    assert (
        'GET',
        '/v1/users/daily-summaries',
        'get_daily_summaries_v1_users_daily_summaries_get',
    ) not in unmodeled_operations
    assert (
        'DELETE',
        '/v1/users/delete-account',
        'delete_account_v1_users_delete_account_delete',
    ) not in unmodeled_operations
    assert (
        'GET',
        '/v1/users/developer/webhooks/status',
        'get_user_webhooks_status_v1_users_developer_webhooks_status_get',
    ) not in unmodeled_operations
    assert (
        'GET',
        '/v1/users/migration/requests',
        'get_migration_requests_v1_users_migration_requests_get',
    ) not in unmodeled_operations
    assert (
        'POST',
        '/v1/users/migration/batch-requests',
        'handle_batch_migration_requests_v1_users_migration_batch_requests_post',
    ) not in unmodeled_operations
    assert (
        'POST',
        '/v1/users/migration/requests',
        'handle_migration_requests_v1_users_migration_requests_post',
    ) not in unmodeled_operations
    assert (
        'POST',
        '/v1/users/migration/requests/data-protection-level/finalize',
        'finalize_migration_request_v1_users_migration_requests_data_protection_level_finalize_post',
    ) not in unmodeled_operations
    assert (
        'PUT',
        '/v1/users/preferences/app',
        'set_preferred_app_for_user_v1_users_preferences_app_put',
    ) not in unmodeled_operations
    assert ('GET', '/v1/users/profile', 'get_user_profile_endpoint_v1_users_profile_get') not in unmodeled_operations
    assert ('GET', '/v2/firmware/latest', 'get_latest_version_v2_firmware_latest_get') not in unmodeled_operations
    assert ('GET', '/v2/firmware/stable', 'get_stable_version_v2_firmware_stable_get') not in unmodeled_operations
    assert ('GET', '/v3/speech-profile', 'has_speech_profile_v3_speech_profile_get') not in unmodeled_operations
    assert (
        'DELETE',
        '/v3/speech-profile/expand',
        'delete_extra_speech_profile_sample_v3_speech_profile_expand_delete',
    ) not in unmodeled_operations
    assert (
        'GET',
        '/v3/speech-profile/expand',
        'get_extra_speech_profile_samples_v3_speech_profile_expand_get',
    ) not in unmodeled_operations
    assert ('POST', '/v3/upload-audio', 'upload_profile_v3_upload_audio_post') not in unmodeled_operations
    assert ('GET', '/v4/speech-profile', 'get_speech_profile_v4_speech_profile_get') not in unmodeled_operations
    assert (
        'GET',
        '/v1/users/store-recording-permission',
        'get_store_recording_permission_v1_users_store_recording_permission_get',
    ) not in unmodeled_operations
    assert ('GET', '/v1/users/language', 'get_user_language_v1_users_language_get') not in unmodeled_operations
    assert ('GET', '/v1/users/export', 'export_all_user_data_v1_users_export_get') not in unmodeled_operations
    assert ('POST', '/v2/sync-local-files', 'sync_local_files_v2_v2_sync_local_files_post') not in unmodeled_operations
    assert (
        'POST',
        '/v2/messages/{message_id}/report',
        'report_message_v2_messages__message_id__report_post',
    ) not in unmodeled_operations
    assert ('POST', '/v2/tts/synthesize', 'tts_synthesize_v2_tts_synthesize_post') not in unmodeled_operations
    assert (
        'POST',
        '/v2/voice-message/transcribe',
        'transcribe_voice_message_v2_voice_message_transcribe_post',
    ) not in unmodeled_operations
    assert (
        'POST',
        '/v2/voice-messages',
        'create_voice_message_stream_v2_voice_messages_post',
    ) not in unmodeled_operations
    assert report['unmodeled_success_response_count'] == 0
    assert report['app_used_unmodeled_success_response_count'] == 0
    assert report['remaining_manual_dart_json_schema_file_count'] == 0
    assert report['unmodeled_success_response_count'] == len(report['unmodeled_success_responses'])
    assert report['app_used_unmodeled_success_response_count'] == len(report['app_used_unmodeled_success_responses'])
    assert report['app_operation_manifest_count'] == len(report['app_operation_manifest'])
    message_routes = {
        (item['path'], item['http_method'], item['normalized_route']): item for item in report['app_operation_manifest']
    }
    message_report_route = message_routes[
        ('app/lib/backend/http/api/messages.dart', 'POST', '/v2/messages/{param}/report')
    ]
    assert any(
        operation['operation_id'] == 'report_message_v2_messages__message_id__report_post'
        and operation['response_schema'] == 'MessageReportResponse'
        for operation in message_report_route['operations']
    )
    assert message_report_route['http_method'] == 'POST'
    assert message_report_route['function_name'] == 'reportMessageServer'
    assert message_report_route['raw_decode_scope'] == 'enclosing_function_and_called_helpers'
    assert message_report_route['raw_decode_site_count'] == 0
    assert message_report_route['raw_response_decode_site_count'] == 0
    message_send_route = message_routes[('app/lib/backend/http/api/messages.dart', 'POST', '/v2/messages')]
    assert message_send_route['http_method'] == 'POST'
    assert message_send_route['function_name'] == 'sendMessageStreamServer'
    assert any(item['function_name'] == 'parseMessageChunk' for item in message_send_route['called_function_ranges'])
    assert message_send_route['raw_decode_site_count'] == 0
    assert message_send_route['generated_backed_decode_site_count'] > 0
    assert report['manual_dart_json_schema_file_count'] == (
        report['generated_backed_adapter_file_count'] + report['remaining_manual_dart_json_schema_file_count']
    )
    assert report['raw_dart_decode_site_count'] > 0

    assert any(
        item['path'] == 'app/lib/backend/schema/app.dart'
        and item['kind'] == 'field_access'
        and 'updated_at' in item['snippet']
        for item in report['raw_dart_decode_sites']
    )
    assert any(
        item['path'] == 'app/lib/backend/schema/conversation.dart'
        and item['kind'] == 'fromJson'
        and 'ConversationExternalData.fromJson' in item['snippet']
        for item in report['raw_dart_decode_sites']
    )
    assert any(
        item['path'] == 'app/lib/backend/http/api/apps.dart' and item['kind'] in {'jsonDecode', 'field_access', 'cast'}
        for item in report['raw_dart_decode_sites']
    )


def test_inventory_normalizes_interpolated_dart_route_segments():
    routes = inventory_app_client_schemas.scan_app_routes()
    routes_by_file = {}
    for route in routes:
        routes_by_file.setdefault(route.path.name, set()).add(route.normalized_route)

    assert '/v2/messages/{param}/report' in routes_by_file['messages.dart']
    assert '/v1/apps/{param}' in routes_by_file['apps.dart']
    assert '/v1/conversations/{param}/reprocess' in routes_by_file['conversations.dart']


def test_inventory_scopes_record_return_type_route_functions():
    routes = inventory_app_client_schemas.scan_app_routes()
    route = next(
        item
        for item in routes
        if item.path.name == 'apps.dart'
        and item.normalized_route == '/v2/apps/capability/{param}/grouped'
        and item.http_method == 'GET'
    )

    assert route.function_name == 'retrieveCapabilityAppsGroupedByCategory'
    assert route.function_start_line is not None
    assert route.function_end_line is not None


def test_inventory_ignores_static_base_url_field_routes():
    routes = [
        route
        for route in inventory_app_client_schemas.scan_app_routes()
        if route.path.name == 'knowledge_graph_api.dart' and route.normalized_route == '/v1/knowledge-graph'
    ]

    assert routes
    assert all(route.function_name is not None for route in routes)


def test_inventory_route_parser_handles_comments_queries_and_nested_interpolation():
    source = """
// '${Env.apiBaseUrl}v1/commented'
/* '${Env.apiBaseUrl}v1/block-commented' */
final app = '${Env.apiBaseUrl}v1/apps/${appData['id']}?tab=$tab';
final reprocess = '${Env.apiBaseUrl}v1/conversations/$conversationId/reprocess${appId != null ? '?app_id=$appId' : ''}';
final onlyBase = _baseUrl;
"""
    masked = inventory_app_client_schemas._mask_dart_comments(source)

    assert inventory_app_client_schemas._scan_marker_routes(
        masked,
        'Env.apiBaseUrl',
        must_start_with='v',
    ) == [
        "v1/apps/${appData['id']}?tab=$tab",
        "v1/conversations/$conversationId/reprocess${appId != null ? '?app_id=$appId' : ''}",
    ]
    assert inventory_app_client_schemas._scan_marker_routes(masked, '_baseUrl', must_start_with='/') == []
    assert inventory_app_client_schemas.normalize_app_route("v1/apps/${appData['id']}?tab=$tab") == '/v1/apps/{param}'
    assert (
        inventory_app_client_schemas.normalize_app_route(
            "v1/conversations/$conversationId/reprocess${appId != null ? '?app_id=$appId' : ''}"
        )
        == '/v1/conversations/{param}/reprocess'
    )


def test_inventory_strict_raw_decode_site_gate_fails_with_actionable_sites():
    result = subprocess.run(
        [
            sys.executable,
            'scripts/inventory_app_client_schemas.py',
            '--fail-on-raw-dart-decode-sites',
        ],
        cwd=ROOT_DIR / 'backend',
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert 'Raw Dart decode sites:' in result.stdout
    assert 'app/lib/backend/schema/app.dart:31' in result.stdout


def test_inventory_openapi_route_response_decode_migration_complete():
    report = inventory_app_client_schemas.build_report(SPEC_PATH)
    response_violations = [item for item in report['app_operation_manifest'] if item['raw_response_decode_site_count']]
    assert not response_violations


def test_inventory_route_raw_decode_gate_checks_total_decode_sites_for_targeted_routes():
    clean_result = subprocess.run(
        [
            sys.executable,
            'scripts/inventory_app_client_schemas.py',
            '--fail-on-raw-json-decode-for-openapi-routes',
            '--operation-id',
            'update_transcription_preferences_endpoint_v1_users_transcription_preferences_patch',
        ],
        cwd=ROOT_DIR / 'backend',
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    assert clean_result.returncode == 0

    dirty_result = subprocess.run(
        [
            sys.executable,
            'scripts/inventory_app_client_schemas.py',
            '--fail-on-raw-json-decode-for-openapi-routes',
            '--operation-id',
            'suggest_goal_v1_goals_suggest_get',
        ],
        cwd=ROOT_DIR / 'backend',
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    assert dirty_result.returncode == 1
    assert 'suggestGoal' in dirty_result.stdout


def test_inventory_route_raw_decode_gate_can_target_operation_ids():
    clean_result = subprocess.run(
        [
            sys.executable,
            'scripts/inventory_app_client_schemas.py',
            '--fail-on-raw-json-decode-for-openapi-routes',
            '--operation-id',
            'send_message_v2_messages_post',
        ],
        cwd=ROOT_DIR / 'backend',
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    formerly_dirty_result = subprocess.run(
        [
            sys.executable,
            'scripts/inventory_app_client_schemas.py',
            '--fail-on-raw-json-decode-for-openapi-routes',
            '--operation-id',
            'get_user_enabled_apps_v1_apps_enabled_get',
        ],
        cwd=ROOT_DIR / 'backend',
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    assert clean_result.returncode == 0
    assert formerly_dirty_result.returncode == 0
    assert 'getApps' not in clean_result.stdout
    assert 'OpenAPI route functions with raw Dart decode sites:' not in formerly_dirty_result.stdout
