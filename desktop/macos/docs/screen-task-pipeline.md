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
before assistant/Rewind distribution and again before upload. A vanished window is
re-resolved, privacy-checked and bound before the replacement window is captured. Title rules cannot detect a private
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
ordinary legacy can use its existing network semantic search. Gate context uses
four descriptions and 1024 profile characters. Gate OCR is full OCR, up to 12,000
Swift characters, rather than the cropped dedupe line list.

The authenticated OCR-only `POST /v1/screen-task/gate` applies company-paid
`screen_frame_judge` managed-plan authorization and the trial paywall. Separate,
boost-exempt gate policies allow 30 requests/minute and 6000/day per UID. Gate
limiter unavailability fails closed. The daily budget covers 5760 frames at the
15-second messaging cadence. Gate-budget 429 responses are typed
`gate_budget_exhausted`; the client caps only that budget cooldown at the
60-second burst window and emits `error_class=gate_budget_cooldown`, including
frames suppressed during cooldown. Screenshot/proxy Retry-After remains uncapped.
Jev uses one gateway decision attempt with
a two-second provider timeout; this does not bound gateway queue time. Threshold
`SCREEN_TASK_JEV_THRESHOLD` defaults .5 and reject audit fraction
`SCREEN_TASK_JEV_AUDIT_RATE` defaults .01. Provider outages, malformed gate
responses, and empty/oversized OCR admit screenshot extraction with named fallback
telemetry while authority remains valid. Plan/auth/quota/backpressure denials are
terminal. Rejection uploads no screenshot unless audited.

A fresh admission read every 30 seconds grants a 55-second lease measured from
request start and bound to the owner/session that fetched it. An account or
same-UID session transition revokes the lease immediately. SDK cached reload
notifications cannot renew that lease. The
client reads the public flag-evaluation endpoint and authenticated
`GET /v1/screen-task/admission`; a failed refresh leaves existing leases to expire.
`SCREEN_TASK_STOP=true` is a backend ops stop read at each gate and flagged
screenshot dispatch. The admission endpoint reports it; gate/proxy return typed
409 `screen_task_stopped`, never an ordinary provider error. Identified macOS
builds below `SCREEN_TASK_MIN_MACOS_BUILD` (default 12435; invalid values keep
that default) get a separate typed 409 `screen_task_build_below_floor` with
`X-Omi-Retryable: false` on the gate, admission, and flagged screenshot proxy.
Unidentified, conflicting, Windows, and other callers are unchanged, and an
unflagged proxy request stays on its existing lane. Builds 12433 and 12434
fail open on that gate error into flagged extraction, then take one legacy
extraction when the proxy refuses; they do not retry the 409 or show it as a
user error. The running client
stops new feature gate/extraction dispatches and feature-result mutations within
55 seconds of its last admission request (within the 60-second requirement),
even if refresh hangs. It rechecks before every dispatch and mutation. Queued
frames after stop use legacy with their original binding; late feature results
are discarded. Stop during gate processing selects the ordinary owner-bound legacy loop.
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

An extraction provider 5xx/timeout/offline terminates the frame with
`outcome=failed`, `error_class=provider_outage`, `extractor=none` and a bounded
`fallback_reason` identifying 5xx/timeout/offline. No legacy request, observation,
staging or content-dedupe entry is created; the next trigger retries naturally.
A feature frame has at most one gate and one new screenshot request. A typed legacy retirement
refusal is terminal and quiet. Feature-off retains the existing legacy loop,
with original-owner/privacy hardening and its existing retry/header behavior.
Ordinary feature-off work does not acquire the separate gate/extraction cooldown.
Legacy model responses are revalidated before any tool executes, and semantic
search passes the original authorization into embedding. Auth acquisition and
actual embedding dispatch both revalidate the original owner/session and app privacy.
The screenshot test runner captures its job owner before loading database rows,
binds each app/window before loading pixels, and uses the same required original
authorization through replay inference and tools. Revoked replay results never
reach the test window.
Capture still proposes pending candidates, never accepted action items. Policy
rejection, coalescence and an unsynced outbox are not delivered suggestions.

The sibling reservation policy can return HTTP 200 with `X-Omi-Error-Class=legacy_task_reservation_inactive`
and `X-Omi-Reservation-State=inactive`. The client terminates quietly without decoding
its synthetic `no_task_found` as inference. Terminal `outcome=refused`,
`error_class=legacy_task_reservation_inactive`, `extractor=none`, zero delivery/failure
counts and `pipeline=legacy` identify the refusal. No retry, observation or candidate is created.

Every processed frame emits `Screen Task Frame Terminal` with `schema_version=2`,
`pipeline` (`screen_task_v2`, `legacy`), `gate_outcome`,
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
Frame-terminal counts describe processing at that moment; deferred receipts do
not rewrite a prior terminal event. Analytics association uses the capture owner, including revocation outcomes, so
an account swap cannot attribute a prior owner’s delivery to the incoming user.

