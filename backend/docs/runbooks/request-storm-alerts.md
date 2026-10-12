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
field drift while preserving existing condition resource names (including the
ratio when adding a volume condition). An unchanged
deploy makes no write and preserves dwell. Provisioning failure warns in the
deploy summary; rerun the production deploy to retry, and confirm both policies
and their notification channels in Monitoring.

- **Prod API edge throttling storm:** `loadbalancing.googleapis.com/https/request_count`,
  `response_code=429`, production project and the three explicit API / sync /
  listen backend names in `.github/monitoring/api_edge_429_policy.json`.
  ALIGN_RATE over 300s, REDUCE_SUM, grouped by backend_target_name. Any backend
  above **2,000/min (33.3333/s) for 1,800s** pages. Backends are never summed together.
- **Prod sync duplicate upload share:** same metric on
  `custom-domains-api-omi-me-backend-sync-49a4-be`. The native ratio condition
  divides 409 count by **all** request count, with identical 300s ALIGN_SUM /
  REDUCE_SUM aggregations and grouping. A five-minute share **above 10%
  for 3,600s**, AND **more than 100 total requests per five-minute window
  for 3,600s**, pages. It is a ratio of counts, not an average of percentages.
  All threshold conditions treat missing data as inactive. The count floor
  prevents tiny-denominator incidents; both sync conditions select the same
  single backend.

