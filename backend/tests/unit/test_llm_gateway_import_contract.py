"""Gateway startup must not inherit backend content-encryption requirements."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[2]
PROD_VALUES = BACKEND / 'charts/llm-gateway/prod_omi_llm_gateway_values.yaml'


def gateway_env(tmp_path):
    # Build from the pod declaration, never inherit the runner's secrets, ADC,
    # PYTHONPATH, or a developer .env. Optional reservation Redis is unbound.
    env = {'PATH': os.defpath, 'HOME': str(tmp_path), 'PYTHONUTF8': '1'}
    for binding in yaml.safe_load(PROD_VALUES.read_text())['env']:
        source = binding.get('valueFrom', {})
        if any(ref.get('optional') for ref in source.values()):
            continue
        env[binding['name']] = str(binding.get('value', 'hermetic-test-value'))
    assert 'ENCRYPTION_SECRET' not in env
    return env


def run_isolated(code, env, tmp_path):
    result = subprocess.run(
        [sys.executable, '-I', '-c', f'import sys; sys.path.insert(0, {str(BACKEND)!r})\n' + textwrap.dedent(code)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('reservation_redis', [False, True])
def test_gateway_import_with_only_prod_env(tmp_path, reservation_redis):
    env = gateway_env(tmp_path)
    if reservation_redis:
        env.update(REDIS_DB_HOST='127.0.0.1', REDIS_DB_PORT='6379', REDIS_DB_PASSWORD='test-password')
    run_isolated(
        """
        import socket

        def no_network(*args, **kwargs):
            raise AssertionError('gateway import attempted network IO')

        socket.socket.connect = no_network
        socket.create_connection = no_network
        import llm_gateway.main as gateway
        assert gateway.app.title == 'Omi LLM Gateway'
        from database import _client
        assert _client._firestore_client is None
        assert _client._customer_firestore_client is None
        assert _client._data_plane_firestore_client is None
        for module in (
            'utils.encryption', 'utils.proactivity', 'database.proactivity',
            'database.proactivity_budget', 'database.redis_db', 'posthog',
        ):
            assert module not in sys.modules, module
        # Real ASGI startup and health use the same pod-only environment.
        from fastapi.testclient import TestClient
        with TestClient(gateway.app) as client:
            assert client.get('/health').status_code == 200
        """,
        env,
        tmp_path,
    )


@pytest.mark.parametrize('operation', ['publish', 'feed'])
@pytest.mark.parametrize('secret', [None, 'too-short'])
def test_v2_content_requires_encryption_secret(tmp_path, operation, secret):
    env = gateway_env(tmp_path)
    if secret is not None:
        env['ENCRYPTION_SECRET'] = secret
    run_isolated(
        f"""
        import asyncio
        from utils import proactivity
        assert 'utils.encryption' not in sys.modules

        def no_write(*args, **kwargs):
            raise AssertionError('missing secret must never persist plaintext')

        proactivity.ledger.publish_item = no_write
        try:
            if {operation!r} == 'publish':
                asyncio.run(proactivity.publish_item(item={{}}, content={{}}, target=None))
            else:
                proactivity.decode_feed_item('synthetic-user', {{'content': 'synthetic-ciphertext'}})
        except ValueError as exc:
            assert 'ENCRYPTION_SECRET' in str(exc), str(exc)
        else:
            raise AssertionError('v2 content operation succeeded without a valid secret')
        """,
        env,
        tmp_path,
    )
