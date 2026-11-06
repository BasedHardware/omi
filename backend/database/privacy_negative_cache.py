"""Negative decision hints, revalidated against durable authority on EVERY use.

Redis invalidation alone cannot authorize privacy-sensitive work: both writer
invalidations can fail while a reader still reaches Redis. The Firestore token
and server revision close that gap (infracost ruling 93d4a1, 2026-11-02).

Lever ``privacy_ttl60`` (David ruling 2026-11-04: reuse bounded at 60s) skips the
per-use token read instead: a clear decision is reused for at most 60 seconds
from the start of the live read that produced it (database.privacy_ttl_cache).
"""

import hashlib

from config.firestore_read_levers import lever_enabled
from database.batch_privacy_attempt import token_version
from database import privacy_check_metrics as metrics


def _candidate(family, uid, client, variant, live, cache_family, *, shadow, reuse_allowed):
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
        clear = live()
        return {'version': version, 'clear': clear, 'reusable': clear is True and reuse_allowed()}

    # The envelope contains only an opaque token and bools. Variant hashes
    # separate conversations; absence for one ID never proves absence for another.
    envelope = cached_read(
        cache_family,
        uid,
        plane_id(client) + ':' + hashlib.sha256(variant.encode()).hexdigest(),
        fetch,
        seconds=30,
        cacheable=lambda value: (
            isinstance(value, dict) and value.get('clear') is True and value.get('reusable') is True
        ),
        validate=lambda value: value.get('version') == version,
        shadow=shadow,
    )
    clear = envelope['clear']
    if not fetched:
        metrics.memo_result(family, 'hit')
    if session_on and holder is not None and clear is True and envelope.get('reusable') is True:
        holder.put(key, version, True)
    return clear


def _ttl_key(family, uid, client, variant):
    from database.fsr_read_cache import plane_id

    # The variant is hashed exactly like the token path: absence for one ID
    # never answers for another, and the key never holds conversation IDs.
    return ('privacy_ttl', plane_id(client), uid, family, hashlib.sha256(variant.encode()).hexdigest())


def _ttl_candidate(family, uid, client, variant, live, reuse_allowed):
    """60s-bounded reuse of a clear decision (David ruling 2026-11-04). No token read.

    Returns (clear, cached_age). Blocked outcomes raise through and are never stored.
    """
    from database import privacy_ttl_cache as ttl_cache

    key = _ttl_key(family, uid, client, variant)
    value, age = ttl_cache.DECISIONS.get(key)
    if value is True:
        metrics.ttl_result(family, 'hit')
        return True, age
    metrics.ttl_result(family, 'miss')
    started = ttl_cache.DECISIONS.clock()
    clear = live()
    if clear is True and reuse_allowed():
        if ttl_cache.DECISIONS.put(key, True, started=started):
            metrics.ttl_result(family, 'store')
    return clear, None


def _ttl_lookup(family, uid, client, variant):
    from database import privacy_ttl_cache as ttl_cache

    value, age = ttl_cache.DECISIONS.get(_ttl_key(family, uid, client, variant))
    return (True, age) if value is True else (None, None)


def _ttl_store(family, uid, client, variant, started):
    from database import privacy_ttl_cache as ttl_cache

    if ttl_cache.DECISIONS.put(_ttl_key(family, uid, client, variant), True, started=started):
        metrics.ttl_result(family, 'store')


def decide(family, uid, client, variant, live, cache_family, *, blocked=(), reuse_allowed=lambda: True):
    """Return live authority in shadow mode; candidate faults cannot change it."""
    shadow = lever_enabled('privacy_checks_shadow', uid)
    # privacy_ttl60 replaces the per-use token read with the 60s bound. It wins
    # over the token-validated cache when both are on; shadow still wins over both.
    from database import privacy_ttl_cache as ttl_cache

    ttl_on = ttl_cache.enabled('privacy_ttl60', uid)
    enforce = lever_enabled(cache_family, uid) or (
        metrics.session_memo() is not None and lever_enabled('privacy_session_token', uid)
    )
    # Shadow wins if both switches are supplied accidentally. Enforcement is a
    # separate later phase after shadow qualification; remove shadow to ramp.
    if shadow or not (ttl_on or enforce):
        function = live
    elif ttl_on:
        function = lambda: _ttl_candidate(family, uid, client, variant, live, reuse_allowed)[0]
    else:
        function = lambda: _candidate(
            family, uid, client, variant, live, cache_family, shadow=False, reuse_allowed=reuse_allowed
        )
    reason = 'allow'
    started = None
    if shadow and ttl_on:
        from database import privacy_ttl_cache as ttl_cache

        started = ttl_cache.DECISIONS.clock()
    try:
        result = function()
        reason = 'allow' if result else 'conversation_deleted'
    except blocked:
        reason = 'destructive_operation'
        metrics.decision(family, reason)
        if shadow:
            _shadow(family, uid, client, variant, live, cache_family, reason, blocked, reuse_allowed, ttl_on)
        raise
    except Exception:
        metrics.decision(family, 'authority_unavailable')
        raise
    metrics.decision(family, reason)
    if shadow:
        _shadow(family, uid, client, variant, live, cache_family, reason, blocked, reuse_allowed, ttl_on)
        if ttl_on and result is True and reuse_allowed():
            # Populate from the live read just made: shadow costs no extra read.
            try:
                _ttl_store(family, uid, client, variant, started)
            except Exception:
                metrics.shadow_error(family)
    return result


def _shadow(family, uid, client, variant, live, cache_family, reason, blocked, reuse_allowed, ttl_on=False):
    try:
        cached_age = None
        with metrics.mode_scope('shadow'):
            metrics.called(family)
            if ttl_on:
                # Compare what the 60s cache WOULD have answered before this live read.
                cached, cached_age = _ttl_lookup(family, uid, client, variant)
                metrics.ttl_result(family, 'hit' if cached else 'miss')
                candidate = 'allow' if cached else reason
            else:
                try:
                    clear = _candidate(
                        family, uid, client, variant, live, cache_family, shadow=True, reuse_allowed=reuse_allowed
                    )
                    candidate = 'allow' if clear else 'conversation_deleted'
                except blocked:
                    candidate = 'destructive_operation'
            metrics.decision(family, candidate)
        metrics.compare(family, reason, candidate, cached_age=cached_age)
    except Exception:
        metrics.shadow_error(family)
