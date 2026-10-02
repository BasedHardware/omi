# Screen task extraction: default-off Jev gate

`screen_task_jev_gate` defaults off for every bundle. Enabling it is separate
from merging this code. OCR and bounded local task/profile context go to
TypeSafe/Jev when enabled; enablement requires privacy approval. This PR does
not change live flags, deploy anything or use personal screen frames.

Capture binds the original owner and authorization generation plus the app's
exclusion generation before capture suspends. The immutable frame carries that
binding through tracking, suppressed distribution, context departure and task
queues. Processing never assigns the current owner to old pixels. Both pipelines
recheck the original authority at upload, awaited handler boundaries, workflow
control, candidate creation, SQLite transactions and receipt updates. Same-UID
sign-out/sign-in revokes old continuations. Durable outbox retries capture the
current authorization for that owner's existing database rows.

Known browser apps reject private-window title markers (Incognito, Private
Browsing, InPrivate, Private Window/Tab and the listed localized equivalents)
before task capture and again before upload. Title rules cannot detect a private
window that exposes no private marker. Excluding or re-including an app advances
its exclusion generation, purges matching pending task pixels, and invalidates
already running frame work. Data already transmitted cannot be recalled.

When enabled, local Vision OCR feeds ordered normalized-line dedupe keyed by
owner, authorization generation, app and normalized window identity. A monotonic
processing clock gives entries a 60-second TTL and a 64-entry bound. Reusing an
old captured frame after 60 processing seconds is eligible again. Telegram and
Messages ignore an approximate sidebar; other apps retain all blocks. Any line,
count or order difference passes. Punctuation, ownership/layout changes and
attachment-only changes can still collide: this is not screenshot equivalence.
No fuzzy or subset matching is used.

Local SQLite FTS selects at most eight related rows including active, completed,
deleted and staged suppression evidence. Retrieval itself makes no embedding
request. The assistant's existing embedding-service initialization remains, and
legacy recovery can use its existing network semantic search. Gate context uses
four descriptions and 1024 profile characters. Gate OCR is full OCR, up to 12,000
Swift characters, rather than the cropped dedupe line list.

The authenticated OCR-only `POST /v1/screen-task/gate` applies company-paid
`screen_frame_judge` managed-plan authorization and the trial paywall. Separate,
boost-exempt gate policies allow 30 requests/minute and 1500/day per UID. Gate
limiter unavailability fails closed. Jev uses one gateway decision attempt with
a two-second provider timeout; this does not bound gateway queue time. Threshold
`SCREEN_TASK_JEV_THRESHOLD` defaults .5 and reject audit fraction
`SCREEN_TASK_JEV_AUDIT_RATE` defaults .01. Provider outages, malformed gate
responses, and empty/oversized OCR admit screenshot extraction with named fallback
telemetry while authority remains valid. Plan/auth/quota/backpressure denials are
terminal. Rejection uploads no screenshot unless audited.

A fresh admission read every 30 seconds grants a 55-second lease measured from
request start. SDK cached reload notifications cannot renew that lease. The
client reads the public flag-evaluation endpoint and authenticated
`GET /v1/screen-task/admission`; a failed refresh leaves existing leases to expire.
`SCREEN_TASK_STOP=true` is a backend ops stop read at each gate and flagged
screenshot dispatch. The admission endpoint reports it; gate/proxy return typed
409 `screen_task_stopped`, never an ordinary provider error. The running client
stops new feature gate/extraction dispatches and feature-result mutations within
55 seconds of its last admission request (within the 60-second requirement),
even if refresh hangs. It rechecks before every dispatch and mutation. Queued
frames after stop use legacy with their original binding; late feature results
are discarded. Stop during gate processing permits one bounded legacy recovery.
These controls stop the new pipeline, and do not disable the legacy extractor or
change reservation routing. Already committed canonical outbox rows remain
durable and can finish delivery under the current owner; admission leases govern
new feature-frame work.

The screenshot extractor makes one 3.8 Flash request through the existing proxy,
thinking level low, 2048 output tokens and bounded JSON (at most eight tasks,
bounded strings/tags). Capacity/location selection belongs to the reservation
routing contract; this PR does not change it. Canonical capture facts map into
the existing policy/outbox/pending-candidate path (INV-TASK-2). Only supplied
active canonical IDs may authorize relation targets. Items decode and validate
independently; one invalid sibling does not discard valid items. `MAX_TOKENS`
retains fully closed task objects from a truncated tasks array. Bounds reduce
output pressure; eight items are not guaranteed to complete under the cap.
Valid empty output preserves an activity observation. Invalid extraction/output
schema, auth, plan, quota, 429 and explicit `X-Omi-Retryable:false` responses are
terminal. `Retry-After` postpones subsequent feature requests for that owner and
session. No same-model repair or automatic schema-to-legacy fallback occurs.

