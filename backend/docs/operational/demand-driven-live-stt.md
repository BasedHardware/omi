# Demand-driven live STT (phase 4)

This listen-only gate starts every eligible session on the existing vendor tail.
After 15 seconds of stable hidden demand, capture moves to the existing Parakeet
window leg. A visible/unknown report, shared visible session, real-time consumer,
or rollback returns it to the vendor. Vendor return is immediate; cheap
re-admission waits the minimum dwell, so tab flips cannot repeatedly admit cheap
legs. The default dwell fits inside the existing 20-second replay-prefix budget
even for quiet capture with no emitted sentence anchor. No admission thresholds
change (including the two-request / 35% GPU gates).

| Environment variable | Default |
| --- | --- |
| `STT_LIVE_DEMAND_ENABLED` | `false` |
| `STT_LIVE_DEMAND_PERCENT` | `0` |
| `STT_LIVE_DEMAND_UID_ALLOWLIST` | empty, comma-separated authenticated UIDs |
| `STT_LIVE_DEMAND_MIN_DWELL_SECONDS` | `15`, valid range 5–300 |

The global enable is required for either allocation or allowlisting. Invalid
settings disable admission. `STT_FAILOVER_RECOVERY_ENABLED=true` is also required;
legacy recovery sessions keep their existing routing. English must be declared
by the user, with single-language mode and exactly English in the expected
language profile. Multi-language, non-English, BYOK, custom, multi-channel,
onboarding and phone-call sessions retain their existing route.

When globally enabled, every new listen session registers authenticated presence,
even if it cannot enter the routing cohort. Old clients never reporting state,
malformed/mixed reports and excessive reports remain unknown/visible. Presence
is shared across pods by stage-scoped Redis keys. Hidden state persists while the
socket heartbeats: existing clients only report changes. Missing heartbeat,
Redis failure, corrupt state, or more than 32 sockets for one user requires a
vendor. Stale members remain conservative until explicit close or 24 hours of
key inactivity. No audio/text is stored in these keys. Visibility from another
registered socket is reconciled within one second, plus bounded consumer reads.

Real-time app and developer webhook state comes from the same authorities as
listen/pusher fanout. Consumer reads refresh every five seconds, with a two-second
wall deadline; failed reads require vendors and back off for 60 seconds so
stalled reads cannot flood the shared database executor. Mentor uses the existing
per-user frequency opt-out, paid admission, and v2 cohort authority. Admitted
users count as active even while context is buffering; flag errors require
vendors. Consumers
must not be disabled merely to make this gate save money. Cheap admission
rechecks shared presence and consumers after dialing, before retiring the vendor.

A healthy handover dials under existing circuits/admission while the old leg
serves. Only after acceptance does it fence old callbacks and transfer capture
through the existing ordered replay pump. A prefix too large for the replay
wall budget declines the handover and keeps the old leg; it is never truncated
for a cost-policy switch. Window refusal/degradation pins that session to the
vendor for its remainder. Ordinary transport failures retain the existing bounded
recovery policy; demand switches do not consume failure episode allowances.

Listen counters:

- `omi_listen_live_lane_seconds_total{lane,reason}`: wall seconds on the adopted
  lane, including `baseline` flag-off sessions. This is session time, not billed
  VAD audio time; pair it with existing vendor audio counters for the cost receipt.
- `omi_listen_live_lane_switches_total{from_lane,to_lane,reason}`: adopted lane changes, including fallback.
- `omi_fallback_total{component="stt_live_session",reason,outcome}`: admission,
  candidate or replay failures, gate dependency outages, plus existing window
  recovery causes. Dependency outages emit once per socket/outage episode. Existing
  window admission/POST metrics distinguish capacity, pressure and degradation.
  Gate outages also count in `omi_listen_demand_failure_detail_total{demand_cohort,reason="gate_unavailable"}`
  so alerts can page on the admitted cohort only. Non-admitted sessions refresh
  their sibling-visible presence entry every 10 s (lease 30 s) instead of every
  second; an admitted session bridges exactly one missed heartbeat with the last
  good answer (under the 30 s lease) and otherwise fails to the vendor. Admission
  into Parakeet never uses a bridged answer. Failures are logged as
  `demand_presence_unavailable error_class=timeout|connection|response|redis_error|other`.

## Lead-owned rollout and rollback

1. Deploy the code dark. Verify full rollout and scrape coverage. Enable global
   presence with percent zero and empty allowlist on **all** listen pods; wait
   for full rollout and old pods/sockets to drain before admitting hidden capture.
   Mixed revisions cannot prove absence of another client's visibility.
2. Canary an English single-language allowlisted account. Exercise hidden →
   visible, two clients with mixed visibility, consumer enablement, and capacity
   refusal. Confirm transcript/capture continuity and the real GPU capacity curve.
3. Lead ramps percentage to at most **5%**. Wait **at least 12 hours** before any
   expansion. Compare session seconds, paid audio seconds, latency, transcript
   success, window POST/admission pressure and fallback causes against controls.
4. Roll back with `STT_LIVE_DEMAND_ENABLED=false`, percentage zero and empty
   allowlist in listen chart/runtime env; deploy through the normal workflow.
   Existing admitted sessions that observe the kill return to the vendor; pod
   replacement restores the original route for new sessions. Emergency Helm
   rollback belongs to the lead. No merge/deploy is part of this lane.
