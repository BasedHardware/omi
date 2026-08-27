"""Server-driven config + storage for the in-app product CSAT ask.

Firestore layout:

  Collection: csat_config — Document ID: product (singleton)

    enabled: bool             default true when the doc is missing
    title: str                default "How would you rate Omi Desktop?"
    body: str                 optional subtitle, default ""
    thank_you_text: str       default "Thank you!"
    refer_cta_text: str       default "Enjoying Omi? Give a friend a free month."
    question_threshold: int   1..50, default 3
    comment_max_score: int    1..5, default 3
    revision: int             incremented on every admin save
    updated_at: number        unix seconds
    updated_by: str           admin uid

  Collection: csat_ratings — Document ID: "{platform}_{uid}"

    uid, platform, app_version, score, comment, revision, created_at

Ratings are create-only (Firestore `create` is an atomic exists=false
compare-and-create): a user gets exactly one rating per platform and a
resubmit never overwrites the first answer.

The config singleton is admin-authored on admin.omi.me; the backend GET is
the only client read path. The doc is cached 60s like app_review_config so
admin copy edits reach clients within one poll (~5 min) plus the cache.
"""

import time
from typing import Any, Dict, Tuple, cast

from google.api_core.exceptions import AlreadyExists, Conflict

from database._client import get_firestore_client
from database.cache import get_memory_cache

CONFIG_COLLECTION = 'csat_config'
CONFIG_DOC = 'product'
RATINGS_COLLECTION = 'csat_ratings'

PLATFORMS = {'macos', 'windows', 'ios', 'android'}

_CACHE_KEY = 'csat_config:product'
_CACHE_TTL_SECONDS = 60

MAX_APP_VERSION_LENGTH = 32
MAX_COMMENT_LENGTH = 500

DEFAULT_TITLE = 'How would you rate Omi Desktop?'
DEFAULT_THANK_YOU_TEXT = 'Thank you!'
DEFAULT_REFER_CTA_TEXT = 'Enjoying Omi? Give a friend a free month.'

# What a missing/empty doc means; also the shape returned to clients.
DEFAULT_CONFIG: Dict[str, Any] = {
    'enabled': True,
    'title': DEFAULT_TITLE,
    'body': '',
    'thank_you_text': DEFAULT_THANK_YOU_TEXT,
    'refer_cta_text': DEFAULT_REFER_CTA_TEXT,
    'question_threshold': 3,
    'comment_max_score': 3,
    'revision': 0,
}


def _clamped_int(raw: Any, default: int, low: int, high: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def normalize_config(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    """Coerce a stored (possibly admin-mangled) config doc to the client shape.

    Pure so both the backend GET and tests can pin the contract: unknown or
    out-of-range fields fall back to defaults / clamps, never 500.
    """
    raw = raw if isinstance(raw, dict) else {}

    def text(field: str, fallback: str) -> str:
        value = raw.get(field)
        return value.strip() if isinstance(value, str) and value.strip() else fallback

    return {
        'enabled': raw.get('enabled') is not False,
        'title': text('title', DEFAULT_TITLE),
        'body': text('body', ''),
        'thank_you_text': text('thank_you_text', DEFAULT_THANK_YOU_TEXT),
        'refer_cta_text': text('refer_cta_text', DEFAULT_REFER_CTA_TEXT),
        'question_threshold': _clamped_int(raw.get('question_threshold'), 3, 1, 50),
        'comment_max_score': _clamped_int(raw.get('comment_max_score'), 3, 1, 5),
        'revision': max(0, _clamped_int(raw.get('revision'), 0, 0, 1_000_000_000)),
    }


def _fetch_config() -> Dict[str, Any]:
    doc = get_firestore_client().collection(CONFIG_COLLECTION).document(CONFIG_DOC).get()
    if not getattr(doc, 'exists', False):
        return dict(DEFAULT_CONFIG)
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else dict(DEFAULT_CONFIG)


def get_product_config() -> Dict[str, Any]:
    """Return the product CSAT config, normalized, cached for 60s."""
    fetched = get_memory_cache().get_or_fetch(_CACHE_KEY, _fetch_config, ttl=_CACHE_TTL_SECONDS)
    raw = cast(Dict[str, Any], fetched) if isinstance(fetched, dict) else dict(DEFAULT_CONFIG)
    return normalize_config(raw)


def submit_rating(
    *,
    uid: str,
    platform: str,
    app_version: str,
    score: int,
    comment: str,
    revision: int,
) -> Tuple[str, bool]:
    """Create the user's one rating doc for the platform.

    The comment is dropped server-side when the score is above the current
    `comment_max_score` (the client may still send one — the server wins).
    Returns `(doc_id, created)`; `created=False` means a rating already
    existed and was left untouched.
    """
    config = get_product_config()
    effective_comment = comment if score <= config['comment_max_score'] else ''
    doc_id = f'{platform}_{uid}'
    payload: Dict[str, Any] = {
        'uid': uid,
        'platform': platform,
        'app_version': app_version[:MAX_APP_VERSION_LENGTH],
        'score': score,
        'comment': effective_comment,
        'revision': max(0, revision),
        'created_at': int(time.time()),
    }
    ref = get_firestore_client().collection(RATINGS_COLLECTION).document(doc_id)
    try:
        ref.create(payload)
    except (AlreadyExists, Conflict):
        return doc_id, False
    return doc_id, True


__all__ = [
    'CONFIG_COLLECTION',
    'CONFIG_DOC',
    'DEFAULT_CONFIG',
    'MAX_APP_VERSION_LENGTH',
    'MAX_COMMENT_LENGTH',
    'PLATFORMS',
    'RATINGS_COLLECTION',
    'get_product_config',
    'normalize_config',
    'submit_rating',
]
