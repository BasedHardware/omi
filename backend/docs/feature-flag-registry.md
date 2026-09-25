<!-- feature-flag-registry as-of: 2026-09-24 -->

# Feature-flag authority registry

GENERATED from `config/feature-flags.yaml` by `scripts/render_feature_flag_registry.py`; do not edit.

Flipping a row here does not turn a feature on; PostHog / bundle identity /
`runtime_env` remain the live levers. This file is a catalog of *which* lever
owns each gate, not the switch itself.

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

Memory belief processing uses two deployment-wide runtime controls:

* `MEMORY_BELIEF_MODEL_ENABLED` is the positive dev-on/prod-off processing
  gate. It is declared for the listener, pusher, Cloud Run memory services,
  desktop-backend, and belief jobs.
* `MEMORY_BELIEF_AUTOMATION_PAUSED` is a reversible incident stop. It defaults
  to `false` in every environment and pauses automated evidence, synthesis, and
  backfill admission while leaving authenticated memory reads and TTL/expiry
  maintenance available. It is intentionally deployment-wide; it is not a
  PostHog user cohort or a per-UID product rollout.

The source of truth is the composed manifest (`backend/deploy/runtime_env.yaml`)
plus the GKE listener/pusher values. A flag value in this registry describes
repository capability, not a deployed or currently serving value.

## Rules

1. If Swift or Python names a PostHog key, the PostHog row must exist. A kill
   row is armed-but-off only when it is **active with a single 0% rollout
   group**; an inactive or absent row reads as unknown, and a missing kill
   row cannot disarm a bad Beta.
2. If a PostHog row exists and no code reads it for enablement, delete it
   and put the name in `retired:` so the checker fails on reintroduction.
3. Kill switches for Beta-by-default features must exist in PostHog as an
   active row with one 0% rollout group, so a bad Beta can be disarmed
   without a build.
4. Do not put fleet-wide backend switches in PostHog.
5. Do not put Beta-vs-stable enablement in PostHog person properties.
   `update_channel` was measured unreliable (person-side channel null or
   `stable` for most Beta installs). Bundle identity is the authority.

`BetaDogfoodRollout` is the shared client shape: non-production requires an
explicit `OMI_FORCE_*=1` (except where noted), Beta is on unless the kill is
true, stable is on only when the enable flag is true.

## Overdue for a decision

None as of 2026-09-24.

## Flags

`_base`, `dev`, and `prod` show declared literals from `runtime_env`
(`dev`/`prod` are `_base` inheritance plus the environment overlay). Chart
values appear as extra sources suffixed `(chart)` and never mask runtime
differences; differing values list their hosts. A declaration without a
literal (`config_map`, `env_var`, `secret`, `valueFrom`) counts as declared,
and an explicit empty literal renders as `''`.

### experiment

