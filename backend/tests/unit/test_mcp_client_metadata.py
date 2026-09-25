"""Client ID Metadata Document (CIMD) fetch/validation/cache tests.

All network access is mocked at the ``socket.getaddrinfo`` /
``_dial_tls`` seams — these tests never perform real DNS or TLS (the one
exception is the explicit slow-drip test, which uses a real loopback socket
through the test-only ``_resolver``/``_dial`` hooks that production never
passes). Redis is replaced with a hermetic fake via ``redis_db.r``.
"""

import base64
import hashlib
import io
import json
import os
import re
import socket as pysocket
import ssl
import threading
import time
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import database.mcp_client_metadata as cimd
import database.redis_db as redis_db

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Captured at import time, before the default-deny fixture replaces them —
# used by the tests that need real DNS/sockets.
_REAL_GETADDRINFO = pysocket.getaddrinfo
_REAL_CREATE_CONNECTION = pysocket.create_connection
_REAL_DIAL_TLS = cimd._dial_tls

CLIENT_ID = "https://app.example.com/oauth/client-metadata.json"
REDIRECT_URI = "https://app.example.com/oauth/callback"
CODE_VERIFIER = "verifier-0123456789-abcdefghijklmnopqrstuvwxyz-ABCDEFGH"
CODE_CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(CODE_VERIFIER.encode("ascii")).digest()).decode("ascii").rstrip("=")
)


class _FakeRedis:
    def __init__(self):
        self.strings = {}
        self.sets = {}
        self.failing = False

    def _check(self):
        if self.failing:
            raise ConnectionError("fake redis outage")

    @staticmethod
    def _live(store, key):
        entry = store.get(key)
        if entry is not None and entry[1] is not None and entry[1] <= time.time():
            store.pop(key, None)
            return None
        return entry

    def get(self, key):
        self._check()
        entry = self._live(self.strings, key)
        return entry[0] if entry else None

    def set(self, key, value, ex=None, nx=False, **_kwargs):
        self._check()
        if nx and self._live(self.strings, key) is not None:
            return None
        self.strings[key] = [value, (time.time() + ex) if ex else None]
        return True

    def exists(self, *keys):
        self._check()
        return sum(
            1 for key in keys if self._live(self.strings, key) is not None or self._live(self.sets, key) is not None
        )

    def delete(self, *keys):
        self._check()
        removed = 0
        for key in keys:
            removed += self.strings.pop(key, None) is not None
            removed += self.sets.pop(key, None) is not None
        return removed

    def sadd(self, key, *members):
        self._check()
        entry = self.sets.setdefault(key, [set(), None])
        entry[0].update(members)
        return len(members)

    def smembers(self, key):
        self._check()
        entry = self._live(self.sets, key)
        return set(entry[0]) if entry else set()

    def expire(self, key, seconds):
        self._check()
        for store in (self.strings, self.sets):
            entry = store.get(key)
            if entry is not None:
                entry[1] = time.time() + seconds
                return True
        return False

    def ttl(self, key):
        self._check()
        entry = self._live(self.strings, key) or self._live(self.sets, key)
        if entry is None:
            return -2
        if entry[1] is None:
            return -1
        return int(entry[1] - time.time())


class _FakeTLSSocket:
    """Replays a canned raw HTTP response through the ``recv`` loop — the
    duck-typed surface ``_read_response`` uses (settimeout/sendall/recv/close).
    ``chunk`` bounds how much each recv returns so reads stay iterative."""

    def __init__(self, data: bytes, *, chunk: int = 512):
        self._stream = io.BytesIO(data)
        self._chunk = chunk
        self.sent = bytearray()
        self.timeouts = []
        self.closed = False

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        self.sent += data

    def recv(self, n):
        return self._stream.read(min(n, self._chunk))

    def close(self):
        self.closed = True


class _Dial:
    """Callable ``_dial`` seam: records each ``(address, hostname, deadline)``
    and hands out a fresh fake socket — or raises for configured addresses.
    ``deadline`` is the absolute monotonic deadline the dial shares with the
    fetch."""

    def __init__(self, response: bytes, fail_addresses=()):
        self.response = response
        self.fail_addresses = set(fail_addresses)
        self.calls = []
        self.sockets = []

    def __call__(self, address, hostname, deadline):
        self.calls.append((address, hostname, deadline))
        if address in self.fail_addresses:
            raise OSError("connect failed")
        sock = _FakeTLSSocket(self.response)
        self.sockets.append(sock)
        return sock


def _raw_http(status=200, reason="OK", headers=None, body=b""):
    merged = {"Content-Length": str(len(body)), **(headers or {})}
    head = "".join(f"{name}: {value}\r\n" for name, value in merged.items())
    return (f"HTTP/1.1 {status} {reason}\r\n{head}\r\n").encode("ascii") + body


def _json_response(body: bytes, *, status=200, headers=None) -> bytes:
    merged = {"Content-Type": "application/json", **(headers or {})}
    return _raw_http(status=status, headers=merged, body=body)


