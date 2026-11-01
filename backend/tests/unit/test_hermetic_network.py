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


def test_hosts_file_alias_to_loopback_is_refused(monkeypatch, tmp_path):
    # A hosts-file name mapped to a loopback address is machine-local and
    # must be refused exactly like the literal address, on both the raw
    # connect and the create_connection paths. Classification is plain
    # hosts-file I/O — never a DNS lookup.
    import testing.hermetic_network as hermetic_network

    hosts_file = tmp_path / 'hosts'
    hosts_file.write_text(
        '# unit-test hosts file\n'
        '127.0.0.1\tlocalhost\n'
        '::1\tlocalhost\n'
        '127.0.0.9\tunit-test-redis.alias\n'
        '::1\tunit-test-redis.alias.v6\n'
    )
    monkeypatch.setattr(hermetic_network, '_HOSTS_FILE_PATH', str(hosts_file))

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with hermetic_network.block_local_redis():
            with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
                client.connect(('unit-test-redis.alias', 6379))
            with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
                socket.create_connection(('unit-test-redis.alias', 6379), timeout=5)
            with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
                socket.create_connection(('unit-test-redis.alias.v6', 6379), timeout=5)
    finally:
        client.close()


def test_hosts_file_alias_refusal_survives_composition_with_outbound_guard(monkeypatch, tmp_path):
    # conftest composes the Redis guard with block_outbound_network, whose
    # hostname checks know nothing about the hosts file. The loopback alias
    # must still be refused as the Redis endpoint (the Redis wrapper is
    # installed last, so it sees the address first), while a hosts-file
    # name mapped off loopback is not local and must flow to the outbound
    # guard's refusal instead.
    import testing.hermetic_network as hermetic_network

    hosts_file = tmp_path / 'hosts'
    hosts_file.write_text('127.0.0.9\tunit-test-redis.alias\n' '10.0.0.9\tunit-test-redis.offloop\n')
    monkeypatch.setattr(hermetic_network, '_HOSTS_FILE_PATH', str(hosts_file))

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with hermetic_network.block_outbound_network(), hermetic_network.block_local_redis():
            with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
                socket.create_connection(('unit-test-redis.alias', 6379), timeout=5)
            with pytest.raises(BlockedNetworkError):
                socket.create_connection(('unit-test-redis.offloop', 6379), timeout=5)
    finally:
        client.close()


def test_remote_redis_hostname_is_never_resolved_by_the_guard(monkeypatch):
    # The Redis guard must never resolve DNS itself: a unit session
    # configured with a remote REDIS_DB_HOST would otherwise turn the
    # guard into a real DNS client from inside the hermetic boundary.
    # Patch every live ``socket`` resolver entry point, plus the captured
    # resolver attribute the pre-fix guard used (``raising=False``: the
    # fixed module no longer defines one, and this test must fail if a
    # captured resolver is ever reintroduced and called); a remote-looking
    # endpoint must flow untouched to the outbound guard (which blocks it)
    # with zero resolver calls.
    import testing.hermetic_network as hermetic_network

    resolver_calls: list[str] = []

    def refuse_to_resolve(entry_point):
        def resolve(*args, **kwargs):
            resolver_calls.append(entry_point)
            raise AssertionError(f'{entry_point} ran inside the hermetic guards')

        return resolve

    monkeypatch.setattr(socket, 'getaddrinfo', refuse_to_resolve('getaddrinfo'))
    monkeypatch.setattr(socket, 'gethostbyname', refuse_to_resolve('gethostbyname'))
    monkeypatch.setattr(socket, 'gethostbyname_ex', refuse_to_resolve('gethostbyname_ex'))
    monkeypatch.setattr(
        hermetic_network,
        '_UNGUARDED_GETADDRINFO',
        refuse_to_resolve('captured-getaddrinfo'),
        raising=False,
    )

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with hermetic_network.block_outbound_network(), hermetic_network.block_local_redis():
            with pytest.raises(BlockedNetworkError):
                client.connect(('unit-test-redis.remote.example', 6379))
            with pytest.raises(BlockedNetworkError):
                socket.create_connection(('unit-test-redis.remote.example', 6379), timeout=5)
    finally:
        client.close()
    assert resolver_calls == []


def test_localhost_name_forms_are_refused(monkeypatch, tmp_path):
    # RFC 6761 loopback name forms — ``localhost.`` and any ``*.localhost``
    # label, in any case, plus the ``::1`` literal — are machine-local
    # without consulting DNS or the hosts file. The hosts file is pointed
    # at an empty fixture so these refusals can only come from the
    # name-form/literal classification itself.
    import testing.hermetic_network as hermetic_network

    empty_hosts_file = tmp_path / 'empty-hosts'
    empty_hosts_file.write_text('')
    monkeypatch.setattr(hermetic_network, '_HOSTS_FILE_PATH', str(empty_hosts_file))

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with hermetic_network.block_local_redis():
            for host in ('localhost.', 'LocalHost', 'Unit-Test.Redis.localhost.', '::1'):
                with pytest.raises(ConnectionRefusedError, match='hermetic unit tests'):
                    client.connect((host, 6379))
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
