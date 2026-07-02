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
    assert 'app/lib/backend/schema/action_item.dart' not in remaining_manual_paths
    assert 'app/lib/backend/schema/folder.dart' not in remaining_manual_paths
    assert ('GET', '/v1/app-categories', 'get_app_categories_v1_app_categories_get') in unmodeled_operations
    assert (
        'POST',
        '/v1/payments/checkout-session',
        'create_checkout_session_endpoint_v1_payments_checkout_session_post',
    ) in unmodeled_operations
    assert report['app_used_unmodeled_success_response_count'] == len(report['app_used_unmodeled_success_responses'])
    assert report['manual_dart_json_schema_file_count'] == (
        report['generated_backed_adapter_file_count'] + report['remaining_manual_dart_json_schema_file_count']
    )
