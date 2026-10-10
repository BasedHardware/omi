"""Signing secrets for webhook destinations (#20939).

Two kinds of destination exist and each keeps its secret where its URL already lives:

- Developer webhooks (``routers/users.py``) store their URLs in Redis under
  ``users:{uid}:developer:webhook:*``; the signing record sits beside them. One record signs
  every webhook type the user has configured.
- Integration apps store ``external_integration.webhook_url`` on the app document. The signing
  record is a subcollection document (like ``api_keys``), never a field on the app document,
  because that document is served to every user through the marketplace, the app cache and
  ``GET /v1/apps/{id}``. Delivery reads go through the shared Redis cache so the hot realtime
  path does not pay a Firestore read per segment.

A signing secret has to be readable to sign with, so unlike app API keys it cannot be stored as
a hash. Records are encrypted at rest with the shared AES-GCM helper under their own key purpose
(``SIGNING_SECRET_KEY_PURPOSE``), keyed by the owner id, so neither a user-data ciphertext nor a
signing-secret ciphertext decrypts as the other; the Redis cache holds only the encrypted record. Rotation is a compare-and-set (Redis
WATCH, Firestore transaction) so two concurrent rotations cannot both believe they are current.

Delivery is fail-open: a record this code cannot read, or a store that cannot be reached, means
the delivery goes out unsigned. An enforcing receiver rejects the missing header, while failing
closed here would feed the auto-disable failure counter for a problem that is ours, not the
developer's. The fallback is reported once per record per cache window, never per delivery.
"""

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from cachetools import TTLCache
from google.cloud import firestore
from redis.exceptions import WatchError

from database._client import get_firestore_client, run_transactional
from database.apps import apps_collection
from database.redis_db import delete_generic_cache, get_generic_cache, r, set_generic_cache
from utils import encryption
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

ROTATION_GRACE = timedelta(hours=24)
# HKDF info for signing-secret keys, distinct from user data's (see utils/encryption.py).
SIGNING_SECRET_KEY_PURPOSE = b'webhook-signing-secret'

_APP_SUBCOLLECTION = 'webhook_signing'
_APP_DOCUMENT = 'current'
_APP_CACHE_TTL_SECONDS = 600
_ROTATE_ATTEMPTS = 5

# One report per (reason, owner) per cache window; the app lookup cache would otherwise re-log an
# unreadable record on every delivery for ten minutes.
_UNSIGNED_REPORTED: TTLCache[tuple[str, str], bool] = TTLCache(maxsize=10_000, ttl=_APP_CACHE_TTL_SECONDS)
_UNSIGNED_REPORTED_LOCK = threading.Lock()


@dataclass(frozen=True)
class WebhookSigningSecrets:
    current: str
    created_at: datetime
    previous: Optional[str] = None
    previous_valid_until: Optional[datetime] = None

    @classmethod
    def issue(
        cls,
        secret: str,
        *,
        previous: Optional['WebhookSigningSecrets'] = None,
        now: Optional[datetime] = None,
        grace: timedelta = ROTATION_GRACE,
    ) -> 'WebhookSigningSecrets':
        """A new record for ``secret``; when rotating, the old current stays valid for ``grace``."""
        issued_at = now or datetime.now(timezone.utc)
        if previous is None:
            return cls(current=secret, created_at=issued_at)
        return cls(
            current=secret,
            created_at=issued_at,
            previous=previous.current,
            previous_valid_until=issued_at + grace,
        )

    def active(self, now: Optional[datetime] = None) -> list[str]:
        """Secrets that should sign a delivery right now, current first."""
        current_time = now or datetime.now(timezone.utc)
        if self.previous and self.previous_valid_until and current_time < self.previous_valid_until:
            return [self.current, self.previous]
        return [self.current]


def note_unsigned_delivery(reason: str, key_id: str) -> None:
    """Report that deliveries for ``key_id`` are going out unsigned, once per window.

    ``reason`` is a fallback-telemetry reason: ``malformed_doc`` for a record that exists but
    cannot be read, ``other`` for a store that could not be reached.
    """
    with _UNSIGNED_REPORTED_LOCK:
        if (reason, key_id) in _UNSIGNED_REPORTED:
            return
        _UNSIGNED_REPORTED[(reason, key_id)] = True
    logger.error(f'webhook signing unavailable key_id={key_id} reason={reason}; delivering unsigned')
    record_fallback(component='webhook', from_mode='signed', to_mode='unsigned', reason=reason, outcome='degraded')


def _encode(secrets: WebhookSigningSecrets, key_id: str) -> dict[str, Any]:
    return {
        'current': encryption.encrypt(secrets.current, key_id, purpose=SIGNING_SECRET_KEY_PURPOSE),
        'previous': (
            encryption.encrypt(secrets.previous, key_id, purpose=SIGNING_SECRET_KEY_PURPOSE)
            if secrets.previous
            else None
        ),
        'previous_valid_until': secrets.previous_valid_until.isoformat() if secrets.previous_valid_until else None,
        'created_at': secrets.created_at.isoformat(),
    }


def _decrypt_secret(ciphertext: str, key_id: str) -> str:
    # ``encryption.decrypt`` fails open and hands back its input when the key or data is wrong,
    # which suits legacy plaintext user data but not a signing secret: signing with the
    # ciphertext would make every delivery fail verification. Treat that as unreadable.
    plaintext = encryption.decrypt(ciphertext, key_id, purpose=SIGNING_SECRET_KEY_PURPOSE)
    if not plaintext or plaintext == ciphertext:
        raise ValueError('signing secret did not decrypt')
    return plaintext