def _public_dns(hostname, port, *args, **_kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def _install_network(monkeypatch, addresses=("93.184.216.34",), response=None, fail_addresses=()):
    """Mock DNS + the dial seam; returns the ``_Dial`` recorder. ``response``
    is raw wire bytes (build with ``_raw_http``/``_json_response``)."""

    def fake_getaddrinfo(hostname, port, *args, **_kwargs):
        return [(2, 1, 6, "", (address, port or 443)) for address in addresses]

    monkeypatch.setattr(cimd.socket, "getaddrinfo", fake_getaddrinfo)
    dial = _Dial(response if response is not None else _json_response(b"{}"), fail_addresses)
    monkeypatch.setattr(cimd, "_dial_tls", dial)
    return dial


def _metadata_body(**overrides):
    document = {
        "client_id": CLIENT_ID,
        "client_name": "Example App",
        "redirect_uris": [REDIRECT_URI],
        "token_endpoint_auth_method": "none",
    }
    document.update(overrides)
    return json.dumps(document).encode("utf-8")


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(redis_db, "r", fake)
    return fake


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Default-deny: any un-mocked fetch attempt explodes rather than escaping."""

    def boom(*args, **kwargs):
        raise AssertionError(f"unexpected network access: {args}")

    monkeypatch.setattr(cimd.socket, "getaddrinfo", boom)
    monkeypatch.setattr(cimd.socket, "create_connection", boom)
    monkeypatch.setattr(cimd, "_dial_tls", boom)


# --- URL shape ------------------------------------------------------------


@pytest.mark.parametrize(
    "client_id",
    [
        "http://app.example.com/meta.json",  # non-HTTPS scheme
        "https://user@app.example.com/meta.json",  # userinfo
        "https://user:pw@app.example.com/meta.json",  # userinfo password
        "https://app.example.com/meta.json#frag",  # fragment
        "https://app.example.com/meta.json#",  # empty fragment marker
        "https://app.example.com/meta.json?x=1",  # query string
        "https://app.example.com/meta.json?v=2&w=3",  # query string
        "https://app.example.com/meta.json?",  # empty query marker
        "https://app.example.com:8443/meta.json",  # non-443 port
        "https://app.example.com\\meta.json",  # backslash
        "https://app.example.com/m\x07eta.json",  # control char
        "https://app.example.com/" + "a" * 2100,  # excessive length
        "https://exämple.com/meta.json",  # non-ASCII host (must be punycode)
        "https://app.example.com/mëtadata.json",  # non-ASCII path
        "not-a-url/",
    ],
    ids=[
        "non_https",
        "userinfo",
        "userinfo_password",
        "fragment",
        "fragment_empty_marker",
        "query",
        "query_multi",
        "query_empty_marker",
        "non443_port",
        "backslash",
        "control_char",
        "too_long",
        "nonascii_host",
        "nonascii_path",
        "garbage",
    ],
)
def test_url_form_client_id_rejected_without_network(client_id, monkeypatch):
    called = []
    monkeypatch.setattr(cimd, "_dial_tls", lambda *a, **k: called.append(a))
    assert cimd.get_url_client(client_id) is None
    assert called == []


# --- DNS / SSRF ------------------------------------------------------------


@pytest.mark.parametrize(
    "addresses",
    [
        ("10.0.0.5",),  # private
        ("192.168.1.9",),  # private
        ("127.0.0.1",),  # loopback
        ("169.254.169.254",),  # link-local metadata service
        ("100.64.1.1",),  # CGNAT shared address space
        ("224.0.0.5",),  # multicast
        ("::1",),  # IPv6 loopback
        ("::",),  # unspecified
        ("fe80::1",),  # IPv6 link-local
        ("fd00::5",),  # IPv6 ULA
        ("ff02::1",),  # IPv6 multicast
        ("fec0::1",),  # IPv6 site-local (deprecated)
        ("::ffff:10.0.0.5",),  # unsafe IPv4-mapped
        ("64:ff9b::a00:5",),  # NAT64 well-known prefix (RFC 6052)
        ("64:ff9b:1::a00:5",),  # NAT64 local-use prefix (RFC 8215)
        ("2002::1",),  # 6to4 relay
        ("2001::ba3e:2:30",),  # Teredo
        ("::10.0.0.5",),  # deprecated IPv4-compatible form
        ("93.184.216.34", "10.0.0.5"),  # one private among publics
    ],
    ids=[
        "private_10",
        "private_192",
        "loopback",
        "link_local_metadata",
        "cgnat",
        "multicast",
        "v6_loopback",
        "v6_unspecified",
        "v6_link_local",
        "v6_ula",
        "v6_multicast",
        "v6_site_local",
        "v4_mapped_private",
        "nat64_well_known",
        "nat64_local_use",
        "6to4",
        "teredo",
        "v4_compatible",
        "mixed_private",
    ],
)
def test_non_global_dns_results_rejected(addresses, monkeypatch):
    dial = _install_network(monkeypatch, addresses=addresses)
    assert cimd.get_url_client(CLIENT_ID) is None
    assert dial.calls == []


def test_public_ipv4_mapped_address_allowed(monkeypatch):
    """A mapped address wrapping a PUBLIC IPv4 is safe — the embedded v4 is
    what gets validated, and the connection pins to it."""
    dial = _install_network(
        monkeypatch,
        addresses=("::ffff:8.8.8.8",),
        response=_json_response(_metadata_body()),
    )
    assert cimd.get_url_client(CLIENT_ID) is not None
    assert dial.calls[0][0] == "::ffff:8.8.8.8"


def test_dns_failure_returns_unknown_client(monkeypatch):
    def fail(hostname, port, *args, **kwargs):
        raise OSError("NXDOMAIN")

    monkeypatch.setattr(cimd.socket, "getaddrinfo", fail)
    assert cimd.get_url_client(CLIENT_ID) is None


def test_dns_past_deadline_returns_unknown_client(monkeypatch):
    """A resolver that never answers is abandoned at the shared deadline —
    the DNS pool thread may keep running, the caller does not wait on it."""
    dial = _Dial(_json_response(_metadata_body()))
    monkeypatch.setattr(cimd, "_dial_tls", dial)

    def slow_dns(hostname, port, *args, **kwargs):
        time.sleep(10)
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(cimd.socket, "getaddrinfo", slow_dns)
    start = time.monotonic()
    assert cimd.get_url_client(CLIENT_ID) is None
    assert time.monotonic() - start < cimd.CIMD_FETCH_TIMEOUT_SECONDS + 1.5
    assert dial.calls == []


def test_fetch_pins_validated_ip_and_preserves_hostname(monkeypatch):
    dial = _install_network(monkeypatch, addresses=("8.8.8.8",), response=_json_response(_metadata_body()))
    assert cimd.get_url_client(CLIENT_ID) is not None

    address, hostname, deadline = dial.calls[0]
    assert address == "8.8.8.8"
    assert hostname == "app.example.com"
    assert 0 < deadline - time.monotonic() <= cimd.CIMD_FETCH_TIMEOUT_SECONDS
    request = bytes(dial.sockets[0].sent).decode("ascii")
    assert request.startswith("GET /oauth/client-metadata.json HTTP/1.1\r\n")
    assert "Host: app.example.com\r\n" in request
    assert dial.sockets[0].closed


def test_ipv4_addresses_are_tried_first(monkeypatch):
    """getaddrinfo may order v6 ahead of v4 — the fetch must prefer a working
    IPv4 path inside the shared deadline."""
    dial = _install_network(
        monkeypatch,
        addresses=("2606:2800:220:1:248:1893:25c8:1946", "93.184.216.34"),
        response=_json_response(_metadata_body()),
    )
    assert cimd.get_url_client(CLIENT_ID) is not None
    assert dial.calls[0][0] == "93.184.216.34"


def test_falls_through_to_next_validated_address(monkeypatch):
    dial = _install_network(
        monkeypatch,
        addresses=("8.8.8.8", "93.184.216.34"),
        response=_json_response(_metadata_body()),
        fail_addresses={"8.8.8.8"},
    )
    assert cimd.get_url_client(CLIENT_ID) is not None
    assert [call[0] for call in dial.calls] == ["8.8.8.8", "93.184.216.34"]


def test_address_iteration_stops_at_the_shared_deadline(monkeypatch):
    """Each attempt gets only the remaining budget — once it is spent, later
    validated addresses are never dialed."""
    monkeypatch.setattr(
        cimd.socket,
        "getaddrinfo",
        lambda hostname, port, *args, **kw: [(2, 1, 6, "", (f"8.8.{i}.1", 443)) for i in range(5)],
    )
    calls = []

    def slow_dial(address, hostname, deadline):
        calls.append(address)
        time.sleep(max(0.0, deadline - time.monotonic()))  # burn the entire remaining budget
        raise OSError("connect timeout")

    monkeypatch.setattr(cimd, "_dial_tls", slow_dial)
    start = time.monotonic()
    assert cimd.get_url_client(CLIENT_ID) is None
    assert calls == ["8.8.0.1"]
    assert time.monotonic() - start < cimd.CIMD_FETCH_TIMEOUT_SECONDS + 1.5


def test_fetch_rejects_redirect_responses(monkeypatch):
    """3xx is never followed — a redirect could point at a private target."""
    _install_network(
        monkeypatch,
        response=_raw_http(status=302, reason="Found", headers={"Location": "https://169.254.169.254/x"}),
    )
    assert cimd.get_url_client(CLIENT_ID) is None


@pytest.mark.parametrize("status", [400, 404, 500])
def test_fetch_requires_http_200(status, monkeypatch):
    _install_network(monkeypatch, response=_raw_http(status=status, reason="ERR"))
    assert cimd.get_url_client(CLIENT_ID) is None


def test_fetch_requires_json_content_type(monkeypatch):
    _install_network(
        monkeypatch,
        response=_raw_http(headers={"Content-Type": "text/html"}, body=_metadata_body()),
    )
    assert cimd.get_url_client(CLIENT_ID) is None


def test_fetch_accepts_json_charset_parameter(monkeypatch):
    _install_network(
        monkeypatch,
        response=_raw_http(headers={"Content-Type": "application/json; charset=utf-8"}, body=_metadata_body()),
    )
    assert cimd.get_url_client(CLIENT_ID) is not None


def test_fetch_rejects_oversized_document(monkeypatch):
    _install_network(
        monkeypatch,
        response=_json_response(_metadata_body() + b" " * (17 * 1024)),
    )
    assert cimd.get_url_client(CLIENT_ID) is None


def test_fetch_rejects_non_object_json(monkeypatch):
    _install_network(monkeypatch, response=_json_response(b"[1,2,3]"))
    assert cimd.get_url_client(CLIENT_ID) is None


def test_fetch_reads_iteratively_under_the_deadline(monkeypatch):
    """The response is consumed in ~1 KiB recvs, each re-timed to the
    remaining deadline."""
    body = _metadata_body()
    dial = _install_network(monkeypatch, response=_json_response(body))
    assert cimd.get_url_client(CLIENT_ID) is not None
    sock = dial.sockets[0]
    # A >1 KiB body must take multiple recvs at the 512-byte test chunk.
    assert len(sock.timeouts) >= 2
    assert all(0 < t <= cimd.CIMD_FETCH_TIMEOUT_SECONDS for t in sock.timeouts)


def test_slow_drip_socket_cannot_hold_worker_past_deadline(monkeypatch):
    """REAL loopback socket through the explicit test-only hooks: a peer
    dripping one byte at a time is cut at the shared 3s deadline. Production
    callers never pass ``_resolver``/``_dial``, so loopback stays rejected
    everywhere else (proven by the vector tests above)."""
    # The autouse default-deny fixture replaced create_connection globally —
    # restore the real one for this explicit test-only socket.
    monkeypatch.setattr(pysocket, "create_connection", _REAL_CREATE_CONNECTION)
    listener = pysocket.socket(pysocket.AF_INET, pysocket.SOCK_STREAM)
    listener.setsockopt(pysocket.SOL_SOCKET, pysocket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def drip():
        try:
            conn, _ = listener.accept()
            with conn:
                conn.recv(4096)
                while not stop.is_set():
                    try:
                        conn.sendall(b"x")
                    except OSError:
                        break
                    time.sleep(0.05)
        except OSError:
            pass

    thread = threading.Thread(target=drip, daemon=True)
    thread.start()
    try:
        start = time.monotonic()
        result = cimd._fetch_document(
            "localhost",
            "/meta.json",
            _resolver=lambda host, deadline: ["127.0.0.1"],
            _dial=lambda address, host, deadline: pysocket.create_connection(
                ("127.0.0.1", port), timeout=max(0.0, deadline - time.monotonic())
            ),
        )
        elapsed = time.monotonic() - start
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=5)
    assert result is None
    assert elapsed < cimd.CIMD_FETCH_TIMEOUT_SECONDS + 1.5


def test_stalled_tls_handshake_cannot_hold_worker_past_deadline(monkeypatch):
    """REAL TLS handshake through the test-only hooks: a peer that accepts
    TCP but never answers the ClientHello is cut at the shared 3s deadline —
    ``_dial_tls`` re-anchors the socket timeout to the remaining budget right
    before ``wrap_socket``. The real verifying TLS context runs; only
    ``create_connection`` is redirected to the local listener, and only
    inside the ``_dial`` hook."""
    listener = pysocket.socket(pysocket.AF_INET, pysocket.SOCK_STREAM)
    listener.setsockopt(pysocket.SOL_SOCKET, pysocket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def accept_and_stall():
        try:
            conn, _ = listener.accept()
            with conn:
                conn.recv(4096)
                while not stop.is_set():
                    time.sleep(0.05)
        except OSError:
            pass

    thread = threading.Thread(target=accept_and_stall, daemon=True)
    thread.start()

    def dial_to_listener(address, hostname, deadline):
        monkeypatch.setattr(
            cimd.socket,
            "create_connection",
            lambda *args, **kwargs: _REAL_CREATE_CONNECTION(("127.0.0.1", port), timeout=kwargs.get("timeout")),
        )
        return _REAL_DIAL_TLS(address, hostname, deadline)

    try:
        start = time.monotonic()
        result = cimd._fetch_document(
            "localhost",
            "/meta.json",
            _resolver=lambda host, deadline: ["127.0.0.1"],
            _dial=dial_to_listener,
        )
        elapsed = time.monotonic() - start
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=5)
    assert result is None
    assert elapsed < cimd.CIMD_FETCH_TIMEOUT_SECONDS + 1.5


def test_dial_tls_reanchors_timeout_after_tls_context_load(monkeypatch):
    """``_get_tls_context`` lazily loads the cert store and can consume budget,
    so ``settimeout`` must run after it — immediately before ``wrap_socket`` —
    with only the remaining deadline."""
    events = []

    class _FakeSock:
        def settimeout(self, value):
            events.append(("settimeout", value))

        def close(self):
            events.append(("close", None))

    fake_sock = _FakeSock()
    monkeypatch.setattr(cimd.socket, "create_connection", lambda *a, **k: fake_sock)

    class _SlowContext:
        def wrap_socket(self, sock, server_hostname):
            events.append(("wrap", server_hostname))
            return sock

    def slow_context_load():
        events.append(("context", None))
        time.sleep(0.5)
        return _SlowContext()

    monkeypatch.setattr(cimd, "_get_tls_context", slow_context_load)
    deadline = time.monotonic() + 10.0

    result = _REAL_DIAL_TLS("93.184.216.34", "app.example.com", deadline)

    assert result is fake_sock
    assert events == [("context", None), ("settimeout", events[1][1]), ("wrap", "app.example.com")]
    anchored = events[1][1]
    assert anchored <= deadline - time.monotonic() + 0.05
    # ~0.5s of context load must be reflected: a pre-load anchor would be ~10.0.
    assert anchored < 9.9


def test_localhost_client_id_rejected_without_hooks(monkeypatch):
    """Real DNS resolves localhost to loopback — and the production path
    still refuses to dial it."""
    monkeypatch.setattr(cimd.socket, "getaddrinfo", _REAL_GETADDRINFO)
    assert cimd.get_url_client("https://localhost/oauth/client-metadata.json") is None


# --- Document validation ---------------------------------------------------


def test_document_client_id_must_match_request_url(monkeypatch):
    _install_network(monkeypatch, response=_json_response(_metadata_body(client_id="https://evil.example/x")))
    assert cimd.get_url_client(CLIENT_ID) is None


@pytest.mark.parametrize(
    "redirect_uris",
    [
        [],
        "not-a-list",
        [REDIRECT_URI, REDIRECT_URI],  # duplicates
        [f"https://app.example.com/cb/{i}" for i in range(21)],  # too many
        ["https://app.example.com/cb#frag"],
        ["https://u:p@app.example.com/cb"],
        ["javascript:alert(1)"],
        ["ftp://app.example.com/cb"],
        ["http://app.example.com/cb"],  # http only allowed on loopback
        ["com.example.app:/oauth"],  # custom scheme rejected
        [REDIRECT_URI, 7],  # non-string member
    ],
    ids=[
        "empty",
        "not_a_list",
        "duplicate",
        "too_many",
        "fragment",
        "userinfo",
        "javascript",
        "ftp",
        "http_remote",
        "custom_scheme",
        "non_string_member",
    ],
)
def test_document_rejects_invalid_redirect_uris(redirect_uris, monkeypatch):
    _install_network(monkeypatch, response=_json_response(_metadata_body(redirect_uris=redirect_uris)))
    assert cimd.get_url_client(CLIENT_ID) is None


@pytest.mark.parametrize(
    "loopback_uri",
    [
        "http://localhost:8080/callback",
        "http://127.0.0.1:9999/callback",
        "http://[::1]:8080/callback",
        "http://my-app.localhost/callback",
    ],
    ids=["localhost", "ipv4_loopback", "ipv6_loopback", "localhost_subdomain"],
)
def test_document_allows_native_loopback_redirects(loopback_uri, monkeypatch):
    _install_network(monkeypatch, response=_json_response(_metadata_body(redirect_uris=[loopback_uri])))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None
    assert client["allowed_redirect_uris"] == [loopback_uri]


@pytest.mark.parametrize(
    "document_extra",
    [
        {"token_endpoint_auth_method": "client_secret_post"},
        {"client_secret": "secret"},
        {"client_secret_hash": "abc"},
        {"code_challenge_methods_supported": ["plain"]},
    ],
    ids=["confidential_method", "client_secret", "secret_hash", "non_s256_methods"],
)
def test_document_rejects_secrets_and_non_pkce_methods(document_extra, monkeypatch):
    _install_network(monkeypatch, response=_json_response(_metadata_body(**document_extra)))
    assert cimd.get_url_client(CLIENT_ID) is None


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("<script>alert(1)</script>", "<script>alert(1)</script>"),  # kept literal, escaped at render
        ("Omi " + "⁮" + "support", "Omi support"),  # bidi override stripped
        ("A" * 100, "A" * 64),  # clamped to 64 chars
        ("Ｅｘａｍｐｌｅ　Ａｐｐ", "Example App"),  # NFKC fullwidth normalization
        ("line\nbreak\tapp", "linebreakapp"),  # control chars removed
    ],
    ids=["xss_literal", "bidi_strip", "long_clamp", "nfkc_normalize", "control_strip"],
)
def test_client_name_sanitized(raw_name, expected, monkeypatch):
    _install_network(monkeypatch, response=_json_response(_metadata_body(client_name=raw_name)))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None
    assert client["name"] == f"{expected} (app.example.com)"


@pytest.mark.parametrize(
    "raw_name",
    ["Claude", "CLAUDE", "chatgpt", "Omi", "Ｃｌａｕｄｅ", " OMI ", "Сlaude", "Claude Notes", "Example App"],
    ids=[
        "claude",
        "claude_upper",
        "chatgpt",
        "omi",
        "claude_fullwidth",
        "omi_padded",
        "claude_cyrillic_homoglyph",
        "claude_near_miss",
        "ordinary_name",
    ],
)
def test_client_name_is_always_host_suffixed(raw_name, monkeypatch):
    """Every self-published client_name carries the verified ASCII host —
    an exact-match brand list cannot catch homoglyphs like Cyrillic
    "Сlaude", so the suffix is unconditional, not only on collisions."""
    _install_network(monkeypatch, response=_json_response(_metadata_body(client_name=raw_name)))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None
    assert client["name"].endswith(" (app.example.com)")


def test_client_name_falls_back_to_host(monkeypatch):
    _install_network(monkeypatch, response=_json_response(_metadata_body(client_name="   ")))
    client = cimd.get_url_client(CLIENT_ID)
    assert client["name"] == "app.example.com"


def test_client_name_matching_host_is_not_doubled(monkeypatch):
    """A client_name that IS the host must not render as 'host (host)'."""
    _install_network(monkeypatch, response=_json_response(_metadata_body(client_name="app.example.com")))
    client = cimd.get_url_client(CLIENT_ID)
    assert client["name"] == "app.example.com"


def test_client_record_shape_and_public_pkce(monkeypatch):
    _install_network(monkeypatch, response=_json_response(_metadata_body()))
    client = cimd.get_url_client(CLIENT_ID)
    assert client["registration_mode"] == "client_id_metadata_document"
    assert client["token_endpoint_auth_method"] == "none"
    assert client["client_secret_hash"] == ""
    assert client["metadata_host"] == "app.example.com"
    assert client["allowed_redirect_uri_prefixes"] == []


# --- Redis cache ------------------------------------------------------------


def _cache_key(client_id=CLIENT_ID):
    return f"mcp:cimd:{hashlib.sha256(client_id.encode('utf-8')).hexdigest()}"


def _neg_cache_key(client_id=CLIENT_ID):
    return f"mcp:cimd:neg:{hashlib.sha256(client_id.encode('utf-8')).hexdigest()}"


def test_validated_metadata_cached_with_clamped_ttl(monkeypatch, _fake_redis):
    _install_network(
        monkeypatch,
        response=_json_response(_metadata_body(), headers={"Cache-Control": "max-age=7200"}),
    )
    assert cimd.get_url_client(CLIENT_ID) is not None
    entry = _fake_redis.strings[_cache_key()]
    assert 3500 <= entry[1] - time.time() <= 3600
    envelope = json.loads(entry[0])
    assert envelope["type"] == "cimd"
    assert set(envelope["data"]) == {"client_id", "client_name", "redirect_uris"}  # whitelist only
    assert isinstance(envelope["mac"], str) and envelope["mac"]


@pytest.mark.parametrize("cache_control", ["no-store", "no-cache", "private"], ids=["no_store", "no_cache", "private"])
def test_no_caching_directives_not_cached(cache_control, monkeypatch, _fake_redis):
    _install_network(
        monkeypatch,
        response=_json_response(_metadata_body(), headers={"Cache-Control": cache_control}),
    )
    assert cimd.get_url_client(CLIENT_ID) is not None
    assert _cache_key() not in _fake_redis.strings


def test_cache_hit_reuses_metadata_without_fetch(monkeypatch, _fake_redis):
    dial = _install_network(monkeypatch, response=_json_response(_metadata_body()))
    assert cimd.get_url_client(CLIENT_ID) is not None
    dial.calls = []
    assert cimd.get_url_client(CLIENT_ID) is not None
    assert dial.calls == []  # served from cache


def test_failed_fetch_is_negative_cached_for_sixty_seconds(monkeypatch, _fake_redis):
    """An unreachable/invalid fetch result suppresses refetching the same
    canonical URL — unauthenticated callers cannot force a fresh 3s fetch
    per request."""
    dial = _install_network(monkeypatch, fail_addresses={"93.184.216.34"})
    assert cimd.get_url_client(CLIENT_ID) is None
    assert _fake_redis.ttl(_neg_cache_key()) <= cimd.CIMD_NEGATIVE_CACHE_TTL_SECONDS
    dial.calls = []
    assert cimd.get_url_client(CLIENT_ID) is None
    assert dial.calls == []  # suppressed by the negative cache


def test_invalid_document_is_negative_cached(monkeypatch, _fake_redis):
    dial = _install_network(monkeypatch, response=_json_response(_metadata_body(client_id="https://evil.example/x")))
    assert cimd.get_url_client(CLIENT_ID) is None
    dial.calls = []
    assert cimd.get_url_client(CLIENT_ID) is None
    assert dial.calls == []


def test_negative_cache_survives_redis_outage_fail_open(monkeypatch, _fake_redis):
    """A Redis outage must not disable the suppression into a fetch loop —
    reads fail open to 'not cached' and writes warn, but never raise."""
    _fake_redis.failing = True
    dial = _install_network(monkeypatch, fail_addresses={"93.184.216.34"})
    assert cimd.get_url_client(CLIENT_ID) is None
    assert len(dial.calls) == 1


def test_cimd_signed_blob_cannot_be_served_as_a_token_identity(_fake_redis):
    """Cross-type reuse fails closed: a blob tagged ``cimd`` never verifies
    as ``at`` and vice versa."""
    import database.mcp_cache_integrity as integrity

    payload = {"uid": "u", "client_id": "c"}
    at_blob = integrity.dumps_signed(payload, "at")
    cimd_blob = integrity.dumps_signed(payload, "cimd")
    assert integrity.loads_verified(at_blob, "at") == payload
    assert integrity.loads_verified(cimd_blob, "cimd") == payload
    assert integrity.loads_verified(at_blob, "cimd") is None
    assert integrity.loads_verified(cimd_blob, "at") is None


def test_integrity_key_is_derived_not_the_raw_secret(_fake_redis):
    """The MAC key is HKDF-SHA256(ENCRYPTION_SECRET, info='mcp-cache-v1') —
    an HMAC keyed by the raw secret cannot verify a stored envelope."""
    import hmac as hmac_module

    import database.mcp_cache_integrity as integrity

    blob = integrity.dumps_signed({"x": 1}, "cimd")
    envelope = json.loads(blob)
    secret = os.environ["ENCRYPTION_SECRET"].encode()
    canonical = json.dumps(
        {"v": envelope["v"], "type": "cimd", "data": {"x": 1}}, sort_keys=True, separators=(",", ":")
    ).encode()
    raw_key_mac = hmac_module.new(secret, canonical, hashlib.sha256).hexdigest()
    assert envelope["mac"] != raw_key_mac


def test_integrity_key_derivation_is_memoized_per_secret(monkeypatch):
    """HKDF runs once per distinct ENCRYPTION_SECRET: repeated envelopes
    reuse the derived key, a rotated secret derives a different key, and a
    missing secret still yields None."""
    import database.mcp_cache_integrity as integrity

    derivations = []
    real_derive = integrity.HKDF.derive

    def counting_derive(self, secret):
        derivations.append(secret)
        return real_derive(self, secret)

    monkeypatch.setattr(integrity.HKDF, "derive", counting_derive)
    integrity._derive_key.cache_clear()
    try:
        monkeypatch.setenv("ENCRYPTION_SECRET", "rotation-test-secret-one")
        blob_one = integrity.dumps_signed({"x": 1}, "cimd")
        integrity.dumps_signed({"x": 2}, "cimd")
        integrity.loads_verified(blob_one, "cimd")
        assert derivations == [b"rotation-test-secret-one"]

        monkeypatch.setenv("ENCRYPTION_SECRET", "rotation-test-secret-two")
        blob_two = integrity.dumps_signed({"x": 1}, "cimd")
        assert derivations == [b"rotation-test-secret-one", b"rotation-test-secret-two"]
        assert json.loads(blob_one)["mac"] != json.loads(blob_two)["mac"]
        assert integrity.loads_verified(blob_one, "cimd") is None  # foreign-keyed blob rejected

        monkeypatch.delenv("ENCRYPTION_SECRET")
        assert integrity.dumps_signed({"x": 1}, "cimd") is None
        assert integrity.loads_verified(blob_two, "cimd") is None
    finally:
        integrity._derive_key.cache_clear()


def test_poisoned_cache_entry_is_revalidated_and_refetched(monkeypatch, _fake_redis):
    _fake_redis.set(
        _cache_key(),
        json.dumps({"client_id": "https://evil.example/other", "client_name": "Evil", "redirect_uris": [REDIRECT_URI]}),
        ex=3600,
    )
    dial = _install_network(monkeypatch, response=_json_response(_metadata_body()))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None and client["name"] == "Example App (app.example.com)"
    assert len(dial.calls) == 1  # bad cache value was not trusted


def test_forged_unsigned_cached_document_never_reaches_consent(monkeypatch, _fake_redis):
    """A validly-shaped but unsigned cached document — attacker-controlled
    name and redirect URIs — fails the MAC check and is never served."""
    forged = {
        "client_id": CLIENT_ID,
        "client_name": "Trusted Connector",
        "redirect_uris": ["https://evil.example/callback"],
    }
    _fake_redis.set(_cache_key(), json.dumps(forged), ex=3600)
    dial = _install_network(monkeypatch, response=_json_response(_metadata_body()))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None
    assert client["name"] == "Example App (app.example.com)"  # fetched document, not the forge
    assert client["allowed_redirect_uris"] == [REDIRECT_URI]
    assert len(dial.calls) == 1


def test_document_signed_with_foreign_secret_is_refetched(monkeypatch, _fake_redis):
    import database.mcp_cache_integrity as integrity

    monkeypatch.setenv("ENCRYPTION_SECRET", "foreign-test-secret-foreign-test-secret")
    blob = integrity.dumps_signed(
        {"client_id": CLIENT_ID, "client_name": "Trusted Connector", "redirect_uris": ["https://evil.example/cb"]},
        "cimd",
    )
    monkeypatch.setenv("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
    _fake_redis.set(_cache_key(), blob, ex=3600)
    dial = _install_network(monkeypatch, response=_json_response(_metadata_body()))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None and client["name"] == "Example App (app.example.com)"
    assert len(dial.calls) == 1


def test_cimd_tagged_blob_misplaced_under_at_key_not_served(_fake_redis):
    """A cimd-tagged blob replayed under an access-token cache key fails the
    type check — cross-type reuse can never mint a token identity."""
    import database.mcp_cache_integrity as integrity
    import database.mcp_token_cache as token_cache

    entry = {
        "uid": "attacker",
        "client_id": "c",
        "grant_id": "g",
        "resource": "https://api.omi.me/v1/mcp",
        "scopes": ["memories.read"],
        "expires_at": time.time() + 300,
        "token_hash": "x",
    }
    _fake_redis.set(
        f"mcp:oauth:at:{hashlib.sha256(b'omi_oat_x').hexdigest()}",
        integrity.dumps_signed(entry, "cimd"),
        ex=60,
    )
    assert token_cache.read_access_token("omi_oat_x", "https://api.omi.me/v1/mcp") is None


def test_missing_signing_secret_skips_cache_entirely(monkeypatch, _fake_redis):
    monkeypatch.delenv("ENCRYPTION_SECRET", raising=False)
    _install_network(monkeypatch, response=_json_response(_metadata_body()))
    assert cimd.get_url_client(CLIENT_ID) is not None
    assert _cache_key() not in _fake_redis.strings  # nothing is ever written unsigned


def test_dial_failure_returns_unknown_client(monkeypatch, _fake_redis):
    _install_network(monkeypatch, fail_addresses={"93.184.216.34"})
    assert cimd.get_url_client(CLIENT_ID) is None


def test_bounded_pool_submit_fails_fast_when_full():
    """The module-local DNS pool rejects work once workers plus queue are
    full instead of growing an unbounded queue."""
    pool = cimd._BoundedPool(1, 1)
    blocker = threading.Event()
    try:
        pool.submit(blocker.wait)  # takes the worker
        pool.submit(blocker.wait)  # takes the queue slot
        with pytest.raises(cimd.McpCimdUnavailable):
            pool.submit(blocker.wait)
    finally:
        blocker.set()


def test_dns_pool_saturation_raises_unavailable(monkeypatch):
    """A saturated DNS pool surfaces as the typed capacity error — the OAuth
    layer maps it to a fast 503 rather than queueing unauthenticated work."""

    def boom(*args, **kwargs):
        raise cimd.McpCimdUnavailable("MCP CIMD DNS pool saturated")

    monkeypatch.setattr(cimd._dns_pool, "submit", boom)
    with pytest.raises(cimd.McpCimdUnavailable):
        cimd.get_url_client(CLIENT_ID)


def test_tls_context_enforces_tls12_floor_and_verification():
    context = cimd._get_tls_context()
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_tls_context_loads_default_cert_store(monkeypatch):
    calls = []
    real_load = ssl.SSLContext.load_default_certs
    monkeypatch.setattr(
        ssl.SSLContext,
        "load_default_certs",
        lambda self, *args, **kwargs: calls.append(1) or real_load(self, *args, **kwargs),
    )
    monkeypatch.setattr(cimd, "_tls_context", None)
    cimd._get_tls_context()
    assert calls == [1]


# --- End-to-end authorize/token flow ---------------------------------------


@pytest.fixture()
def mcp_client(monkeypatch):
    """TestClient with the CIMD network seams mocked and a valid document."""
    _install_network(monkeypatch, response=_json_response(_metadata_body()))
    from routers import mcp_sse as module

    rate_limit_calls = []
    monkeypatch.setattr(
        module._oauth,
        "check_rate_limit_inline",
        lambda key, policy: rate_limit_calls.append((key, policy)),
    )
    module._test_rate_limit_calls = rate_limit_calls

    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app), module


def _authorize_params(**overrides):
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": "opaque-state",
        "code_challenge": CODE_CHALLENGE,
        "code_challenge_method": "S256",
    }
    params.update(overrides)
    return params


def test_cimd_authorize_get_renders_unverified_consent(mcp_client):
    client, _ = mcp_client
    response = client.get("/authorize", params=_authorize_params())
    assert response.status_code == 200
    assert "Unverified third-party app" in response.text
    assert "Client ID host:" in response.text
    assert re.findall(r'<span class="unverified-client-host">([^<]*)</span>', response.text) == ["app.example.com"]
    assert "Example App" in response.text


def test_authorize_errors_never_echo_exception_details(mcp_client, monkeypatch):
    """A backend failure surfaces as a fixed OAuth error body, never its text."""
    client, module = mcp_client

    def boom(_cid):
        raise ValueError("sentinel-secret in stack/credential")

    monkeypatch.setattr(module.mcp_oauth_db, "get_client", boom)
    response = client.get("/authorize", params=_authorize_params())
    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_request",
        "error_description": "Invalid authorization request",
    }
    assert "sentinel-secret" not in response.text

    consent = dict(_authorize_params(), firebase_id_token="not-a-real-token")
    response = client.post("/authorize", data=consent)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
    assert "sentinel-secret" not in response.text

    monkeypatch.setattr(module.mcp_oauth_db, "get_client", lambda cid: None)
    response = client.get("/authorize", params=_authorize_params())
    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_request",
        "error_description": "Invalid authorization request",
    }

    response = client.post("/authorize", data=consent)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
    assert response.json()["error_description"] == "Invalid authorization request"


def test_cimd_authorize_get_missing_scope_defaults_to_read_scopes_only(mcp_client):
    client, _ = mcp_client
    response = client.get("/authorize", params=_authorize_params())
    assert "Read your Omi memories" in response.text
    assert "Search and read your Omi conversations" in response.text
    assert "Read your Omi action items" in response.text
    assert "Read your Omi goals" in response.text
    assert "Read your Omi chat history" in response.text
    assert "Read your Omi screen activity" in response.text
    assert "Read people saved in your Omi account" in response.text
    assert "Create, edit, and delete your Omi memories" not in response.text
    assert "Create, update, and delete your Omi action items" not in response.text


def test_cimd_authorize_get_explicit_write_scope_shown_in_consent(mcp_client):
    client, _ = mcp_client
    response = client.get("/authorize", params=_authorize_params(scope="memories.read memories.write"))
    assert "Create, edit, and delete your Omi memories" in response.text


def test_cimd_consent_post_redirects_with_code_state_and_iss(mcp_client, monkeypatch):
    client, module = mcp_client
    monkeypatch.setattr(module.firebase_admin.auth, "verify_id_token", lambda token: {"uid": "user-cimd"})
    captured = {}

    def fake_grant(uid, client_id, redirect_uri, resource, scopes, code_challenge):
        captured["client_id"] = client_id
        captured["scopes"] = scopes
        return {"id": "grant-1"}, "auth-code-1"

    monkeypatch.setattr(module.mcp_oauth_db, "create_grant_and_authorization_code_if_allowed", fake_grant)
    form = _authorize_params()
    form["firebase_id_token"] = "firebase-token"
    response = client.post("/authorize", data=form)
    assert response.status_code == 200
    params = dict(parse_qsl(urlsplit(response.json()["redirect_uri"]).query))
    assert params["code"] == "auth-code-1"
    assert params["state"] == "opaque-state"
    assert params["iss"] == "https://api.omi.me"
    assert captured["client_id"] == CLIENT_ID
    assert captured["scopes"] == sorted(
        scope for scope in module.mcp_oauth_db.SUPPORTED_SCOPES if scope.endswith(".read")
    )


def test_cimd_metadata_cached_across_get_and_post(mcp_client, monkeypatch):
    client, module = mcp_client
    assert client.get("/authorize", params=_authorize_params()).status_code == 200
    monkeypatch.setattr(module.firebase_admin.auth, "verify_id_token", lambda token: {"uid": "user-cimd"})
    monkeypatch.setattr(
        module.mcp_oauth_db,
        "create_grant_and_authorization_code_if_allowed",
        lambda *a: ({"id": "g"}, "code-1"),
    )
    form = _authorize_params()
    form["firebase_id_token"] = "firebase-token"
    assert client.post("/authorize", data=form).status_code == 200


def test_cimd_token_exchange_uses_metadata_client(mcp_client, monkeypatch):
    client, module = mcp_client
    exchanged = {}
    monkeypatch.setattr(
        module.mcp_oauth_db,
        "exchange_authorization_code_for_tokens",
        lambda code, cid, uri, res, ver: exchanged.update(client_id=cid)
        or {
            "access_token": "at-1",
            "refresh_token": "rt-1",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "memories.read",
        },
    )
    response = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": "auth-code-1",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
        },
    )
    assert response.status_code == 200
    assert response.json()["access_token"] == "at-1"
    assert exchanged["client_id"] == CLIENT_ID


def test_url_form_client_id_rate_limited_per_host_on_all_endpoints(mcp_client, monkeypatch):
    """GET/POST /authorize and POST /token all enforce the URL-form limiter:
    the global backstop first, then a bucket keyed by the normalized CIMD
    host — never the connection peer (the load balancer) or a forwarded
    header."""
    client, module = mcp_client
    calls = module._test_rate_limit_calls

    assert client.get("/authorize", params=_authorize_params()).status_code == 200
    monkeypatch.setattr(module.firebase_admin.auth, "verify_id_token", lambda token: {"uid": "u"})
    monkeypatch.setattr(
        module.mcp_oauth_db,
        "create_grant_and_authorization_code_if_allowed",
        lambda *a: ({"id": "g"}, "code-1"),
    )
    form = _authorize_params()
    form["firebase_id_token"] = "t"
    assert client.post("/authorize", data=form).status_code == 200
    monkeypatch.setattr(module.mcp_oauth_db, "verify_client_auth", lambda *a, **k: True)
    monkeypatch.setattr(
        module.mcp_oauth_db,
        "rotate_refresh_token",
        lambda *a, **k: {
            "access_token": "at",
            "refresh_token": "rt",
            "token_type": "Bearer",
            "expires_in": 1,
            "scope": "memories.read",
        },
    )
    assert (
        client.post(
            "/token",
            data={"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": "omi_rt_x"},
        ).status_code
        == 200
    )
    assert calls == [("global", "mcp:oauth_url_client_global"), ("host:app.example.com", "mcp:oauth_url_client")] * 3


def test_url_form_rate_limit_buckets_are_independent_per_host(mcp_client):
    """Distinct metadata hosts get distinct buckets — one abusive host cannot
    drain the budget of another."""
    client, module = mcp_client
    calls = module._test_rate_limit_calls
    other = "https://other.example.net/oauth/client-metadata.json"
    client.get("/authorize", params=_authorize_params())
    client.get("/authorize", params=_authorize_params(client_id=other))
    host_keys = [key for key, policy in calls if policy == "mcp:oauth_url_client"]
    assert host_keys == ["host:app.example.com", "host:other.example.net"]


def test_url_form_rate_limit_key_normalizes_case_and_path(mcp_client):
    """Host case and differing paths collapse into one bucket — a client_id
    cannot evade its limit by varying either."""
    client, module = mcp_client
    calls = module._test_rate_limit_calls
    variants = [
        "https://APP.example.com/oauth/client-metadata.json",
        "https://app.example.com/other/path.json",
        "https://app.example.com",
    ]
    for variant in variants:
        client.get("/authorize", params=_authorize_params(client_id=variant))
    host_keys = [key for key, policy in calls if policy == "mcp:oauth_url_client"]
    assert host_keys == ["host:app.example.com"] * 3


def test_url_form_rate_limit_malformed_ids_share_one_invalid_bucket(mcp_client):
    """A URL-form client_id that fails ``_parse_metadata_url`` lands in one
    shared invalid bucket — garbage ids never mint unbounded limiter keys."""
    client, module = mcp_client
    calls = module._test_rate_limit_calls
    malformed = [
        "http://app.example.com/meta.json",  # non-HTTPS
        "https://user@app.example.com/meta.json",  # userinfo
        "https://app.example.com/meta.json?x=1",  # query
        "https://app.example.com:8443/meta.json",  # non-443 port
    ]
    for variant in malformed:
        client.get("/authorize", params=_authorize_params(client_id=variant))
    host_keys = [key for key, policy in calls if policy == "mcp:oauth_url_client"]
    assert host_keys == ["host:invalid"] * 4


def test_url_form_rate_limit_denial_is_a_fast_429(mcp_client, monkeypatch):
    client, module = mcp_client

    def deny(key, policy):
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "30"})

    monkeypatch.setattr(module._oauth, "check_rate_limit_inline", deny)
    response = client.get("/authorize", params=_authorize_params())
    assert response.status_code == 429


def test_url_form_rate_limit_429_fires_before_client_lookup(mcp_client, monkeypatch):
    """The limiter sits in front of the metadata lookup: a denied request
    must never reach ``get_client`` or a dial."""
    client, module = mcp_client

    def deny(key, policy):
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "30"})

    monkeypatch.setattr(module._oauth, "check_rate_limit_inline", deny)
    monkeypatch.setattr(
        module.mcp_oauth_db,
        "get_client",
        lambda *a, **k: pytest.fail("client lookup ran after a 429"),
    )
    assert client.get("/authorize", params=_authorize_params()).status_code == 429
    assert (
        client.post(
            "/token",
            data={"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": "omi_rt_x"},
        ).status_code
        == 429
    )


def test_registered_client_id_is_not_url_form_rate_limited(mcp_client, monkeypatch):
    """Registered (non-URL) client ids never touch the URL-form limiter."""
    client, module = mcp_client
    registered = {
        "id": "omi-claude-prod",
        "name": "Claude",
        "registration_mode": "claude_env",
        "allowed_redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "allowed_redirect_uri_prefixes": [],
        "allowed_resources": [module.mcp_oauth_db.MCP_RESOURCE_URL],
        "allowed_scopes": list(module.mcp_oauth_db.SUPPORTED_SCOPES),
        "token_endpoint_auth_method": "none",
        "client_secret_hash": "",
        "disabled_at": None,
    }
    monkeypatch.setattr(
        module.mcp_oauth_db,
        "get_client",
        lambda cid: registered if cid == "omi-claude-prod" else None,
    )
    response = client.get(
        "/authorize",
        params=_authorize_params(client_id="omi-claude-prod", redirect_uri="https://claude.ai/api/mcp/auth_callback"),
    )
    assert response.status_code == 200
    assert module._test_rate_limit_calls == []


def test_cimd_pool_saturation_returns_fast_503_on_authorize(mcp_client, monkeypatch):
    """A saturated CIMD pool is a fast OAuth error — never a parked worker."""
    from utils.executors import ExecutorSaturatedError

    client, module = mcp_client

    def boom(*args, **kwargs):
        raise ExecutorSaturatedError("saturated")

    monkeypatch.setattr(module._oauth.cimd_executor, "submit", boom)
    response = client.get("/authorize", params=_authorize_params())
    assert response.status_code == 503
    assert response.json()["error"] == "temporarily_unavailable"
    assert "Retry-After" in response.headers


def test_cimd_pool_saturation_returns_fast_503_on_token(mcp_client, monkeypatch):
    from utils.executors import ExecutorSaturatedError

    client, module = mcp_client

    def boom(*args, **kwargs):
        raise ExecutorSaturatedError("saturated")

    monkeypatch.setattr(module._oauth.cimd_executor, "submit", boom)
    response = client.post(
        "/token",
        data={"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": "omi_rt_x"},
    )
    assert response.status_code == 503
    assert response.json()["error"] == "temporarily_unavailable"


def test_refresh_grant_returns_503_when_revocation_store_unavailable(mcp_client, monkeypatch):
    """A refresh whose replay-revoke cannot be written to Redis is a
    retryable 503 temporarily_unavailable — never a silent success and never
    a 401."""
    import database.mcp_token_cache as token_cache

    client, module = mcp_client

    def boom(*args, **kwargs):
        raise token_cache.McpTokenStoreUnavailable("redis down")

    monkeypatch.setattr(module.mcp_oauth_db, "rotate_refresh_token", boom)
    response = client.post(
        "/token",
        data={"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": "omi_rt_x"},
    )
    assert response.status_code == 503
    assert response.json()["error"] == "temporarily_unavailable"
    assert "Retry-After" in response.headers


def test_cimd_redirect_uri_must_exactly_match_document(mcp_client):
    client, _ = mcp_client
    response = client.get(
        "/authorize",
        params=_authorize_params(redirect_uri="https://app.example.com/oauth/callback/evil"),
        follow_redirects=False,
    )
    # Mismatched redirect_uri: JSON error, never a redirect.
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_cimd_unknown_document_gives_json_error_never_redirect(mcp_client, monkeypatch):
    _install_network(monkeypatch, response=_raw_http(status=404, reason="Not Found"))
    client, _ = mcp_client
    response = client.get("/authorize", params=_authorize_params(), follow_redirects=False)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_cimd_error_redirect_carries_iss_after_client_and_redirect_validated(mcp_client):
    client, _ = mcp_client
    response = client.get(
        "/authorize",
        params=_authorize_params(resource="https://evil.example/v1/mcp/sse"),
        follow_redirects=False,
    )
    assert response.status_code == 302
    params = dict(parse_qsl(urlsplit(response.headers["location"]).query))
    assert params["error"] == "invalid_target"
    assert params["iss"] == "https://api.omi.me"
    assert params["state"] == "opaque-state"


def test_redirect_clears_conflicting_query_params(mcp_client, monkeypatch):
    """A registered redirect URI carrying stale code/error/state params gets
    them replaced, while unrelated params survive."""
    redirect_with_params = "https://app.example.com/oauth/callback?code=stale&keep=1&error=stale"
    _install_network(monkeypatch, response=_json_response(_metadata_body(redirect_uris=[redirect_with_params])))
    client, module = mcp_client
    monkeypatch.setattr(module.firebase_admin.auth, "verify_id_token", lambda token: {"uid": "user-cimd"})
    monkeypatch.setattr(
        module.mcp_oauth_db,
        "create_grant_and_authorization_code_if_allowed",
        lambda *a: ({"id": "g"}, "fresh-code"),
    )
    form = _authorize_params(redirect_uri=redirect_with_params)
    form["firebase_id_token"] = "firebase-token"
    response = client.post("/authorize", data=form)
    params = dict(parse_qsl(urlsplit(response.json()["redirect_uri"]).query))
    assert params["code"] == "fresh-code"
    assert params["keep"] == "1"
    assert "error" not in params
    assert params["iss"] == "https://api.omi.me"


def test_explicit_scope_not_in_allowed_rejected_via_error_redirect(mcp_client, monkeypatch):
    """Write scopes are granted only when the client is allowed them — a
    restricted client requesting ``memories.write`` gets an invalid_scope
    redirect, not a silent grant."""
    client, module = mcp_client
    registered = {
        "id": "omi-claude-prod",
        "name": "Claude",
        "registration_mode": "claude_env",
        "allowed_redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "allowed_redirect_uri_prefixes": [],
        "allowed_resources": [module.mcp_oauth_db.MCP_RESOURCE_URL],
        "allowed_scopes": ["memories.read"],
        "token_endpoint_auth_method": "none",
        "client_secret_hash": "",
        "disabled_at": None,
    }
    monkeypatch.setattr(module.mcp_oauth_db, "get_client", lambda cid: registered)
    response = client.get(
        "/authorize",
        params=_authorize_params(
            client_id="omi-claude-prod",
            redirect_uri="https://claude.ai/api/mcp/auth_callback",
            scope="memories.write",
        ),
        follow_redirects=False,
    )
    assert response.status_code == 302
    params = dict(parse_qsl(urlsplit(response.headers["location"]).query))
    assert params["error"] == "invalid_scope"
    assert params["iss"] == "https://api.omi.me"


def test_preregistered_client_unaffected_by_cimd_path(mcp_client, monkeypatch):
    client, module = mcp_client
    registered = {
        "id": "omi-claude-prod",
        "name": "Claude",
        "registration_mode": "claude_env",
        "allowed_redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "allowed_redirect_uri_prefixes": [],
        "allowed_resources": [module.mcp_oauth_db.MCP_RESOURCE_URL],
        "allowed_scopes": list(module.mcp_oauth_db.SUPPORTED_SCOPES),
        "token_endpoint_auth_method": "none",
        "client_secret_hash": "",
        "disabled_at": None,
    }
    monkeypatch.setattr(module.mcp_oauth_db, "get_client", lambda cid: registered if cid == "omi-claude-prod" else None)
    response = client.get(
        "/authorize",
        params=_authorize_params(client_id="omi-claude-prod", redirect_uri="https://claude.ai/api/mcp/auth_callback"),
    )
    assert response.status_code == 200
    assert "Unverified third-party app" not in response.text
    assert "Connect <span dir=\"ltr\">Claude</span>" in response.text


def test_authorization_server_metadata_advertises_cimd():
    from utils.mcp_server.metadata import authorization_server_document

    assert authorization_server_document()["client_id_metadata_document_supported"] is True


def test_authorization_server_metadata_advertises_iss_parameter():
    """RFC 9207: authorization responses carry ``iss``; the AS metadata must
    advertise it so clients enforce the binding."""
    from utils.mcp_server.metadata import authorization_server_document

    assert authorization_server_document()["authorization_response_iss_parameter_supported"] is True
