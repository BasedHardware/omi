from __future__ import annotations

from pathlib import Path

from scripts import inventory_app_client_schemas

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'


def test_inventory_separates_generated_backed_adapters_from_raw_manual_dtos():
    report = inventory_app_client_schemas.build_report(SPEC_PATH)

    generated_backed_paths = {item['path'] for item in report['generated_backed_adapter_files']}
    remaining_manual_paths = {item['path'] for item in report['remaining_manual_dart_json_schema_files']}
    unmodeled_operations = {
        (item['method'], item['path'], item['operation_id']) for item in report['app_used_unmodeled_success_responses']
    }

    assert 'app/lib/backend/schema/conversation.dart' in generated_backed_paths
    assert 'app/lib/backend/schema/action_item.dart' in generated_backed_paths
    assert 'app/lib/backend/schema/folder.dart' in generated_backed_paths
    assert 'app/lib/backend/http/api/apps.dart' in generated_backed_paths
    assert 'app/lib/backend/http/api/users.dart' in generated_backed_paths
    assert 'app/lib/backend/schema/action_item.dart' not in remaining_manual_paths
    assert 'app/lib/backend/schema/folder.dart' not in remaining_manual_paths
    assert (
        'POST',
        '/v1/conversations/search',
        'search_conversations_endpoint_v1_conversations_search_post',
    ) not in unmodeled_operations
    assert ('GET', '/v1/app-categories', 'get_app_categories_v1_app_categories_get') not in unmodeled_operations
    assert ('POST', '/v1/app/generate', 'generate_app_endpoint_v1_app_generate_post') not in unmodeled_operations
    assert ('GET', '/v2/apps', 'get_apps_v2_v2_apps_get') not in unmodeled_operations
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
    assert report['app_used_unmodeled_success_response_count'] == len(report['app_used_unmodeled_success_responses'])
    assert report['manual_dart_json_schema_file_count'] == (
        report['generated_backed_adapter_file_count'] + report['remaining_manual_dart_json_schema_file_count']
    )
