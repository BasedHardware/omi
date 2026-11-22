# Home live-owner read cache

Home's unfiltered conversation-list projection now caches only the live owner's
IDs, status and ownership timestamps in Redis by UID for 30 seconds. This is
approach A: sync-job admission knows recording/target IDs, but not the current
episode. Stamping an episode onto jobs would require another lookup and retain
ownership metadata for the job's 24-hour lifetime.

The [Home ownership contract](../../listen_pusher_pipeline.mdx#home-processing-ownership-default-on)
keeps Firestore authoritative. Cache hits never renew TTL, and a payload deadline
starts before the Firestore fetch to bound late writes. Missing or non-live owners
are cached too. Redis read/write/decoding faults fall back to the fresh lookup;
a Firestore error leaves rows visible. Only this acknowledged Home-list path opts
in; pending-work, detail escalation and writer-lease probes remain fresh.

A stale positive answer may keep an already acknowledged member omitted for at
most 30 seconds. The exact client-held episode/member pair is still required for
each omission. Missing, malformed, different-episode or different-member acks
keep recordings visible, including newly attached members.

`HOME_LIVE_OWNER_CACHE_ENABLED` defaults true because this is a read optimization,
with the same call-time true/false parser as the other Home ownership switches.
It changes no UI or response shape. Rollback: set it to false to bypass both
Redis operations and restore the original Firestore lookup on every eligible
poll. No production config or deployment is changed by this PR.

Verification: `test_home_owner_cache.py` covers hits, misses, expiry, stale acks,
slow fills, corrupt data, outages, admission gates and rollback. Existing
`test_homesettle.py`, `test_pending_work.py`, and
`test_episodes_finalizer_hook.py` retain ownership and detail-lease coverage.

`omi_home_live_owner_lookups_total{source="cache"|"firestore"}` counts only this
eligible acknowledged Home-list path, without user labels. The daily total gives
N; Firestore attempts divided by total gives the effective miss/fallback rate m.
It includes cold misses, errors, concurrent fills and kill-switch bypass. Until
deployed and observed for a full day, m is unmeasured, not a TTL-derived saving.
