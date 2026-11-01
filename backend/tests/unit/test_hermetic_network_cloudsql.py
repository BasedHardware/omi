"""The Cloud SQL IAM allowance in the hermetic network guard: explicit knob, two endpoints, nothing else."""

import socket

import pytest

from testing.hermetic_network import BlockedNetworkError, block_outbound_network

PG = '10.20.0.5'


@pytest.fixture
def reached(monkeypatch):
    """Replace the real socket calls so an allowed endpoint is recorded, never dialled."""
    seen = []
    monkeypatch.setattr(socket.socket, 'connect', lambda sock, address: seen.append(('connect', address)))
    monkeypatch.setattr(socket, 'create_connection', lambda address, *a, **k: seen.append(('create', address)))
    monkeypatch.setattr(socket, 'getaddrinfo', lambda host, *a, **k: seen.append(('dns', host)) or [])
    return seen


def _try_connect(address):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(address)
    finally:
        sock.close()


@pytest.mark.parametrize('env', [None, '', 'only,two', ',db,user'])
def test_no_allowance_without_a_valid_knob(monkeypatch, reached, env):
    if env is None:
        monkeypatch.delenv('OMI_TEST_POSTGRES_IAM', raising=False)
    else:
        monkeypatch.setenv('OMI_TEST_POSTGRES_IAM', env)
    with block_outbound_network():
        for address in (('169.254.169.254', 80), ('metadata.google.internal', 80), (PG, 5432)):
            with pytest.raises(BlockedNetworkError):
                _try_connect(address)
            with pytest.raises(BlockedNetworkError):
                socket.create_connection(address)
        with pytest.raises(BlockedNetworkError):
            socket.getaddrinfo('metadata.google.internal', 80)
    assert reached == []


def test_knob_allows_exactly_the_metadata_server_and_the_pg_endpoint(monkeypatch, reached):
    monkeypatch.setenv('OMI_TEST_POSTGRES_IAM', f'{PG},jobstore_staging,staging-worker@p.iam')
    with block_outbound_network():
        _try_connect(('169.254.169.254', 80))
        _try_connect(('metadata.google.internal', 80))  # google-auth dials the hostname
        _try_connect((PG, 5432))
        socket.create_connection(('169.254.169.254', 80))
        socket.create_connection(('metadata.google.internal', 80))
        socket.getaddrinfo(PG, 5432)
        socket.getaddrinfo('metadata.google.internal', 80)
        # everything else stays blocked: other ports on those hosts, other hosts, the public internet
        for address in (
            ('metadata.google.internal', 443),
            ('169.254.169.254', 443),
            (PG, 5433),
            (PG, 80),
            ('10.20.0.6', 5432),
            ('8.8.8.8', 53),
        ):
            with pytest.raises(BlockedNetworkError):
                _try_connect(address)
            with pytest.raises(BlockedNetworkError):
                socket.create_connection(address)
        for name in ('example.com', '10.20.0.6', 'oauth2.googleapis.com'):
            with pytest.raises(BlockedNetworkError):
                socket.getaddrinfo(name, 443)
    assert [kind for kind, _ in reached] == ['connect', 'connect', 'connect', 'create', 'create', 'dns', 'dns']


def test_allowance_ends_with_the_environment(monkeypatch, reached):
    monkeypatch.setenv('OMI_TEST_POSTGRES_IAM', f'{PG},db,user')
    with block_outbound_network():
        _try_connect((PG, 5432))
        monkeypatch.delenv('OMI_TEST_POSTGRES_IAM')
        with pytest.raises(BlockedNetworkError):
            _try_connect((PG, 5432))