def _decode(raw: Optional[dict[str, Any]], key_id: str) -> Optional[WebhookSigningSecrets]:
    if not raw or not raw.get('current'):
        return None
    try:
        previous_valid_until = raw.get('previous_valid_until')
        return WebhookSigningSecrets(
            current=_decrypt_secret(raw['current'], key_id),
            created_at=datetime.fromisoformat(raw['created_at']),
            previous=_decrypt_secret(raw['previous'], key_id) if raw.get('previous') else None,
            previous_valid_until=datetime.fromisoformat(previous_valid_until) if previous_valid_until else None,
        )
    except (KeyError, TypeError, ValueError):
        # A record this code cannot read must not sign with garbage; deliver unsigned and say so.
        note_unsigned_delivery('malformed_doc', key_id)
        return None


# --- developer webhooks (Redis, beside users:{uid}:developer:webhook:*) ---------------------------


def _user_key(uid: str) -> str:
    return f'users:{uid}:developer:webhook_signing'


def get_user_webhook_signing_db(uid: str) -> Optional[WebhookSigningSecrets]:
    raw = r.get(_user_key(uid))
    if not raw:
        return None
    return _decode(json.loads(raw), uid)


def set_user_webhook_signing_db(uid: str, secrets: WebhookSigningSecrets) -> None:
    r.set(_user_key(uid), json.dumps(_encode(secrets, uid)))


def rotate_user_webhook_signing_db(uid: str, secret: str) -> WebhookSigningSecrets:
    """Make ``secret`` current, keeping whatever was current for the grace window, atomically.

    Read-modify-write under WATCH: if another rotation lands between the read and the write,
    this one re-reads and composes against the record that actually won.
    """
    key = _user_key(uid)
    with r.pipeline() as pipe:
        for _ in range(_ROTATE_ATTEMPTS):
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                record = WebhookSigningSecrets.issue(secret, previous=_decode(json.loads(raw), uid) if raw else None)
                pipe.multi()
                pipe.set(key, json.dumps(_encode(record, uid)))
                pipe.execute()
                return record
            except WatchError:
                continue
    raise RuntimeError(f'webhook signing rotation kept colliding for uid={uid}')


def delete_user_webhook_signing_db(uid: str) -> None:
    r.delete(_user_key(uid))


# --- integration apps (Firestore subcollection + shared Redis cache) -----------------------------


def _app_cache_path(app_id: str) -> str:
    return f'webhook_signing:app:{app_id}'


def _app_document(app_id: str, firestore_client: Any) -> Any:
    client = firestore_client or get_firestore_client()
    return client.collection(apps_collection).document(app_id).collection(_APP_SUBCOLLECTION).document(_APP_DOCUMENT)


def _snapshot_record(snapshot: Any) -> dict[str, Any]:
    raw: object = snapshot.to_dict() if snapshot.exists else None
    return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}


def get_app_webhook_signing_db(app_id: str, *, firestore_client: Any | None = None) -> Optional[WebhookSigningSecrets]:
    cached = get_generic_cache(_app_cache_path(app_id))
    if isinstance(cached, dict):
        # An empty dict is a cached "no secret": most apps have none and must not cost a
        # Firestore read per delivery.
        return _decode(cached, app_id)
    record = _snapshot_record(_app_document(app_id, firestore_client).get())
    set_generic_cache(_app_cache_path(app_id), record, ttl=_APP_CACHE_TTL_SECONDS)
    return _decode(record, app_id)


def active_app_signing_secrets(app_id: str) -> list[str]:
    """Secrets that sign the app's outbound requests right now, current first; empty means unsigned.

    Shared by the app's webhook deliveries (``utils/app_integrations.py``) and its chat-tool calls
    (``utils/retrieval/tools/app_tools.py``). A store error must not stop a request the developer
    configured: it goes out unsigned, reported once per app per window (error log + fallback
    metric) so unsigned requests never pass silently. Blocking; call it through ``run_blocking``.
    """
    try:
        record = get_app_webhook_signing_db(app_id)
    except Exception:
        note_unsigned_delivery('other', app_id)
        return []
    return record.active() if record else []


def set_app_webhook_signing_db(
    app_id: str, secrets: WebhookSigningSecrets, *, firestore_client: Any | None = None
) -> None:
    _app_document(app_id, firestore_client).set(_encode(secrets, app_id))
    delete_generic_cache(_app_cache_path(app_id))


def rotate_app_webhook_signing_db(
    app_id: str, secret: str, *, firestore_client: Any | None = None
) -> WebhookSigningSecrets:
    """Make ``secret`` current for the app inside one Firestore transaction (see the user variant)."""
    client = firestore_client or get_firestore_client()
    ref = _app_document(app_id, client)

    @firestore.transactional
    def rotate(transaction: Any) -> WebhookSigningSecrets:
        previous = _decode(_snapshot_record(ref.get(transaction=transaction)), app_id)
        record = WebhookSigningSecrets.issue(secret, previous=previous)
        transaction.set(ref, _encode(record, app_id))
        return record

    record = run_transactional(client, rotate)
    delete_generic_cache(_app_cache_path(app_id))
    return record


def delete_app_webhook_signing_db(app_id: str, *, firestore_client: Any | None = None) -> None:
    _app_document(app_id, firestore_client).delete()
    delete_generic_cache(_app_cache_path(app_id))
