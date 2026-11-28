# Live STT visibility and custody-fallback attribution (SCA-3656 Stage 0)

Telemetry only: no routing, no audio, no transcript, no data-path change. This is
the measurement the live-Soniox displacement decision needs before any session is
routed off a vendor stream.

## What changed

- `omi_listen_demand_capture_audio_seconds_total` gains `visibility`
  (`visible|foreground|background|unreported`). The counter still increments once
  per decoded frame before VAD and replay, so each captured second is attributed
  exactly once; the label is the `client_state` bucket in force at that frame.
  `unreported` is a client that never sent a state, never a guess: a malformed
  report keeps the last known bucket.
- `omi_soniox_connected_seconds_total` gains `provider`, `visibility` and
  `fallback_reason` (`none|policy|archive|claim`). Each flush interval is split at
  the recorded `client_state` transitions, so a session that goes background
  mid-flush is attributed to the bucket in force for each second. The transition
  log is bounded at 32 entries; the retained tail still splits a flush.
- `omi_listen_preview_batch_custody_total` gains `reason`. `live_fallback` now
  names `policy` (consent, ownership, locale or watch-state exclusion), `archive`
  (no durable original archive) or `claim` (the claim failed or was absent);
  `promoted` carries `none`. The reason is sticky on the session and is carried
  onto every live transport it opens, reconnects included, so connected seconds
  can be priced by cause.

## Why

The 2026-11-23 baseline read 591 Soniox connected hours/day ($61.02/day) against
9,708 live session wall hours, 48.7% of them background. Nothing in the metrics
said how many of those connected seconds happened while the app was in the
background, and the single `live_fallback` label mixed three causes. Both gaps
blocked sizing the displacement and pricing recoverable claim misses.

## Compatibility

Existing dashboard and alert queries aggregate over the new labels and keep
working: `sum by (demand_cohort)`, `sum by (outcome)`, and
`sum(increase(omi_soniox_connected_seconds_total[24h]))` are unchanged. No metric
name changed, so the scrape keep-list and metric inventory need no edit. Zero
children are pre-created for every new label value.

## Rollout

One backend deploy. No kill switch is needed because no behavior changes; the
existing `CLOUD_LIVE_STT_MODE=stream` remains the routing default. Stage 1
(routing background off the vendor stream) is a separate design and is not in
this change.
