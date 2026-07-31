import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'generate_integration_sdks.py'
_spec = importlib.util.spec_from_file_location('generate_integration_sdks_under_test', SCRIPT)
assert _spec is not None and _spec.loader is not None
generator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generator)


def test_dart_typed_request_models_serialize_to_json():
    dart = generator.generate_all(generator.DEFAULT_SPEC)['dart/lib/omi_integration.g.dart']

    assert 'Map<String, dynamic> toJson()' in dart
    assert 'body: body.toJson()' in dart


def test_dart_numeric_fields_accept_any_json_number():
    dart = generator.generate_all(generator.DEFAULT_SPEC)['dart/lib/omi_integration.g.dart']

    assert 'as num).toInt()' in dart
    assert 'as num).toDouble()' in dart


def test_generated_clients_supply_the_configured_app_id_to_v1_notifications():
    files = generator.generate_all(generator.DEFAULT_SPEC)

    assert '{ ...body, aid: this.appId }' in files['typescript/src/client.ts']
    assert 'payload["aid"] = c.AppID' in files['go/omiintegration/client_gen.go']
    assert 'json_body = {**json_body, "aid": self.app_id}' in files['python/src/omi_integration/client.py']
    assert 'object.insert("aid".to_string(), Value::String(self.app_id.clone()));' in files['rust/src/client_gen.rs']
    assert 'json_escape(app_id_)' in files['cpp/src/client.cpp']


def test_check_rejects_stale_dart_generated_client(tmp_path):
    files = generator.generate_all(generator.DEFAULT_SPEC)
    generator.write_tree(tmp_path, files)

    assert generator.main(['--check', '--out', str(tmp_path)]) == 0
    dart_client = tmp_path / 'dart/lib/omi_integration.g.dart'
    dart_client.write_text('stale\n', encoding='utf-8')

    assert generator.main(['--check', '--out', str(tmp_path)]) == 1
    dart_client.write_text(files['dart/lib/omi_integration.g.dart'], encoding='utf-8')
    dart_barrel = tmp_path / 'dart/lib/omi_integration.dart'
    dart_barrel.write_text('stale\n', encoding='utf-8')

    assert generator.main(['--check', '--out', str(tmp_path)]) == 1
