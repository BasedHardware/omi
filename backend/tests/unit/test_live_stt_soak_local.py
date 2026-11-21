"""Local soak credential isolation and external-destination rejection."""

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from testing.live_stt_soak import local
from testing.live_stt_soak.local import local_environment


def test_parent_credentials_never_reach_local_children(tmp_path, monkeypatch):
    for name in (
        'GOOGLE_APPLICATION_CREDENTIALS',
        'SERVICE_ACCOUNT_JSON',
        'OPENAI_API_KEY',
        'SONIOX_API_KEY',
        'MODULATE_API_KEY',
        'FIREBASE_AUTH_CREDENTIALS_PATH',
        'CLOUDSDK_AUTH_ACCESS_TOKEN',
        'HTTP_PROXY',
    ):
        monkeypatch.setenv(name, 'poison-parent')
    env = local_environment(tmp_path, 16, 'parakeet-window,soniox,modulate-velma-2', False, 12)
    assert not any(value == 'poison-parent' for value in env.values())
    assert env['SONIOX_API_KEY'] == env['MODULATE_API_KEY'] == 'local-protocol-peer'
    assert 'GOOGLE_APPLICATION_CREDENTIALS' not in env and 'OPENAI_API_KEY' not in env
    assert not list(Path(env['CLOUDSDK_CONFIG']).iterdir())
    assert not list(Path(env['HOME']).iterdir())
    assert env['STT_FAILOVER_RECOVERY_ENABLED'] == 'false'
    assert env['OMI_STT_SOAK_FAULTS'] == '0'


def test_loopback_guard_rejects_provider_and_metadata_without_network():
    # Audit hooks are permanent: exercise the fence in an owned subprocess.
    code = '''
import json, socket
from testing.live_stt_soak.local import loopback_only
loopback_only()
rejected = []
for host in ('firestore.googleapis.com', 'stt-rt.soniox.com', '169.254.169.254', '10.0.0.1'):
    try:
        socket.getaddrinfo(host, 443)
    except (ValueError, RuntimeError):
        rejected.append(host)
socket.getaddrinfo('127.0.0.1', 8080)
print(json.dumps(rejected))
'''
    result = subprocess.run(
        [sys.executable, '-c', code],
        env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(Path(__file__).resolve().parents[2])},
        capture_output=True,
        text=True,
        check=True,
    )
    assert len(json.loads(result.stdout)) == 4


def test_busy_port_is_rejected_without_touching_existing_listener(monkeypatch):
    with socket.socket() as owned_listener:
        owned_listener.bind(('127.0.0.1', 0))
        owned_listener.listen()
        monkeypatch.setattr(local, 'PORTS', (owned_listener.getsockname()[1],))
        with pytest.raises(OSError):
            local.ensure_ports_free()
        assert owned_listener.fileno() >= 0
