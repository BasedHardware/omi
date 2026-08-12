"""UnifiedPush send channel (ADR-0011 on-prem push).

Delivers a :class:`PushMessage` by POSTing it to each of the user's registered UnifiedPush
endpoints (self-hosted ntfy). The endpoint is opaque to us; the app decodes the JSON body and
reproduces the same dispatch it does for an FCM message, so the payload carries the FCM-shaped
fields (``notification``/``data``/``tag``/``priority``/``is_background``).

Dead-endpoint cleanup mirrors the FCM invalid-token taxonomy: HTTP 404/410 (Gone) → the endpoint
is permanently gone → drop it; any other non-2xx is transient (log only). When the endpoint carries
a WebPush key set (``p256dh``/``auth``) the body is encrypted per RFC 8291 and **hex-armored** before
POST — ntfy is a text-only transport (it turns any non-UTF8 body into an attachment), so the binary
ciphertext is sent as a lowercase-hex UTF-8 string and the app hex-decodes it before decrypting. One
ciphertext per recipient; an endpoint without keys (pre-encryption client) falls back to plaintext JSON.

Addressing: when ``UNIFIEDPUSH_INTERNAL_BASE_URL`` is set the backend keeps only the *path* of the
stored endpoint and POSTs to ``${base}${path}`` — so a phone that registered the push server under
its host-facing URL is reachable from a backend that only has an internal name for the same server,
without giving the backend outbound egress. Unset → POST the stored endpoint verbatim.
"""

import asyncio
import json
import logging
import os
from typing import List, Optional
from urllib.parse import urlsplit

import httpx

import database.notifications as notification_db
from database.notifications import UnifiedPushEndpoint
from utils.executors import db_executor, push_crypto_executor, run_blocking
from utils.http_client import get_ntfy_client
from utils.push import webpush_encryption
from utils.push.base import PushMessage

logger = logging.getLogger(__name__)

# HTTP statuses that mean the endpoint is permanently gone (parity with PERMANENT_FAILURE_CODES).
_DEAD_ENDPOINT_STATUSES = frozenset({404, 410})
_PLAINTEXT_HEADERS = {'Content-Type': 'application/json'}
# Encrypted body is hex-armored UTF-8 text (see module docstring) so ntfy carries it as a normal
# message rather than rejecting it as a binary attachment.
_ENCRYPTED_HEADERS = {'Content-Type': 'text/plain'}

# Lazy process-wide sync client for the synchronous send seam (used on sync request paths and in
# executor worker threads). The async seam uses the pooled get_ntfy_client() instead.
_sync_client: Optional[httpx.Client] = None


def _get_sync_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(timeout=httpx.Timeout(10.0, connect=2.0))
    return _sync_client


def _internal_base() -> Optional[str]:
    value = os.getenv('UNIFIEDPUSH_INTERNAL_BASE_URL')
    return value.strip() if value and value.strip() else None


def _target_url(endpoint: str) -> str:
    """Resolve the URL to POST to via the operator-configured internal push server.

    Fail closed: ``UNIFIEDPUSH_INTERNAL_BASE_URL`` is REQUIRED. The stored ``endpoint`` is
    user-registered, so POSTing to it verbatim would let an authenticated user turn delivery into
    an SSRF primitive. We keep only the endpoint's *path* and send it to the trusted internal base;
    without that base configured we refuse to send rather than fetch a user-controlled URL.
    """
    base = _internal_base()
    if not base:
        raise ValueError(
            'UNIFIEDPUSH_INTERNAL_BASE_URL is not set; refusing to POST to a user-registered '
            'endpoint verbatim (SSRF). Configure the internal push-server base URL.'
        )
    parts = urlsplit(endpoint)
    path = parts.path or '/'
    if parts.query:
        path = f'{path}?{parts.query}'
    return base.rstrip('/') + path


def render_payload(msg: PushMessage) -> dict:
    """Serialize a neutral PushMessage into the JSON body the app expects.

    ``notification`` is present only for a visible message; a data-only/silent message omits it
    (the app then dispatches purely on ``data``), mirroring the FCM ``notification is None`` rule.
    """
    payload: dict = {
        'tag': msg.tag,
        'priority': msg.priority,
        'is_background': msg.is_background,
        'data': msg.data or {},
    }
    if not msg.is_data_only:
        payload['notification'] = {'title': msg.title, 'body': msg.body}
    return payload


def _classify(endpoint_url: str, status: Optional[int], dead: List[str]) -> bool:
    """Return True if the send succeeded; record permanently-dead endpoint URLs for cleanup."""
    if status is None:
        return False
    if status in _DEAD_ENDPOINT_STATUSES:
        dead.append(endpoint_url)
        logger.error('Dead UnifiedPush endpoint removed - status %s: %s', status, endpoint_url)
        return False
    if 200 <= status < 300:
        return True
    logger.error('UnifiedPush send failed - status %s: %s', status, endpoint_url)
    return False


