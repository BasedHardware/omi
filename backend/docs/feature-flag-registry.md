<!-- feature-flag-registry as-of: 2026-10-06 -->

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

## Running experiments

Every running experiment links its preregistration doc. `decision: kill`
entries are exempt: they are queued for removal, not running.

| key | owner | prereg | review_by |
| --- | --- | --- | --- |
| `CAPTURE_JEV_SHADOW_ENABLED` | David | [backend/docs/experiments/EXP-003-jev-capture-shadow.md](../../backend/docs/experiments/EXP-003-jev-capture-shadow.md) | 2026-10-18 |
| `CAPTURE_JEV_SHADOW_EXPIRY` | David | [backend/docs/experiments/EXP-003-jev-capture-shadow.md](../../backend/docs/experiments/EXP-003-jev-capture-shadow.md) | 2026-10-18 |
| `CAPTURE_JEV_SHADOW_GLOBAL_DAILY_CAP` | David | [backend/docs/experiments/EXP-003-jev-capture-shadow.md](../../backend/docs/experiments/EXP-003-jev-capture-shadow.md) | 2026-10-18 |
| `CAPTURE_JEV_SHADOW_PERCENT` | David | [backend/docs/experiments/EXP-003-jev-capture-shadow.md](../../backend/docs/experiments/EXP-003-jev-capture-shadow.md) | 2026-10-18 |
| `CAPTURE_JEV_SHADOW_UID_ALLOWLIST` | David | [backend/docs/experiments/EXP-003-jev-capture-shadow.md](../../backend/docs/experiments/EXP-003-jev-capture-shadow.md) | 2026-10-18 |
| `CAPTURE_JEV_SHADOW_USER_DAILY_CAP` | David | [backend/docs/experiments/EXP-003-jev-capture-shadow.md](../../backend/docs/experiments/EXP-003-jev-capture-shadow.md) | 2026-10-18 |
| `CONVERSATION_RELEVANCE_JEV_PERCENT` | dazheng | [backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md](../../backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md) | 2026-10-21 |
| `CONVERSATION_RELEVANCE_JEV_SHADOW_DAILY_CAP` | dazheng | [backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md](../../backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md) | 2026-10-21 |
| `CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT` | dazheng | [backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md](../../backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md) | 2026-10-21 |
| `CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST` | dazheng | [backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md](../../backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md) | 2026-10-21 |
| `CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT` | dazheng | [backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md](../../backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md) | 2026-10-21 |
| `DAY3_REENGAGEMENT_EMAIL_ENABLED` | dazheng | [backend/docs/experiments/EXP-001-day3-reengagement.md](../../backend/docs/experiments/EXP-001-day3-reengagement.md) | 2026-10-28 |
| `MEETING_NOTES_EPISODE_CLAIMS_ENABLED` | dazheng | [backend/utils/conversations/EPISODE_EVIDENCE.md](../../backend/utils/conversations/EPISODE_EVIDENCE.md) | 2026-11-05 |
| `MEETING_NOTES_EPISODE_EFFORT` | dazheng | [backend/utils/conversations/EPISODE_EVIDENCE.md](../../backend/utils/conversations/EPISODE_EVIDENCE.md) | 2026-11-05 |
| `MEETING_NOTES_EPISODE_SELECTION` | dazheng | [backend/utils/conversations/EPISODE_EVIDENCE.md](../../backend/utils/conversations/EPISODE_EVIDENCE.md) | 2026-11-05 |
| `MEETING_NOTES_EPISODE_SELECTION_EFFORT` | dazheng | [backend/utils/conversations/EPISODE_EVIDENCE.md](../../backend/utils/conversations/EPISODE_EVIDENCE.md) | 2026-11-05 |
| `MEETING_NOTES_EPISODE_SELECTION_TIMEOUT_SECONDS` | dazheng | [backend/utils/conversations/EPISODE_EVIDENCE.md](../../backend/utils/conversations/EPISODE_EVIDENCE.md) | 2026-11-05 |
| `MEETING_NOTES_EPISODE_THINKING_MAX_INPUT_BYTES` | dazheng | [backend/utils/conversations/EPISODE_EVIDENCE.md](../../backend/utils/conversations/EPISODE_EVIDENCE.md) | 2026-11-05 |
| `MEMORY_OWNER_JEV_FLIP_PERCENT` | dazheng | [backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md](../../backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md) | 2026-10-21 |
| `MEMORY_OWNER_JEV_SHADOW_DAILY_CAP` | dazheng | [backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md](../../backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md) | 2026-10-21 |
| `MEMORY_OWNER_JEV_SHADOW_PERCENT` | dazheng | [backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md](../../backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md) | 2026-10-21 |
| `exp-002-desktop-identity-v1` | unowned | [backend/docs/experiments/EXP-002-desktop-identity-memory-v1.md](../../backend/docs/experiments/EXP-002-desktop-identity-memory-v1.md) | 2026-10-26 |

## Overdue for a decision

