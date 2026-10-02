"""Client ID Metadata Document (CIMD) fetch, validation, and Redis caching.

A URL-form OAuth ``client_id`` is an HTTPS URL pointing at a JSON metadata
document the third-party client publishes itself. Because the document comes
from an arbitrary host on the internet — and the URL is supplied by an
unauthenticated caller — fetching it is both an SSRF surface and a thread
exhaustion vector:

- DNS resolves on the dedicated bounded module-local pool and every single
  resolved address must be unambiguously public unicast (private, loopback,
  link-local, multicast, unspecified, reserved, NAT64 ``64:ff9b::/96`` and
  ``64:ff9b:1::/48``, IPv4-compatible ``::/96``, 6to4 ``2002::/16``, Teredo,
  and any IPv4-mapped/embedded form whose inner address is unsafe all reject
  the whole host — anti-rebinding).
- The TLS connection is pinned to a validated address while hostname
  verification stays on the original host, never follows redirects, tries
  valid addresses IPv4-first, and bounds the response size.
- DNS, connect, and the iterative ~1 KiB reads share ONE hard monotonic
  deadline of ``CIMD_FETCH_TIMEOUT_SECONDS`` — the socket read timeout is
  reset to the remaining budget before every recv so no slow-drip peer can
  hold a worker past the deadline.
- Failures are negative-cached for ``CIMD_NEGATIVE_CACHE_TTL_SECONDS`` keyed
  by the canonical URL so cache-busting retries back off.

Only a whitelist of validated fields is ever cached or returned — the raw
response is discarded. ``_resolver``/``_dial`` keyword hooks exist strictly
for tests; production callers never pass them, so loopback stays rejected.
"""

import concurrent.futures
import hashlib
import http.client
import io
import ipaddress
import json
import logging
import socket
import ssl
import threading
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Tuple, cast
from urllib.parse import urlsplit

import database.mcp_cache_integrity as mcp_cache_integrity
import database.redis_db as redis_db
from config.mcp_scopes import MCP_FULL_ACCESS_SCOPES

logger = logging.getLogger(__name__)

CIMD_MAX_URL_CHARS = 2048
CIMD_MAX_BODY_BYTES = 16 * 1024
CIMD_FETCH_TIMEOUT_SECONDS = 3.0
CIMD_NEGATIVE_CACHE_TTL_SECONDS = 60
CIMD_MAX_REDIRECT_URIS = 20
CIMD_MAX_CLIENT_NAME_CHARS = 64
CIMD_CACHE_TTL_MAX_SECONDS = 3600
_CIMD_CACHE_KEY_PREFIX = "mcp:cimd:"
_CIMD_NEG_CACHE_KEY_PREFIX = "mcp:cimd:neg:"
_CIMD_INTEGRITY_TAG = "cimd"

_CIMD_READ_CHUNK_BYTES = 1024
# Response head (status line + headers) allowance on top of the body bound.
_CIMD_MAX_HEAD_BYTES = 16 * 1024
_CIMD_MAX_WIRE_BYTES = _CIMD_MAX_HEAD_BYTES + CIMD_MAX_BODY_BYTES + 64

_NATIVE_LOOPBACK_HOSTS = {"localhost"}
_NATIVE_LOOPBACK_SUFFIX = ".localhost"

_NAT64_WELL_KNOWN_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")
_NAT64_LOCAL_USE_PREFIX = ipaddress.IPv6Network("64:ff9b:1::/48")
_6TO4_PREFIX = ipaddress.IPv6Network("2002::/16")
_IPV4_COMPATIBLE_PREFIX = ipaddress.IPv6Network("::/96")
_SITE_LOCAL_PREFIX = ipaddress.IPv6Network("fec0::/10")


class McpCimdUnavailable(RuntimeError):
    """The bounded CIMD fetch path cannot take more work right now.

    The OAuth layer maps this to a fast ``temporarily_unavailable``/503 —
    never queueing unauthenticated network fetches on shared pools and never
    negative-caching a capacity signal.
    """


_CIMD_DNS_WORKERS = 4
_CIMD_DNS_QUEUE = 8


