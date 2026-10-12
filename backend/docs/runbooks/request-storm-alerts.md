# Request storm alerts

The 2026-10-07 mobile job-status poll storm (PR #21206) went unpaged until a
user screenshot exposed it. These two policies use built-in LB metrics, so
they also cover requests rejected before reaching Cloud Run and the sync
backend whose request logging is disabled.

## Managed policies

The production step in `.github/workflows/gcp_backend.yml` invokes
`.github/scripts/ensure_request_storm_alerts.py` with the existing
`SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS` variable. There is no manual
production mutation in this change. The shared JSON reconciler lists by
display name, rejects duplicates, creates absent policies, and repairs managed
field drift while preserving the existing condition resource name. An unchanged
deploy makes no write and preserves dwell. Provisioning failure warns in the
deploy summary; rerun the production deploy to retry, and confirm both policies
and their notification channels in Monitoring.

- **Prod API edge throttling storm:** `loadbalancing.googleapis.com/https/request_count`,
  `response_code=429`, production project and the three explicit API / sync /
  listen backend names in `.github/monitoring/api_edge_429_policy.json`.
  ALIGN_RATE over 300s, REDUCE_SUM, grouped by backend_target_name. Any backend
  above **1,000/min (16.6667/s) for 1,800s** pages. Backends are never summed together.
- **Prod sync duplicate upload share:** same metric on
  `custom-domains-api-omi-me-backend-sync-49a4-be`. The native ratio condition
  divides 409 count by **all** request count, with identical 3,600s ALIGN_SUM /
  REDUCE_SUM aggregations and grouping. A rolling one-hour share **above 10%
  for 3,600s** pages. It is a ratio of counts, not an average of percentages.
  Both conditions treat missing data as inactive.

The [Monitoring ratio API](https://docs.cloud.google.com/monitoring/alerts/policies-in-json)
supports numerator/denominator filters directly; neither MQL nor PromQL is
needed. The ratio policy body is checked in at
`.github/monitoring/sync_upload_409_policy.json`.

## Triage

1. Identify backend_target_name and the onset window. A 429 metric counts all
   throttling responses, including application 429s; it is not proof of Cloud
   Armor denial. Compare LB `denied_by_security_policy` counts with backend
   responses, policy names, method/path family and app-build cohorts.
2. Check job polling rate, Retry-After/cooldowns, reconnect loops and health
   probe traffic. For upgraded sync clients, expect at most 18 job polls/min
   per process, plus no polls during returned throttle cooldowns. One upgraded
   phone is not fleet acceptance: compare adoption cohorts and like-for-like
   UTC windows over 24–48h.
3. For the sync alert, inspect the 409 reason and owner/job hints. Backend-wide
   409 share is a duplicate-upload proxy; it cannot distinguish
   `sync_content_in_progress` from other 409s or identify a request route.
   Also check pending uploaded age, completion surfacing and sync latency.
   Low request volume alone does not prove recordings are progressing.
4. In PostHog, compare `api_edge_throttled` by existing app_version/app_build,
   endpoint_template, method, path_family and retry_after. The event covers
   HTTP 429s on official HTTPS Omi API hosts in pooled, streaming and unpooled
   multipart paths. It cannot identify the enforcing policy from status alone.
   Known endpoints are allowlisted; unknown paths become `/other`.
   No URL, query, identifier or arbitrary header value is sent. Protocol-shaped
   Retry-After delay/date values are included; malformed values are omitted.
   At most one event per template per five minutes per process (shared across
   methods) is sent through AnalyticsManager's existing consent/queue/PostHog
   path. Process restart resets the limiter. These sampled events are not
   request counts, and WebSocket handshake errors are outside this HTTP hook.

## Read-only measurement and replay

Use the incident `measure.sh` approach: read aggregate LB metrics through the
Monitoring REST API, and use bounded/sanitized LB log counts for Cloud Armor
attribution. Do not call the production API as a signed-in user. No raw
customer log payload is needed. The original run's `measure.sh` also checked
poll denials/min, total polls, distinct IP count and one-hour upload 409 share.
This checked-in aggregate-only counterpart uses `ro-prod`, curl and
`gcloud auth print-access-token`; it never creates or edits a policy and keeps
tokens off stdout and out of command arguments:

```bash
bash backend/scripts/measure-request-storm-alerts.sh \
  2026-09-21T04:00:00Z 2026-10-12T04:00:00Z /tmp/omi-storm-history
python3 .github/scripts/replay_request_storm_alerts.py \
  --edge /tmp/omi-storm-history/edge.json --sync /tmp/omi-storm-history/sync.json
```

To inspect a current window, supply current UTC start/end times to the shell
script. It prints that selected window and retains aggregate JSON. The replay
without start/end uses the incident windows below. The reader fails on a
pagination token instead of silently accepting truncated history; split a
larger window if needed. Evidence is aggregate-only and belongs outside Git.

## Threshold evidence / coordinator PR notes

Read-only production history collected on 2026-10-12 covers 21 days:
**2026-09-21 04:00 to 2026-10-12 04:00 UTC**. Metric queries use 300s
alignment, sum across LB labels, and retain the response code or backend name.
No pagination token was returned. The replay constructs matching rolling
one-hour totals for the ratio, checks every five-minute sample, resets dwell
on gaps or recovery, and requires the full dwell between violating samples.
These are conservative sampled eligibility times, not a claim about an actual
Monitoring incident, notification delivery or exact continuously evaluated
minute. Metric ingestion can add delay.

Baseline = Sep 21 04:00–Oct 7 12:00; incident = Oct 7 12:00–Oct 11 17:00;
post-fix = Oct 11 17:00–Oct 12 04:00 (all UTC).

| Window (UTC) | Series | Peak aligned value | First eligible fire (UTC) |
| --- | --- | ---: | --- |
| baseline | custom-domains-api-omi-me-backend-49a4-be | 960.6/min | none |
| baseline | custom-domains-api-omi-me-backend-listen-49a4-be | 463.0/min | none |
| baseline | custom-domains-api-omi-me-backend-sync-49a4-be | 123.8/min | none |
| baseline | sync 409 share (1h) | 9.38% | none |
| incident | custom-domains-api-omi-me-backend-49a4-be | 21329.6/min | 2026-10-07T15:55:00Z |
| incident | custom-domains-api-omi-me-backend-listen-49a4-be | 283.0/min | none |
| incident | custom-domains-api-omi-me-backend-sync-49a4-be | 12.8/min | none |
| incident | sync 409 share (1h) | 51.04% | 2026-10-08T23:10:00Z |
| post-fix | custom-domains-api-omi-me-backend-49a4-be | 26508.4/min | 2026-10-11T17:30:00Z |
| post-fix | custom-domains-api-omi-me-backend-listen-49a4-be | 114.2/min | none |
| post-fix | custom-domains-api-omi-me-backend-sync-49a4-be | 8.0/min | none |
| post-fix | sync 409 share (1h) | 7.15% | none |


The edge threshold exceeds the entire observed baseline (including existing
health probes). The scout estimated health noise around 1,900 denials/hour,
about 32/min; removing that noise cannot by itself approach 1,000/min.
There is little headroom over the baseline's rare peak of 960.6/min, but the
30-minute dwell guards isolated bursts. The post-fix edge policy deliberately
still fires on old-build storms: **there is no observed healthy fleet rollout
window yet**, and subtracting health noise does not remove those storms.
Read-only data cannot prove the future post-adoption steady state.

The requested 10% ratio could **not** have fired by October 7 evening:
that day's upload 409 share was only 0.93%, and five-minute peaks after 12:00
were 8.53%. The first sustained one-hour ratio violation replayed on October 8,
with full dwell eligible at 23:10 UTC. The edge policy does meet the October 7
detection objective at 15:55 UTC. Keeping 10% avoids paging the observed post-fix
3–7% old-build duplicate uploads (rolling peak 7.15%).

Ordinary mobile connectivity callers consume general internet state for offline
capture and sync wake-ups. They now retain the existing Cloudflare HEAD probe,
without a production Omi API fallback; an isolated Cloudflare outage can thus
report offline. Explicit capture-only physical qualification retains its local
backend health probe. Backend routes and Cloud Armor configuration are unchanged.
