from __future__ import annotations

import socket
from urllib.request import urlopen

import pytest

from utils import metrics


def _unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def test_sidecar_server_is_loopback_only_and_needs_no_bearer(monkeypatch):
    port = _unused_port()
    monkeypatch.setenv('PROMETHEUS_SIDECAR_PORT', str(port))
    try:
        metrics.start_metrics_sidecar_server()
        assert metrics._sidecar_server.server_address[0] == '127.0.0.1'
        with urlopen(f'http://127.0.0.1:{port}/metrics', timeout=2) as response:
            body = response.read().decode('utf-8')
        assert response.status == 200
        assert 'omi_journey_accepted_total' in body
    finally:
        metrics.stop_metrics_sidecar_server()


def test_sidecar_server_rejects_invalid_port(monkeypatch):
    monkeypatch.setenv('PROMETHEUS_SIDECAR_PORT', 'not-a-port')

    with pytest.raises(RuntimeError, match='must be an integer'):
        metrics.start_metrics_sidecar_server()
