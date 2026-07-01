from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'backend/scripts/verify-secret-consumer-registry.py'
SENTINEL = 'fake-sentinel-secret-value-must-not-print'


def _load_verifier():
    spec = importlib.util.spec_from_file_location('secret_registry_verifier', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')


def _base_registry() -> dict:
    return {
        'schema_version': 1,
        'ignored_secret_names': [],
        'high_risk_name_patterns': ['(^|_)API_KEY$', '(^|_)SECRET$', '(^|_)TOKEN$'],
        'runtime_refresh_methods': {
            'gke': {'after_rotation': 'restart deployment', 'verify': 'rollout status'},
            'github_actions': {'after_rotation': 'rerun workflow', 'verify': 'workflow success'},
        },
        'secrets': {},
    }


def test_unregistered_high_risk_workflow_secret_fails_without_printing_values(tmp_path):
    verifier = _load_verifier()
    registry = _base_registry()
    registry_path = tmp_path / 'backend/deploy/secret_consumer_registry.yaml'
    _write_yaml(registry_path, registry)

    workflow = tmp_path / '.github/workflows/deploy.yml'
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        '\n'.join(
            [
                'name: deploy',
                'jobs:',
                '  deploy:',
                '    steps:',
                '      - uses: google-github-actions/deploy-cloudrun@v2',
                '        with:',
                '          secrets: |',
                '            OPENAI_API_KEY=UNREGISTERED_API_KEY:latest',
                f'      - run: echo "{SENTINEL}"',
            ]
        ),
        encoding='utf-8',
    )

    report = verifier.build_report(root=tmp_path, registry_path=registry_path)
    rendered = verifier.render_text_report(report)

    assert report['status'] == 'FAIL'
    assert report['issues'][0]['secret'] == 'UNREGISTERED_API_KEY'
    assert SENTINEL not in rendered
    assert SENTINEL not in yaml.safe_dump(report)


def test_registered_chart_secret_reports_consumer_and_refresh_method(tmp_path):
    verifier = _load_verifier()
    registry = _base_registry()
    registry['secrets']['OPENAI_API_KEY'] = {
        'description': 'OpenAI provider key',
        'category': 'provider_api_key',
        'owner': 'backend',
        'rotation_verification': 'run smoke',
    }
    registry_path = tmp_path / 'backend/deploy/secret_consumer_registry.yaml'
    _write_yaml(registry_path, registry)

    chart = tmp_path / 'backend/charts/llm-gateway/prod_omi_llm_gateway_values.yaml'
    _write_yaml(
        chart,
        {
            'env': [
                {
                    'name': 'OPENAI_API_KEY',
                    'valueFrom': {'secretKeyRef': {'name': 'prod-omi-backend-secrets', 'key': 'OPENAI_API_KEY'}},
                }
            ]
        },
    )

    report = verifier.build_report(root=tmp_path, registry_path=registry_path)
    consumers = [entry for entry in report['consumers'] if entry['secret'] == 'OPENAI_API_KEY']

    assert report['status'] == 'PASS'
    assert consumers
    assert consumers[0]['runtime'] == 'gke'
    assert consumers[0]['service'] == 'llm-gateway'
    assert consumers[0]['refresh_after_rotation'] == 'restart deployment'


def test_registered_lowercase_chart_secret_reports_text_consumer(tmp_path):
    verifier = _load_verifier()
    registry = _base_registry()
    registry['secrets']['password'] = {
        'description': 'Loki canary basic-auth password key',
        'category': 'datastore_credential',
        'owner': 'observability',
        'rotation_verification': 'run smoke',
    }
    registry_path = tmp_path / 'backend/deploy/secret_consumer_registry.yaml'
    _write_yaml(registry_path, registry)

    chart = tmp_path / 'backend/charts/monitoring/loki/prod_omi_loki_values.yaml'
    chart.parent.mkdir(parents=True)
    chart.write_text(
        '\n'.join(
            [
                'lokiCanary:',
                '  extraEnv:',
                '    - name: LOKI_PASS',
                '      valueFrom:',
                '        secretKeyRef:',
                '          name: canary-basic-auth',
                '          key: password',
            ]
        ),
        encoding='utf-8',
    )

    report = verifier.build_report(root=tmp_path, registry_path=registry_path)
    consumers = [entry for entry in report['consumers'] if entry['secret'] == 'password']

    assert report['status'] == 'PASS'
    assert consumers
    assert consumers[0]['runtime'] == 'gke'
    assert consumers[0]['service'] == 'monitoring'
    assert consumers[0]['env_name'] == 'password'


def test_non_mapping_secrets_returns_schema_failure(tmp_path):
    verifier = _load_verifier()
    registry = _base_registry()
    registry['secrets'] = ['OPENAI_API_KEY']
    registry_path = tmp_path / 'backend/deploy/secret_consumer_registry.yaml'
    _write_yaml(registry_path, registry)

    report = verifier.build_report(root=tmp_path, registry_path=registry_path)

    assert report['status'] == 'FAIL'
    assert any(issue['secret'] == 'secrets' and 'mapping' in issue['message'] for issue in report['issues'])


