# Feature-flag authority registry

Flipping a row here does not turn a feature on; PostHog / bundle identity /
`runtime_env` remain the live levers. This file is a catalog of *which* lever
owns each gate, not the switch itself.

Inventory below was measured 2026-09-04 against `origin/main` `7704e0b` plus
live PostHog project **302298**, then re-checked on this tree
(`3d72f77aea`). Prefer the worktree if a key has moved.

This is **not** a second classification of deployment wiring. Secret vs config
vs `public_build` still lives only in
[`config/deployment-setting-classification.json`](../../config/deployment-setting-classification.json)
and [`deployment-setting-classification.mdx`](deployment-setting-classification.mdx).
JIT admission (allowlist, `jit-processing-v1`, kill, decoy names) is specified
in [`jit_rollout_authority.mdx`](jit_rollout_authority.mdx); this registry
points at that contract and does not replace it.

## How to read the three authorities

### Bundle identity

Omi Beta (`com.omi.computer-macos.beta`) vs stable (`com.omi.computer-macos`).
Use this for dogfood features whose backend half is only on the **dev** API:
Beta is the only production-family identity that talks to that API
(`DesktopBackendEnvironment.shouldForceDevelopmentServingEndpoints`). Stable
stays dark until an explicit PostHog enable flag is true. Named/dev bundles
are a third identity (non-production) and usually take a local `OMI_FORCE_*`
override instead of PostHog.

### PostHog (project 302298)

Per-user, percent, or remote kill **without a new build**. The SDK
(`PostHogManager.isFeatureEnabled`) is fail-closed while uninitialized: a
missing row is `false`. That is why a Beta-by-default feature needs an
**inverted kill** (`*_kill` true means off) so "flag missing" leaves Beta on,
and why a dark production launch needs a **positive** enable flag so "flag
missing" stays off.

### `runtime_env`

Whole environment or Cloud Run job, declared in
`backend/deploy/runtime_env/{_base,dev.overlay,prod.overlay}.yaml`. Use this
for fleet-wide backend switches. Do not put those in PostHog.

## Rules

1. If Swift or Python names a PostHog key, the PostHog row must exist (even
   inactive / 0%). Missing kill rows cannot disarm a bad Beta.
2. If a PostHog row exists and no code reads it for enablement, delete it or
   mark it `unused`.
3. Kill switches for Beta-by-default features must exist in PostHog
   (inactive) so a bad Beta can be disarmed without a build.
4. Do not put fleet-wide backend switches in PostHog.
5. Do not put Beta-vs-stable enablement in PostHog person properties.
   `update_channel` was measured unreliable (person-side channel null or
   `stable` for most Beta installs). Bundle identity is the authority.

`BetaDogfoodRollout` is the shared client shape: non-production requires an
explicit `OMI_FORCE_*=1` (except where noted), Beta is on unless the kill is
true, stable is on only when the enable flag is true.

## Registry

Columns: **PH row** is live PostHog 302298 as of 2026-09-04 (`yes` / `no` /
`unused` = row exists but code does not read it for gating). **Fail** is what
happens when the live lever is missing or unreachable.

