# Conversation-context cache baseline

Use this query in PostHog HogQL before setting a cache SLO. It reports warm
continuation cache reads by realtime provider and model without collecting
conversation IDs or prompt content.

```sql
SELECT
  properties.provider AS provider,
  properties.model AS model,
  count() AS warm_continuation_turns,
  sum(toInt(properties.cache_read_tokens)) AS cache_read_tokens,
  sum(toInt(properties.input_tokens)) AS input_tokens,
  round(
    sum(toInt(properties.cache_read_tokens)) /
      nullIf(sum(toInt(properties.input_tokens)), 0),
    4
  ) AS cache_read_share
FROM events
WHERE event = 'desktop_health_event'
  AND properties.health_event = 'realtime_context_plan'
  AND properties.phase = 'turn_usage'
  AND timestamp >= now() - INTERVAL 14 DAY
GROUP BY provider, model
ORDER BY warm_continuation_turns DESC
```

For replacement diagnostics, filter the same event to `phase = 'session_start'`
and group by `session_replacement_reason`. The only plan fields emitted are
hashes plus retained-sequence bounds and omitted-turn count; never add a
conversation ID, rendered context, or user text to this event.