`desktop_health_event` / `event=fallback_triggered` retains the registered areas
`screen_task_gate` and `screen_task_extraction`, with bounded reasons
`ocr_unusable`, `gate_invalid_response`, `provider_5xx`, `timeout`, `offline`,
`dispatch_disabled`. Backend Jev fail-open uses
`omi_fallback_total{component="screen_task_gate",reason="gate_unavailable"}`.
`omi_screen_task_gate_frames_total{outcome}` counts backend gate admissions,
including terminal plan/quota/stop states;
`omi_screen_task_build_floor_refusals_total{surface}` counts build-floor refusals
on `gate`, `admission`, and `proxy` with no build number or user agent;
`omi_screen_task_client_bypass_total` counts flagged screenshot requests carrying
client-bypass metadata. Client terminal events are the authoritative eligible
frame denominator, since rejected and pre-upload-failed frames send no screenshot.
Backend counters cannot deduplicate ambiguous client transport outcomes.

Every new outbox row persists bounded `screen_task_delivery_provenance` containing
`extractor`, `gate_outcome` and `audit_sample`. The first canonical receipt claims
a `Screen Task Delivery Completed` event in the receipt's SQLite transaction.
Repeated receipt updates and coalesced/reused candidates do not claim another
event. Immediate and deferred retries use the same receipt path, retaining the
original extractor/audit provenance rather than attributing it to the retrying
frame. Older unsynced rows without provenance report `extractor=unknown`,
`gate_outcome=none`, `audit_sample=false`.

Completion properties are `schema_version=1`, `extractor`, `gate_outcome`,
`audit_sample`, `delivery_status` (pending/accepted/rejected/expired/unknown),
`pending_delivered` (one only for a first pending receipt), and `delivery_path`
(immediate/deferred). They contain no screen/task text, titles or identifiers.
The SDK envelope associates the event with the receipt owner's `distinctId`.
Local transactional claiming prevents duplicate events on receipt replays and
process restarts; SDK delivery is best effort, and a crash between the receipt
commit and SDK enqueue can lose the event. This is not an exactly-once analytics
transport guarantee.

Audited rejects still emit `Task Extracted` with `gate_outcome=rejected`,
`audit_sample=true`, actual `extractor`, `extracted_candidate_count` (0–8) and
`task_count` equal to immediately delivered pending suggestions, including zero.
The ordinary per-task extraction event is suppressed for audits. Read delivery
completion events for both immediate and deferred audit suggestions; use frame
terminal events and `Task Extracted` for the original processing denominator.
An audit is model disagreement evidence, not human recall ground
truth. Existing candidate-attribution events retain canonical IDs separately.
Flag-configured logging suppresses inherited content-bearing task logs through
extraction, ordinary legacy and staging. Other capture/coordinator logs are outside that
scope, and derived context/task content still persists in observations/outbox and
candidates. Provider residency, retention and real cost are not verified here.

At each consented ramp stage read these signals:

| Signal | Event/fields or metric |
| --- | --- |
| Gate pass rate | Within terminal events filtered to `feature_enabled_at_start=true`, count `gate_outcome=passed` / sum of `eligible_frames`; report rejected, fail-open, dedupe and bypass separately. Backend gate counter cross-checks received calls; report `outcome=gate_budget_exhausted` separately |
| Audited-reject misses | Completion events filtered to `gate_outcome=rejected`, `audit_sample=true`, `extractor=gemini_3_8`, sum `pending_delivered`; show terminal audited frame count and human labels separately |
| Fallback rate | `desktop_health_event`, `event=fallback_triggered`, the two areas and `reason`; terminal `fallback_reason` supplies cause context (extraction outages issue no fallback request); distinguish gate bypass from admission-loss legacy |
| Delivered suggestions/user-day | Sum completion `pending_delivered` by analytics user/receipt day and original extractor, sliced by `delivery_path`; compare a contemporaneous legacy baseline and active-user exposure |
| Latency | Terminal stage `*_ms`, especially `capture_to_terminal_ms`; slice by pipeline/extractor and messaging cohort using existing cohort metadata |
| Errors | Terminal `outcome=failed`, `error_class` (including `provider_outage` and `gate_budget_cooldown`), `invalid_items`, `failed`; backend gate terminal outcome counts and existing proxy status/error telemetry |

Percentages and hold periods remain the operator's decision. Offline behavioral
coverage is required before consented dogfood; human labeling of positives,
rejects and dedupe skips is needed before recall claims. Historical benchmark
aggregates and modeled daily costs are not production acceptance evidence.
No fleet-wide dollar ceiling is introduced by this PR. Windows remains outside
this implementation. See [reservation transition](../../../backend/docs/vertex-pt-flash.md)
for the sibling's routing/capacity authority and accepted thinking-config changes.
