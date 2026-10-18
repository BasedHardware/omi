import socket

import pytest

from testing.hermetic_network import BlockedNetworkError, is_local_address


def test_localhost_addresses_are_allowed_by_guard():
    assert is_local_address('localhost')
    assert is_local_address('127.0.0.1')
    assert is_local_address('::1')


def test_external_socket_connect_is_blocked():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(BlockedNetworkError):
            sock.connect(('8.8.8.8', 53))
    finally:
        sock.close()


def test_local_socket_connect_does_not_require_af_unix(monkeypatch):
    monkeypatch.delattr(socket, 'AF_UNIX', raising=False)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        try:
            client.connect(('127.0.0.1', 9))
        except BlockedNetworkError as exc:
            pytest.fail(f'localhost connect was blocked without AF_UNIX: {exc}')
        except OSError:
            pass
    finally:
        client.close()


def test_external_dns_resolution_is_blocked():
    with pytest.raises(BlockedNetworkError):
        socket.getaddrinfo('example.com', 443)


def test_localhost_dns_resolution_is_allowed():
    assert socket.getaddrinfo('localhost', 80)


def test_local_redis_endpoint_is_refused_even_when_redis_is_running():
    # A machine-local Redis is exactly the state CI never has and a developer
    # box often has: without the block, this connect succeeds and unit tests
    # consume real ``rl:*`` rate-limit quota that persists across runs.
    from testing.hermetic_network import block_local_redis

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with block_local_redis():
            with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
                client.connect(('127.0.0.1', 6379))
    finally:
        client.close()


def test_local_redis_block_leaves_other_loopback_ports_alone():
    from testing.hermetic_network import block_local_redis

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with block_local_redis():
            # Port 9 (discard) is closed on CI and dev machines alike; the
            # refusal must be the OS's, not the Redis block's.
            try:
                client.connect(('127.0.0.1', 9))
            except ConnectionRefusedError as error:
                assert 'hermetic unit tests' not in str(error)
    finally:
        client.close()


def test_local_redis_block_surfaces_as_redis_connection_error():
    # redis-py maps OSError with ECONNREFUSED to redis.ConnectionError, which
    # every fail-open path in database.redis_db already handles like CI does.
    import redis

    from testing.hermetic_network import block_local_redis

    with block_local_redis():
        with pytest.raises(redis.exceptions.ConnectionError, match='hermetic unit tests'):
            redis.Redis(host='127.0.0.1', port=6379).ping()


def test_fake_redis_opt_out_keeps_a_test_hosted_endpoint_reachable(monkeypatch):
    # A test that deliberately binds its own fake Redis listener needs the
    # socket I/O to happen; the opt-out must suspend the block for it.
    from testing.hermetic_network import block_local_redis

    monkeypatch.setenv('OMI_HERMETIC_ALLOW_FAKE_REDIS', '1')
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with block_local_redis():
            try:
                client.connect(('127.0.0.1', 6379))
            except ConnectionRefusedError as error:
                # A machine without Redis still refuses — but never the block.
                assert 'hermetic unit tests' not in str(error)
    finally:
        client.close()