| Key | Name | Authority | Fail | Who it hits today | PH row | runtime_env | Code |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `desktop-onboarding-rerun` | Onboarding rerun | posthog | closed (off) | 100% of clients; each install evaluates payload locally | yes (100%, payload `generation=1`, `min_account_age_days=7`, `active_questions_30d=8`) | — | `OnboardingRerunPolicy` in `desktop/macos/Desktop/Sources/Onboarding/OnboardingRerunPolicy.swift` |
| `context_buckets` | Context buckets enable | bundle | n/a for PH; stable off, Beta on unless kill | Beta Mac; stable stays on fallback assistants | unused (active; cohort 484445 ~307 **or** person `update_channel=beta`. Client does not read this for enablement) | — | `ContextBucketsFeature.flagName` / `isEnabled` in `desktop/macos/Desktop/Sources/ProactiveAssistants/Core/ContextBucketsFeature.swift` |
| `context_buckets_kill` | Context buckets kill | posthog | Beta fail-open (inverted) | nobody (inactive) | yes (inactive) | — | `ContextBucketsFeature.killSwitchFlagName` |
| `context_buckets_destination_kill` | Destination routing kill | posthog | Beta fail-open (inverted) | nobody (row missing ⇒ hop stays on for Beta) | no | — | `ContextBucketsFeature.destinationKillSwitchFlagName` / `isDestinationRoutingEnabled` |
| `context_buckets_retrieval_kill` | Retrieval hop kill | posthog | Beta fail-open (inverted) | nobody (row missing) | no | — | `ContextBucketsFeature.retrievalKillSwitchFlagName` / `isRetrievalHopEnabled` |
| `context_buckets_departure_eval_kill` | Departure evaluation kill | posthog | Beta fail-open (inverted) | nobody (row missing) | no | — | `ContextBucketsFeature.departureEvaluationKillSwitchFlagName` / `isDepartureEvaluationEnabled` |
| `context_buckets_dwell_refresh_kill` | Dwell refresh kill | posthog | Beta fail-open (inverted) | nobody (row missing) | no | — | `ContextBucketsFeature.dwellRefreshKillSwitchFlagName` / `isDwellRefreshEnabled` |
| `context_buckets_fact_write_policy_kill` | Fact write-policy kill | posthog | Beta fail-open (inverted) | nobody (row missing) | no | — | `ContextBucketsFeature.factWritePolicyKillSwitchFlagName` / `isFactWritePolicyEnabled` |
| *(none)* | Workstream pooling | bundle (hardcoded) | n/a | non-prod only (`OMI_FORCE_BUCKET_WORKSTREAMS=0` off). Production/Beta always false. No remote flag on purpose | no | — | `ContextBucketsFeature.isWorkstreamPoolingEnabled` |
| *(none)* | Proactive candidates | bundle (hardcoded) | n/a | non-prod only (`OMI_FORCE_BUCKET_CANDIDATES=0` off). Production/Beta always false. No remote flag on purpose | no | — | `ContextBucketsFeature.isProactiveCandidatesEnabled` |
| `system_calendar_meeting_context` | System calendar meeting context | hybrid | Beta fail-open / stable fail-closed | Beta Mac (dev API has calendar read on). Stable off (flag missing). Kill row missing | no | pairs with `CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED` | `SystemCalendarMeetingContextFeature` in `desktop/macos/Desktop/Sources/CalendarMeetingContext/SystemCalendarMeetingContextFeature.swift` |
| `system_calendar_meeting_context_kill` | System calendar kill | posthog | Beta fail-open (inverted) | nobody (row missing; cannot remotely disarm Beta) | no | — | `SystemCalendarMeetingContextFeature.killSwitchFlagName` |
| `on_device_meeting_identity` | On-device meeting identity | hybrid | Beta fail-open / stable fail-closed | Beta Mac. Stable off. Kill row missing | no | pairs with `CONVERSATION_OCR_CONTEXT_ENABLED` | `OnDeviceMeetingIdentityFeature` in the same file |
| `on_device_meeting_identity_kill` | On-device identity kill | posthog | Beta fail-open (inverted) | nobody (row missing) | no | — | `OnDeviceMeetingIdentityFeature.killSwitchFlagName` |
| `desktop_interject` | Interject (voice reply on floating cards) | hybrid | Beta fail-open / stable fail-closed | Beta Mac. Stable off. Kill row missing | no | — | `InterjectFeature` in `desktop/macos/Desktop/Sources/FloatingControlBar/Interject/InterjectFeature.swift` |
| `desktop_interject_kill` | Interject kill | posthog | Beta fail-open (inverted) | nobody (row missing) | no | — | `InterjectFeature.killSwitchFlagName` |
| `negative_feedback_remediation` | Thumbs-down remediation | hybrid | Beta fail-open / stable fail-closed | Beta Mac. Stable off. Kill row missing | no | — | `NegativeFeedbackRemediationFeature` in `desktop/macos/Desktop/Sources/Chat/NegativeFeedbackRemediationFeature.swift` |
| `negative_feedback_remediation_kill` | Thumbs-down remediation kill | posthog | Beta fail-open (inverted) | nobody (row missing) | no | — | `NegativeFeedbackRemediationFeature.killSwitchFlagName` |
| `screen_activity_lossless_sync` | Lossless screen-activity sync | hybrid | Beta fail-open / stable fail-closed. Non-prod defaults **on** (`OMI_FORCE_LOSSLESS_SCREEN_SYNC=0` off) | Beta Mac + named/dev. Stable on the legacy cursor until the enable flag is true | no | — | `ScreenActivityLosslessSyncFeature` in `desktop/macos/Desktop/Sources/ScreenActivitySyncService.swift` |
| `screen_activity_lossless_sync_kill` | Lossless sync kill | posthog | Beta fail-open (inverted) | nobody (row missing) | no | — | `ScreenActivityLosslessSyncFeature.killSwitchFlagName` |
| `desktop_persistent_capture_stream` | Persistent window-capture stream | posthog | **fail-closed for all production bundles including Beta**. Missing ⇒ off for shipped users. Non-prod defaults on (`OMI_PERSISTENT_CAPTURE_STREAM=0` off) | named/dev only | no | — | `ScreenCaptureStreamFeature` in `desktop/macos/Desktop/Sources/ScreenCaptureStreamFeature.swift` |
| `desktop-rating-prompt-disabled` | Rating-prompt kill | posthog | inverted: missing ⇒ prompt **stays on** | nobody (row missing; prompt still shows) | no | — | `RatingPromptPolicy.killSwitchFlag` in `desktop/macos/Desktop/Sources/RatingPrompt.swift` |
| `jit-processing-v1` | JIT processing admission | hybrid | non-allowlist fail-closed; allowlist still admits if PostHog is down | dual admission: PostHog 100% of cohort 529814 (2 UIDs) **and** hardcoded `JIT_ADMISSION_ALLOWLIST` (same 2 UIDs) | yes | — | `JIT_PROCESSING_FLAG_KEY` / `JIT_ADMISSION_ALLOWLIST` / `resolve_jit_rollout_sync` in `backend/utils/jit_rollout.py`. See `jit_rollout_authority.mdx` |
| `jit-processing-kill-switch-v1` | JIT kill | posthog | unknown/absent kill never blocks by itself | nobody at 0% rollout; **only** lever that can revoke the allowlist | yes (active, 0%) | — | `JIT_KILL_SWITCH_FLAG_KEY` |
| `daily-memory-sweep-v1` | Daily memory sweep (decoy) | posthog | n/a — **not admission** | nobody. Prod job is env-off. Sweep cohort flag is not `permits_work` | yes (active, 0%) | `MEMORY_DAILY_MEMORY_SWEEP_*` | `JIT_DAILY_SWEEP_FLAG_KEY` (must not be read for admission). Job: `daily_memory_sweep_authority_from_environment` |
| `CONVERSATION_NOTES_V2_ENABLED` | Conversation notes v2 | env | closed (off) unless set | prod + dev (true since 2026-09-01). `_base` default is false | no | `CONVERSATION_NOTES_V2_ENABLED` | `_flag_enabled` / `summary_pipeline_mode` in `backend/utils/conversations/process_conversation.py` |
| `CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED` | Calendar context read | env | closed (off) | false prod, true dev (Beta Mac talks to dev) | no | `CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED` | `_calendar_context_read_enabled` in `process_conversation.py` |
| `CONVERSATION_OCR_CONTEXT_ENABLED` | OCR meeting context | env | closed (off) | false prod, true dev | no | `CONVERSATION_OCR_CONTEXT_ENABLED` | `_ocr_meeting_context_enabled` in `process_conversation.py` |
| `CONVERSATION_STORED_MEETING_CONTEXT_ENABLED` | Stored meeting lookup | env | **fail-open** (code default true) | everyone unless env-killed. Not declared in `runtime_env` | no | unset (kill via env) | `_stored_meeting_lookup_enabled` in `process_conversation.py` |
| `WAKE_WORD_ADJUDICATION_ENABLED` | Wake-word LLM adjudication | env | fail-open (unset ⇒ on) | on (`_base` `true`) | no | `WAKE_WORD_ADJUDICATION_ENABLED` | `wake_word_adjudication_enabled` in `backend/utils/task_intelligence/conversation_capture.py` |
| `OMI_LLM_GATEWAY_FEATURE_MODE` | LLM gateway feature mode | env | closed (direct) unless `gateway` | `gateway` in `_base` / prod / dev | no | `OMI_LLM_GATEWAY_FEATURE_MODE` | `should_route_features_through_gateway` in `backend/utils/llm/gateway_client.py` |
| `MEMORY_DAILY_MEMORY_SWEEP_*` | Daily memory sweep job | env | closed (off) | disabled in prod (`MEMORY_DAILY_MEMORY_SWEEP_ENABLED=false` and model/cohort off). Not admission | no | `MEMORY_DAILY_MEMORY_SWEEP_ENABLED` and siblings on `daily-memory-sweep-job` | `daily_memory_sweep_authority_from_environment` in `backend/utils/memory/daily_memory_sweep.py` |
| `DAY3_REENGAGEMENT_EMAIL_ENABLED` | Day-3 re-engagement email | env | closed (off) | false prod (and `_base`) | no | `DAY3_REENGAGEMENT_EMAIL_ENABLED` | `authority_from_environment` in `backend/utils/email/day3_reengagement.py` |
| `PUBLIC_SHARED_CONVERSATION_CHAT_MODE` | Public shared-conversation chat | env | closed (`off`) | off | no | `PUBLIC_SHARED_CONVERSATION_CHAT_MODE` | `_gateway_mode_enabled` in `backend/routers/public_shared_conversation_chat.py` |
| `ACCOUNT_CUTOVER_ENFORCEMENT` | Account cutover fence | env | closed (`off`) | off | no | `ACCOUNT_CUTOVER_ENFORCEMENT` | `cutover_enforcement_enabled` in `backend/utils/account_cutover/access.py` |
| `FAIR_USE_ENABLED` | Fair-use metering | env | closed (false) | unset in `runtime_env`; code default false | no | unset | `FAIR_USE_ENABLED` in `backend/utils/fair_use.py` |

## Not feature flags

Do not list these as rollout flags:

- Flutter `OmiFeatures` hardware capability bits.
- Integration-nudge UserDefaults opt-out (per-user preference, not a remote gate).
- Local-only process overrides (`OMI_FORCE_*`, `OMI_PERSISTENT_CAPTURE_STREAM`,
  `OMI_FORCE_CONTEXT_BUCKETS`, `OMI_FORCE_LOSSLESS_SCREEN_SYNC`, and the
  bucket-pipeline `OMI_FORCE_BUCKET_*` / `OMI_FORCE_DWELL_REFRESH` /
  `OMI_FORCE_DEPARTURE_EVALUATION` / `OMI_FORCE_FACT_WRITE_POLICY` knobs).
  They never ship as remote authority.

## Retired names

Do not re-read these for admission:

| Key | Why |
| --- | --- |
| `jit-processing-ledger-migration-v1` | Retired. Kept as `JIT_LEDGER_MIGRATION_FLAG_KEY` so tests can prove it no longer authorizes work. See `jit_rollout_authority.mdx`. |
| `daily-memory-sweep-v1` | Live PostHog row, but it is a decoy name on the sweep job, **not** `permits_work`. Listed in the table above so the dashboard is not mistaken for admission. |
