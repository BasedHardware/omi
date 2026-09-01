from __future__ import annotations

import ast
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
TEXT_IO_SURFACES = (
    'backend/scripts/check_app_client_openapi_compatibility.py',
    'backend/scripts/export_openapi.py',
    'backend/scripts/generate_dart_models.py',
    'backend/scripts/generate_swift_openapi_types.py',
    'backend/scripts/generate_ts_openapi_types.py',
    'backend/scripts/inventory_app_client_schemas.py',
    'backend/scripts/run_dart_wire_hardening_check.py',
    'backend/tests/unit/test_app_client_dart_generator.py',
    'backend/tests/unit/test_app_client_generator_utf8_contract.py',
    'backend/tests/unit/test_app_client_openapi_compatibility.py',
    'backend/tests/unit/test_app_client_schema_inventory.py',
    'backend/tests/unit/test_app_client_swift_generator.py',
    'backend/tests/unit/test_app_client_ts_generator.py',
    'backend/tests/unit/test_assistant_settings_response_models.py',
    'backend/tests/unit/test_desktop_rest_inventory.py',
    'backend/tests/unit/test_dev_ask_endpoint.py',
    'backend/tests/unit/test_flutter_rest_inventory.py',
    'backend/tests/unit/test_integration_public_contract.py',
    'backend/tests/unit/test_windows_rest_inventory.py',
)


def _declares_utf8(call: ast.Call) -> bool:
    return any(
        keyword.arg == 'encoding' and isinstance(keyword.value, ast.Constant) and keyword.value.value == 'utf-8'
        for keyword in call.keywords
    )


def test_openapi_contract_path_text_io_declares_utf8():
    violations: list[str] = []

    for relative_path in TEXT_IO_SURFACES:
        source_path = ROOT_DIR / relative_path
        tree = ast.parse(source_path.read_text(encoding='utf-8'), filename=relative_path)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {'read_text', 'write_text'} or _declares_utf8(node):
                continue
            violations.append(f'{relative_path}:{node.lineno} {node.func.attr}()')

    assert not violations, 'Path text I/O must declare UTF-8:\n' + '\n'.join(violations)
