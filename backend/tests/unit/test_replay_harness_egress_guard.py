"""Hermetic unit tests for the Phase 0A replay-harness egress guard.

The guard patches process-global socket state, so each test saves and restores
the originals.  No live network is needed — denied attempts raise before any
syscall.
"""

from __future__ import annotations

import socket
import contextlib
from typing import Any

import pytest

from testing.replay_harness_phase0a import egress_guard


@pytest.fixture()
def restored_sockets():
    """Snapshot socket entrypoints and restore them after the test."""
    saved = {
        "connect": socket.socket.connect,
        "connect_ex": socket.socket.connect_ex,
        "create_connection": socket.create_connection,
        "getaddrinfo": socket.getaddrinfo,
        "gethostbyname": socket.gethostbyname,
        "gethostbyname_ex": socket.gethostbyname_ex,
        "sendto": socket.socket.sendto,
        "sendmsg": socket.socket.sendmsg,
    }
    yield saved
    socket.socket.connect = saved["connect"]
    socket.socket.connect_ex = saved["connect_ex"]
    socket.create_connection = saved["create_connection"]
    socket.getaddrinfo = saved["getaddrinfo"]
    socket.gethostbyname = saved["gethostbyname"]
    socket.gethostbyname_ex = saved["gethostbyname_ex"]
    socket.socket.sendto = saved["sendto"]
    socket.socket.sendmsg = saved["sendmsg"]


class TestUdpGuard:
    def test_sendto_to_non_loopback_denied(self, restored_sockets):
        events: list[dict[str, Any]] = []
        egress_guard.install_default_deny_guard(role="test", allow=frozenset(), sink=lambda e: events.append(e))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            with pytest.raises(OSError, match="denied UDP sendto"):
                sock.sendto(b"x", ("10.0.0.1", 53))
        finally:
            sock.close()
        assert any(e["decision"] == "deny" for e in events)

    def test_sendto_to_loopback_allowed_port_proceeds(self, restored_sockets):
        """sendto to an allowed loopback port must not raise (it may fail at the
        syscall level if nothing is listening, but the guard itself allows it)."""
        events: list[dict[str, Any]] = []
        # Use a real ephemeral loopback listener so sendto succeeds end-to-end.
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        try:
            egress_guard.install_default_deny_guard(
                role="test", allow=frozenset({("127.0.0.1", port)}), sink=lambda e: events.append(e)
            )
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.sendto(b"x", ("127.0.0.1", port))
            finally:
                sock.close()
            assert any(e["decision"] == "allow" and e["port"] == port for e in events)
        finally:
            listener.close()

    def test_sendmsg_to_non_loopback_denied(self, restored_sockets):
        events: list[dict[str, Any]] = []
        egress_guard.install_default_deny_guard(role="test", allow=frozenset(), sink=lambda e: events.append(e))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            with pytest.raises(OSError, match="denied UDP sendmsg"):
                sock.sendmsg([b"x"], (), 0, ("10.0.0.1", 53))
        finally:
            sock.close()
        assert any(e["decision"] == "deny" for e in events)


class TestTcpGuard:
    def test_connect_to_non_loopback_denied(self, restored_sockets):
        events: list[dict[str, Any]] = []
        egress_guard.install_default_deny_guard(role="test", allow=frozenset(), sink=lambda e: events.append(e))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OSError, match="denied egress"):
                sock.connect(("10.0.0.1", 443))
        finally:
            sock.close()
        assert any(e["decision"] == "deny" for e in events)

    def test_dns_to_non_loopback_denied(self, restored_sockets):
        events: list[dict[str, Any]] = []
        egress_guard.install_default_deny_guard(role="test", allow=frozenset(), sink=lambda e: events.append(e))
        with pytest.raises(OSError, match="denied DNS"):
            socket.gethostbyname("10.0.0.1")
        assert any(e["decision"] == "deny" for e in events)


# --------------------------------------------------------------------------- #
# Final-review 2 — canonical host+port endpoint enforcement (not port-only)
# --------------------------------------------------------------------------- #


class TestHostPortEnforcement:
    """The guard must enforce the declared canonical host+port endpoint identity,
    not a port-only loopback set. When only 127.0.0.1 is declared, ``localhost``/``::1``
    aliases on a declared port must be denied — matching the attestation layer.
    """

    def test_parse_allow_list_preserves_host_port(self):
        """Parsing must preserve canonical (host, port) identity, not collapse to ports."""
        parsed = egress_guard._parse_allow_list('[{"host": "127.0.0.1", "port": 6390}]')
        assert ("127.0.0.1", 6390) in parsed
        assert 6390 not in parsed  # a bare port entry must not exist

    def test_guard_denies_localhost_alias_when_only_127_declared(self, restored_sockets):
        events: list[dict[str, Any]] = []
        allow = egress_guard._parse_allow_list('[{"host": "127.0.0.1", "port": 6390}]')
        egress_guard.install_default_deny_guard(role="test", allow=allow, sink=lambda e: events.append(e))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OSError, match="denied egress"):
                sock.connect(("localhost", 6390))
        finally:
            sock.close()
        assert any(e["decision"] == "deny" for e in events)

    def test_guard_denies_ipv6_alias_when_only_127_declared(self, restored_sockets):
        events: list[dict[str, Any]] = []
        allow = egress_guard._parse_allow_list('[{"host": "127.0.0.1", "port": 6390}]')
        egress_guard.install_default_deny_guard(role="test", allow=allow, sink=lambda e: events.append(e))
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            with pytest.raises(OSError, match="denied egress"):
                sock.connect(("::1", 6390, 0, 0))
        finally:
            sock.close()
        assert any(e["decision"] == "deny" for e in events)

    def test_guard_allows_canonical_declared_endpoint(self, restored_sockets):
        events: list[dict[str, Any]] = []
        allow = egress_guard._parse_allow_list('[{"host": "127.0.0.1", "port": 6390}]')
        egress_guard.install_default_deny_guard(role="test", allow=allow, sink=lambda e: events.append(e))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Nothing listens on 6390; the guard allows before the real connect fails.
            with contextlib.suppress(OSError):
                sock.connect(("127.0.0.1", 6390))
        finally:
            sock.close()
        assert any(e["decision"] == "allow" and e["host"] == "127.0.0.1" for e in events)

    def test_guard_denies_loopback_on_undeclared_port(self, restored_sockets):
        events: list[dict[str, Any]] = []
        allow = egress_guard._parse_allow_list('[{"host": "127.0.0.1", "port": 6390}]')
        egress_guard.install_default_deny_guard(role="test", allow=allow, sink=lambda e: events.append(e))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OSError, match="denied egress"):
                sock.connect(("127.0.0.1", 54321))
        finally:
            sock.close()
        assert any(e["decision"] == "deny" for e in events)