class _BoundedPool:
    """Thread pool whose submit fails fast once workers plus queue are full.

    Kept module-local (not ``utils.executors``) because ``database`` must not
    import ``utils`` — and because an unauthenticated caller must never grow
    an unbounded DNS work queue on a shared pool."""

    def __init__(self, workers: int, queue: int) -> None:
        self._slots = threading.BoundedSemaphore(workers + queue)
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cimd-dns")

    def submit(self, fn: Callable[..., Any], *args: Any) -> "concurrent.futures.Future[Any]":
        if not self._slots.acquire(blocking=False):
            raise McpCimdUnavailable("MCP CIMD DNS pool saturated")
        try:
            future = self._pool.submit(fn, *args)
        except BaseException:
            self._slots.release()
            raise
        future.add_done_callback(lambda _done: self._slots.release())
        return future


_dns_pool = _BoundedPool(_CIMD_DNS_WORKERS, _CIMD_DNS_QUEUE)


def parse_metadata_url(client_id: str) -> Optional[Tuple[str, str]]:
    """Return ``(ascii_host, request_target)`` for a safe HTTPS metadata URL.

    Query strings are rejected outright: they cannot change which client a
    document describes but would let an attacker mint unbounded distinct
    fetch/cache identities for one host (cache-busting).
    """
    if (
        len(client_id) > CIMD_MAX_URL_CHARS
        or "\\" in client_id
        or "?" in client_id
        or "#" in client_id
        or not client_id.isascii()
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in client_id)
    ):
        return None
    try:
        parts = urlsplit(client_id)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() != "https" or parts.fragment or parts.query or parts.username or parts.password:
        return None
    if port is not None and port != 443:
        return None
    host = parts.hostname
    if not host or "@" in (parts.netloc.rsplit(":", 1)[0] if parts.netloc else ""):
        return None
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        return None
    if not ascii_host or any(ord(char) < 0x20 or ord(char) == 0x7F for char in ascii_host):
        return None
    return ascii_host, parts.path or "/"


def _is_global_unicast(address: Any) -> bool:
    # ``is_global`` alone is not sufficient: IANA marks multicast ranges
    # globally reachable, so every non-unicast class gets an explicit check.
    return (
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
        and not address.is_loopback
        and not address.is_private
        and not address.is_link_local
    )


def _is_safe_resolved_address(raw: str) -> bool:
    """A resolved address is usable only when it — or the IPv4 embedded in a
    transition form — is unambiguously public unicast."""
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped
        if mapped is not None:
            return _is_global_unicast(mapped)
        if (
            address in _NAT64_WELL_KNOWN_PREFIX
            or address in _NAT64_LOCAL_USE_PREFIX
            or address in _6TO4_PREFIX
            or address in _IPV4_COMPATIBLE_PREFIX
            or address in _SITE_LOCAL_PREFIX
            or address.sixtofour is not None
            or address.teredo is not None
        ):
            return False
        return _is_global_unicast(address)
    return _is_global_unicast(address)


def _ipv4_first(addresses: List[str]) -> List[str]:
    """Order validated addresses IPv4-first so a working v4 path wins over a
    possibly blackholed v6 route inside the shared deadline."""

    def _is_v6(raw: str) -> bool:
        try:
            return isinstance(ipaddress.ip_address(raw), ipaddress.IPv6Address)
        except ValueError:
            return False

    return sorted(addresses, key=_is_v6)