None as of 2026-10-06.

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
| `CAPTURE_JEV_SHADOW_ENABLED` | Log Jev same-scene and re-summary advice without changing capture behavior | backend | env | closed | — | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-18 | David |
| `CAPTURE_JEV_SHADOW_EXPIRY` | Shorten the Jev capture shadow hard deadline | backend | env | closed | — | — | — | — | pending | 2026-10-18 | David |
| `CAPTURE_JEV_SHADOW_GLOBAL_DAILY_CAP` | Global daily Jev capture shadow call budget | backend | env | closed | — | — | — | — | pending | 2026-10-18 | David |
| `CAPTURE_JEV_SHADOW_PERCENT` | Optional Jev capture shadow percentage cohort, default zero | backend | env | closed | — | 0 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | 0 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-18 | David |
| `CAPTURE_JEV_SHADOW_UID_ALLOWLIST` | Explicit UIDs for Jev capture shadow | backend | env | closed | — | vi7SA9ckQCe4ccobWNxlbdcNdC23 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | vi7SA9ckQCe4ccobWNxlbdcNdC23 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-18 | David |
| `CAPTURE_JEV_SHADOW_USER_DAILY_CAP` | Per-user daily Jev capture shadow call budget | backend | env | closed | — | — | — | — | pending | 2026-10-18 | David |
| `CONVERSATION_RELEVANCE_JEV_PERCENT` | Jev conversation percentage after keep-all; production stage 4 is 100% (2026-10-06); ramp 1 -> 10 -> 50 -> 100; unset is 100 when enabled | backend | env | closed | — | 0 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | 100 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-21 | dazheng |
| `CONVERSATION_RELEVANCE_JEV_SHADOW_DAILY_CAP` | Global UTC daily admission cap for discard shadow, default 60000 | backend | env | closed | — | 60000 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | 60000 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-21 | dazheng |
| `CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT` | Conversation-hash percentage for advisory discard measurement | backend | env | closed | — | 0 (cloud_run/backend-sync, cloud_run/backend-sync-backfill); 100 (backend-listen (chart), cloud_run/backend, gke/backend-listen, gke/pusher, pusher (chart)) | 100 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-21 | dazheng |
| `CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST` | Dev-only Jev dogfooding UIDs (OMI_ENV_STAGE=dev); never read or declared in prod; keep-all and enable flag take precedence | backend | env | closed | — | '' (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | — | pending | 2026-10-21 | dazheng |
| `CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT` | Conversation percentage kept at the ambiguous model tier without a decision call | backend | env | closed | — | 0 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | 0 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-21 | dazheng |
| `DAY3_REENGAGEMENT_EMAIL_ENABLED` | Send randomized day-three re-engagement email | backend | env | closed | false | false | true | — | pending | 2026-10-28 | dazheng |
| `MEETING_NOTES_EPISODE_CLAIMS_ENABLED` | Generate optional episode claim bindings, default off; visible provenance rules remain | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_EFFORT` | Episode writer thinking effort: default, high or xhigh; baseline unchanged | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_SELECTION` | Episode evidence selector: deterministic, jev or luna; compact remains an offline experiment | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_SELECTION_EFFORT` | Optional selector effort, default low; writer effort is independent | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_SELECTION_TIMEOUT_SECONDS` | Optional selection pass timeout, default 30 seconds, bounded 1-30; fallback keeps writing | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_THINKING_MAX_INPUT_BYTES` | Optional high/xhigh byte ceiling, default disabled (0); long transcript guard stays active | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEMORY_OWNER_JEV_FLIP_PERCENT` | Universal owner flip control: 0 off, 100 on; unset follows live flag; other values off | backend | env | closed | — | 0 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | — | pending | 2026-10-21 | dazheng |
| `MEMORY_OWNER_JEV_SHADOW_DAILY_CAP` | Global UTC daily admission cap for owner shadow, default 60000 | backend | env | closed | — | 60000 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | 60000 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-21 | dazheng |
| `MEMORY_OWNER_JEV_SHADOW_PERCENT` | Candidate-hash percentage for advisory owner measurement | backend | env | closed | — | 0 (cloud_run/backend-sync, cloud_run/backend-sync-backfill); 100 (backend-listen (chart), cloud_run/backend, gke/backend-listen, gke/pusher, pusher (chart)) | 100 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-21 | dazheng |
| `OMI_LLM_GATEWAY_OUTPUT_BUDGET_EXPERIMENTS` | Select gateway output-budget experiments | llm-gateway | env | closed | — | — | — | — | kill | 2026-10-15 | dazheng |
| `exp-002-desktop-identity-v1` | EXP-002 memory_v1 desktop identity arm enrollment | backend, macos | posthog | closed | — | — | — | expected (enable) | pending | 2026-10-26 | unowned |

### rollout

| key | summary | surfaces | kind | fail | _base | dev | prod | PostHog row | decision | review_by | owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ACCOUNT_CUTOVER_COHORT` | Account cutover cohort | backend | hardcoded | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `ACCOUNT_CUTOVER_ENFORCEMENT` | Fence accounts onto the rewritten backend | backend | env | closed | off | off (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | off (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENABLED` | Measure, in the action_item_identity log line only, how many reprocess-unmatched prior tasks pair one-to-one with a new task by stored transcript segment ids; never changes what is written or delivered (default on) | backend | env | open | — | — | — | — | pending | 2026-10-31 | dazheng |
| `ACTION_ITEM_IDENTITY_PRESERVE_ENABLED` | Keep a task's id and export marker when a conversation reprocess re-extracts the same task, so it is not sent to the user's cloud task app again; Apple Reminders excluded (default on) | backend | env | open | — | — | — | — | graduate | 2026-10-31 | dazheng |
| `ACTION_ITEM_REFRESH_PRESERVE_ENABLED` | Preserve existing tasks and transfer smart-merge donor tasks on SMART_MERGE and SYNC_UPDATE; append exact-unmatched tasks (default on) | backend | env | closed | {value: 'true', category: rollout} | true (backend-listen (chart), pusher (chart)); {value: 'true', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | true (backend-listen (chart), pusher (chart)); {value: 'true', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | — | graduate | 2026-11-01 | dazheng |
| `AUDIO_TIMELINE_SPANS` | Persist projected span-bearing live audio through the existing pusher capability without enabling v2 transcript translation; default off | backend | env | closed | {value: 'false', category: rollout} | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | true (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill); {value: 'true', category: rollout} (gke/backend-listen, gke/pusher) | — | pending | 2026-11-02 | dazheng |
| `BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED` | Gate basic-plan eager extraction | backend | env | closed | declared | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | graduate | 2026-10-23 | dazheng |
| `BASIC_PLAN_GATE_PROXY_EMBED_ENABLED` | Gate basic-plan embedding proxy | backend | env | closed | declared | true | false | — | graduate | 2026-10-23 | dazheng |
| `CAPTURE_EVIDENCE_V1_DARK_WRITE` | Piggyback bounded capture evidence metadata on existing writes | backend, mobile, macos | env | closed | {value: 'false', category: rollout} | true (backend-listen (chart), pusher (chart)); {value: 'true', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | true (backend-listen (chart), pusher (chart)); {value: 'true', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | — | pending | 2026-10-27 | dazheng |
| `CAPTURE_GROUP_CONTAINMENT_MODE` | Time-aligned user utterance containment for complementary cross-source capture groups; off\|shadow\|on, default shadow, unknown off | backend | env | closed | {value: 'shadow', category: rollout} | shadow (backend-listen (chart), pusher (chart)); {value: 'shadow', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | shadow (backend-listen (chart), pusher (chart)); {value: 'shadow', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | — | pending | 2026-11-03 | dazheng |
| `CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED` | Read calendar context during conversation processing | backend | env | closed | declared | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | graduate | 2026-10-23 | dazheng |
| `CONVERSATION_NOTES_V2_ENABLED` | Select notes-v2 summary versus legacy structure extraction | backend | env | closed | true | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `CONVERSATION_OCR_CONTEXT_ENABLED` | Read OCR meeting identity during conversation processing | backend | env | closed | declared | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | graduate | 2026-10-23 | dazheng |
| `CONVERSATION_RELEVANCE_JEV_ENABLED` | Enable Jev conversation relevance decisions | backend | env | closed | — | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-23 | unowned |
| `CONVERSATION_SMART_MERGE_MODE` | Fold a finished pendant conversation into its predecessor when Jev says same occasion (default merge; off\|shadow\|merge) | backend | env | open | — | — | — | — | graduate | 2026-10-29 | dazheng |
| `CONVERSATION_SMART_MERGE_UID_ALLOWLIST` | Limit smart merge to listed UIDs; empty admits every user | backend | env | closed | — | — | — | — | pending | 2026-10-29 | dazheng |
| `CONVERSATION_SMART_MERGE_WALLCLOCK_GAP_MODE` | Opt-in smart-merge gap policy for proven same-recording live pairs: off keeps the legacy speech-gap gate (code default), shadow logs/meters the corrected wall-clock verdict without acting on it, on rescues legacy-skipped pairs by created_at/finished_at wall clock (unset/blank/unknown = off) | backend | env | open | {value: 'off', category: rollout} | shadow (backend-listen (chart), pusher (chart)); {value: 'shadow', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | shadow (backend-listen (chart), pusher (chart)); {value: 'shadow', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | — | keep | 2026-11-05 | dazheng |
| `FAIR_USE_ENABLED` | Enforce fair-use metering on selected hosts | backend | env | closed | — | true (backend-listen (chart)) | true (backend-listen (chart)) | — | pending | 2026-10-23 | unowned |
| `FREE_TIER_LOCAL_PROCESSING` | Enable on-device processing for eligible free users | backend | env | closed | declared | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, pusher (chart)) | — | graduate | 2026-10-23 | dazheng |
| `FREE_TIER_LOCAL_PROCESSING_COHORT` | Admitted UIDs for free-tier local processing | backend | env | closed | declared | config_map (gke/backend-listen, gke/pusher); env_var (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend); valueFrom (backend-listen (chart), pusher (chart)) | '' (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, pusher (chart)) | — | graduate | 2026-10-23 | dazheng |
| `FREE_TIER_MEMORY_SUPPRESSION` | Suppress cloud memory extraction for eligible free users | backend | env | closed | — | — | — | — | pending | 2026-10-23 | unowned |
| `FREE_TIER_MEMORY_SUPPRESSION_COHORT` | Admitted UIDs for free-tier memory suppression | backend | env | closed | — | — | — | — | pending | 2026-10-23 | unowned |
| `KNOWLEDGE_LEDGER_DRAIN_ENABLED` | Drain knowledge-ledger writes | backend | env | closed | false | false | false | — | pending | 2026-10-23 | unowned |
| `LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED` | Persist committed live source-frame coverage with capture lifetime anchors (default on) | backend | env | closed | {value: 'true', category: rollout} | true (backend-listen (chart), pusher (chart)); {value: 'true', category: rollout} (gke/backend-listen, gke/pusher) | true (backend-listen (chart), pusher (chart)); {value: 'true', category: rollout} (gke/backend-listen, gke/pusher) | — | pending | 2026-11-02 | dazheng |
| `LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION` | Preserve original live provider segments when a merge or partial repair would discard known capture windows; default off | backend | env | closed | {value: 'false', category: rollout} | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | — | pending | 2026-11-03 | dazheng |
| `LIVE_CAPTURE_WINDOW_MERGE_UNION` | Union known live windows across positive gaps only with same-epoch accepted-send proof; default off | backend | env | closed | {value: 'false', category: rollout} | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | true (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill); {value: 'true', category: rollout} (gke/backend-listen, gke/pusher) | — | pending | 2026-11-04 | dazheng |
| `LIVE_CAPTURE_WINDOW_RETENTION` | Retain up to 512 observed capture anchors and 16384 accepted-send spans for delayed live finals; default off | backend | env | closed | {value: 'false', category: rollout} | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | — | pending | 2026-11-03 | dazheng |
| `LIVE_CAPTURE_WINDOW_STRICT_PROJECTION` | Project legacy capture windows as half-open intervals and refuse observed wall hiatuses; default off | backend | env | closed | {value: 'false', category: rollout} | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | — | pending | 2026-11-03 | dazheng |
| `LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS` | Register observed raw replay and managed pre-finalize sends; default off | backend | env | closed | {value: 'false', category: rollout} | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | true (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill); {value: 'true', category: rollout} (gke/backend-listen, gke/pusher) | — | pending | 2026-11-04 | dazheng |
| `LIVE_SPEAKER_SPAN_RESOLUTION` | Resolve live and mixed conversation voices only from validated capture spans or trusted sync/v2 placement; default off | backend | env | closed | {value: 'false', category: rollout} | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | true (backend-listen (chart), pusher (chart)); {value: 'true', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | — | pending | 2026-11-02 | dazheng |
| `MEETING_NOTES_EPISODE_C6_TIMEOUT_SECONDS` | Requested C6 writer budget, default 180s; existing gateway limit clamps to 115s; C7 fallback | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_EVIDENCE_ENABLED` | Episode notes master kill switch; production stage 1 enabled at 1% (2026-10-06); boolean false is the kill switch | backend | env | closed | — | — | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-25 | dazheng |
| `MEETING_NOTES_EPISODE_EVIDENCE_PERCENT` | Sticky UID episode-notes ramp; production stage 1 is 1% (2026-10-06); ramp 1 -> 10 -> 50 -> 100 with 24h soaks and >=200 kept notes per step | backend | env | closed | — | — | 1 (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_JEV_THRESHOLD` | Calibrated Jev evidence connection cutoff; deterministic remains default selector | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_TIERED_ENABLED` | Universal evidence-volume cost routing: high-value C6, otherwise C7; default enabled inside episode cohort | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_TIER_MIN_SOURCE_KINDS` | C6 admitted source-kind threshold, default 2 | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_TIER_MIN_WORDS` | C6 admitted speech word threshold, default 1500 | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_EPISODE_WRITER_TIMEOUT_SECONDS` | Episode C7 writer budget, default 120s in durable jobs; synchronous requests retain 60s | backend | env | closed | — | — | — | — | pending | 2026-11-05 | dazheng |
| `MEETING_NOTES_RICH_CONTEXT_ENABLED` | Gather the rich meeting context pack for meeting notes | backend | env | closed | false | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | graduate | 2026-10-15 | dazheng |
| `MEETING_NOTES_SCREEN_FRAMES_CONTEXT_ENABLED` | Attach up to four approved meeting screenshots as images on the rich notes call | backend | env | closed | false | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | graduate | 2026-10-21 | dazheng |
| `MEETING_NOTES_SCREEN_TEXT_CONTEXT_ENABLED` | Include screen text context in the rich meeting-notes pack | backend | env | closed | false | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | graduate | 2026-10-15 | dazheng |
| `MEETING_RECEIPT_RECONCILER_ENABLED` | Reconcile meeting receipts | backend | env | closed | false | false (backend-listen (chart), cloud_run/backend, gke/backend-listen) | false (backend-listen (chart), cloud_run/backend, gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `MEMORY_BELIEF_MODEL_ENABLED` | Enable belief-model processing | backend | env | closed | declared | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, job/daily-memory-sweep-job, job/memory-maintenance-job, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, job/daily-memory-sweep-job, job/memory-maintenance-job, pusher (chart)) | — | graduate | 2026-10-23 | dazheng |
| `MEMORY_CANONICAL_CONSOLIDATION_ENABLED` | Enable canonical memory consolidation | backend | env | closed | true | true | true | — | pending | 2026-10-15 | unowned |
| `MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED` | Enable canonical graph backfill | backend | env | closed | false | false | false | — | pending | 2026-10-15 | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED` | Enable daily memory sweep cohort gate | backend | env | closed | declared | false | false | — | pending | 2026-10-23 | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG` | PostHog exposure name for sweep cohort, empty in overlays | backend | env | closed | declared | '' | '' | — | pending | 2026-10-23 | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_ENABLED` | Enable daily memory sweep job | backend | env | closed | declared | true | false | — | pending | 2026-10-23 | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED` | Allow model calls during daily memory sweep | backend | env | closed | declared | true | false | — | pending | 2026-10-23 | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENABLED` | Reconcile sweep timezone selection | backend | env | closed | declared | true | false | — | pending | 2026-10-23 | unowned |
| `MEMORY_OWNER_JEV_FLIP_ENABLED` | Switch memory owner decisions to Jev | backend | env | closed | — | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | — | — | pending | 2026-10-23 | unowned |
| `MENTOR_GATE_DEBOUNCE_ENABLED` | Debounce mentor gate evaluation | backend | env | closed | — | true (backend-listen (chart), cloud_run/backend, gke/backend-listen, gke/pusher, pusher (chart)) | true (backend-listen (chart), cloud_run/backend, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-10-15 | unowned |
| `MENTOR_GATE_PROMPT_CACHE_ENABLED` | Cache mentor gate prompts | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `OMI_GEMINI_OVERFLOW_ENABLED` | Enable overflow routing to Gemini | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `OMI_LLM_GATEWAY_CONVERSATION_ACTION_ITEMS_SHADOW_ENABLED` | Shadow gateway action-items extraction | backend | env | closed | — | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | — | pending | 2026-10-15 | unowned |
| `OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED` | Shadow gateway conversation structuring | backend | env | closed | — | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | — | pending | 2026-10-15 | unowned |
| `OMI_LLM_GATEWAY_DEV_SHADOW_ALL_ENABLED` | Shadow all development gateway lanes | backend | env | closed | — | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | — | pending | 2026-10-15 | unowned |
| `OMI_LLM_GPT56_EXPLICIT_CACHE_ENABLED` | Enable explicit GPT-5.6 cache hints | backend | env | closed | true | true (backend-listen (chart), gke/backend-listen) | true (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `OMI_SHAPED_AGENT_MODE` | Notes and mobile/app chat shaped invocation: unset/off/unknown keeps old serving; cohort serves the named account and shadows a stable five percent of other UIDs; on serves shaped only. Default off. | backend | env | closed | — | — | cohort (backend-listen (chart), cloud_run/backend, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-11-05 | dazheng |
| `PARAKEET_STREAM_ALLOCATION_PERCENT` | Allocate streaming sessions to Parakeet | backend | env | closed | 100 | 100 (gke/parakeet, parakeet (chart)) | 100 (gke/parakeet, parakeet (chart)) | — | pending | 2026-10-23 | unowned |
| `PARAKEET_WINDOW_ALLOCATION_PERCENT` | Allocate live sessions to Parakeet window | backend | env | closed | 0 | 1 (backend-listen (chart), gke/backend-listen) | 100 (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-23 | dazheng |
| `PARAKEET_WINDOW_DIARIZATION` | Enable Parakeet window diarization | backend | env | closed | false | false (backend-listen (chart), gke/backend-listen) | false (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-23 | unowned |
| `PINNED_SPEAKER_PRIOR_ENABLED` | Turn near-misses on pinned people into suggestions and record voice candidates for the suggestion card (never loosens auto-labels) | backend | env | closed | — | — | — | — | pending | 2026-10-30 | dazheng |
| `PUBLIC_SHARED_CONVERSATION_CHAT_MODE` | Enable chat on public shared conversations | backend | env | closed | off | gateway (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | gateway (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill); off (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-15 | dazheng |
| `RATE_LIMIT_SHADOW_MODE` | Shadow backend rate limits | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `SCREEN_FRAME_EGRESS_ENABLED` | Allow meeting-note screen frame egress | backend | env | closed | — | true | true | — | graduate | 2026-10-23 | dazheng |
| `SELFHEAL_MODE` | Conversation self-heal sweeper mode: off/detect-only/nudge/heal | backend | env | closed | — | — | — | — | pending | 2026-10-15 | backend runtime_env (PR #18855) |
| `SONIOX_CAPTURE_AXIS_DIAGNOSTICS` | Measure raw Soniox token clocks against wire PCM and the managed send ledger; default off, no placement changes | backend | env | closed | {value: 'false', category: rollout} | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | true (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill); {value: 'true', category: rollout} (gke/backend-listen, gke/pusher) | — | pending | 2026-11-04 | dazheng |
| `SONIOX_CONTEXT_TERMS` | Send session vocabulary (Omi first) as Soniox context terms after dev config-frame validation | backend | env | closed | false | false (backend-listen (chart), gke/backend-listen) | false (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-29 | dazheng |
| `SONIOX_ELAPSED_AXIS` | Measure Soniox elapsed timestamps before enabling speaker windows | backend | env | closed | — | — | — | — | pending | 2026-10-27 | dazheng |
| `SONIOX_IDLE_CLOSE_SECONDS` | Close paid Soniox transports after continuous active-VAD silence; unset or zero off; prod listen 45 | backend | env | closed | — | — | 45 (backend-listen (chart), gke/backend-listen) | — | pending | 2026-11-04 | backend |
| `SONIOX_MONTHLY_CEILING_USD` | Enable Soniox monthly spend runway against a configured USD ceiling | backend | env | closed | 0 | 0 (backend-listen (chart), gke/backend-listen) | 10000 (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-28 | dazheng |
| `SONIOX_ORDERED_FINALIZE` | Reserve strict next-120ms finalize padding on ordered 16kHz Soniox writes; verify FIFO acknowledgments before capture admission; mismatch refuses the suffix until a clean checkpoint; default off | backend | env | closed | — | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | — | pending | 2026-11-05 | dazheng |
| `SONIOX_WIRE_LEDGER` | Account every emitted managed Soniox sample on the compact axis; unknown capture origins reserve unplaceable intervals; reserve reported finalize padding as provider-only holes and refuse raced intervals; preserve every control frame; default off | backend | env | closed | {value: 'false', category: rollout} | false (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | true (backend-listen (chart), pusher (chart)); {value: 'false', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill); {value: 'true', category: rollout} (gke/backend-listen, gke/pusher) | — | pending | 2026-11-04 | dazheng |
| `SPEAKER_MATCH_SCORES_ENABLED` | Persist bounded internal voice-match evidence on existing conversation writes; dev/local/offline default on; production hosts explicitly on | backend | env | closed | — | — | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, pusher (chart)) | — | pending | 2026-11-04 | dazheng |
| `STT_CONNECT_ORDER_FROM_CONFIG` | Use configured STT provider connection order | backend | env | closed | false | true (backend-listen (chart), gke/backend-listen) | true (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-15 | unowned |
| `STT_FAILOVER_RECOVERY_ENABLED` | Enable live-STT failover recovery on prod listen | backend | env | closed | false | false (backend-listen (chart), gke/backend-listen) | true (backend-listen (chart), gke/backend-listen) | — | pending | 2026-11-03 | backend |
| `STT_LEARNED_LANGUAGE_PROFILE` | Use a bounded per-user spoken-language history for live STT routing and Soniox hints | backend | env | closed | false | true (backend-listen (chart), gke/backend-listen) | true (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-28 | backend |
| `STT_MULTI_LANGUAGE_HINTS` | Send primary and English hints to Soniox in non-English multilingual live sessions | backend | env | closed | true | true (backend-listen (chart), gke/backend-listen) | true (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-27 | backend |
| `STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT` | Prefer Soniox for allocated non-English multilingual live sessions | backend | env | closed | 0 | 100 (backend-listen (chart), gke/backend-listen) | 100 (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-27 | backend |
| `STT_NO_TEXT_RESCUE_ENABLED` | Default-off bounded paid rescue and cheap failback for silent window episodes; requires recovery enabled | backend | env | closed | — | — | true (backend-listen (chart), gke/backend-listen) | — | pending | 2026-11-04 | backend |
| `STT_PAID_SPILLOVER_BUDGET_ENABLED` | Default-off fleet budget for paid router promotions after Parakeet capacity refusal; denial restores static order | backend | env | closed | — | — | — | — | pending | 2026-11-04 | backend |
| `STT_RESILIENT_RECONNECT` | Replay bounded live audio on eligible Soniox reconnects | backend | env | closed | false | false (backend-listen (chart), gke/backend-listen) | false (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-28 | backend |
| `STT_ROUTING_MODE` | Off shadow or cost-ordered health-gated live STT routing | backend | env | closed | off | shadow (backend-listen (chart), gke/backend-listen) | on (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-28 | dazheng |
| `STT_ROUTING_ON_PERCENT` | Sticky UID percentage admitted to the cost router; zero keeps static routing | backend | env | closed | 0 | 0 (backend-listen (chart), gke/backend-listen) | 100 (backend-listen (chart), gke/backend-listen) | — | pending | 2026-10-31 | dazheng |
| `SYNC_ASSIGNMENT_RECOVERY_ENABLED` | Recover incompatible explicit sync targets through compatible temporal assignment; default on, invalid values off | backend | env | open | {value: 'true', category: rollout} | true (backend-listen (chart)); {value: 'true', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | true (backend-listen (chart)); {value: 'true', category: rollout} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | pending | 2026-11-01 | dazheng |
| `SYNC_BACKFILL_INFLIGHT_LIMIT` | One in-flight backfill upload per uid; excess uploads get 429 backfill_paced | backend | env | closed | false | false | false | — | pending | 2026-10-27 | dazheng |
| `SYNC_BACKFILL_ROUTING_ENABLED` | Route eligible sync work to backfill lane | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `SYNC_BACKFILL_UID_SEQUENCER` | Accept backfill uploads then dispatch one worker job per uid from durable queue | backend | env | closed | on | on | on | — | pending | 2026-10-27 | dazheng |
| `SYNC_LINEAGE_LIVE_DEDUPE_ENABLED` | Proof-gated sync live intake: conservative repeat suppression, strict-stamp overlap deferral and bounded diagnostics (default on) | backend | env | open | true | true | true | — | pending | 2026-11-02 | dazheng |
| `SYNC_LINEAGE_RESOLVE_ENABLED` | Bind each segment of a recording-id safety-WAL upload to the live rollover generation that owns its audio, and stamp live generations with their origin recording id (default on) | backend | env | open | — | — | — | — | graduate | 2026-10-30 | dazheng |
| `SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST` | Limit sync lineage binding and its live-row fences to listed UIDs; empty admits every user | backend | env | open | — | — | vi7SA9ckQCe4ccobWNxlbdcNdC23 (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | pending | 2026-10-30 | dazheng |
| `SYNC_LINEAGE_S1_REQUIRED` | Require valid S1 upload claims before per-segment lineage binding (default gated) | backend | env | closed | {value: 'true', category: rollout} | {value: 'true', category: rollout} | {value: 'true', category: rollout} | — | pending | 2026-11-02 | dazheng |
| `SYNC_WAL_AUDIO_COVERAGE_ENABLED` | Trim safety-WAL frames positively proven live-received by shared source-frame identity before VAD/STT (default on) | backend | env | open | true | true | true | — | pending | 2026-11-02 | dazheng |
| `TRANSCRIPTION_SHADOW_ENABLED` | Run the stored-audio Parakeet final pass in shadow | backend | env | closed | — | false (backend-listen (chart), cloud_run/backend-sync, gke/backend-listen); true (gke/pusher, pusher (chart)) | true (gke/pusher, pusher (chart)) | — | pending | 2026-10-26 | dazheng |
| `TRANSCRIPTION_SHADOW_PERCENT` | Allocate UIDs to the Parakeet final-pass shadow | backend | env | closed | — | 0 (backend-listen (chart), cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | 0 (gke/pusher, pusher (chart)) | — | pending | 2026-10-26 | dazheng |
| `TRANSCRIPT_CHUNK_INDEXING_ENABLED` | Index transcript chunks for retrieval | backend | env | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `TRANSLATION_DEMAND_LEASE_V1_ENABLED` | Accept lease-v1 demand semantics from opted-in clients | backend | env | closed | {value: 'true', category: rollout} | true (backend-listen (chart)); {value: 'true', category: rollout} (cloud_run/backend, gke/backend-listen) | true (backend-listen (chart)); {value: 'true', category: rollout} (cloud_run/backend, gke/backend-listen) | — | pending | 2026-10-29 | dazheng |
| `TRANSLATION_DEMAND_SHADOW_ENABLED` | Measure would-be demand admission without changing translation behavior | backend | env | closed | {value: 'false', category: rollout} | false (backend-listen (chart)); {value: 'false', category: rollout} (cloud_run/backend, gke/backend-listen) | false (backend-listen (chart)); {value: 'false', category: rollout} (cloud_run/backend, gke/backend-listen) | — | pending | 2026-10-29 | dazheng |
| `TRANSLATION_ONDEMAND_COHORT_PERCENT` | Percentage of eligible UIDs admitted to on-demand translation (100 = all eligible) | backend | env | closed | {value: '100', category: rollout} | 100 (backend-listen (chart)); {value: '100', category: rollout} (cloud_run/backend, gke/backend-listen) | 100 (backend-listen (chart)); {value: '100', category: rollout} (cloud_run/backend, gke/backend-listen) | — | pending | 2026-10-29 | dazheng |
| `TRANSLATION_ONDEMAND_GEMINI_ENABLED` | Select Gemini-only viewed_v1 policy for admitted demand traffic | backend | env | closed | {value: 'true', category: rollout} | true (backend-listen (chart)); {value: 'true', category: rollout} (cloud_run/backend, gke/backend-listen) | true (backend-listen (chart)); {value: 'true', category: rollout} (cloud_run/backend, gke/backend-listen) | — | pending | 2026-10-29 | dazheng |
| `TRANSLATION_ONOPEN_ENABLED` | Serve bounded on-open translation for opt-in detail GETs | backend | env | closed | {value: 'true', category: rollout} | true (backend-listen (chart)); {value: 'true', category: rollout} (cloud_run/backend, gke/backend-listen) | true (backend-listen (chart)); {value: 'true', category: rollout} (cloud_run/backend, gke/backend-listen) | — | pending | 2026-10-29 | dazheng |
| `TRANSLATION_OUTPUT_GUARD_ENABLED` | Reject conservative same-language translation rewrites | backend | env | open | — | — | — | — | pending | 2026-10-28 | dazheng |
| `TRANSLATION_PROFILE_GATE_ENABLED` | Defer short out-of-profile translation guesses | backend | env | open | — | — | — | — | pending | 2026-10-28 | dazheng |
| `VAD_GATE_MODE` | Select off, shadow, or active server VAD gate | backend, mobile | env | closed | — | active (backend-listen (chart)) | active (backend-listen (chart)) | — | pending | 2026-10-15 | unowned |
| `X-Omi-Memory-Belief-Enabled` | Expose belief processing capability to memory clients | backend, macos | server_capability | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `X-Omi-Memory-Canonical-Lifecycle-Exposed` | Canonical memory lifecycle response header retained for older clients | backend, macos | server_capability | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `chat_first_ui` | Universal chat-first capability sent for older clients and sampled by macOS | backend, macos | server_capability | closed | — | — | — | — | pending | 2026-10-15 | unowned |
| `free-tier-cohort-v1` | Free-tier exposure cohort, never direct admission | backend | posthog | closed | — | — | — | absent (exposure) | pending | 2026-10-15 | unowned |
| `jit-processing-v1` | JIT processing admission cohort | backend | posthog | closed | — | — | — | expected (enable) | graduate | 2026-10-23 | dazheng |
| `negative_feedback_remediation` | Enable negative-feedback remediation on stable | macos | posthog | closed | — | — | — | absent (enable) | pending | 2026-10-23 | unowned |
| `negative_feedback_remediation_kill` | Beta negative-feedback remediation stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-23 | unowned |
| `on_device_meeting_identity` | Enable on-device meeting identity on stable | macos | posthog | closed | — | — | — | absent (enable) | graduate | 2026-10-23 | dazheng |
| `on_device_meeting_identity_kill` | Beta on-device meeting identity stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `onboarding-setup-rating-prompt` | Mobile onboarding Setting up your Omi page with the store-rating pre-prompt before the completion screen; client-evaluated, default off so the flow is unchanged and store review never sees it | mobile | posthog | closed | — | — | — | expected (enable) | pending | 2026-11-05 | nik |
| `proactivity_v2` | Server v2 proactivity admission; absent or unknown denies | backend, llm-gateway | posthog | closed | — | — | — | expected (enable) | pending | 2026-11-03 | dazheng |
| `screen_activity_lossless_sync` | Enable lossless screen sync on stable | macos | posthog | closed | — | — | — | absent (enable) | pending | 2026-10-15 | unowned |
| `screen_activity_lossless_sync_kill` | Beta lossless screen sync stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |
| `screen_task_jev_gate` | Default-off screen dedupe, Jev OCR gate and one-call extraction; privacy approval required | macos | posthog | closed | — | — | — | absent (enable) | pending | 2026-11-01 | dazheng |
| `system_calendar_meeting_context` | Enable system calendar meeting context on stable | macos | posthog | closed | — | — | — | absent (enable) | graduate | 2026-10-23 | dazheng |
| `system_calendar_meeting_context_kill` | Beta system calendar meeting context stop | macos | posthog | inverted | — | — | — | expected (kill) | pending | 2026-10-15 | unowned |

### ops_kill

| key | summary | surfaces | kind | fail | _base | dev | prod | PostHog row | decision | review_by | owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ACTION_ITEMS_LIST_STALE_CLIENT_REFUSE` | Refuse stale action-items list clients | backend | env | open | — | — | 1 | — | keep | — | unowned |
| `ADMIN_KEY_AUTH_ENABLED` | Allow administrator-key authentication | backend | env | open | — | — | — | — | keep | — | unowned |
| `CONVERSATION_SMART_MERGE_AUDIT_ENABLED` | Write the content-free smart-merge audit sibling inside the absorb transaction (unset = on; off or any unrecognized value = no gate read, no audit write) | backend | env | open | — | — | — | — | keep | — | dazheng |
| `CONVERSATION_SMART_MERGE_FLATTEN_ENABLED` | Flatten a smart-merge donor's absorbed sync-bridge ancestry onto the survivor in the absorb transaction and resolve redirected sync targets one hop (unset = on; off or any unrecognized value = legacy eligibility and no ancestor reads/writes) | backend | env | open | {value: 'true', category: ops_kill} | true (backend-listen (chart), pusher (chart)); {value: 'true', category: ops_kill} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | true (backend-listen (chart), pusher (chart)); {value: 'true', category: ops_kill} (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher) | — | keep | — | dazheng |
| `CONVERSATION_SPEAKER_RESOLUTION_ENABLED` | Incident stop for conversation-wide speaker resolution | backend | env | open | — | — | — | — | keep | — | unowned |
| `CONVERSATION_STORED_MEETING_CONTEXT_ENABLED` | Incident stop for stored meeting context lookup | backend | env | open | — | — | — | — | keep | — | unowned |
| `DAY3_REENGAGEMENT_EMAIL_KILL_SWITCH` | Stop day-three re-engagement email | backend | env | inverted | false | false | false | — | keep | — | unowned |
| `DEEPGRAM_SELF_HOSTED_ENABLED` | Select self-hosted Deepgram filler-word policy on pusher | backend | env | closed | — | false (backend-listen (chart)) | false (backend-listen (chart)); true (pusher (chart)) | — | keep | — | unowned |
| `DESKTOP_UPDATE_POINTERS_MODE` | Fall back to legacy desktop update pointers | backend | env | open | primary | primary (backend-listen (chart), cloud_run/backend, gke/backend-listen) | primary (backend-listen (chart), cloud_run/backend, gke/backend-listen) | — | keep | — | unowned |
| `FAIR_USE_KILL_SWITCH` | Emergency stop for fair-use enforcement | backend | env | inverted | — | false (backend-listen (chart)) | false (backend-listen (chart)) | — | keep | — | unowned |
| `FRAME_REQUEST_RETENTION_INDEPENDENT_HEALTHY` | Skip shared retention when independent job is healthy | backend | env | closed | false | false | false | — | keep | — | unowned |
| `FREE_TIER_EMERGENCY_STOP` | Stop all free-tier cohorts | backend | env | inverted | declared | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, pusher (chart)) | — | keep | — | unowned |
| `LISTEN_FINALIZATION_BYOK_ABANDONMENT_ENABLED` | Abandon finalization after BYOK failure | backend | env | open | true | true (backend-listen (chart), gke/backend-listen) | true (backend-listen (chart), gke/backend-listen) | — | keep | — | unowned |
| `LISTEN_FINALIZATION_DURABLE_ATTEMPT_CAP_ENABLED` | Cap durable listen worker attempts while retaining transcript-only conversations | backend | env | open | — | — | true | — | keep | — | dazheng |
| `LISTEN_FINALIZATION_RECOVERY_MINIMUM_TERMINAL_ENABLED` | End self-heal jobs after a minimal structure and skip obvious trivial content before paid notes | backend | env | open | — | — | true | — | keep | — | dazheng |
| `LLM_GATEWAY_ACCOUNTING_ENABLED` | Record gateway-managed usage accounting | backend, llm-gateway | env | closed | true | true (backend-listen (chart), cloud_run/backend, desktop-backend, gke/backend-listen, gke/pusher, llm-gateway (chart), pusher (chart)) | true (backend-listen (chart), cloud_run/backend, desktop-backend, gke/backend-listen, gke/pusher, llm-gateway (chart), pusher (chart)) | — | keep | — | unowned |
| `LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS` | Expose provider error details from gateway | llm-gateway | env | closed | — | true (llm-gateway (chart)) | — | — | keep | — | unowned |
| `MEMORY_BELIEF_AUTOMATION_PAUSED` | Pause automated belief processing | backend | env | inverted | false | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, job/daily-memory-sweep-job, job/memory-maintenance-job, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, job/daily-memory-sweep-job, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `MEMORY_CANONICAL_MAINTENANCE_ENABLED` | Enable canonical memory maintenance job | backend | env | closed | false (cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen); true (job/memory-maintenance-job) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen); true (job/memory-maintenance-job) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen); true (job/memory-maintenance-job) | — | keep | — | unowned |
| `MEMORY_DAILY_MEMORY_SWEEP_KILL_SWITCH` | Emergency stop for daily memory sweep | backend | env | inverted | false | false | false | — | keep | — | unowned |
| `MEMORY_ENABLED` | Global incident stop for canonical memory intake and reads | backend | env | closed | on | on (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, job/daily-memory-sweep-job, job/knowledge-ledger-drain-job, job/memory-maintenance-job, pusher (chart)) | on (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, job/daily-memory-sweep-job, job/knowledge-ledger-drain-job, job/memory-maintenance-job, job/x-connector-sync-job, pusher (chart)) | — | keep | — | unowned |
| `MEMORY_IMPORT_WRITE_BLOCK_MODE` | Block memory import writes during incident | backend | env | inverted | — | — | — | — | keep | — | unowned |
| `OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION` | Permit direct-model gateway exception | backend | env | closed | false | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, job/memory-maintenance-job, pusher (chart)) | false (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE` | Allow production gateway feature mode | backend | env | closed | — | — | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `OMI_LLM_GATEWAY_OBSERVABILITY_LOGS_ENABLED` | Enable gateway observability logs | backend | env | closed | — | — | — | — | keep | — | unowned |
| `OMI_VERTEX_LEGACY_TASK_MODE` | enforce (default) refuses positively identified macOS task loops below the configured capable build after confirmed inactivity; unset/invalid threshold or observe only counts | backend | env | closed | env_var | env_var | env_var | — | keep | — | dazheng |
| `SCREEN_ACTIVITY_KEYWORD_FALLBACK_ENABLED` | Fallback to keyword search for screen activity | backend | env | open | — | — | — | — | keep | — | unowned |
| `SCREEN_TASK_STOP` | Stop screen-task gate and flagged extraction admission; default false; clients poll every 30 seconds with a 55-second lease | backend | env | inverted | — | — | — | — | keep | — | dazheng |
| `SYNC_BACKFILL_ENABLED` | Emergency stop for accepting sync backfill | backend | env | open | true | true | true | — | keep | — | unowned |
| `TRANSCRIPTION_SHADOW_KILL_SWITCH` | Stop Parakeet final-pass shadow admission | backend | env | inverted | — | false (backend-listen (chart), cloud_run/backend-sync, gke/backend-listen, gke/pusher, pusher (chart)) | false (gke/pusher, pusher (chart)) | — | keep | — | dazheng |
| `TRANSLATION_DEMAND_GATE_ENABLED` | Gate live translation on transcript-view demand (on-demand rollout; false restores legacy always-translate) | backend | env | closed | {value: 'true', category: rollout} | true (backend-listen (chart)); {value: 'true', category: rollout} (cloud_run/backend, gke/backend-listen) | true (backend-listen (chart)); {value: 'true', category: rollout} (cloud_run/backend, gke/backend-listen) | — | keep | — | dazheng |
| `WAKE_WORD_ADJUDICATION_ENABLED` | Incident stop for wake-word adjudication | backend | env | open | true | true (backend-listen (chart), cloud_run/backend, gke/backend-listen) | true (backend-listen (chart), cloud_run/backend, gke/backend-listen) | — | keep | — | unowned |
| `desktop-rating-prompt-disabled` | Stop the rating prompt | macos | posthog | inverted | — | — | — | expected (kill) | keep | — | unowned |
| `exp-002-desktop-identity-kill-v1` | EXP-002 desktop identity arm emergency stop | backend, macos | posthog | inverted | — | — | — | expected (kill) | keep | — | unowned |
| `free-tier-kill-switch-v1` | Remote free-tier stop | backend | posthog | inverted | — | — | — | expected (kill) | keep | — | unowned |
| `jit-processing-kill-switch-v1` | JIT remote kill for allowlisted accounts | backend | posthog | inverted | — | — | — | expected (kill) | keep | — | unowned |

### config_switch

| key | summary | surfaces | kind | fail | _base | dev | prod | PostHog row | decision | review_by | owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ACCOUNT_DELETION_DISPATCH_MODE` | Select Cloud Tasks for account deletion | backend | env | closed | — | — | cloud_tasks (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen) | — | keep | — | unowned |
| `AUDIO_MERGE_DISPATCH_MODE` | Select audio-merge dispatch lane | backend | env | closed | — | — | — | — | keep | — | unowned |
| `COMMITMENT_FOLLOWUP_TASKS_HANDLER_URL` | One-shot commitment due callback transport; absent disables scheduling | backend | env | closed | — | — | — | — | keep | — | dazheng |
| `COMMITMENT_FOLLOWUP_TASKS_INVOKER_SA` | One-shot commitment due callback transport; absent disables scheduling | backend | env | closed | — | — | — | — | keep | — | dazheng |
| `COMMITMENT_FOLLOWUP_TASKS_QUEUE` | One-shot commitment due callback transport; absent disables scheduling | backend | env | closed | — | — | — | — | keep | — | dazheng |
| `FIRESTORE_CACHE_ENABLED` | Enable Firestore response cache | backend | env | closed | — | — | — | — | keep | — | unowned |
| `LISTEN_FINALIZATION_DISPATCH_MODE` | Select conversation finalization dispatch lane | backend | env | closed | — | — | cloud_tasks | — | keep | — | unowned |
| `LISTEN_RECONNECT_BUDGET_PER_MIN` | Bound per-user and per-device listen websocket reconnect admissions per minute | backend | env | closed | 6 | 6 (backend-listen (chart), gke/backend-listen) | 6 (backend-listen (chart), gke/backend-listen) | — | keep | — | dazheng |
| `MEMORY_CANONICAL_MAINTENANCE_FLEX` | Select gateway Flex lane for memory maintenance | backend | env | closed | true | true | true | — | keep | — | unowned |
| `MEMORY_IMPORT_BODY_STORAGE_MODE` | Select memory import body storage mode | backend | env | closed | — | — | — | — | keep | — | unowned |
| `MEMORY_TYPESENSE_READINESS_REQUIRED` | Require Typesense projection readiness for memory reads | backend | env | closed | — | — | — | — | keep | — | unowned |
| `MENTOR_PIPELINE` | Per-user cohort mentor dispatch; only cohort is valid — flag false/error or any other value dispatches nothing (legacy lane deleted) | backend | env | closed | — | — | cohort (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen, gke/pusher, llm-gateway (chart), pusher (chart)) | — | keep | — | dazheng |
| `OMI_BACKGROUND_FLEX_CAPABLE` | Allow background gateway Flex work | backend | env | closed | true | true | true | — | keep | — | unowned |
| `OMI_LLM_CHAT_AGENT_ROUTE` | Select managed chat-agent gateway route | backend | env | closed | gateway | gateway (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, job/memory-maintenance-job, pusher (chart)) | gateway (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `OMI_LLM_GATEWAY_FEATURE_MODE` | Select LLM gateway versus direct serving | backend | env | closed | gateway | gateway (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, gke/pusher, job/memory-maintenance-job, pusher (chart)) | gateway (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, gke/backend-listen, job/memory-maintenance-job, pusher (chart)) | — | keep | — | unowned |
| `OMI_MODEL_TIER` | Select proxy budget tier | backend | env | closed | — | — | — | — | keep | — | unowned |
| `OMI_VERTEX_LEGACY_TASK_MIN_CAPABLE_MACOS_BUILD` | First released macOS build containing #20374; positive integer read per request; unset/invalid serves all and counts candidate would-refuse volume in bounded build buckets | backend | env | open | env_var | env_var | env_var | — | keep | — | dazheng |
| `OMI_VERTEX_PT_TARGET_LOCATION` | Moved Vertex order location; default us; global explicitly widens residency | backend | env | closed | — | — | — | — | keep | — | dazheng |
| `OMI_VERTEX_RESERVATION_STATES` | Per-model active/inactive/unknown/auto JSON overrides; read per request, invalid JSON fails open | backend, llm-gateway | env | open | env_var | env_var | env_var | — | keep | — | dazheng |
| `PARAKEET_ATTENTION_MODE` | Choose full versus local attention on Parakeet GPU | backend | env | closed | — | — | auto (parakeet (chart)) | — | keep | — | unowned |
| `PARAKEET_DIARIZATION` | Enable prerecorded Parakeet diarization | backend | env | closed | — | — | — | — | keep | — | unowned |
| `PARAKEET_INFERENCE_MODE` | Choose Parakeet transcription inference backend | backend | env | closed | — | nemo (parakeet (chart)) | nemo (parakeet (chart)) | — | keep | — | unowned |
| `PARAKEET_USE_V2` | Select Parakeet prerecorded v2 pipeline | backend | env | open | — | — | — | — | keep | — | unowned |
| `RECORDING_SESSION_MODE` | Select recording session migration mode | backend | env | closed | — | — | — | — | keep | — | unowned |
| `SCREEN_TASK_JEV_AUDIT_RATE` | Screen gate reject audit fraction, default 0.01 | backend | env | open | — | — | — | — | keep | — | dazheng |
| `SCREEN_TASK_JEV_THRESHOLD` | Screen gate threshold, default 0.5 | backend | env | open | — | — | — | — | keep | — | dazheng |
| `SCREEN_TASK_MIN_MACOS_BUILD` | Minimum identified macOS build admitted to the screen-task gate, admission, and flagged extraction; default 12435; invalid values use the default | backend | env | closed | — | — | — | — | keep | — | dazheng |
| `SONIOX_ESTIMATED_USD_PER_HOUR` | Metered-audio fallback price for Soniox runway | backend | env | closed | 0.07537 | 0.07537 (backend-listen (chart), gke/backend-listen) | 0.07537 (backend-listen (chart), gke/backend-listen) | — | pending | — | dazheng |
| `STT_NO_TEXT_RESCUE_SECONDS` | Maximum paid wall and admitted audio seconds per no-text rescue; default 60 bounded 5-120 | backend | env | closed | — | — | — | — | pending | — | backend |
| `STT_NO_TEXT_SECONDS` | Deadline from VAD-confirmed speech to first provider text | backend | env | closed | 30 | 30 (backend-listen (chart), gke/backend-listen) | 30 (backend-listen (chart), gke/backend-listen) | — | pending | — | dazheng |
| `STT_PAID_SPILLOVER_DEEPGRAM_PER_MINUTE` | Deepgram fleet paid router promotion cap per UTC minute; default 30; zero refuses promotions | backend | env | closed | — | — | — | — | keep | — | backend |
| `STT_PAID_SPILLOVER_MODULATE_PER_MINUTE` | Modulate fleet paid router promotion cap per UTC minute; default 30; zero refuses promotions | backend | env | closed | — | — | — | — | keep | — | backend |
| `STT_PAID_SPILLOVER_SONIOX_PER_MINUTE` | Soniox fleet paid router promotion cap per UTC minute; default 30; zero refuses promotions | backend | env | closed | — | — | — | — | keep | — | backend |
| `STT_ROUTING_DISRUPTION_GATE` | Maximum acceptable speech-session disruption rate | backend | env | closed | 0.08 | 0.08 (backend-listen (chart), gke/backend-listen) | 0.08 (backend-listen (chart), gke/backend-listen) | — | pending | — | dazheng |
| `STT_ROUTING_REDIS_TIMEOUT_SECONDS` | Maximum Redis wait for live routing health state | backend | env | closed | 0.075 | 0.075 (backend-listen (chart), gke/backend-listen) | 0.075 (backend-listen (chart), gke/backend-listen) | — | pending | — | dazheng |
| `STT_ROUTING_TARGETS_JSON` | Declarative live STT targets with cost capability endpoint and ramp | backend | env | closed | '' | '' (backend-listen (chart), gke/backend-listen) | '' (backend-listen (chart), gke/backend-listen) | — | pending | — | dazheng |
| `STT_SHED_CONNECT_FAILURES` | Real consecutive live STT connect failures required before all-open circuit shedding | backend | env | closed | 3 | 3 (backend-listen (chart), gke/backend-listen) | 3 (backend-listen (chart), gke/backend-listen) | — | pending | — | dazheng |
| `SYNC_DISPATCH_MODE` | Select sync dispatch lane | backend | env | closed | — | — | — | — | keep | — | unowned |
| `SYNC_LEDGER_FENCE_MODE` | Select sync ledger fence authority | backend | env | closed | env_var | env_var | env_var | — | keep | — | unowned |
| `SYNC_PHASE_METRICS_EXPORT_ENABLED` | Export aggregate sync phase histograms through a bounded background flush; default off, enabled by reviewed deploy overlays | backend | env | closed | — | {value: 'true', category: telemetry} | {value: 'true', category: telemetry} | — | keep | — | dazheng |
| `TYPESENSE_CONVERSATION_INDEX_WRITES` | Write conversations to Typesense index | backend | env | closed | — | — | — | — | keep | — | unowned |
| `USE_VERTEX_AI` | Select Vertex AI model route | backend | env | closed | true | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen) | true (backend-listen (chart), cloud_run/backend, cloud_run/backend-integration, cloud_run/backend-sync, cloud_run/backend-sync-backfill, desktop-backend, gke/backend-listen) | — | keep | — | unowned |
| `VITE_ENABLE_GMAIL_SESSION` | Keep shipped Gmail session integration enabled | windows | build_define | open | — | — | — | — | keep | — | unowned |
| `X-Omi-Memory-Default-Delete-Supported` | Indicate default-memory deletion support | backend, macos | server_capability | closed | — | — | — | — | keep | — | unowned |
| `X-Omi-Memory-Device-Scope-Supported` | Indicate device-scoped memory query support | backend, macos | server_capability | closed | — | — | — | — | keep | — | unowned |

## Undeclared env flags

Env flags with no declaration in `runtime_env` or any chart; they run on
their code default (`fail` tells you which way a missing value resolves).

- `ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENABLED` — Measure, in the action_item_identity log line only, how many reprocess-unmatched prior tasks pair one-to-one with a new task by stored transcript segment ids; never changes what is written or delivered (default on) (fail: open)
- `ACTION_ITEM_IDENTITY_PRESERVE_ENABLED` — Keep a task's id and export marker when a conversation reprocess re-extracts the same task, so it is not sent to the user's cloud task app again; Apple Reminders excluded (default on) (fail: open)
- `ADMIN_KEY_AUTH_ENABLED` — Allow administrator-key authentication (fail: open)
- `AUDIO_MERGE_DISPATCH_MODE` — Select audio-merge dispatch lane (fail: closed)
- `CAPTURE_JEV_SHADOW_EXPIRY` — Shorten the Jev capture shadow hard deadline (fail: closed)
- `CAPTURE_JEV_SHADOW_GLOBAL_DAILY_CAP` — Global daily Jev capture shadow call budget (fail: closed)
- `CAPTURE_JEV_SHADOW_USER_DAILY_CAP` — Per-user daily Jev capture shadow call budget (fail: closed)
- `COMMITMENT_FOLLOWUP_TASKS_HANDLER_URL` — One-shot commitment due callback transport; absent disables scheduling (fail: closed)
- `COMMITMENT_FOLLOWUP_TASKS_INVOKER_SA` — One-shot commitment due callback transport; absent disables scheduling (fail: closed)
- `COMMITMENT_FOLLOWUP_TASKS_QUEUE` — One-shot commitment due callback transport; absent disables scheduling (fail: closed)
- `CONVERSATION_SMART_MERGE_AUDIT_ENABLED` — Write the content-free smart-merge audit sibling inside the absorb transaction (unset = on; off or any unrecognized value = no gate read, no audit write) (fail: open)
- `CONVERSATION_SMART_MERGE_MODE` — Fold a finished pendant conversation into its predecessor when Jev says same occasion (default merge; off|shadow|merge) (fail: open)
- `CONVERSATION_SMART_MERGE_UID_ALLOWLIST` — Limit smart merge to listed UIDs; empty admits every user (fail: closed)
- `CONVERSATION_SPEAKER_RESOLUTION_ENABLED` — Incident stop for conversation-wide speaker resolution (fail: open)
- `CONVERSATION_STORED_MEETING_CONTEXT_ENABLED` — Incident stop for stored meeting context lookup (fail: open)
- `FIRESTORE_CACHE_ENABLED` — Enable Firestore response cache (fail: closed)
- `FREE_TIER_MEMORY_SUPPRESSION` — Suppress cloud memory extraction for eligible free users (fail: closed)
- `FREE_TIER_MEMORY_SUPPRESSION_COHORT` — Admitted UIDs for free-tier memory suppression (fail: closed)
- `MEETING_NOTES_EPISODE_C6_TIMEOUT_SECONDS` — Requested C6 writer budget, default 180s; existing gateway limit clamps to 115s; C7 fallback (fail: closed)
- `MEETING_NOTES_EPISODE_CLAIMS_ENABLED` — Generate optional episode claim bindings, default off; visible provenance rules remain (fail: closed)
- `MEETING_NOTES_EPISODE_EFFORT` — Episode writer thinking effort: default, high or xhigh; baseline unchanged (fail: closed)
- `MEETING_NOTES_EPISODE_JEV_THRESHOLD` — Calibrated Jev evidence connection cutoff; deterministic remains default selector (fail: closed)
- `MEETING_NOTES_EPISODE_SELECTION` — Episode evidence selector: deterministic, jev or luna; compact remains an offline experiment (fail: closed)
- `MEETING_NOTES_EPISODE_SELECTION_EFFORT` — Optional selector effort, default low; writer effort is independent (fail: closed)
- `MEETING_NOTES_EPISODE_SELECTION_TIMEOUT_SECONDS` — Optional selection pass timeout, default 30 seconds, bounded 1-30; fallback keeps writing (fail: closed)
- `MEETING_NOTES_EPISODE_THINKING_MAX_INPUT_BYTES` — Optional high/xhigh byte ceiling, default disabled (0); long transcript guard stays active (fail: closed)
- `MEETING_NOTES_EPISODE_TIERED_ENABLED` — Universal evidence-volume cost routing: high-value C6, otherwise C7; default enabled inside episode cohort (fail: closed)
- `MEETING_NOTES_EPISODE_TIER_MIN_SOURCE_KINDS` — C6 admitted source-kind threshold, default 2 (fail: closed)
- `MEETING_NOTES_EPISODE_TIER_MIN_WORDS` — C6 admitted speech word threshold, default 1500 (fail: closed)
- `MEETING_NOTES_EPISODE_WRITER_TIMEOUT_SECONDS` — Episode C7 writer budget, default 120s in durable jobs; synchronous requests retain 60s (fail: closed)
- `MEMORY_IMPORT_BODY_STORAGE_MODE` — Select memory import body storage mode (fail: closed)
- `MEMORY_IMPORT_WRITE_BLOCK_MODE` — Block memory import writes during incident (fail: inverted)
- `MEMORY_TYPESENSE_READINESS_REQUIRED` — Require Typesense projection readiness for memory reads (fail: closed)
- `MENTOR_GATE_PROMPT_CACHE_ENABLED` — Cache mentor gate prompts (fail: closed)
- `OMI_GEMINI_OVERFLOW_ENABLED` — Enable overflow routing to Gemini (fail: closed)
- `OMI_LLM_GATEWAY_OBSERVABILITY_LOGS_ENABLED` — Enable gateway observability logs (fail: closed)
- `OMI_LLM_GATEWAY_OUTPUT_BUDGET_EXPERIMENTS` — Select gateway output-budget experiments (fail: closed)
- `OMI_MODEL_TIER` — Select proxy budget tier (fail: closed)
- `OMI_VERTEX_PT_TARGET_LOCATION` — Moved Vertex order location; default us; global explicitly widens residency (fail: closed)
- `PARAKEET_DIARIZATION` — Enable prerecorded Parakeet diarization (fail: closed)
- `PARAKEET_USE_V2` — Select Parakeet prerecorded v2 pipeline (fail: open)
- `PINNED_SPEAKER_PRIOR_ENABLED` — Turn near-misses on pinned people into suggestions and record voice candidates for the suggestion card (never loosens auto-labels) (fail: closed)
- `RATE_LIMIT_SHADOW_MODE` — Shadow backend rate limits (fail: closed)
- `RECORDING_SESSION_MODE` — Select recording session migration mode (fail: closed)
- `SCREEN_ACTIVITY_KEYWORD_FALLBACK_ENABLED` — Fallback to keyword search for screen activity (fail: open)
- `SCREEN_TASK_JEV_AUDIT_RATE` — Screen gate reject audit fraction, default 0.01 (fail: open)
- `SCREEN_TASK_JEV_THRESHOLD` — Screen gate threshold, default 0.5 (fail: open)
- `SCREEN_TASK_MIN_MACOS_BUILD` — Minimum identified macOS build admitted to the screen-task gate, admission, and flagged extraction; default 12435; invalid values use the default (fail: closed)
- `SCREEN_TASK_STOP` — Stop screen-task gate and flagged extraction admission; default false; clients poll every 30 seconds with a 55-second lease (fail: inverted)
- `SELFHEAL_MODE` — Conversation self-heal sweeper mode: off/detect-only/nudge/heal (fail: closed)
- `SONIOX_ELAPSED_AXIS` — Measure Soniox elapsed timestamps before enabling speaker windows (fail: closed)
- `STT_NO_TEXT_RESCUE_SECONDS` — Maximum paid wall and admitted audio seconds per no-text rescue; default 60 bounded 5-120 (fail: closed)
- `STT_PAID_SPILLOVER_BUDGET_ENABLED` — Default-off fleet budget for paid router promotions after Parakeet capacity refusal; denial restores static order (fail: closed)
- `STT_PAID_SPILLOVER_DEEPGRAM_PER_MINUTE` — Deepgram fleet paid router promotion cap per UTC minute; default 30; zero refuses promotions (fail: closed)
- `STT_PAID_SPILLOVER_MODULATE_PER_MINUTE` — Modulate fleet paid router promotion cap per UTC minute; default 30; zero refuses promotions (fail: closed)
- `STT_PAID_SPILLOVER_SONIOX_PER_MINUTE` — Soniox fleet paid router promotion cap per UTC minute; default 30; zero refuses promotions (fail: closed)
- `SYNC_BACKFILL_ROUTING_ENABLED` — Route eligible sync work to backfill lane (fail: closed)
- `SYNC_DISPATCH_MODE` — Select sync dispatch lane (fail: closed)
- `SYNC_LINEAGE_RESOLVE_ENABLED` — Bind each segment of a recording-id safety-WAL upload to the live rollover generation that owns its audio, and stamp live generations with their origin recording id (default on) (fail: open)
- `TRANSCRIPT_CHUNK_INDEXING_ENABLED` — Index transcript chunks for retrieval (fail: closed)
- `TRANSLATION_OUTPUT_GUARD_ENABLED` — Reject conservative same-language translation rewrites (fail: open)
- `TRANSLATION_PROFILE_GATE_ENABLED` — Defer short out-of-profile translation guesses (fail: open)
- `TYPESENSE_CONVERSATION_INDEX_WRITES` — Write conversations to Typesense index (fail: closed)

## Not feature flags

Do not list these as rollout flags:

- Flutter `OmiFeatures` hardware capability bits.
- Integration-nudge UserDefaults opt-out (per-user preference, not a remote gate).
- Local process overrides (`OMI_FORCE_*` and the bucket-pipeline
  `OMI_FORCE_BUCKET_*` / `OMI_FORCE_DWELL_REFRESH` /
  `OMI_FORCE_DEPARTURE_EVALUATION` / `OMI_FORCE_FACT_WRITE_POLICY` knobs).
  Most are dev-only controls, but some (e.g. `OMI_FORCE_CLOUD_STT`,
  `OMI_FORCE_NOTCH`) are deliberately honored by shipped builds. Either way
  the `ignore:` row records the classification as a visible decision: local
  environment data, never remote rollout authority.

The registry `ignore:` block names every other intentional non-flag with its
reason:

| Key | Reason | owner | decision | review_by | notes |
| --- | --- | --- | --- | --- | --- |
| `DD_TRACE_ENABLED` | Datadog telemetry instrumentation switch, not a product behavior flag | — | — | — | — |
| `DD_LOGS_ENABLED` | Datadog telemetry log routing switch, not a product behavior flag | — | — | — | — |
| `OMI_FORCE_CONTEXT_BUCKETS` | Local-only dev override, not shipped remote authority | — | — | — | — |
| `OMI_FORCE_BUCKET_RETRIEVAL` | Local-only dev override, not shipped remote authority | — | — | — | — |
| `OMI_FORCE_BUCKET_DESTINATIONS` | Local-only dev override, not shipped remote authority | — | — | — | — |
| `OMI_FORCE_BUCKET_WORKSTREAMS` | Local-only dev override, not shipped remote authority | — | — | — | — |
| `OMI_FORCE_BUCKET_CANDIDATES` | Local-only dev override, not shipped remote authority | — | — | — | — |
| `OMI_FORCE_LOSSLESS_SCREEN_SYNC` | Local-only dev override, not shipped remote authority | — | — | — | — |
| `OMI_FORCE_DWELL_REFRESH` | Local-only dev override, not shipped remote authority | — | — | — | — |
| `OMI_FORCE_DEPARTURE_EVALUATION` | Local-only dev override, not shipped remote authority | — | — | — | — |
| `OMI_FORCE_FACT_WRITE_POLICY` | Local-only dev override, not shipped remote authority | — | — | — | — |
| `OMI_FORCE_CANONICAL_MEMORY_ATLAS` | Local-only dev brain-map override retained while the legacy fallback remains | — | — | — | — |
| `OMI_FORCE_INTERJECT` | Local-only dev floating-card override, not remote rollout authority | — | — | — | — |
| `OMI_FORCE_NEGATIVE_FEEDBACK_REMEDIATION` | Local-only dev remediation override, not remote rollout authority | — | — | — | — |
| `OMI_FORCE_SYSTEM_CALENDAR_MEETING_CONTEXT` | Local-only dev calendar override, not remote rollout authority | — | — | — | — |
| `OMI_FORCE_ON_DEVICE_MEETING_IDENTITY` | Local-only dev meeting identity override, not remote rollout authority | — | — | — | — |
| `OMI_FORCE_NOTCH` | Local display override honored by shipped builds, not remote rollout authority | — | — | — | — |
| `OMI_FORCE_NO_NOTCH` | Local display override honored by shipped builds, not remote rollout authority | — | — | — | — |
| `OMI_FORCE_SYNTHESIS_FAIL` | Local QA fault-injection override honored by shipped builds, not remote rollout authority | — | — | — | — |
| `OMI_FORCE_CLOUD_STT` | Local override deliberately honored in shipped builds; not remote rollout authority | — | — | — | — |
| `OMI_LOCAL_EMBEDDINGS` | Local override deliberately honored in shipped builds; not remote rollout authority | — | — | — | — |
| `OMI_DISABLE_LOCAL_EMBEDDINGS` | Local incident override deliberately honored in shipped builds; not remote rollout authority | — | — | — | — |
| `OMI_DISABLE_LOCAL_INFERENCE` | Local incident override deliberately honored in shipped builds; not remote rollout authority | — | — | — | — |
| `freeTierLocalProcessing` | UserDefaults override deliberately honored in shipped builds; not remote rollout authority | — | — | — | — |
| `localEmbeddingsEnabled` | UserDefaults override deliberately honored in shipped builds; not remote rollout authority | dazheng | graduate | 2026-10-23 | Blocked on production local-embedding availability and fallback verification |
| `disableLocalInference` | UserDefaults override deliberately honored in shipped builds; not remote rollout authority | — | — | — | — |
| `forceCloudSTT` | UserDefaults override deliberately honored in shipped builds; not remote rollout authority | — | — | — | — |
| `vadGateEnabled` | Mobile shipped developer preference, pending product decision; not remote rollout authority | — | pending | 2026-10-23 | David: decide after registry+cleanup is prod-stable |
| `meeting_note_screenshots_enabled` | Account-level screenshot consent, not remote rollout authority | dazheng | graduate | 2026-10-23 | Blocked on screen-frame consent and prod egress validation |
| `OMI_FREE_TIER_LOCAL_PROCESSING` | Environment override deliberately honored in shipped builds; not remote rollout authority | — | — | — | — |
| `OMI_FORCE_LOCAL_INFERENCE_ENGINE` | Local inference engine override deliberately honored in shipped builds | — | — | — | — |
| `forceLocalInferenceEngine` | UserDefaults inference engine override deliberately honored in shipped builds | — | — | — | — |
| `OMI_FORCE_LOCAL_EMBEDDING_ENGINE` | Local embedding engine override deliberately honored in shipped builds | — | — | — | — |
| `forceLocalEmbeddingEngine` | UserDefaults embedding engine override deliberately honored in shipped builds | — | — | — | — |
| `disableLocalEmbeddings` | UserDefaults embedding incident override deliberately honored in shipped builds | — | — | — | — |
| `OMI_LOCAL_INFERENCE_URL` | Local engine endpoint override deliberately honored in shipped builds, not rollout authority | — | — | — | — |
| `localInferenceServerURL` | UserDefaults local engine endpoint override deliberately honored in shipped builds | — | — | — | — |
| `OMI_LOCAL_INFERENCE_MODEL` | Local model choice deliberately honored in shipped builds, not rollout authority | — | — | — | — |
| `localInferenceModel` | UserDefaults local model choice deliberately honored in shipped builds | — | — | — | — |
| `OMI_LOCAL_INFERENCE_CONTEXT_TOKENS` | Local numeric tuning deliberately honored in shipped builds, not rollout authority | — | — | — | — |
| `localInferenceContextTokens` | UserDefaults local numeric tuning deliberately honored in shipped builds | — | — | — | — |
| `OMI_LOCAL_INFERENCE_TIMEOUT_SECONDS` | Local timeout deliberately honored in shipped builds, not rollout authority | — | — | — | — |
| `localInferenceTimeoutSeconds` | UserDefaults local timeout deliberately honored in shipped builds | — | — | — | — |
| `OMI_FORCE_PARAKEET_FAIL` | Local QA failure override, not remote rollout authority | — | — | — | — |
| `forceParakeetFail` | Local QA failure override, not remote rollout authority | — | — | — | — |
| `OMI_YOLO_MODE` | Local agent override restricted to non-production builds; not remote rollout authority | — | — | — | — |
| `PROVIDER_MODE` | Local offline provider harness, not a product flag | — | — | — | — |

## Retired names — do not reuse

Code was deleted but an external row may still exist. Names cover PostHog
keys and shipped local preference keys; the sync reports live PostHog
leftovers as read-only delete candidates. Never re-read these names for
admission.

| Key | Retired | Reason |
| --- | --- | --- |
| `autoCreateSpeakersEnabled` | 2026-09-26 | Shipped developer preference removed; create_speakers always true |
| `context_buckets` | 2026-09-24 | Unused nominal enable row; bundle identity owns the active gate |
| `daily-memory-sweep-v1` | 2026-09-24 | Decoy name never authorizes JIT or sweep admission |
| `desktop-onboarding-rerun` | 2026-09-26 | Onboarding rerun policy removed; onboarding resumes via persisted state |
| `desktop_persistent_capture_stream` | 2026-09-26 | Persistent capture stream removed; capture uses the one-shot path |
| `isWorkstreamPoolingEnabled` | 2026-09-26 | Workstream pooling gate and its delivery path removed |
| `mobile-experiments-enabled` | 2026-09-26 | Empty mobile experiment framework removed |
| `jit-processing-ledger-migration-v1` | 2026-09-24 | Old ledger migration name never authorizes JIT processing |
| `mobile-summary-feedback-layout-v1` | 2026-09-26 | Experiment removed; summary feedback uses the standard layout |
