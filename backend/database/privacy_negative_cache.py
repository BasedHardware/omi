"""Negative decision hints, revalidated against durable authority on EVERY use.

Redis invalidation alone cannot authorize privacy-sensitive work: both writer
invalidations can fail while a reader still reaches Redis. The Firestore token
and server revision close that gap (infracost ruling 93d4a1, 2026-11-02).

Lever ``privacy_ttl60`` retains a 60s upper bound from the start of the live
read. Every ALLOW reuse also requires a fresh durable token/server revision and
generation match; elapsed time alone never authorizes reuse.
"""

import hashlib
import time

from config.firestore_read_levers import lever_enabled
from database.batch_privacy_attempt import token_version
from database import privacy_check_metrics as metrics, privacy_ttl_cache as ttl_cache
from database.batch_pipeline_privacy import PRIVACY_COLLECTION, privacy_owner_key
from database.fsr_read_cache import cached_read, plane_id


def _certificate(family, uid, client):
    snapshot = metrics.read_snapshot(
        family, client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid)), uid=uid
    )
    version = token_version(snapshot)
    generation = (snapshot.to_dict() or {}).get('generation', 0)
    if version is None or type(generation) is not int:
        return None
    return {'version': list(version), 'generation': generation}


def _safe_certificate(family, uid, client, evidence):
    try:
        return _certificate(family, uid, client)
    except Exception:
        # Unavailable certification cannot authorize a cached ALLOW. Read live.
        evidence.token_seen, evidence.token, evidence.generation = True, None, None
        return None


def _certified(value, certificate):
    return (
        certificate is not None
        and isinstance(value, dict)
        and value.get('clear') is True
        and value.get('reusable') is True
        and value.get('version') == certificate['version']
        and type(value.get('generation')) is int
        and value.get('generation') == certificate['generation']
    )


def _envelope(clear, certificate, reuse_allowed, evidence, observed_at):
    return {
        **(certificate or {}),
        'clear': clear,
        'reusable': certificate is not None and clear is True and reuse_allowed(),
        'markers': dict(evidence.markers),
        'observed_at': observed_at,
    }


def _cache_age(value):
    observed = value.get('observed_at')
    return time.time() - observed if isinstance(observed, (int, float)) else None


def _candidate(family, uid, client, variant, live, cache_family, *, shadow, reuse_allowed, evidence=None):
    evidence = evidence or metrics.DecisionEvidence()
    certificate = _safe_certificate(family, uid, client, evidence)
    if certificate is None:
        metrics.memo_result(family, 'ineligible')
        evidence.certification = 'unavailable'
        return live()
    version = certificate['version']
    holder = metrics.session_memo()
    session_on = holder is not None and (shadow or lever_enabled('privacy_session_token', uid))
    key = (client, uid, family, variant)
    session_entry = holder.get(key, version) if session_on and holder is not None else None
    cached = session_entry.get('payload') if isinstance(session_entry, dict) else None
    expires = session_entry.get('expires_at') if isinstance(session_entry, dict) else None
    if _certified(cached, certificate) and isinstance(expires, (int, float)) and ttl_cache.DECISIONS.clock() < expires:
        metrics.memo_result(family, 'hit')
        evidence.source, evidence.certification = 'session_hit', 'matched'
        evidence.cached(cached, _cache_age(cached))
        return True

    fetched = False
    live_started = None
    evidence.certification = 'miss'

    def fetch():
        nonlocal fetched, live_started
        fetched = True
        live_started = ttl_cache.DECISIONS.clock()
        metrics.memo_result(family, 'miss')
        observed_at = time.time()
        clear = live()
        return _envelope(clear, certificate, reuse_allowed, evidence, observed_at)

    def validate(value):
        evidence.age = _cache_age(value)
        valid = _certified(value, certificate)
        evidence.certification = 'matched' if valid else 'mismatch'
        return valid

    lookup_started = ttl_cache.DECISIONS.clock()
    envelope = cached_read(
        cache_family,
        uid,
        plane_id(client) + ':' + hashlib.sha256(variant.encode()).hexdigest(),
        fetch,
        seconds=30,
        cacheable=lambda value: isinstance(value, dict)
        and value.get('clear') is True
        and value.get('reusable') is True,
        validate=validate,
        shadow=shadow,
    )
    # Redis bounds the entry to 30s at lookup; reject a reply delayed another
    # 30s so transport latency cannot extend the 60s upper bound.
    if not fetched and ttl_cache.DECISIONS.clock() - lookup_started >= 30:
        envelope = fetch()
    clear = envelope['clear']
    if not fetched:
        metrics.memo_result(family, 'hit')
        evidence.source = 'token_hit'
        evidence.cached(envelope, _cache_age(envelope))
    if session_on and holder is not None and _certified(envelope, certificate):
        # Same-process session expiry uses monotonic time, never wall time. A
        # Redis hit was at most 30s old when its lookup began; another 30s is
        # conservative. Fresh authority starts its own 60s upper bound.
        expires = live_started + ttl_cache.MAX_SECONDS if live_started is not None else lookup_started + 30
        if ttl_cache.DECISIONS.clock() < expires:
            holder.put(key, version, {'payload': envelope, 'expires_at': expires})
    return clear


