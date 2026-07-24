"""Hermetic unit tests for the Phase 0A replay-harness egress guard.

The guard patches process-global socket state, so each test saves and restores
the originals.  No live network is needed — denied attempts raise before any
syscall.
"""

from __future__ import annotations

import socket
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
                role="test", allow=frozenset({port}), sink=lambda e: events.append(e)
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
