# Closed episode composer: bounded background recovery

Default-on `EPISODE_COMPOSE_SWEEP_ENABLED` adds closed-episode discovery to the
existing two-minute enrichment maintenance route. A shared cursor lease reads
one newest-first 32-episode page and admits at most four qualifying episodes per
tick. The durable keyset cursor advances past composed, fresh, merged, waiting,
throttled and poison rows, then wraps after a short page so older debt is not
starved behind the newest rows.

Discovery unseals each episode through the normal owner-specific reader and
calls `needs_compose`. Freshly closed rows keep their existing settle window;
merge donors and accounts blocked by the shared deletion fence are not queued.
The admission uses the existing read-side throttle without foreground promotion,
so it cannot bypass a newer background quiet window. Actual work still goes
through `composer.schedule`: freshness, unchanged-evidence and backoff checks,
the paid-once lease, post-call evidence checks and final CAS are unchanged. The
worker rechecks account deletion on every run, including deferred retry; that
exit is the bounded compose outcome `deleted`.

`omi_episode_compose_sweep_total{outcome}` records `scheduled`,
`skipped_composed`, `skipped_inflight`, `budget_exhausted` and `error` without
identity labels. The seven-day bounded sample contained 401 closed episodes:
54 pending plus 40 never composed gives an upper-bound recovery demand of 94/7
= **13.4 paid composer calls per day** in that sample. Empty/no-speech episodes,
unchanged evidence, existing leases and throttled work do not buy another call.
The schedule cap bounds bursts; it is not a daily paid-call quota.

The new collection-group composite is `status ASC, closed_at DESC, __name__
DESC`. It is declared in the registry and generated manifest, and **must be
READY in the target project before deploying a runtime that runs this query**.
The existing shard deploy readiness gate also enforces this prerequisite.

Set `EPISODE_COMPOSE_SWEEP_ENABLED=false` to stop new discovery. Existing close,
finalize, deferred-settle and Home-read triggers continue. The
[environment contract](../../listen_pusher_pipeline.mdx#closed-episode-compose-cost-control)
covers the same rollback. Verification is hermetic in
`backend/tests/unit/test_episode_compose_sweep.py`, the enrichment maintenance
tests and the Firestore index guard set; no production data or deploy was used.
