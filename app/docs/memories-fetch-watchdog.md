# Memories fetch outage monitoring

PR #21226 pins non-fatal classification for memories fetch failures. The released
fatal attribution needs a sample stack and build SHA to confirm which path produced
it; this PR ensures the handled fetch/reporting path cannot be fatal going forward.
It does not establish that the dominant released fatal producer was reproduced.

Crashlytics is useful for sampled diagnostic stacks, not the outage-volume alarm:
it keeps eight recent non-fatals per device and delivery can wait for a restart or
subsequent fatal. A 100% memories outage can therefore remain underrepresented there.

Use hourly PostHog **Product Error** events matching
`properties.error LIKE '%Failed to fetch memories%'` as the outage signal. The app
emits one event per failed HTTP attempt, including failures followed by recovery;
network/no-response failures also emit the event. Payloads contain only a bounded
status/reason message, `response_status_code`, `failure_reason`, `error_kind` and
`diagnostic_source`; no memory contents, URLs, bodies or exception text are sent.
Existing analytics consent, buffering and identity rules still apply, so missing
analytics is unknown coverage rather than proof of health.

```sql
SELECT toStartOfHour(timestamp) AS hour,
       count() AS failures,
       count(DISTINCT distinct_id) AS affected_users
FROM events
WHERE event = 'Product Error'
  AND properties.error LIKE '%Failed to fetch memories%'
  AND timestamp >= now() - INTERVAL 24 HOUR
GROUP BY hour
ORDER BY hour
```

Filter by the exact released platform/build/git SHA when investigating. Compare
hourly counts and affected users with predecessor builds and active-user volume.
Retries amplify attempt counts (up to three per fetch); this query has no success
or attempt denominator and is not an exact failure-rate percentage. Watch 429/503
separately from no-response and decode failures. The nightly watchdog can adopt an
hourly-volume threshold later, after establishing build-specific baselines and
coverage; this PR does not change alert thresholds or scheduled jobs.

Pool retries are disabled for this endpoint so Retry-After and the ten-second caller
deadline cannot be bypassed. The new policy retries only 429/503; socket, TLS, timeout
and other 5xx failures now surface as single-shot failures. Monitor their volume and
consider including them in the retry class if field data warrants a follow-up.
