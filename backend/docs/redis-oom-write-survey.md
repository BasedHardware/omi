# Redis OOM cache-write survey

Surveyed before editing against `d78a25da3f3d805e0db9338ccf08217a309f7324`.
All line numbers below refer to that base, not the patched file. The motivating
incident was Redis noeviction saturation on 2026-10-15; TTL expiry restored writes.

## Cache fills covered

| Base file / lines | Write surface | Treatment |
| --- | --- | --- |
| `database/redis_db.py:170-178` | Generic cache SET | Already catches all exceptions via decorator; reuse `_cache_set_fail_open` to add bounded logging and fallback telemetry. The follow-up commit makes `ttl` required (no immortal branch remains). |
| `database/redis_db.py:193-194` | App-by-ID SET | Use existing helper; preserve 600-second TTL. |
| `database/redis_db.py:241-242` | App usage count SET | Use existing helper; preserve 900-second TTL. |
| `database/redis_db.py:259-260` | App money-made amount SET | Use existing helper; preserve 900-second TTL. |
| `database/redis_db.py:275-276` | App usage history SET | Use existing helper; preserve 600-second TTL. |
| `database/redis_db.py:299-300` | App money summary SET | Use existing helper; preserve 600-second TTL. |
| `database/redis_db.py:309-325` | Atomic review-cache Lua SET | **Stays strict — intentionally NOT wrapped.** This is the read model for app reviews (incremental GET+merge+SET, no TTL); nothing rebuilds it from Firestore (`utils/apps.py:579-580` only writes through), so a skipped merge permanently drops a review. Fail-open requires a rebuild path first; see the not-covered section below. |
| `database/redis_db.py:493-494` | Signed-URL SET | Use existing helper; preserve `ttl - 1`. |
| `database/redis_db.py:851-855` | Data-protection-level cache SET | Already decorated fail-open; use existing helper for telemetry. |
| `database/redis_db.py:1383-1386` | Speech-profile-duration SET | Already decorated fail-open; use existing helper for telemetry. Audio and voiceprint are stored first (`routers/speech_profile.py:145-159`); cached duration is display metadata. |
| `utils/translation_core/cache.py:86-95` | `translate:v1` positive SET | Already catches every RedisError; add warning and shared `record_fallback` event. Preserve None return and cache-miss behavior. |
| `utils/translation_core/cache.py:108-117` | `translate:v2:neg` negative SET | Same; a skipped negative write must never assert a negative-cache hit. |

Existing `_cache_set_fail_open` calls at `redis_db.py:490,528,597,619`
(name, geolocation, in-progress conversation hint, conversation/meeting mapping)
retain their behavior. Its error classification is unchanged: OOM, auth,
connection, and timeout faults are skipped; unrelated ResponseError/programming
errors stay loud. Translation retains its broader pre-existing RedisError catch.
Only static reasons and cache namespaces are logged, never payloads or full keys.

## Other direct writes surveyed and intentionally unchanged

| Base `database/redis_db.py` lines | Surface | Reason |
| --- | --- | --- |
| 182-185, 205-206, 510-514, 543-544, 600-601 | Cache/hint DELETEs | Invalidation is not a disposable fill: retaining stale values can violate privacy or correctness. Redis DEL can free memory during OOM; the saturation fix does not need to suppress its errors. Generic DELETE already has its existing broad decorator. |
| 228-233 | Username mapping and user-name set | Stored identity data. |
| 338-339, 349-351 | Paid-app entitlement and Stripe customer ID | Authorization/billing data, no safe cache-miss substitute. |
| 362-367 | Enabled app SADD/SREM | User settings. |
| 407-416 | Install count SET/INCR/DECR | Redis-maintained aggregate; skipping deltas changes counts. Rebuild SET is an administrative operation. |
| 548-584 | Summary/conversation ownership and public-conversation membership SET/DELETE/SADD/SREM | Sharing/visibility authority. |
| 630-639 | Webhook URL/status SETs | User configuration. |
| 691-743 | Filter-category trim/admit Lua writes | Existing bounded, instrumented fail-open policy; unchanged. |
| 754-756 | Retrieval migration SADD/EXPIRE | Migration state. |
| 759-760, 820-824, 1045-1057, 1080-1082, 1358-1370 | Notification suppression/counts and persona cooldown | Deduplication/rate policy, not pure caches. |
| 778-788 | Proactive-message PUBLISH | Message delivery. |
| 838-841 | Preferred app SET | User setting. |
| 872-900, 924-927, 935-955, 970-973 | API-key fill/revocation adapters and strict DELETEs | Existing revocation-fenced authorization semantics; fill functions already decorated. |
| 980-997 | Migration status SET | Job state. |
| 1006-1037 | Auth session/code SET/DELETE | Authentication state; retain existing decorators. |
| 1065-1072, 1328-1354, 1463-1521, 1553-1570 | Notification/listen/device/platform/daily-summary/daily-wear/job/goal locks and release Lua/DELETE | Coordination and policy, not cache fills. |
| 1105-1114 | Conversation-summary app SADD/SREM | App configuration. |
| 1125-1220, 1229-1297 | Rate-limit check/reserve/release and TTS Lua writes | Preserve admission semantics and existing TTS fail-open behavior. |
| 1412-1450 | Task/chat share SET, acceptance SADD/EXPIRE/SREM | User sharing and acceptance state. |
| 1525-1533 | Credits invalidation SET | Billing invalidation signal. |
| 1578-1628 | Screen-frame JTI consumption, adjudication reservation/result SETs | Replay prevention and idempotency state. |

`utils/fair_use.py` was also checked: speech/LLM accounting Lua and pipeline
writes, enforcement-cache SETEX/DELETE, and restriction markers retain their
existing error policies, including `raise_on_error` accounting. No rate-limit
files change. A follow-up commit adds bounded stale-history pruning to the
idempotent speech path (retention windows and admission semantics unchanged);
see `tests/unit/test_fair_use_idempotent_pruning.py`.

## Explicitly NOT covered (strict by design)

- `set_app_review_cache` (`database/redis_db.py`): reviewed during this change and
  reverted to strict. It is the read model for app reviews — an incremental
  GET+merge+SET with no TTL, written after the Firestore write with nothing
  rebuilding it from Firestore — so a skipped merge would permanently drop a
  review from the API. Fail-open there needs a rebuild path first.
- Daily-summary / visibility mappings / user preference writes: semantic review
  pending; behavior unchanged.

## Regression coverage

`tests/unit/test_redis_oom_cache_writes.py` uses fakeredis and injected SET/script
failures. It covers every changed fill, bounded telemetry, translation positive
and negative misses, the real translation engine returning a provider result
under OOM/generic RedisError, success payload/TTL behavior, telemetry failures,
and the preserved unrelated ResponseError contract. Run it in its own pytest
process, as required by backend test isolation.
