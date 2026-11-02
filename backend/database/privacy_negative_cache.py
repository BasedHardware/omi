"""Negative decision hints, revalidated against durable authority on EVERY use.

Redis invalidation alone cannot authorize privacy-sensitive work: both writer
invalidations can fail while a reader still reaches Redis. The Firestore token
and server revision close that gap (infracost ruling 93d4a1, 2026-11-02).
"""

import hashlib

from config.firestore_read_levers import lever_enabled
from database.batch_privacy_attempt import token_version
from database import privacy_check_metrics as metrics


def _candidate(family, uid, client, variant, live, cache_family, *, shadow):
    from database.batch_pipeline_privacy import PRIVACY_COLLECTION, privacy_owner_key
    from database.fsr_read_cache import cached_read, plane_id

    # Never memoize this read, even within one request/session. Redis generations
    # are hints; only the same-commit Firestore token certifies unchanged state.
    version = token_version(
        metrics.read_snapshot(family, client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid)))
    )
    if version is None:
        metrics.memo_result(family, 'ineligible')
        return live()
    version = list(version)
    holder = metrics.session_memo()
    session_on = holder is not None and (shadow or lever_enabled('privacy_session_token', uid))
    key = (client, uid, family, variant)
    if session_on and holder is not None and holder.get(key, version) is True:
        metrics.memo_result(family, 'hit')
        return True

    fetched = False

    def fetch():
        nonlocal fetched
        fetched = True
        metrics.memo_result(family, 'miss')
        return {'version': version, 'clear': live()}

    # The envelope contains only an opaque token and a bool. Variant hashes
    # separate conversations; absence for one ID never proves absence for another.
    envelope = cached_read(
        cache_family,
        uid,
        plane_id(client) + ':' + hashlib.sha256(variant.encode()).hexdigest(),
        fetch,
        seconds=30,
        cacheable=lambda value: isinstance(value, dict) and value.get('clear') is True,
        validate=lambda value: value.get('version') == version,
        shadow=shadow,
    )
    clear = envelope['clear']
    if not fetched:
        metrics.memo_result(family, 'hit')
    if session_on and holder is not None and clear is True:
        holder.put(key, version, True)
    return clear


def decide(family, uid, client, variant, live, cache_family, *, blocked=()):
    """Return live authority in shadow mode; candidate faults cannot change it."""
    shadow = lever_enabled('privacy_checks_shadow', uid)
    enforce = lever_enabled(cache_family, uid) or (
        metrics.session_memo() is not None and lever_enabled('privacy_session_token', uid)
    )
    # Shadow wins if both switches are supplied accidentally. Enforcement is a
    # separate later phase after shadow qualification; remove shadow to ramp.
    function = (
        live
        if shadow or not enforce
        else lambda: _candidate(family, uid, client, variant, live, cache_family, shadow=False)
    )
    reason = 'allow'
    try:
        result = function()
        reason = 'allow' if result else 'conversation_deleted'
    except blocked:
        reason = 'destructive_operation'
        metrics.decision(family, reason)
        if shadow:
            _shadow(family, uid, client, variant, live, cache_family, reason, blocked)
        raise
    except Exception:
        metrics.decision(family, 'authority_unavailable')
        raise
    metrics.decision(family, reason)
    if shadow:
        _shadow(family, uid, client, variant, live, cache_family, reason, blocked)
    return result


def _shadow(family, uid, client, variant, live, cache_family, reason, blocked):
    try:
        with metrics.mode_scope('shadow'):
            metrics.called(family)
            try:
                clear = _candidate(family, uid, client, variant, live, cache_family, shadow=True)
                candidate = 'allow' if clear else 'conversation_deleted'
            except blocked:
                candidate = 'destructive_operation'
            metrics.decision(family, candidate)
        metrics.compare(family, reason, candidate)
    except Exception:
        metrics.shadow_error(family)