def _encode_for(endpoint: UnifiedPushEndpoint, plaintext: bytes) -> tuple[bytes, dict]:
    """Return the (body, headers) to POST for one endpoint: RFC 8291-encrypted then hex-armored when
    it registered a WebPush key set, else the plaintext JSON (back-compat with pre-encryption clients).
    """
    if endpoint.p256dh and endpoint.auth:
        ciphertext = webpush_encryption.encrypt(plaintext, p256dh=endpoint.p256dh, auth=endpoint.auth)
        # Hex-armor so ntfy carries the ciphertext as UTF-8 text; the app hex-decodes then decrypts.
        return ciphertext.hex().encode('utf-8'), _ENCRYPTED_HEADERS
    return plaintext, _PLAINTEXT_HEADERS


def _post_sync(url: str, body: bytes, headers: dict) -> Optional[int]:
    try:
        return _get_sync_client().post(url, content=body, headers=headers).status_code
    except Exception as e:  # network error: transient, keep the endpoint
        logger.error('UnifiedPush POST error to %s: %s', url, e)
        return None


async def _post_async(url: str, body: bytes, headers: dict) -> Optional[int]:
    try:
        response = await get_ntfy_client().post(url, content=body, headers=headers)
        return response.status_code
    except Exception as e:
        logger.error('UnifiedPush POST error to %s: %s', url, e)
        return None


def _send_one_sync(endpoint: UnifiedPushEndpoint, plaintext: bytes) -> Optional[int]:
    try:
        # Resolve the target inside the guard: a malformed key set OR a fail-closed addressing
        # error (no UNIFIEDPUSH_INTERNAL_BASE_URL) skips just this endpoint, never aborts the
        # fan-out and never POSTs to a user-controlled URL.
        target = _target_url(endpoint.url)
        body, headers = _encode_for(endpoint, plaintext)
    except ValueError as e:
        logger.error('UnifiedPush skipping endpoint %s: %s', endpoint.url, e)
        return None
    return _post_sync(target, body, headers)


async def _send_one_async(endpoint: UnifiedPushEndpoint, plaintext: bytes) -> Optional[int]:
    try:
        # Fail-closed target resolution before any work (see _send_one_sync): a missing internal
        # base URL skips this endpoint instead of POSTing a user-registered URL verbatim (SSRF).
        target = _target_url(endpoint.url)
        if endpoint.p256dh and endpoint.auth:
            # RFC 8291 encryption is CPU-bound (P-256 keygen + ECDH + AES): offload it so a fan-out
            # (asyncio.gather over N endpoints) never runs the crypto on the event loop, and cap the
            # in-flight crypto at push_crypto_executor's worker count rather than one job per recipient.
            body, headers = await run_blocking(push_crypto_executor, _encode_for, endpoint, plaintext)
        else:
            # Plaintext fallback (pre-encryption client): trivial, no reason to bounce off the loop.
            body, headers = _encode_for(endpoint, plaintext)
    except ValueError as e:
        logger.error('UnifiedPush skipping endpoint %s: %s', endpoint.url, e)
        return None
    return await _post_async(target, body, headers)


def send_to_user(user_id: str, msg: PushMessage, *, endpoints: Optional[List[UnifiedPushEndpoint]] = None) -> int:
    """Send to all of a user's UnifiedPush endpoints (sync). Returns successful-send count."""
    if endpoints is None:
        endpoints = notification_db.get_all_endpoints(user_id)
    if not endpoints:
        logger.info('No UnifiedPush endpoints found for user %s', user_id)
        return 0

    plaintext = json.dumps(render_payload(msg)).encode('utf-8')
    dead: List[str] = []
    success = sum(1 for ep in endpoints if _classify(ep.url, _send_one_sync(ep, plaintext), dead))

    if dead:
        notification_db.remove_bulk_endpoints(dead)
    logger.info('UnifiedPush send: %s/%s successful', success, len(endpoints))
    return success


async def send_to_user_async(
    user_id: str, msg: PushMessage, *, endpoints: Optional[List[UnifiedPushEndpoint]] = None
) -> int:
    """Async counterpart: token read and dead-endpoint cleanup are offloaded to the DB pool."""
    if endpoints is None:
        endpoints = await run_blocking(db_executor, notification_db.get_all_endpoints, user_id)
    if not endpoints:
        logger.info('No UnifiedPush endpoints found for user %s', user_id)
        return 0

    plaintext = json.dumps(render_payload(msg)).encode('utf-8')
    statuses = await asyncio.gather(*[_send_one_async(ep, plaintext) for ep in endpoints])

    dead: List[str] = []
    success = sum(1 for ep, status in zip(endpoints, statuses) if _classify(ep.url, status, dead))

    if dead:
        await run_blocking(db_executor, notification_db.remove_bulk_endpoints, dead)
    logger.info('UnifiedPush send: %s/%s successful', success, len(endpoints))
    return success


async def send_bulk(endpoints: List[UnifiedPushEndpoint], msg: PushMessage) -> None:
    """Broadcast a message to many endpoints (bulk daily notification); dead endpoints are dropped."""
    if not endpoints:
        return

    plaintext = json.dumps(render_payload(msg)).encode('utf-8')
    statuses = await asyncio.gather(*[_send_one_async(ep, plaintext) for ep in endpoints])

    dead: List[str] = []
    success = sum(1 for ep, status in zip(endpoints, statuses) if _classify(ep.url, status, dead))

    if dead:
        await run_blocking(db_executor, notification_db.remove_bulk_endpoints, dead)
    logger.info('UnifiedPush bulk send: %s/%s successful', success, len(endpoints))
