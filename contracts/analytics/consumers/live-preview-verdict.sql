-- Project verdict/platform/verdict_latency_ms/hold_timeout_replayed from Live Preview Verdict
-- properties into this event view (one row per socket that declared local_preview).
-- quantile() is the PostHog/ClickHouse aggregate.
SELECT verdict,
       platform,
       count(*) AS sockets,
       quantile(0.5)(verdict_latency_ms) AS verdict_latency_p50_ms,
       quantile(0.95)(verdict_latency_ms) AS verdict_latency_p95_ms,
       quantile(0.5)(hold_duration_ms) AS hold_duration_p50_ms,
       avg(held_frames) AS held_frames_avg,
       avg(CASE WHEN hold_timeout_replayed THEN 1 ELSE 0 END) AS timeout_replay_rate
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event = 'Live Preview Verdict'
GROUP BY verdict, platform;