def _ttl_key(family, uid, client, variant):
    # The variant is hashed exactly like the token path: absence for one ID
    # never answers for another, and the key never holds conversation IDs.
    return ('privacy_ttl', plane_id(client), uid, family, hashlib.sha256(variant.encode()).hexdigest())


def _ttl_candidate(family, uid, client, variant, live, reuse_allowed, *, evidence):
    """Reuse only a token-certified clear, for at most 60s after its live read started."""
    key = _ttl_key(family, uid, client, variant)
    certificate = _safe_certificate(family, uid, client, evidence)
    value, age = ttl_cache.DECISIONS.get(key)
    evidence.age = age
    if _certified(value, certificate):
        metrics.ttl_result(family, 'hit')
        evidence.source, evidence.certification = 'ttl_hit', 'matched'
        evidence.cached(value, age)
        return True, age
    evidence.certification = (
        'unavailable' if certificate is None else 'miss' if ttl_cache.is_missing(value) else 'mismatch'
    )
    # Reject legacy boolean entries, malformed envelopes and mismatched tokens.
    ttl_cache.DECISIONS.forget(key)
    metrics.ttl_result(family, 'miss')
    started, observed_at = ttl_cache.DECISIONS.clock(), time.time()
    clear = live()
    envelope = _envelope(clear, certificate, reuse_allowed, evidence, observed_at)
    if envelope['reusable'] and ttl_cache.DECISIONS.put(key, envelope, started=started):
        metrics.ttl_result(family, 'store')
    return clear, None


def decide(family, uid, client, variant, live, cache_family, *, blocked=(), reuse_allowed=lambda: True):
    """Return live authority in shadow mode; candidate faults cannot change it."""
    shadow = lever_enabled('privacy_checks_shadow', uid)
    ttl_on = ttl_cache.enabled('privacy_ttl60', uid)
    enforce = lever_enabled(cache_family, uid) or (
        metrics.session_memo() is not None and lever_enabled('privacy_session_token', uid)
    )
    if not (shadow or ttl_on or enforce):
        # Preserve the default path, including its read sequence.
        return _run(family, uid, live, blocked)
    live_evidence = metrics.DecisionEvidence()
    with metrics.evidence_scope(live_evidence):
        if shadow:
            # Observe certification BEFORE the live read. Never stamp a prior
            # ALLOW with a token obtained after a concurrent authority change.
            _safe_certificate(family, uid, client, live_evidence)
            function = live
        elif ttl_on:
            function = lambda: _ttl_candidate(
                family, uid, client, variant, live, reuse_allowed, evidence=live_evidence
            )[0]
        else:
            function = lambda: _candidate(
                family,
                uid,
                client,
                variant,
                live,
                cache_family,
                shadow=False,
                reuse_allowed=reuse_allowed,
                evidence=live_evidence,
            )
        reason = 'allow'
        try:
            result = function()
            reason = 'allow' if result else 'conversation_deleted'
        except blocked:
            reason = 'destructive_operation'
            metrics.decision(family, reason, uid=uid)
            if shadow:
                _shadow(
                    family,
                    uid,
                    client,
                    variant,
                    live,
                    cache_family,
                    reason,
                    blocked,
                    reuse_allowed,
                    ttl_on,
                    live_evidence,
                )
            raise
        except Exception:
            metrics.decision(family, 'authority_unavailable', uid=uid)
            raise
        metrics.decision(family, reason, uid=uid)
        if shadow:
            _shadow(
                family, uid, client, variant, live, cache_family, reason, blocked, reuse_allowed, ttl_on, live_evidence
            )
        return result


def _run(family, uid, live, blocked):
    try:
        result = live()
    except blocked:
        metrics.decision(family, 'destructive_operation', uid=uid)
        raise
    except Exception:
        metrics.decision(family, 'authority_unavailable', uid=uid)
        raise
    metrics.decision(family, 'allow' if result else 'conversation_deleted', uid=uid)
    return result


def _shadow(
    family, uid, client, variant, live, cache_family, reason, blocked, reuse_allowed, ttl_on=False, live_evidence=None
):
    try:
        evidence = metrics.DecisionEvidence()
        with metrics.mode_scope('shadow'), metrics.evidence_scope(evidence):
            metrics.called(family)
            try:
                if ttl_on:
                    clear, _ = _ttl_candidate(family, uid, client, variant, live, reuse_allowed, evidence=evidence)
                else:
                    clear = _candidate(
                        family,
                        uid,
                        client,
                        variant,
                        live,
                        cache_family,
                        shadow=True,
                        reuse_allowed=reuse_allowed,
                        evidence=evidence,
                    )
                candidate = 'allow' if clear else 'conversation_deleted'
            except blocked:
                candidate = 'destructive_operation'
            metrics.decision(family, candidate, uid=uid)
        metrics.compare(family, reason, candidate, live_evidence=live_evidence, candidate_evidence=evidence)
    except Exception:
        metrics.shadow_error(family)
