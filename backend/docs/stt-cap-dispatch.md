# Transcription cap at provider dispatch

`STT_CAP_DISPATCH_ENFORCEMENT` is a default-off backend rollout switch. This PR
adds no deployment binding and does not enable it. Enabling changes the policy
for existing capped paid plans: exhausted sync uploads wait as audio rather than
being transcribed into locked conversations. Product approval is required before
activation. No ladder-v1 code or prices change.

## Boundaries

Live receiver creation installs one funded admission state for the session.
Actual Deepgram, Soniox, Modulate, Parakeet and window-provider constructors use
that state, including direct registry endpoints and fallback/recovery legs.
The state debits accepted PCM seconds across channels, replay and successors.
The existing 60-second usage flush refreshes it from ordinary funded allowance;
root counters retain their received-audio semantics. Timestamp adapters suppress
before recording accepted-provider spans. Denial is a policy pause, not provider
death: receiving, pusher audio and existing private-cloud/raw archive paths
continue. Accepted provider queues drain. Nothing enables cloud audio retention
for live users who did not already opt into it. Custom/on-device STT bypasses the
new state. The existing Plus threshold event still uses its existing wire shape.

Deepgram cloud with a request key is customer funded. Every other provider,
including self-hosted Deepgram and an Omi-funded fallback from BYOK, uses the
ordinary allowance with both BYOK quota and desktop-paywall exemptions disabled.
No key or identity is a metric label.

Sync v1 intake and v2 execution hold full decoded WAVs before VAD when denied.
The shared segment processor rechecks immediately before each STT invocation,
including its empty-result retry. Late exhaustion holds the remaining segment.
No denied segment reaches cloud STT. A successfully persisted hold is acknowledged
without creating a locked transcript. Hold failures fail the upload/job; callers
must retain/retry their source audio. V1 adds `held_audio` and `held_files` to the
exhausted acknowledgment; v2 adds `held_audio` to its durable result.

Batch compute authorization checks current funded allowance. The worker calls
that authority again after decode/VAD and before each ASR microbatch. Missing
worker policy authority holds work. Held work uses the scheduler's existing
`defer`, preserving raw artifacts and refunding the provider-failure attempt.
Quarantine recovery rechecks both before fetching audio and before claiming its
sole provider attempt; a denied prepared intent remains recoverable.

## Durable sync recovery

Encrypted source audio lives under the existing private-cloud bucket's
`chunks/{uid}/cap-held/` owner prefix; encrypted metadata and progress live under
`users/{uid}/stt_cap_holds`. The checkpoint has no application TTL. Existing
account deletion recursively removes the manifest and purges this chunk prefix.
A failed object upload cannot publish a successful manifest or acknowledgment.
Concurrent identical uploads cannot overwrite a recovery checkpoint.

The existing `locked_content_recovery` authenticated-request path kicks an async
recovery pass independently of its once-per-month unlock receipt and legacy reset
flag. A distributed 60-second cooldown bounds requests; token-fenced renewable
leases prevent concurrent processing of a hold. At reset or upgrade, current
funded allowance must pass again before every recovered piece is sent. Recovery
reuses VAD, segment intake, enrichment and optional playback finalization. Piece
receipts and idempotent usage keys preserve progress across retries. Completed
objects are deleted only after content and usage settlement. WS-only and inactive
accounts wait for their next authenticated HTTP request; there is no new cron.
Rolling back the dispatch flag pauses this new recovery, preserving its audio.

## Launch configuration and measurement

With enforcement off, launch-date handling is unchanged. With it on, missing or
invalid `SUBSCRIPTION_LAUNCH_DATE` logs `event=stt_cap_launch_config` and increments
`omi_stt_cap_launch_config_errors_total{reason="missing|invalid"}`. Finite-plan
allowance fails conservatively instead of inventing zero usage. A valid explicit
future date continues to mean intentionally unlaunched.

`omi_stt_cap_provider_audio_seconds_total` is additive provenance:

- `path`: `live` or `sync`;
- `outcome`: `accepted`, `suppressed` (live), or `held` (sync);
- `provider`: a bounded serving family or `unknown`;
- `allowance`: `exhausted` or `available`, at the admission/acceptance observation.

Accepted live quantities count PCM accepted by a provider adapter, including
replay; failed sends do not count. Suppressed quantities count input PCM, before
VAD. Sync successful provider calls count WAV duration, including retries;
quarantine recovery counts its accepted request duration. The GPU worker counts
actual padded microbatch audio and persists additive `cap_dispatch` provenance
with `omi_funded_accepted_provider_audio_seconds` and its compute admission origin.
Held sync quantities count durably retained audio; queue denials count attempted
held quantities and can repeat across policy retries. They are not a distinct
captured-content counter. Provider-internal retries/uncertain failures are not an
exact vendor invoice ledger. Existing root counters and unit projections do not
change, and no new provenance is emitted with the flag off.

Admission checks are not distributed quota reservations. Concurrent already
admitted work can drain across the cap; live refresh is bounded by its existing
flush cadence. Do not interpret a zero violation metric as proof against every
cross-process admission race.

## What users see when the flag is on

- **Mobile, on-device overflow flag off:** capture continues as main permits, but
  exhausted managed sessions stop producing new cloud transcripts. Existing Plus
  threshold handling remains. Uploaded offline audio waits durably; this PR adds
  no held-content card or automatic on-device processing of that backlog.
- **Mobile, on-device overflow flag on:** eligible clients keep the existing
  on-device offer/mode switch. Custom/on-device sessions continue normally.
  Already-held server uploads still wait for reset/upgrade recovery.
- **macOS:** the existing threshold handler can stop capture, as it does today.
  The backend also refuses new funded sends if the client continues; accepted work
  drains. There is no new macOS on-device overflow flow in this PR.
- **Web:** no new on-device offer is added. Exhausted funded live transcription
  pauses; supported sync uploads wait for recovery. Existing content stays as it
  was, and current clients do not gain a new waiting-audio view from these additive
  backend fields.

These visible gaps and the change from locked transcripts to held audio are the
activation decision for David; default-off deployment preserves today's policy.

## Follow-ups in #21488

Findings #6 and #7 remain outside this PR: budget-aware live refresh when ladder
allowance returns `remaining_seconds=None`, and conservative admission when usage
unit projection has coverage gaps. Carry this funded-dispatch/held-audio contract
into that ladder cutover without changing the legacy meter here.