| key | summary | surfaces | kind | fail | _base | dev | prod | PostHog row | decision | review_by | owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DAY3_REENGAGEMENT_EMAIL_ENABLED` | Send randomized day-three re-engagement email | backend | env | closed | false | false | true | — | pending | 2026-10-15 | unowned |
| `OMI_LLM_GATEWAY_OUTPUT_BUDGET_EXPERIMENTS` | Select gateway output-budget experiments | llm-gateway | env | closed | — | public_shared_conversation_chat (llm-gateway (chart)) | public_shared_conversation_chat (llm-gateway (chart)) | — | pending | 2026-10-15 | unowned |
| `mobile-experiments-enabled` | Master gate for mobile experiment enrollment | mobile | posthog | closed | — | — | — | absent (enable) | pending | 2026-10-15 | unowned |
| `mobile-summary-feedback-layout-v1` | Compare summary feedback layouts | mobile | posthog | closed | — | — | — | absent (exposure) | pending | 2026-10-15 | unowned |

### rollout

| key | summary | surfaces | kind | fail | _base | dev | prod | PostHog row | decision | review_by | owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ACCOUNT_CUTOVER_COHORT` | Account cutover cohort | backend | hardcoded | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `ACCOUNT_CUTOVER_ENFORCEMENT` | Fence accounts onto the rewritten backend | backend | env | closed | off | off (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | off (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED` | Gate basic-plan eager extraction | backend | env | closed | declared | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `BASIC_PLAN_GATE_PROACTIVITY_ENABLED` | Gate basic-plan proactivity | backend | env | closed | declared | true | false | — | pending | 2026-10-15 | unowned |
| `BASIC_PLAN_GATE_PROXY_EMBED_ENABLED` | Gate basic-plan embedding proxy | backend | env | closed | declared | true | false | — | pending | 2026-10-15 | unowned |
| `CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED` | Read calendar context during conversation processing | backend | env | closed | declared | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `CONVERSATION_NOTES_V2_ENABLED` | Select notes-v2 summary versus legacy structure extraction | backend | env | closed | true | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `CONVERSATION_OCR_CONTEXT_ENABLED` | Read OCR meeting identity during conversation processing | backend | env | closed | declared | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `CONVERSATION_RELEVANCE_JEV_ENABLED` | Enable Jev conversation relevance decisions | backend | env | closed | — | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | — | pending | 2026-10-15 | unowned |
| `ContextBucketsFeature.isEnabled` | Beta-by-bundle context bucket pipeline, stable off | macos | bundle | open | — | — | — | — | pending | 2026-10-15 | unowned |
| `FAIR_USE_ENABLED` | Enforce fair-use metering on selected hosts | backend | env | closed | — | true (backend-listen (chart)) | true (backend-listen (chart)) | — | pending | 2026-10-15 | unowned |
| `FREE_TIER_LOCAL_PROCESSING` | Enable on-device processing for eligible free users | backend | env | closed | declared | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `FREE_TIER_LOCAL_PROCESSING_COHORT` | Admitted UIDs for free-tier local processing | backend | env | closed | declared | config_map (gke/backend-listen, gke/pusher); env_var (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend); valueFrom (backend-listen (chart), pusher (chart)) | '' (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `FREE_TIER_MEMORY_SUPPRESSION` | Suppress cloud memory extraction for eligible free users | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `FREE_TIER_MEMORY_SUPPRESSION_COHORT` | Admitted UIDs for free-tier memory suppression | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `GOOGLE_CALENDAR_AUTO_LINK_ENABLED` | Automatically link conversations to calendar events | backend | env | closed | — | true (backend-listen (chart), gke/backend-listen) | — | — | pending | 2026-10-15 | unowned |
| `KNOWLEDGE_LEDGER_DRAIN_ENABLED` | Drain knowledge-ledger writes | backend | env | closed | false | false | false | — | pending | 2026-10-15 | unowned |
| `MEETING_NOTES_RICH_CONTEXT_ENABLED` | Gather the rich meeting context pack for meeting notes | backend | env | closed | false | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `MEETING_NOTES_SCREEN_TEXT_CONTEXT_ENABLED` | Include screen text context in the rich meeting-notes pack | backend | env | closed | false | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `MEETING_RECEIPT_RECONCILER_ENABLED` | Reconcile meeting receipts | backend | env | closed | false | false (backend-listen (chart), cloud_run/backend, gke/backend-listen) | false (backend-listen (chart), cloud_run/backend, gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `MEMORY_BELIEF_MODEL_ENABLED` | Enable belief-model processing | backend | env | closed | declared | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, job/daily-memory-sweep-job, job/memory-maintenance-job, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, job/daily-memory-sweep-job, job/memory-maintenance-job, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `MEMORY_CANONICAL_CONSOLIDATION_ENABLED` | Enable canonical memory consolidation | backend | env | closed | true | true | true | — | pending | 2026-10-15 | unowned |
| `MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED` | Enable canonical graph backfill | backend | env | closed | false | false | false | — | pending | 2026-10-15 | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED` | Enable daily memory sweep cohort gate | backend | env | closed | declared | false | false | — | pending | 2026-10-15 | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG` | PostHog exposure name for sweep cohort, empty in overlays | backend | env | closed | declared | '' | '' | — | pending | 2026-10-15 | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_ENABLED` | Enable daily memory sweep job | backend | env | closed | declared | true | false | — | pending | 2026-10-15 | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED` | Allow model calls during daily memory sweep | backend | env | closed | declared | true | false | — | pending | 2026-10-15 | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENABLED` | Reconcile sweep timezone selection | backend | env | closed | declared | true | false | — | pending | 2026-10-15 | unowned |
| `MEMORY_OWNER_JEV_FLIP_ENABLED` | Switch memory owner decisions to Jev | backend | env | closed | — | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | — | pending | 2026-10-15 | unowned |
| `MENTOR_GATE_DEBOUNCE_ENABLED` | Debounce mentor gate evaluation | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `MENTOR_GATE_PROMPT_CACHE_ENABLED` | Cache mentor gate prompts | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `OMI_GEMINI_OVERFLOW_ENABLED` | Enable overflow routing to Gemini | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `OMI_LLM_GATEWAY_CONVERSATION_ACTION_ITEMS_SHADOW_ENABLED` | Shadow gateway action-items extraction | backend | env | closed | — | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | — | pending | 2026-10-15 | unowned |
| `OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED` | Shadow gateway conversation structuring | backend | env | closed | — | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | — | pending | 2026-10-15 | unowned |
| `OMI_LLM_GATEWAY_DEV_SHADOW_ALL_ENABLED` | Shadow all development gateway lanes | backend | env | closed | — | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | — | pending | 2026-10-15 | unowned |
| `OMI_LLM_GPT56_EXPLICIT_CACHE_ENABLED` | Enable explicit GPT-5.6 cache hints | backend | env | closed | true | true (backend-listen (chart), gke/backend-listen) | true (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `PARAKEET_STREAM_ALLOCATION_PERCENT` | Allocate streaming sessions to Parakeet | backend | env | closed | 100 | 100 (gke/parakeet, parakeet (chart)) | 100 (gke/parakeet, parakeet (chart)) | — | pending | 2026-10-15 | unowned |
| `PARAKEET_WINDOW_ALLOCATION_PERCENT` | Allocate live sessions to Parakeet window | backend | env | closed | 0 | 100 (backend-listen (chart), gke/backend-listen) | 0 (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `PARAKEET_WINDOW_DIARIZATION` | Enable Parakeet window diarization | backend | env | closed | false | false (backend-listen (chart), gke/backend-listen) | false (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `PUBLIC_SHARED_CONVERSATION_CHAT_MODE` | Enable chat on public shared conversations | backend | env | closed | off | off (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | off (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `RATE_LIMIT_SHADOW_MODE` | Shadow backend rate limits | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `SCREEN_FRAME_EGRESS_ENABLED` | Allow meeting-note screen frame egress | backend | env | closed | — | true | — | — | pending | 2026-10-15 | unowned |
| `SELFHEAL_MODE` | Conversation self-heal sweeper mode: off/detect-only/nudge/heal | backend | env | closed | — | — | — | — | pending | 2026-10-15 | backend runtime_env (PR #18855) |
| `STT_CONNECT_ORDER_FROM_CONFIG` | Use configured STT provider connection order | backend | env | closed | false | true (backend-listen (chart), gke/backend-listen) | false (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `SYNC_BACKFILL_ROUTING_ENABLED` | Route eligible sync work to backfill lane | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `TRANSCRIPT_CHUNK_INDEXING_ENABLED` | Index transcript chunks for retrieval | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `TRIAL_PAYWALL_ENABLED` | Enable desktop trial paywall | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `VAD_GATE_MODE` | Select off, shadow, or active server VAD gate | backend, mobile | env | closed | — | active (backend-listen (chart)) | active (backend-listen (chart)) | — | pending | 2026-10-15 | unowned |
| `X-Omi-Memory-Belief-Enabled` | Expose belief processing capability to memory clients | backend, macos | server_capability | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `X-Omi-Memory-Canonical-Lifecycle-Exposed` | Canonical memory lifecycle response header retained for older clients | backend, macos | server_capability | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `chat_first_ui` | Universal chat-first capability sent for older clients and sampled by macOS | backend, macos | server_capability | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `context_buckets_departure_eval_kill` | Beta departure-evaluation stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `context_buckets_destination_kill` | Beta destination-routing stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `context_buckets_dwell_refresh_kill` | Beta dwell-refresh stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `context_buckets_fact_write_policy_kill` | Beta fact-write policy stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `context_buckets_kill` | Beta context-buckets emergency stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `context_buckets_retrieval_kill` | Beta retrieval-hop stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `desktop-onboarding-rerun` | Payload-controlled onboarding rerun | macos | posthog | closed | — | — | — | expected (payload) | pending | 2026-10-15 | unowned |
| `desktop_interject` | Enable floating-card interject on stable | macos | posthog | closed | — | — | — | absent (enable) | pending | 2026-10-15 | unowned |
| `desktop_interject_kill` | Beta floating-card interject stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `desktop_persistent_capture_stream` | Enable persistent capture stream in shipped bundles | macos | posthog | closed | — | — | — | absent (enable) | pending | 2026-10-15 | unowned |
| `free-tier-cohort-v1` | Free-tier exposure cohort, never direct admission | backend | posthog | closed | — | — | — | absent (exposure) | pending | 2026-10-15 | unowned |
| `isProactiveCandidatesEnabled` | Dogfood-only prewritten proactive candidates | macos | hardcoded | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `isWorkstreamPoolingEnabled` | Dogfood-only context-bucket workstream pooling | macos | hardcoded | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `jit-processing-v1` | JIT processing admission cohort | backend | posthog | closed | — | — | — | expected (enable) | pending | 2026-10-15 | unowned |
| `negative_feedback_remediation` | Enable negative-feedback remediation on stable | macos | posthog | closed | — | — | — | absent (enable) | pending | 2026-10-15 | unowned |
| `negative_feedback_remediation_kill` | Beta negative-feedback remediation stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `on_device_meeting_identity` | Enable on-device meeting identity on stable | macos | posthog | closed | — | — | — | absent (enable) | pending | 2026-10-15 | unowned |
| `on_device_meeting_identity_kill` | Beta on-device meeting identity stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `screen_activity_lossless_sync` | Enable lossless screen sync on stable | macos | posthog | closed | — | — | — | absent (enable) | pending | 2026-10-15 | unowned |
| `screen_activity_lossless_sync_kill` | Beta lossless screen sync stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `system_calendar_meeting_context` | Enable system calendar meeting context on stable | macos | posthog | closed | — | — | — | absent (enable) | pending | 2026-10-15 | unowned |
| `system_calendar_meeting_context_kill` | Beta system calendar meeting context stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |

### ops_kill

| key | summary | surfaces | kind | fail | _base | dev | prod | PostHog row | decision | review_by | owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ACTION_ITEMS_LIST_STALE_CLIENT_REFUSE` | Refuse stale action-items list clients | backend | env | open | — | — | 1 | — | keep | — | unowned |
| `ADMIN_KEY_AUTH_ENABLED` | Allow administrator-key authentication | backend | env | open | — | — | — | — | keep | — | unowned |
| `CONVERSATION_STORED_MEETING_CONTEXT_ENABLED` | Incident stop for stored meeting context lookup | backend | env | open | — | — | — | — | keep | — | unowned |
| `DAY3_REENGAGEMENT_EMAIL_KILL_SWITCH` | Stop day-three re-engagement email | backend | env | inverted | false | false | false | — | keep | — | unowned |
| `DESKTOP_UPDATE_POINTERS_MODE` | Fall back to legacy desktop update pointers | backend | env | open | primary | primary (backend-listen (chart), cloud_run/backend, gke/backend-listen) | primary (backend-listen (chart), cloud_run/backend, gke/backend-listen) | — | keep | — | unowned |
| `FAIR_USE_KILL_SWITCH` | Emergency stop for fair-use enforcement | backend | env | inverted | — | false (backend-listen (chart)) | false (backend-listen (chart)) | — | keep | — | unowned |
| `FRAME_REQUEST_RETENTION_INDEPENDENT_HEALTHY` | Skip shared retention when independent job is healthy | backend | env | closed | false | false | false | — | keep | — | unowned |
| `FREE_TIER_EMERGENCY_STOP` | Stop all free-tier cohorts | backend | env | inverted | declared | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, pusher (chart)) | — | keep | — | unowned |
| `LISTEN_FINALIZATION_BYOK_ABANDONMENT_ENABLED` | Abandon finalization after BYOK failure | backend | env | open | true | true (backend-listen (chart), gke/backend-listen) | true (backend-listen (chart), gke/backend-listen) | — | keep | — | unowned |
| `LLM_GATEWAY_ACCOUNTING_ENABLED` | Record gateway-managed usage accounting | backend, llm-gateway | env | closed | true | true (backend-listen (chart), cloud_run/backend, desktop-backend, gke/backend-listen, gke/pusher, llm-gateway (chart), pusher (chart)) | true (backend-listen (chart), cloud_run/backend, desktop-backend, gke/backend-listen, gke/pusher, llm-gateway (chart), pusher (chart)) | — | keep | — | unowned |
| `LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS` | Expose provider error details from gateway | llm-gateway | env | closed | — | true (llm-gateway (chart)) | — | — | keep | — | unowned |
| `MEMORY_BELIEF_AUTOMATION_PAUSED` | Pause automated belief processing | backend | env | inverted | false | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, job/daily-memory-sweep-job, job/memory-maintenance-job, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, job/daily-memory-sweep-job, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `MEMORY_CANONICAL_MAINTENANCE_ENABLED` | Enable canonical memory maintenance job | backend | env | closed | false (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen); true (job/memory-maintenance-job) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen); true (job/memory-maintenance-job) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen); true (job/memory-maintenance-job) | — | keep | — | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_KILL_SWITCH` | Emergency stop for daily memory sweep | backend | env | inverted | false | false | false | — | keep | — | unowned |
| `MEMORY_ENABLED` | Global incident stop for canonical memory intake and reads | backend | env | closed | on | on (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, job/daily-memory-sweep-job, job/knowledge-ledger-drain-job, job/memory-maintenance-job, pusher (chart)) | on (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, job/daily-memory-sweep-job, job/knowledge-ledger-drain-job, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `MEMORY_IMPORT_WRITE_BLOCK_MODE` | Block memory import writes during incident | backend | env | inverted | — | — | — | — | keep | — | unowned |
| `OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION` | Permit direct-model gateway exception | backend | env | closed | false | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, job/memory-maintenance-job, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE` | Allow production gateway feature mode | backend | env | closed | — | — | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `OMI_LLM_GATEWAY_OBSERVABILITY_LOGS_ENABLED` | Enable gateway observability logs | backend | env | closed | — | — | — | — | keep | — | unowned |
| `SCREEN_ACTIVITY_KEYWORD_FALLBACK_ENABLED` | Fallback to keyword search for screen activity | backend | env | open | — | — | — | — | keep | — | unowned |
| `SYNC_BACKFILL_ENABLED` | Emergency stop for accepting sync backfill | backend | env | open | true | true | true | — | keep | — | unowned |
| `WAKE_WORD_ADJUDICATION_ENABLED` | Incident stop for wake-word adjudication | backend | env | open | true | true (backend-listen (chart), cloud_run/backend, gke/backend-listen) | true (backend-listen (chart), cloud_run/backend, gke/backend-listen) | — | keep | — | unowned |
| `desktop-rating-prompt-disabled` | Stop the rating prompt | macos | posthog | inverted | — | — | — | expected (kill) | keep | — | unowned |
| `free-tier-kill-switch-v1` | Remote free-tier stop | backend | posthog | inverted | — | — | — | expected (kill) | keep | — | unowned |
| `jit-processing-kill-switch-v1` | JIT remote kill for allowlisted accounts | backend | posthog | inverted | — | — | — | expected (kill) | keep | — | unowned |

### config_switch

| key | summary | surfaces | kind | fail | _base | dev | prod | PostHog row | decision | review_by | owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ACCOUNT_DELETION_DISPATCH_MODE` | Select Cloud Tasks for account deletion | backend | env | closed | — | — | cloud_tasks (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | keep | — | unowned |
| `AUDIO_MERGE_DISPATCH_MODE` | Select audio-merge dispatch lane | backend | env | closed | — | — | — | — | keep | — | unowned |
| `DEEPGRAM_SELF_HOSTED_ENABLED` | Select self-hosted Deepgram filler-word policy on pusher | backend | env | closed | — | false (backend-listen (chart)) | false (backend-listen (chart)); true (pusher (chart)) | — | keep | — | unowned |
| `FIRESTORE_CACHE_ENABLED` | Enable Firestore response cache | backend | env | closed | — | — | — | — | keep | — | unowned |
| `LISTEN_FINALIZATION_DISPATCH_MODE` | Select conversation finalization dispatch lane | backend | env | closed | — | — | cloud_tasks | — | keep | — | unowned |
| `MEMORY_CANONICAL_MAINTENANCE_FLEX` | Select gateway Flex lane for memory maintenance | backend | env | closed | true | true | true | — | keep | — | unowned |
| `MEMORY_IMPORT_BODY_STORAGE_MODE` | Select memory import body storage mode | backend | env | closed | — | — | — | — | keep | — | unowned |
| `MEMORY_TYPESENSE_READINESS_REQUIRED` | Require Typesense projection readiness for memory reads | backend | env | closed | — | — | — | — | keep | — | unowned |
| `OMI_BACKGROUND_FLEX_CAPABLE` | Allow background gateway Flex work | backend | env | closed | true | true | true | — | keep | — | unowned |
| `OMI_LLM_CHAT_AGENT_ROUTE` | Select managed chat-agent gateway route | backend | env | closed | gateway | gateway (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, job/memory-maintenance-job, pusher (chart)) | gateway (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `OMI_LLM_GATEWAY_FEATURE_MODE` | Select LLM gateway versus direct serving | backend | env | closed | gateway | gateway (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, job/memory-maintenance-job, pusher (chart)) | gateway (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `OMI_MODEL_TIER` | Select proxy budget tier | backend | env | closed | — | — | — | — | keep | — | unowned |
| `PARAKEET_ATTENTION_MODE` | Choose full versus local attention on Parakeet GPU | backend | env | closed | — | — | auto (parakeet (chart)) | — | keep | — | unowned |
| `PARAKEET_DIARIZATION` | Enable prerecorded Parakeet diarization | backend | env | closed | — | — | — | — | keep | — | unowned |
| `PARAKEET_INFERENCE_MODE` | Choose Parakeet transcription inference backend | backend | env | closed | — | nemo (parakeet (chart)) | nemo (parakeet (chart)) | — | keep | — | unowned |
| `PARAKEET_USE_V2` | Select Parakeet prerecorded v2 pipeline | backend | env | open | — | — | — | — | keep | — | unowned |
| `RECORDING_SESSION_MODE` | Select recording session migration mode | backend | env | closed | — | — | — | — | keep | — | unowned |
| `SYNC_DISPATCH_MODE` | Select sync dispatch lane | backend | env | closed | — | — | — | — | keep | — | unowned |
| `SYNC_LEDGER_FENCE_MODE` | Select sync ledger fence authority | backend | env | closed | env_var | env_var | env_var | — | keep | — | unowned |
| `TYPESENSE_CONVERSATION_INDEX_WRITES` | Write conversations to Typesense index | backend | env | closed | — | — | — | — | keep | — | unowned |
| `USE_VERTEX_AI` | Select Vertex AI model route | backend | env | closed | true | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen) | — | keep | — | unowned |
| `VITE_ENABLE_GMAIL_SESSION` | Keep shipped Gmail session integration enabled | windows | build_define | open | — | — | — | — | keep | — | unowned |
| `X-Omi-Memory-Default-Delete-Supported` | Indicate default-memory deletion support | backend, macos | server_capability | closed | — | — | — | — | keep | — | unowned |
| `X-Omi-Memory-Device-Scope-Supported` | Indicate device-scoped memory query support | backend, macos | server_capability | closed | — | — | — | — | keep | — | unowned |

## Undeclared env flags

Env flags with no declaration in `runtime_env` or any chart; they run on
their code default (`fail` tells you which way a missing value resolves).

- `ADMIN_KEY_AUTH_ENABLED` — Allow administrator-key authentication (fail: open)
- `AUDIO_MERGE_DISPATCH_MODE` — Select audio-merge dispatch lane (fail: closed)
- `CONVERSATION_STORED_MEETING_CONTEXT_ENABLED` — Incident stop for stored meeting context lookup (fail: open)
- `FIRESTORE_CACHE_ENABLED` — Enable Firestore response cache (fail: closed)
- `FREE_TIER_MEMORY_SUPPRESSION` — Suppress cloud memory extraction for eligible free users (fail: closed)
- `FREE_TIER_MEMORY_SUPPRESSION_COHORT` — Admitted UIDs for free-tier memory suppression (fail: closed)
- `MEMORY_IMPORT_BODY_STORAGE_MODE` — Select memory import body storage mode (fail: closed)
- `MEMORY_IMPORT_WRITE_BLOCK_MODE` — Block memory import writes during incident (fail: inverted)
- `MEMORY_TYPESENSE_READINESS_REQUIRED` — Require Typesense projection readiness for memory reads (fail: closed)
- `MENTOR_GATE_DEBOUNCE_ENABLED` — Debounce mentor gate evaluation (fail: closed)
- `MENTOR_GATE_PROMPT_CACHE_ENABLED` — Cache mentor gate prompts (fail: closed)
- `OMI_GEMINI_OVERFLOW_ENABLED` — Enable overflow routing to Gemini (fail: closed)
- `OMI_LLM_GATEWAY_OBSERVABILITY_LOGS_ENABLED` — Enable gateway observability logs (fail: closed)
- `OMI_MODEL_TIER` — Select proxy budget tier (fail: closed)
- `PARAKEET_DIARIZATION` — Enable prerecorded Parakeet diarization (fail: closed)
- `PARAKEET_USE_V2` — Select Parakeet prerecorded v2 pipeline (fail: open)
- `RATE_LIMIT_SHADOW_MODE` — Shadow backend rate limits (fail: closed)
- `RECORDING_SESSION_MODE` — Select recording session migration mode (fail: closed)
- `SCREEN_ACTIVITY_KEYWORD_FALLBACK_ENABLED` — Fallback to keyword search for screen activity (fail: open)
- `SELFHEAL_MODE` — Conversation self-heal sweeper mode: off/detect-only/nudge/heal (fail: closed)
- `SYNC_BACKFILL_ROUTING_ENABLED` — Route eligible sync work to backfill lane (fail: closed)
- `SYNC_DISPATCH_MODE` — Select sync dispatch lane (fail: closed)
- `TRANSCRIPT_CHUNK_INDEXING_ENABLED` — Index transcript chunks for retrieval (fail: closed)
- `TRIAL_PAYWALL_ENABLED` — Enable desktop trial paywall (fail: closed)
- `TYPESENSE_CONVERSATION_INDEX_WRITES` — Write conversations to Typesense index (fail: closed)

## Not feature flags

Do not list these as rollout flags:

- Flutter `OmiFeatures` hardware capability bits.
- Integration-nudge UserDefaults opt-out (per-user preference, not a remote gate).
- Local process overrides (`OMI_FORCE_*`, `OMI_PERSISTENT_CAPTURE_STREAM`,
  and the bucket-pipeline `OMI_FORCE_BUCKET_*` / `OMI_FORCE_DWELL_REFRESH` /
  `OMI_FORCE_DEPARTURE_EVALUATION` / `OMI_FORCE_FACT_WRITE_POLICY` knobs).
  Most are dev-only controls, but some (e.g. `OMI_FORCE_CLOUD_STT`,
  `OMI_FORCE_NOTCH`) are deliberately honored by shipped builds. Either way
  the `ignore:` row records the classification as a visible decision: local
  environment data, never remote rollout authority.

The registry `ignore:` block names every other intentional non-flag with its
reason:

| Key | Reason |
| --- | --- |
| `DD_TRACE_ENABLED` | Datadog telemetry instrumentation switch, not a product behavior flag |
| `DD_LOGS_ENABLED` | Datadog telemetry log routing switch, not a product behavior flag |
| `OMI_FORCE_CONTEXT_BUCKETS` | Local-only dev override, not shipped remote authority |
| `OMI_FORCE_BUCKET_RETRIEVAL` | Local-only dev override, not shipped remote authority |
| `OMI_FORCE_BUCKET_DESTINATIONS` | Local-only dev override, not shipped remote authority |
| `OMI_FORCE_BUCKET_WORKSTREAMS` | Local-only dev override, not shipped remote authority |
| `OMI_FORCE_BUCKET_CANDIDATES` | Local-only dev override, not shipped remote authority |
| `OMI_FORCE_LOSSLESS_SCREEN_SYNC` | Local-only dev override, not shipped remote authority |
| `OMI_FORCE_DWELL_REFRESH` | Local-only dev override, not shipped remote authority |
| `OMI_FORCE_DEPARTURE_EVALUATION` | Local-only dev override, not shipped remote authority |
| `OMI_FORCE_FACT_WRITE_POLICY` | Local-only dev override, not shipped remote authority |
| `OMI_FORCE_CANONICAL_MEMORY_ATLAS` | Local-only dev brain-map override retained while the legacy fallback remains |
| `OMI_FORCE_INTERJECT` | Local-only dev floating-card override, not remote rollout authority |
| `OMI_FORCE_NEGATIVE_FEEDBACK_REMEDIATION` | Local-only dev remediation override, not remote rollout authority |
| `OMI_FORCE_SYSTEM_CALENDAR_MEETING_CONTEXT` | Local-only dev calendar override, not remote rollout authority |
| `OMI_FORCE_ON_DEVICE_MEETING_IDENTITY` | Local-only dev meeting identity override, not remote rollout authority |
| `OMI_FORCE_NOTCH` | Local display override honored by shipped builds, not remote rollout authority |
| `OMI_FORCE_NO_NOTCH` | Local display override honored by shipped builds, not remote rollout authority |
| `OMI_FORCE_SYNTHESIS_FAIL` | Local QA fault-injection override honored by shipped builds, not remote rollout authority |
| `OMI_FORCE_CLOUD_STT` | Local override deliberately honored in shipped builds; not remote rollout authority |
| `OMI_LOCAL_EMBEDDINGS` | Local override deliberately honored in shipped builds; not remote rollout authority |
| `OMI_DISABLE_LOCAL_EMBEDDINGS` | Local incident override deliberately honored in shipped builds; not remote rollout authority |
| `OMI_DISABLE_LOCAL_INFERENCE` | Local incident override deliberately honored in shipped builds; not remote rollout authority |
| `freeTierLocalProcessing` | UserDefaults override deliberately honored in shipped builds; not remote rollout authority |
| `localEmbeddingsEnabled` | UserDefaults override deliberately honored in shipped builds; not remote rollout authority |
| `disableLocalInference` | UserDefaults override deliberately honored in shipped builds; not remote rollout authority |
| `forceCloudSTT` | UserDefaults override deliberately honored in shipped builds; not remote rollout authority |
| `vadGateEnabled` | Mobile shipped developer preference, pending product decision; not remote rollout authority |
| `autoCreateSpeakersEnabled` | Mobile shipped developer preference, pending product decision; not remote rollout authority |
| `OMI_FREE_TIER_LOCAL_PROCESSING` | Environment override deliberately honored in shipped builds; not remote rollout authority |
| `OMI_FORCE_LOCAL_INFERENCE_ENGINE` | Local inference engine override deliberately honored in shipped builds |
| `forceLocalInferenceEngine` | UserDefaults inference engine override deliberately honored in shipped builds |
| `OMI_FORCE_LOCAL_EMBEDDING_ENGINE` | Local embedding engine override deliberately honored in shipped builds |
| `forceLocalEmbeddingEngine` | UserDefaults embedding engine override deliberately honored in shipped builds |
| `disableLocalEmbeddings` | UserDefaults embedding incident override deliberately honored in shipped builds |
| `OMI_LOCAL_INFERENCE_URL` | Local engine endpoint override deliberately honored in shipped builds, not rollout authority |
| `localInferenceServerURL` | UserDefaults local engine endpoint override deliberately honored in shipped builds |
| `OMI_LOCAL_INFERENCE_MODEL` | Local model choice deliberately honored in shipped builds, not rollout authority |
| `localInferenceModel` | UserDefaults local model choice deliberately honored in shipped builds |
| `OMI_LOCAL_INFERENCE_CONTEXT_TOKENS` | Local numeric tuning deliberately honored in shipped builds, not rollout authority |
| `localInferenceContextTokens` | UserDefaults local numeric tuning deliberately honored in shipped builds |
| `OMI_LOCAL_INFERENCE_TIMEOUT_SECONDS` | Local timeout deliberately honored in shipped builds, not rollout authority |
| `localInferenceTimeoutSeconds` | UserDefaults local timeout deliberately honored in shipped builds |
| `OMI_FORCE_PARAKEET_FAIL` | Local QA failure override, not remote rollout authority |
| `forceParakeetFail` | Local QA failure override, not remote rollout authority |
| `OMI_YOLO_MODE` | Local agent override restricted to non-production builds; not remote rollout authority |
| `PROVIDER_MODE` | Local offline provider harness, not a product flag |

## Retired names — do not reuse

Code was deleted but an external row may still exist; the sync reports
live leftovers as read-only delete candidates. Never re-read these names
for admission.

| Key | Retired | Reason |
| --- | --- | --- |
| `context_buckets` | 2026-09-24 | Unused nominal enable row; bundle identity owns the active gate |
| `daily-memory-sweep-v1` | 2026-09-24 | Decoy name never authorizes JIT or sweep admission |
| `jit-processing-ledger-migration-v1` | 2026-09-24 | Old ledger migration name never authorizes JIT processing |
