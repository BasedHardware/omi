"""Client ID Metadata Document (CIMD) fetch, validation, and Redis caching.

A URL-form OAuth ``client_id`` is an HTTPS URL pointing at a JSON metadata
document the third-party client publishes itself. Because the document comes
from an arbitrary host on the internet, fetching it is an SSRF surface: this
module resolves DNS itself, requires EVERY resolved address to be globally
routable, pins the TLS connection to a resolved public IP while keeping
hostname verification on the original host, never follows redirects, and
bounds the response size. Only a whitelist of validated fields is ever cached
or returned — the raw response is discarded.
"""

import hashlib
import ipaddress
import json
import logging
import socket
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import urllib3

import database.mcp_cache_integrity as mcp_cache_integrity
import database.redis_db as redis_db
from config.mcp_scopes import MCP_FULL_ACCESS_SCOPES

logger = logging.getLogger(__name__)

CIMD_MAX_URL_CHARS = 2048
CIMD_MAX_BODY_BYTES = 16 * 1024
CIMD_FETCH_TIMEOUT_SECONDS = 3
CIMD_MAX_REDIRECT_URIS = 20
CIMD_MAX_CLIENT_NAME_CHARS = 64
CIMD_CACHE_TTL_MAX_SECONDS = 3600
_CIMD_CACHE_KEY_PREFIX = "mcp:cimd:"

_NATIVE_LOOPBACK_HOSTS = {"localhost"}
_NATIVE_LOOPBACK_SUFFIX = ".localhost"


def is_url_form_client_id(client_id: object) -> bool:
    """URL-form client ids contain a path separator and are never valid
    Firestore document ids, so the registry lookup must branch before
    ``.document(client_id)`` is attempted."""
    return isinstance(client_id, str) and "/" in client_id


def _parse_metadata_url(client_id: str) -> Optional[Tuple[str, str]]:
    """Return ``(ascii_host, request_target)`` for a safe HTTPS metadata URL."""
    if (
        len(client_id) > CIMD_MAX_URL_CHARS
        or "\\" in client_id
        or not client_id.isascii()
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in client_id)
    ):
        return None
    try:
        parts = urlsplit(client_id)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() != "https" or parts.fragment or parts.username or parts.password:
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
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    return ascii_host, target


def _resolved_public_addresses(hostname: str) -> List[str]:
    """Resolve ``hostname`` and return its addresses only when every single
    one is globally routable — a single private/loopback/link-local/multicast
    or non-global IPv4-mapped result rejects the whole host (anti-rebinding)."""
    try:
        infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError, UnicodeError):
        return []
    addresses = sorted({info[4][0] for info in infos if info and info[4]})
    if not addresses:
        return []
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            return []
        # ``is_global`` does not exclude multicast (IANA marks it globally
        # reachable), so multicast/reserved/unspecified get explicit checks.
        mapped = getattr(address, "ipv4_mapped", None)
        if mapped is not None:
            if not mapped.is_global or mapped.is_multicast or mapped.is_reserved or mapped.is_unspecified:
                return []
            continue
        if not address.is_global or address.is_multicast or address.is_reserved or address.is_unspecified:
            return []
    return addresses


def _fetch_document(hostname: str, target: str) -> Optional[Tuple[Dict[str, Any], int]]:
    """Fetch the metadata document pinned to a resolved public IP.

    Returns ``(document, cache_ttl_seconds)`` or ``None`` on any failure."""
    addresses = _resolved_public_addresses(hostname)
    if not addresses:
        return None
    pool = None
    response = None
    try:
        pool = urllib3.HTTPSConnectionPool(
            addresses[0],
            port=443,
            server_hostname=hostname,
            assert_hostname=hostname,
            cert_reqs="CERT_REQUIRED",
            timeout=urllib3.Timeout(total=CIMD_FETCH_TIMEOUT_SECONDS),
            retries=False,
        )
        response = pool.request(
            "GET",
            target,
            headers={
                "Host": hostname,
                "Accept": "application/json",
                "User-Agent": "omi-mcp-oauth/1.0",
            },
            redirect=False,
            preload_content=False,
        )
        if response.status != 200:
            return None
        content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return None
        body = response.read(CIMD_MAX_BODY_BYTES + 1)
        if len(body) > CIMD_MAX_BODY_BYTES:
            return None
        document = json.loads(body.decode("utf-8"))
        if not isinstance(document, dict):
            return None
        return document, _cache_ttl_seconds(response.headers.get("Cache-Control"))
    except Exception as exc:
        logger.warning("MCP CIMD fetch failed: %s", type(exc).__name__)
        return None
    finally:
        if response is not None:
            try:
                response.release_conn()
            except Exception:
                pass
            try:
                response.close()
            except Exception:
                pass
        if pool is not None:
            try:
                pool.close()
            except Exception:
                pass


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
    cached = mcp_cache_integrity.loads_verified(raw)
    if cached is None:
        return None
    return _validated_metadata(cached, client_id)


def _write_cache(client_id: str, metadata: Dict[str, Any], ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    blob = mcp_cache_integrity.dumps_signed(metadata)
    if blob is None:
        return
    try:
        redis_db.r.set(_cache_key(client_id), blob, ex=ttl_seconds)
    except Exception as exc:
        logger.warning("MCP CIMD cache write failed: %s", type(exc).__name__)


def get_url_client(client_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a URL-form client id to a client record, or ``None``.

    Non-HTTPS URLs, unsafe URLs, unreachable hosts, and invalid documents all
    return ``None`` — an unknown client — without any network access unless the
    URL itself passed the SSRF checks above.
    """
    parsed = _parse_metadata_url(client_id)
    if parsed is None:
        return None
    hostname, target = parsed

    metadata = _read_cached(client_id)
    if metadata is None:
        fetched = _fetch_document(hostname, target)
        if fetched is None:
            return None
        document, ttl_seconds = fetched
        metadata = _validated_metadata(document, client_id)
        if metadata is None:
            return None
        _write_cache(client_id, metadata, ttl_seconds)

    return {
        "id": client_id,
        "name": metadata["client_name"] or hostname,
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
