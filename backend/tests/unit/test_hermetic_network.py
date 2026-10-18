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


def test_localhost_redis_endpoint_is_refused():
    # redis_db passes host=None to redis-py when REDIS_DB_HOST is unset, and
    # redis-py then connects to the ``localhost`` name, not to a literal IP.
    from testing.hermetic_network import block_local_redis

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with block_local_redis():
            with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
                client.connect(('localhost', 6379))
    finally:
        client.close()


def test_redis_hostname_resolving_to_loopback_is_refused(monkeypatch):
    # A hosts-file alias (or any configured REDIS_DB_HOST name) that resolves
    # to loopback must be refused exactly like the literal address, on both
    # the raw connect and the create_connection paths. The resolver is
    # patched so the test needs no real DNS entry.
    import testing.hermetic_network as hermetic_network

    def resolver(host, port, *args, **kwargs):
        assert host == 'unit-test-redis.alias'
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.9', port))]

    monkeypatch.setattr(hermetic_network, '_UNGUARDED_GETADDRINFO', resolver)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with hermetic_network.block_local_redis():
            with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
                client.connect(('unit-test-redis.alias', 6379))
            with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
                socket.create_connection(('unit-test-redis.alias', 6379), timeout=5)
    finally:
        client.close()


def test_redis_hostname_refusal_survives_composition_with_outbound_guard(monkeypatch):
    # conftest composes the Redis guard beneath block_outbound_network, whose
    # guarded getaddrinfo refuses every non-local name before it could be
    # classified; endpoint resolution must still consult the real resolver
    # there and refuse the alias as the Redis endpoint.
    import testing.hermetic_network as hermetic_network

    monkeypatch.setattr(
        hermetic_network,
        '_UNGUARDED_GETADDRINFO',
        lambda host, port, *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.9', port))],
    )

    with hermetic_network.block_outbound_network(), hermetic_network.block_local_redis():
        with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
            socket.create_connection(('unit-test-redis.alias', 6379), timeout=5)


def test_redis_hostname_resolving_off_loopback_is_not_refused(monkeypatch):
    # Negative control: a name that resolves off loopback is not the local
    # Redis endpoint, so the Redis guard must let it flow to the chained
    # outbound guard instead of refusing it (203.0.113.0/24 is TEST-NET-3;
    # the outbound guard stops the connect before any packet leaves).
    import testing.hermetic_network as hermetic_network

    monkeypatch.setattr(
        hermetic_network,
        '_UNGUARDED_GETADDRINFO',
        lambda host, port, *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('203.0.113.7', port))],
    )

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with hermetic_network.block_outbound_network(), hermetic_network.block_local_redis():
            with pytest.raises(BlockedNetworkError):
                client.connect(('unit-test-redis.external', 6379))
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
    # socket I/O to happen. Bind a real listener on an ephemeral port and
    # point REDIS_DB_PORT at it, so reachability is asserted against a peer
    # that genuinely accepts rather than a port the OS would refuse anyway.
    from testing.hermetic_network import block_local_redis

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    endpoint_port = listener.getsockname()[1]
    monkeypatch.setenv('REDIS_DB_PORT', str(endpoint_port))
    try:
        monkeypatch.delenv('OMI_HERMETIC_ALLOW_FAKE_REDIS', raising=False)
        with block_local_redis():
            # The listener is demonstrably accepting, so without the opt-out
            # this refusal can only come from the guard itself.
            with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
                socket.create_connection(('127.0.0.1', endpoint_port), timeout=5)

        monkeypatch.setenv('OMI_HERMETIC_ALLOW_FAKE_REDIS', '1')
        with block_local_redis():
            client = socket.create_connection(('127.0.0.1', endpoint_port), timeout=5)
            client.close()
    finally:
        listener.close()