def test_invalid_high_risk_pattern_returns_schema_failure(tmp_path):
    verifier = _load_verifier()
    registry = _base_registry()
    registry['high_risk_name_patterns'] = ['[']
    registry_path = tmp_path / 'backend/deploy/secret_consumer_registry.yaml'
    _write_yaml(registry_path, registry)

    report = verifier.build_report(root=tmp_path, registry_path=registry_path)

    assert report['status'] == 'FAIL'
    assert any(
        issue['secret'] == '[' and 'invalid high-risk regex pattern' in issue['message'] for issue in report['issues']
    )


def test_malformed_cloud_run_section_is_ignored(tmp_path):
    verifier = _load_verifier()
    registry = _base_registry()
    registry_path = tmp_path / 'backend/deploy/secret_consumer_registry.yaml'
    _write_yaml(registry_path, registry)
    runtime_env = tmp_path / 'backend/deploy/runtime_env.yaml'
    _write_yaml(
        runtime_env,
        {
            'environments': {
                'prod': {
                    'cloud_run': ['malformed'],
                }
            }
        },
    )

    report = verifier.build_report(root=tmp_path, registry_path=registry_path)

    assert report['status'] == 'PASS'
    assert report['issues'] == []


def test_secret_context_name_without_high_risk_pattern_still_fails(tmp_path):
    verifier = _load_verifier()
    registry = _base_registry()
    registry_path = tmp_path / 'backend/deploy/secret_consumer_registry.yaml'
    _write_yaml(registry_path, registry)

    workflow = tmp_path / '.github/workflows/deploy.yml'
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        '\n'.join(
            [
                'name: deploy',
                'jobs:',
                '  deploy:',
                '    steps:',
                '      - uses: google-github-actions/deploy-cloudrun@v2',
                '        with:',
                '          secrets: |',
                '            DATABASE_URL=DATABASE_URL:latest',
            ]
        ),
        encoding='utf-8',
    )

    report = verifier.build_report(root=tmp_path, registry_path=registry_path)

    assert report['status'] == 'FAIL'
    assert report['issues'][0]['secret'] == 'DATABASE_URL'
    assert 'secret-bearing deploy reference' in report['issues'][0]['message']


def test_source_high_risk_env_reference_requires_registry_entry(tmp_path):
    verifier = _load_verifier()
    registry = _base_registry()
    registry_path = tmp_path / 'backend/deploy/secret_consumer_registry.yaml'
    _write_yaml(registry_path, registry)

    source = tmp_path / 'backend/routers/example.py'
    source.parent.mkdir(parents=True)
    env_name = 'NEW_' + 'PROVIDER_TOKEN'
    source.write_text(f'import os\nvalue = os.getenv("{env_name}")\n', encoding='utf-8')

    report = verifier.build_report(root=tmp_path, registry_path=registry_path)

    assert report['status'] == 'FAIL'
    assert report['issues'][0]['secret'] == env_name
    assert 'source env reference' in report['issues'][0]['message']


def test_dynamic_workflow_secret_lookup_fails_closed(tmp_path):
    verifier = _load_verifier()
    registry = _base_registry()
    registry_path = tmp_path / 'backend/deploy/secret_consumer_registry.yaml'
    _write_yaml(registry_path, registry)

    workflow = tmp_path / '.github/workflows/dynamic.yml'
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        '\n'.join(
            [
                'name: dynamic',
                'jobs:',
                '  deploy:',
                '    steps:',
                '      - run: echo "${{ secrets[env.SECRET_NAME] }}"',
            ]
        ),
        encoding='utf-8',
    )

    report = verifier.build_report(root=tmp_path, registry_path=registry_path)

    assert report['status'] == 'FAIL'
    assert report['issues'][0]['secret'] == 'secrets[...]'


def test_ignored_public_name_does_not_fail_registry(tmp_path):
    verifier = _load_verifier()
    registry = _base_registry()
    registry['ignored_secret_names'] = ['PUBLIC_POSTHOG_API_KEY']
    registry_path = tmp_path / 'backend/deploy/secret_consumer_registry.yaml'
    _write_yaml(registry_path, registry)

    codemagic = tmp_path / 'codemagic.yaml'
    codemagic.write_text(
        '\n'.join(
            [
                'workflows:',
                '  ios:',
                '    scripts:',
                '      - PUBLIC_POSTHOG_API_KEY="$PUBLIC_POSTHOG_API_KEY" ./scripts/create-public-client-env.sh',
            ]
        ),
        encoding='utf-8',
    )

    report = verifier.build_report(root=tmp_path, registry_path=registry_path)

    assert report['status'] == 'PASS'
    assert report['issues'] == []