The [Monitoring ratio API](https://docs.cloud.google.com/monitoring/alerts/policies-in-json)
supports numerator/denominator filters directly; neither MQL nor PromQL is
needed. The sync policy has two conditions with combiner AND. The reconciler
accepts one threshold condition or two threshold conditions combined with AND,
refuses ambiguous identities, preserves names on migration, and compares both
conditions before deciding whether a write is needed. The ratio policy body is checked in at
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
   request counts. WebSocket handshake errors are outside this HTTP hook.
   Raw `http.post` authentication/token exchange (including the local-dev
   custom-token path), dedicated audio-download clients, and custom-STT clients
   are also excluded: they do not traverse the shared API HTTP layer. Token
   exchange is an interactive startup/auth flow, not a sustained job poll;
   download and custom-STT requests commonly go to signed storage or third-party
   authorities. The shared-layer hook deliberately does not expand into those
   auth/media flows. If one of these raw clients targets an official Omi host,
   its 429 is still absent from this telemetry. The LB alert remains fleet-wide
   coverage for official-host HTTP throttling.

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
No pagination token was returned. The replay consumes the same five-minute ALIGN_SUM counts that the revised sync
policy uses; it does not reconstruct a rolling hour. Ratio and volume are
checked together for the full 3,600-second duration, with strict greater-than
comparisons and dwell reset on gaps or recovery. Edge rate and thresholds/durations
come from the checked-in policy JSON as well.

The independent review assumed native 3,600s alert alignment was a fixed
clock-hour bucket. Google documents that metric-alert alignment windows
[slide at evaluator time](https://docs.cloud.google.com/monitoring/alerts/concepts-indepth#alignment_period).
Rather than retain that ambiguity, the policy now uses 300s sums directly,
matching the sampled REST evidence and replay. Both sync conditions retain the
one-hour retest duration. Historical REST output contains non-overlapping 300s
samples; Monitoring also evaluates sliding windows between those samples.
Reported times are **five-minute sampled eligibility estimates**, not exact
Monitoring incident or notification timestamps. Unsampled intra-bucket dips,
ingestion delay and evaluator scheduling can alter the live first-alert time.

Baseline = Sep 21 04:00–Oct 7 12:00; incident = Oct 7 12:00–Oct 11 17:00;
post-fix = Oct 11 17:00–Oct 12 04:00 (all UTC).

| Window (UTC) | Series | Peak aligned value | First eligible fire (UTC) |
| --- | --- | ---: | --- |
| baseline | custom-domains-api-omi-me-backend-49a4-be | 960.6/min | none |
| baseline | custom-domains-api-omi-me-backend-listen-49a4-be | 463.0/min | none |
| baseline | custom-domains-api-omi-me-backend-sync-49a4-be | 123.8/min | none |
| baseline | sync 409 share (5m; volume-qualified) | 31.09% | none |
| incident | custom-domains-api-omi-me-backend-49a4-be | 21329.6/min | 2026-10-07T17:55:00Z |
| incident | custom-domains-api-omi-me-backend-listen-49a4-be | 283.0/min | none |
| incident | custom-domains-api-omi-me-backend-sync-49a4-be | 12.8/min | none |
| incident | sync 409 share (5m; volume-qualified) | 63.83% | 2026-10-09T00:15:00Z |
| post-fix | custom-domains-api-omi-me-backend-49a4-be | 26508.4/min | 2026-10-11T17:30:00Z |
| post-fix | custom-domains-api-omi-me-backend-listen-49a4-be | 114.2/min | none |
| post-fix | custom-domains-api-omi-me-backend-sync-49a4-be | 8.0/min | none |
| post-fix | sync 409 share (5m; volume-qualified) | 11.01% | none |

The edge threshold is **2.08×** the observed baseline maximum of 960.6/min,
with 30-minute dwell. It still meets the October 7 detection objective at
17:55 UTC in the sampled replay. The scout estimated health noise around
1,900 denials/hour (32/min); that noise cannot approach 2,000/min.
The post-fix edge policy deliberately still fires on old-build storms:
**there is no observed healthy fleet rollout window yet**.

For the volume floor, >100 requests per five-minute window corresponds to
>1,200/hour if sustained. The baseline median was 217 requests/five minutes;
567 of 4,702 baseline buckets had at most 100 requests. Every incident and
post-fix bucket cleared the floor; the first-alert retest hour had 1,269–2,111
requests per bucket. The floor therefore suppresses low-volume ratios without
delaying this incident. It excludes a ratio such as one 409 out of two requests.
Synthetic replay tests pin the low-volume case, exact count boundary, and
one-hour qualified dwell. The table reports peaks only in volume-qualified
buckets. Even the baseline's 31.09% and post-fix 11.01% five-minute spikes do not
last for the one-hour duration, so neither window pages.

The requested 10% ratio could **not** have fired by October 7 evening:
that day's upload 409 share was only 0.93%, and five-minute peaks after 12:00
were 8.53%. With the revised policy, the first full ratio-plus-volume retest
window is eligible at October 9 00:15 UTC. The old October 8 23:10 replay time
used a reconstructed rolling-hour statistic and no longer applies.

## Connectivity probe verification

`internet_connection_checker_plus` **2.7.2** was read from the pub cache:
`lib/src/internet_connection.dart` sends `http.head`, catches transport errors
as failure, and returns online as soon as any host succeeds when
`enableStrictCheck=false`. `lib/src/internet_check_option.dart` defaults to
exactly HTTP 200. We explicitly keep that status rule, three-second timeout,
no default host additions, and non-strict checks.

Production checks only `https://one.one.one.one` and
`https://captive.apple.com/`, Apple's connectivity-check host. These provide
independent alternatives without sending periodic checks to commerce sites.
An unauthenticated Apple HEAD returned 200 from the validation machine on
2026-10-12. That validates HEAD/status behavior here, not reachability from
every Chinese/corporate network. Geography-specific device testing was not
performed. Either host's success is enough; a failed single host cannot force
offline state.

Non-production profiles (`local_dev`, `local_prod`, `mobile_beta`) and
physical qualification check only `v1/health` relative to the configured API
base. A private fixture cannot be made online by a healthy public endpoint.
An accidental `api.omi.me` override falls back to public probes rather than
putting that production edge back on the timer.

The hermetic connectivity test calls the real package through a mocked HTTP
client. A successful Apple HEAD preserves live transport with Cloudflare blocked,
and a successful Cloudflare HEAD does the same with Apple blocked. All failed
HEADs feed the actual capture reducer and produce
`phoneBatchLive`, a batch session and `StartPhoneSessionStage(batch)`.
This proves transport selection at unit level; it does not claim microphone or
filesystem acceptance on a physical phone. Backend routes and Cloud Armor
configuration are unchanged.
