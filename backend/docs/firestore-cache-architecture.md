# Firestore Cache Architecture

## Status

Accepted for incremental rollout (DD-007 PR #29).

## Context

Firestore reads are a P0 cost driver. The default database is responsible for roughly **$3,807/mo net** with **10.7B reads/month**. DD-007 found repeated reads of the same `users/{uid}` document on WebSocket startup and other hot paths.

The tempting fix is to cache the full user document. We explicitly do **not** do that.

## Decision

Introduce a reusable projection-based Firestore read-through cache under `backend/database/` and apply it only to low-risk typed projections first.

```text
Firestore source of truth
    ↓
typed projection fetcher in database/*
    ↓
database.firestore_cache.get_or_fetch(...)
    ↓
Redis shared L2 cache, disabled by default
```

## Why projection cache instead of full user-doc cache

`users/{uid}` mixes low-risk preferences with correctness-critical fields:

| Field family | Risk if stale |
|---|---|
| Subscription / entitlement | grants or blocks paid features incorrectly |
| BYOK | accepts removed keys or misroutes provider billing |
| Data protection / migration state | writes data under wrong storage/encryption policy |
| Privacy consent | continues recording/training/syncing after opt-out |
| Account/security state | stale security decisions |

Therefore, this cache stores only allowlisted projections such as language, transcription preferences, and AI profile metadata. It must not be used for whole documents or critical fields without a separate design review and shadow rollout.

## Current PR scope

Cached projections:

| Projection | Namespace | TTL | Notes |
|---|---|---:|---|
| language preference | `user_language` | 300s | low-risk listen startup setting |
| transcription preferences | `user_transcription_prefs` | 120s | low-risk startup prefs; includes language |
| AI user profile | `user_ai_profile` | 300s | read-mostly metadata |

Not cached:

- `get_user_subscription()` / `get_user_valid_subscription()`
- BYOK state
- data protection level
- private cloud sync flag
- recording / training consent
- full `get_user_profile()`

## Runtime flags

Cache reads/writes are disabled by default.

```bash
FIRESTORE_CACHE_ENABLED=true
```

Per-namespace override:

```bash
FIRESTORE_CACHE_USER_LANGUAGE_ENABLED=true
FIRESTORE_CACHE_USER_TRANSCRIPTION_PREFS_ENABLED=true
FIRESTORE_CACHE_USER_AI_PROFILE_ENABLED=true
```

Emergency namespace reset:

```bash
FIRESTORE_CACHE_GLOBAL_VERSION=2
```

Bumping the global version abandons all existing keys without scanning Redis.

## Cache keys

```text
fs:v{global_version}:{namespace}:v{policy_version}:b64:{base64url(entity_id)}
```

Example for entity ID `uid_123`:

```text
fs:v1:user_transcription_prefs:v1:b64:dWlkXzEyMw
```

Keys must include:

- global version
- namespace
- policy version
- base64url-encoded UID / entity ID

Entity IDs are encoded rather than character-replaced so keys are collision-free. For example, `a:b` and `a_b` must not map to the same Redis key.

Never include raw names, emails, user text, or secrets in key names.

## Cache envelope

Redis stores a typed envelope:

```json
{
  "v": 1,
  "kind": "value",
  "created_at": 1781460000.123,
  "fresh_until": 1781460120.123,
  "payload": {}
}
```

The envelope supports schema version checks, TTL jitter, payload-size metrics, and future stale-while-revalidate support.

## Failure behavior

Redis is never the source of truth.

- cache disabled → fetch Firestore
- Redis read error → fetch Firestore
- malformed envelope → fetch Firestore
- Redis write error → return Firestore result
- payload too large → do not cache

## Invalidation

Setter functions for cached projections must invalidate after successful Firestore writes.

Current invalidation hooks:

| Write path | Invalidates |
|---|---|
| `set_user_language_preference()` | `user_language`, `user_transcription_prefs` |
| `set_user_transcription_preferences()` | `user_transcription_prefs` |
| `set_user_custom_stt_usage()` | `user_transcription_prefs` |
| `update_ai_user_profile()` | `user_ai_profile` |

## Metrics

Prometheus metrics use low-cardinality labels only:

- `firestore_cache_requests_total{namespace,result}`
- `firestore_cache_fetch_seconds{namespace}`
- `firestore_cache_payload_bytes{namespace}`

Do not add UID, email, route path, or free-form cache keys as labels.

## Rollout plan

1. Deploy with cache disabled.
2. Enable `user_language` for internal users / small percentage.
3. Monitor cache hit/miss, Redis errors, Firestore reads, listen startup errors.
4. Enable `user_transcription_prefs`.
5. Enable `user_ai_profile`.
6. Only consider entitlement/BYOK/data-protection caches after shadow-mode mismatch metrics exist.

## Rollback

Disable all cache reads/writes:

```bash
FIRESTORE_CACHE_ENABLED=false
```

Or abandon all existing keys:

```bash
FIRESTORE_CACHE_GLOBAL_VERSION=<new integer>
```

No data migration is required because Firestore remains the source of truth.

## References

- `deep-dives/DD-007-firestore-read-amplification.md`
- `deep-dives/DD-007-firestore-cache-architecture-proposal.md`
- `deep-dives/DD-007-committee-synthesis.md`