def _resolve_public_addresses(hostname: str, deadline: float) -> List[str]:
    """Resolve ``hostname`` on the dedicated bounded DNS pool and keep the
    addresses only when every single one passes the vector checks — a single
    unsafe answer rejects the whole host (anti-rebinding). IPv4 sorts first."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return []
    future = _dns_pool.submit(socket.getaddrinfo, hostname, 443, 0, socket.SOCK_STREAM)
    try:
        infos = future.result(timeout=remaining)
    except concurrent.futures.TimeoutError:
        return []
    except (socket.gaierror, OSError, UnicodeError):
        return []
    except Exception as exc:
        logger.warning("MCP CIMD DNS resolution failed: %s", type(exc).__name__)
        return []
    addresses = sorted({info[4][0] for info in infos if info and info[4]})
    if not addresses or any(not _is_safe_resolved_address(raw) for raw in addresses):
        return []
    return _ipv4_first(addresses)


_tls_context: Optional[ssl.SSLContext] = None
_tls_context_lock = threading.Lock()


def _get_tls_context() -> ssl.SSLContext:
    """Lazily load the default verifying context — importing this module (and
    its cert store I/O) must stay cheap."""
    global _tls_context
    if _tls_context is None:
        with _tls_context_lock:
            if _tls_context is None:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.load_default_certs()
                _tls_context = context
    return _tls_context


def _dial_tls(address: str, hostname: str, deadline: float) -> ssl.SSLSocket:
    """TCP-connect to the VALIDATED ``address``:443 and complete TLS with SNI
    and certificate/hostname verification for ``hostname`` (never the IP).
    ``deadline`` is the absolute monotonic deadline shared with the caller:
    the socket timeout is re-anchored to the remaining budget immediately
    before ``wrap_socket`` so a stalled handshake cannot overrun it."""
    sock = socket.create_connection((address, 443), timeout=max(0.0, deadline - time.monotonic()))
    try:
        context = _get_tls_context()
        sock.settimeout(max(0.0, deadline - time.monotonic()))
        return context.wrap_socket(sock, server_hostname=hostname)
    except BaseException:
        sock.close()
        raise


def _header_content_length(head: bytes) -> Optional[int]:
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            try:
                return max(0, int(value.strip()))
            except ValueError:
                return None
    return None


def _read_response(tls: ssl.SSLSocket, hostname: str, target: str, deadline: float) -> Optional[bytes]:
    """Send one GET and read the raw response in ~1 KiB chunks, each recv
    bounded by the remaining shared deadline so no single read can overrun
    it. A peer that stalls mid-response ends usable input here — whatever
    arrived is parsed (or rejected) downstream."""
    request = (
        f"GET {target} HTTP/1.1\r\n"
        f"Host: {hostname}\r\n"
        "Accept: application/json\r\n"
        "User-Agent: omi-mcp-oauth/1.0\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    buf = bytearray()
    head_end = -1
    content_length: Optional[int] = None
    try:
        tls.settimeout(max(0.0, deadline - time.monotonic()))
        tls.sendall(request)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            tls.settimeout(remaining)
            try:
                chunk = tls.recv(_CIMD_READ_CHUNK_BYTES)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            if len(buf) > _CIMD_MAX_WIRE_BYTES:
                return None
            if head_end < 0:
                head_end = buf.find(b"\r\n\r\n")
                if head_end >= 0:
                    content_length = _header_content_length(bytes(buf[:head_end]))
            if content_length is not None and len(buf) - (head_end + 4) >= content_length:
                break
    except (ssl.SSLError, OSError):
        return None
    if head_end < 0:
        return None
    return bytes(buf)


class _PreloadedSocket:
    """Feeds already-buffered response bytes into ``http.client``'s parser —
    all real socket I/O happened under the shared deadline."""

    def __init__(self, data: bytes):
        self._stream = io.BytesIO(data)

    def makefile(self, *args: Any, **kwargs: Any) -> io.BytesIO:
        return self._stream


def _parse_metadata_response(raw: bytes) -> Optional[Tuple[Dict[str, Any], int]]:
    """Parse the buffered response: 200 + application/json + bounded JSON
    object body, or ``None``. Returns ``(document, cache_ttl_seconds)``."""
    try:
        response = http.client.HTTPResponse(cast(socket.socket, _PreloadedSocket(raw)), method="GET")
        response.begin()
        if response.status != 200:
            return None
        content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return None
        body = response.read(CIMD_MAX_BODY_BYTES + 1)
        if len(body) > CIMD_MAX_BODY_BYTES:
            return None
        document = json.loads(body.decode("utf-8"))
        if not isinstance(document, dict):
            return None
        return document, _cache_ttl_seconds(response.getheader("Cache-Control"))
    except Exception:
        return None


def _fetch_document(
    hostname: str,
    target: str,
    *,
    _resolver: Optional[Callable[[str, float], List[str]]] = None,
    _dial: Optional[Callable[[str, str, float], Any]] = None,
) -> Optional[Tuple[Dict[str, Any], int]]:
    """Fetch the metadata document under ONE hard monotonic deadline shared by
    DNS, connect, and the iterative body reads; every validated address is
    tried IPv4-first until one serves a usable response or the deadline ends.

    ``_resolver``/``_dial`` are test-only hooks — production callers never
    pass them, so the SSRF address checks can never be bypassed in prod."""
    deadline = time.monotonic() + CIMD_FETCH_TIMEOUT_SECONDS
    resolver = _resolver or _resolve_public_addresses
    dial = _dial or _dial_tls
    try:
        addresses = resolver(hostname, deadline)
    except McpCimdUnavailable:
        raise
    except Exception as exc:
        logger.warning("MCP CIMD address resolution failed: %s", type(exc).__name__)
        return None
    for address in addresses:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        raw = None
        tls = None
        try:
            tls = dial(address, hostname, deadline)
            raw = _read_response(tls, hostname, target, deadline)
        except Exception as exc:
            logger.warning("MCP CIMD fetch failed: %s", type(exc).__name__)
        finally:
            if tls is not None:
                try:
                    tls.close()
                except Exception:
                    pass
        if raw is None:
            continue
        parsed = _parse_metadata_response(raw)
        if parsed is not None:
            return parsed
    return None


def _cache_ttl_seconds(cache_control: Optional[str]) -> int:
    """Honor ``max-age`` and the no-caching directives, clamped at one hour.
    ``no-store``, ``no-cache`` (must revalidate), and ``private`` (not for a
    shared/server-side cache) all disable caching entirely."""
    if not cache_control:
        return CIMD_CACHE_TTL_MAX_SECONDS
    directives = {item.strip().lower() for item in cache_control.split(",")}
    if {"no-store", "no-cache", "private"} & directives:
        return 0
    for directive in directives:
        if directive.startswith("max-age="):
            try:
                max_age = int(directive.split("=", 1)[1].strip().strip('"'))
            except ValueError:
                return 0
            if max_age <= 0:
                return 0
            return min(max_age, CIMD_CACHE_TTL_MAX_SECONDS)
    return CIMD_CACHE_TTL_MAX_SECONDS


def _is_native_loopback_host(host: str) -> bool:
    lowered = host.lower()
    if lowered in _NATIVE_LOOPBACK_HOSTS or lowered.endswith(_NATIVE_LOOPBACK_SUFFIX):
        return True
    try:
        address = ipaddress.ip_address(lowered.strip("[]"))
    except ValueError:
        return False
    return address.is_loopback


def _valid_cimd_redirect_uri(uri: object) -> bool:
    """CIMD redirect URIs are exact-match only: HTTPS, or HTTP strictly on a
    loopback/localhost host for native PKCE apps. No userinfo, no fragment."""
    if not isinstance(uri, str) or not uri or len(uri) > CIMD_MAX_URL_CHARS or "\\" in uri:
        return False
    try:
        parts = urlsplit(uri)
        parts.port
    except ValueError:
        return False
    if parts.fragment or parts.username or parts.password or not parts.hostname:
        return False
    scheme = parts.scheme.lower()
    if scheme == "https":
        return True
    return scheme == "http" and _is_native_loopback_host(parts.hostname)


def sanitize_client_name(value: object) -> str:
    """NFKC-normalize, strip bidi/control/format characters, clamp to 64
    printable characters so a hostile ``client_name`` cannot spoof or inject."""
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    cleaned = "".join(
        char for char in normalized if char.isprintable() and not unicodedata.category(char).startswith("C")
    )
    return cleaned.strip()[:CIMD_MAX_CLIENT_NAME_CHARS]


def _display_name_for(metadata: Dict[str, Any], hostname: str) -> str:
    """Consent-screen name: every self-published ``client_name`` is suffixed
    with the verified ASCII host — a near-homoglyph like Cyrillic "Сlaude"
    slips past any exact-match brand check, so the suffix is unconditional.
    The host itself is never doubled when it is already the fallback name."""
    name = metadata["client_name"] or hostname
    if name == hostname:
        return name
    return f"{name} ({hostname})"


def _validated_metadata(document: Dict[str, Any], client_id: str) -> Optional[Dict[str, Any]]:
    """Reduce a fetched (or cached) document to the whitelisted fields the
    authorization flow may trust, or ``None`` when anything fails."""
    if document.get("client_id") != client_id:
        return None
    redirect_uris = document.get("redirect_uris")
    if (
        not isinstance(redirect_uris, list)
        or not redirect_uris
        or len(redirect_uris) > CIMD_MAX_REDIRECT_URIS
        or any(not isinstance(uri, str) for uri in redirect_uris)
        or len(set(redirect_uris)) != len(redirect_uris)
        or any(not _valid_cimd_redirect_uri(uri) for uri in redirect_uris)
    ):
        return None
    auth_method = document.get("token_endpoint_auth_method")
    if auth_method is not None and auth_method != "none":
        return None
    if document.get("client_secret") or document.get("client_secret_hash") or document.get("client_secret_expires_at"):
        return None
    challenge_methods = document.get("code_challenge_methods_supported")
    if challenge_methods is not None and (not isinstance(challenge_methods, list) or "S256" not in challenge_methods):
        return None
    return {
        "client_id": client_id,
        "client_name": sanitize_client_name(document.get("client_name")),
        "redirect_uris": [str(uri) for uri in redirect_uris],
    }


def _cache_key(client_id: str) -> str:
    return f"{_CIMD_CACHE_KEY_PREFIX}{hashlib.sha256(client_id.encode('utf-8')).hexdigest()}"


def _neg_cache_key(canonical_url: str) -> str:
    return f"{_CIMD_NEG_CACHE_KEY_PREFIX}{hashlib.sha256(canonical_url.encode('utf-8')).hexdigest()}"


def _read_cached(client_id: str) -> Optional[Dict[str, Any]]:
    if not mcp_cache_integrity.integrity_available():
        return None
    try:
        raw = redis_db.r.get(_cache_key(client_id))
    except Exception as exc:
        logger.warning("MCP CIMD cache read failed: %s", type(exc).__name__)
        return None
    if raw is None:
        return None
    # The HMAC tag is checked before any field is trusted: an unsigned or
    # tampered cached document can never reach the consent screen. The same
    # field validation as a fresh document then applies on top.
    cached = mcp_cache_integrity.loads_verified(raw, _CIMD_INTEGRITY_TAG)
    if cached is None:
        return None
    return _validated_metadata(cached, client_id)


def _write_cache(client_id: str, metadata: Dict[str, Any], ttl_seconds: int) -> None:
    if ttl_seconds <= 0 or not mcp_cache_integrity.integrity_available():
        return
    blob = mcp_cache_integrity.dumps_signed(metadata, _CIMD_INTEGRITY_TAG)
    if blob is None:
        return
    try:
        redis_db.r.set(_cache_key(client_id), blob, ex=ttl_seconds)
    except Exception as exc:
        logger.warning("MCP CIMD cache write failed: %s", type(exc).__name__)


def _negative_cached(canonical_url: str) -> bool:
    try:
        return bool(redis_db.r.get(_neg_cache_key(canonical_url)))
    except Exception as exc:
        logger.warning("MCP CIMD negative-cache read failed: %s", type(exc).__name__)
        return False


def _negative_cache(canonical_url: str) -> None:
    """Suppress repeat fetches for a URL that just failed for
    ``CIMD_NEGATIVE_CACHE_TTL_SECONDS`` — a failing host must not get a fresh
    3-second fetch on every unauthenticated request."""
    try:
        redis_db.r.set(_neg_cache_key(canonical_url), "1", ex=CIMD_NEGATIVE_CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.warning("MCP CIMD negative-cache write failed: %s", type(exc).__name__)


def get_url_client(client_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a URL-form client id to a client record, or ``None``.

    Non-HTTPS URLs, URLs with query/fragment components, unreachable hosts,
    and invalid documents all return ``None`` — an unknown client — without
    any network access unless the URL itself passed the SSRF checks above.
    May raise ``McpCimdUnavailable`` when the bounded fetch path is saturated.
    """
    parsed = parse_metadata_url(client_id)
    if parsed is None:
        return None
    hostname, target = parsed
    canonical_url = f"https://{hostname}{target}"

    metadata = _read_cached(client_id)
    if metadata is None:
        if _negative_cached(canonical_url):
            return None
        fetched = _fetch_document(hostname, target)
        if fetched is None:
            _negative_cache(canonical_url)
            return None
        document, ttl_seconds = fetched
        metadata = _validated_metadata(document, client_id)
        if metadata is None:
            _negative_cache(canonical_url)
            return None
        _write_cache(client_id, metadata, ttl_seconds)

    return {
        "id": client_id,
        "name": _display_name_for(metadata, hostname),
        "registration_mode": "client_id_metadata_document",
        "allowed_redirect_uris": metadata["redirect_uris"],
        "allowed_redirect_uri_prefixes": [],
        "allowed_resources": None,  # filled by caller with the MCP audience
        "allowed_scopes": list(MCP_FULL_ACCESS_SCOPES),
        "token_endpoint_auth_method": "none",
        "client_secret_hash": "",
        "disabled_at": None,
        "metadata_url": client_id,
        "metadata_host": hostname,
    }