A genuine extraction provider 5xx/timeout/offline permits one explicit legacy
request, with no inner retry/model ladder. Thus a feature frame has at most one
gate, one new screenshot request and one legacy screenshot request; provider
internal retries are outside this client budget. A typed legacy retirement
refusal is terminal and quiet. Feature-off retains the existing legacy loop,
with original-owner/privacy hardening and its existing retry/header behavior.
The bounded feature recovery call honours the feature cooldown; ordinary
feature-off work does not acquire that separate gate/extraction cooldown.
Capture still proposes pending candidates, never accepted action items. Policy
rejection, coalescence and an unsynced outbox are not delivered suggestions.

Every processed frame emits `Screen Task Frame Terminal` with `schema_version=2`,
`pipeline` (`screen_task_v2`, `legacy`, `legacy_recovery`), `gate_outcome`,
`audit_sample`, actual `extractor` (`gemini_3_8`, `legacy`, `none`), terminal
`outcome`, `error_class`, `fallback_reason`, `eligible_frames` (one for a valid owner/privacy-bound frame),
`feature_enabled_at_start`, `client_bypass`,
`invalid_items`, stage attempt counts (`legacy_attempts` counts loop invocations,
not inner feature-off tool/model requests), and delivery counts `policy_rejected`,
`outbox_saved`, `coalesced`, `pending_delivered`, `failed`. Stage durations are
`ocr_ms`, `retrieval_ms` (including profile lookup), `gate_ms`, `extraction_ms`,
`delivery_ms`, and `capture_to_terminal_ms` (includes queue delay). A stage that
never completes can report zero; this is not a separate timeout-duration metric.
Event properties contain no screen/task text, window/app titles, IDs or scores.
Analytics association uses the capture owner, including revocation outcomes, so
an account swap cannot attribute a prior owner’s delivery to the incoming user.

`desktop_health_event` / `event=fallback_triggered` retains the registered areas
`screen_task_gate` and `screen_task_extraction`, with bounded reasons
`ocr_unusable`, `gate_invalid_response`, `provider_5xx`, `timeout`, `offline`,
`dispatch_disabled`. Backend Jev fail-open uses
`omi_fallback_total{component="screen_task_gate",reason="gate_unavailable"}`.
`omi_screen_task_gate_frames_total{outcome}` counts backend gate admissions,
including terminal plan/quota/stop states;
`omi_screen_task_client_bypass_total` counts flagged screenshot requests carrying
client-bypass metadata. Client terminal events are the authoritative eligible
frame denominator, since rejected and pre-upload-failed frames send no screenshot.
Backend counters cannot deduplicate ambiguous client transport outcomes.

Audited rejects emit `Task Extracted` with `gate_outcome=rejected`,
`audit_sample=true`, actual `extractor`, `extracted_candidate_count` (0–8) and
`task_count` equal to delivered pending suggestions, including zero. The ordinary
per-task extraction event is suppressed for audits. Compare audit counts with
`pending_delivered` in the terminal event; legacy-produced results are identified
separately. An audit is model disagreement evidence, not human recall ground
truth. Existing candidate-attribution events retain canonical IDs separately.
Flag-configured logging suppresses inherited content-bearing task logs through
extraction, recovery and staging. Other capture/coordinator logs are outside that
scope, and derived context/task content still persists in observations/outbox and
candidates. Provider residency, retention and real cost are not verified here.

At each consented ramp stage read these signals:

| Signal | Event/fields or metric |
| --- | --- |
| Gate pass rate | Terminal events, `feature_enabled_at_start=true`, `gate_outcome=passed` / sum of `eligible_frames`; report rejected, fail-open, dedupe and bypass separately. Backend gate counter cross-checks received calls |
| Audited-reject misses | `gate_outcome=rejected`, `audit_sample=true`, `extractor=gemini_3_8`, sum `pending_delivered`; show audited frame count and human labels separately |
| Fallback rate | `desktop_health_event`, `event=fallback_triggered`, the two areas and `reason`; terminal `fallback_reason` over processed feature frames; distinguish gate bypass from extractor recovery |
| Delivered suggestions/user-day | Sum terminal `pending_delivered` by analytics user/day and actual extractor; compare a contemporaneous legacy baseline and active-user exposure |
| Latency | Terminal stage `*_ms`, especially `capture_to_terminal_ms`; slice by pipeline/extractor and messaging cohort using existing cohort metadata |
| Errors | Terminal `outcome=failed`, `error_class`, `invalid_items`, `failed`; backend gate terminal outcome counts and existing proxy status/error telemetry |

Percentages and hold periods remain the operator's decision. Offline behavioral
coverage is required before consented dogfood; human labeling of positives,
rejects and dedupe skips is needed before recall claims. Historical benchmark
aggregates and modeled daily costs are not production acceptance evidence.
No fleet-wide dollar ceiling is introduced by this PR. Windows remains outside
this implementation. See [reservation transition](../../../backend/docs/vertex-pt-flash.md)
for the sibling's routing/capacity authority and accepted thinking-config changes.
