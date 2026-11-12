# Omi flags (PostHog flag replacement)

New client builds use Omi's store as their only flag authority. PostHog stays
for event capture and mobile replay. Older released builds still read PostHog;
keep their rows until those builds age out. Mobile paywall/onboarding arms are
fixed in code by #24370 (Nik's release gate still applies).

## Shape

- **Store:** Firestore in a dedicated project (`OMI_FLAGS_FIRESTORE_PROJECT`, optional
  `OMI_FLAGS_FIRESTORE_DATABASE`), never the customer-data project: dev and prod share
  that one, and every runtime SA there can write it. Only the flag writer can write the
  flag project; serving SAs get read. Dev gets its own project.
  - `omi_flags/{key}`: `active`, `rollout_percentage` (0–100), optional `variant`,
    `payload` (JSON text), `allow_uids`, `deny_uids`, `surfaces` (copied from
    `config/feature-flags.yaml`), plus `version`, `updated_at`, `updated_by`.
  - `omi_flags_meta/state.version`: bumped by every write.
  - `omi_flags_audit/*`: before/after, actor, reason; written in the same transaction.
- **Evaluation:** `utils/omi_flags.py`, in process. Each process re-checks the version
  every 15 s through Redis `omi_flags:version` (fast path) and every 60 s through the
  meta doc (always), reloads on change, and keeps the last good snapshot when a read
  fails (`omi_fallback_total{component="feature_flags"}`). Rollout buckets use PostHog's
  hash (`sha1("{key}.{uid}")`), so a key imported at the same percentage keeps its users.
- **Absent means unknown:** a key with no rule resolves to nothing. New clients
  apply their existing caller default; they never fall back to PostHog. Deleting a
  rule restores that default. Older clients retain the per-key PostHog fallback.
- **Clients:** `GET /v1/flags?surface=macos|mobile|web-app|windows` returns the caller's
  resolved values for keys whose `surfaces` include that surface. macOS
  (`OmiFlagStore`), Flutter (`PostHogAnalyticsAdapter.omiFlags`) and web
  (`lib/omiFlags.ts`) answer only from this store. Failed refreshes retain the
  same-account snapshot on mobile/macOS; account changes clear it. Missing web
  keys fail closed. Refresh cadence is unchanged.
- **SDK traffic:** preloads and explicit reloads are disabled. Swift and Android
  SDKs still attempt flag HTTP requests on identify/reset, so SDK-scoped transports
  answer only `/flags` and `/decide` locally with empty flags. Capture, replay and
  remote-config requests pass through. Mobile's `com.omi/posthog_setup` configures
  that transport before the Flutter bridge's idempotent native setup; preserve this
  order. The bridge still installs its Dart replay and event callbacks. Web sets
  `advanced_disable_feature_flags` in both the signed-in app and personas snippet.
- **Chat/replay proposals (not applied):** `mobile-chat-apps` serves Telegram at
  100%; `mobile-chat-apps-all-channels` protects private channel endpoints behind a
  David-only allowlist. A malformed public payload cannot expose those endpoints.
  `mobile-session-replay` uses 5% plus an approved internal UID list. The UID-only
  evaluator cannot preserve email/new-device targeting; David/Nik must rule before
  these rules and the client release. No PostHog mirror writes for the new key.
- **Server:** `proactivity_v2` follows `OMI_FLAGS_SOURCE`: `posthog` (default),
  `dual` (serve PostHog, count `omi_flag_dual_read_total{outcome}`), `omi`.

## Operate (`backend/scripts/omi_flags.py`)

Run from `backend/` with the flag project's writer identity (`prod-operator` tier for prod).

```bash
python scripts/omi_flags.py --project <flag-project> list
python scripts/omi_flags.py --project <flag-project> import-posthog            # dry run
python scripts/omi_flags.py --project <flag-project> import-posthog --apply --keys screen_task_jev_gate
python scripts/omi_flags.py --project <flag-project> set screen_activity_lossless_sync --rollout 25 --reason "ramp" --mirror-posthog
python scripts/omi_flags.py --project <flag-project> set screen_task_jev_gate --inactive --reason "stop" --mirror-posthog
python scripts/omi_flags.py --project <flag-project> history screen_task_jev_gate
python scripts/omi_flags.py --project <flag-project> delete screen_task_jev_gate --reason "back to PostHog"
```

- Only registry `kind: posthog` keys can be written; `experiment` keys stay on PostHog.
- `import-posthog` converts active rows with one unconditioned group (percentage and
  `true` payload). Inactive rows, targeting conditions and multivariate rows need a
  hand-written rule.
- While released builds still read PostHog, pass `--mirror-posthog` so both agree. It
  only handles single-group rows; a kill stays an active 0% group, because an inactive
  PostHog row reads as unknown on released clients.
- Without Redis access the CLI still writes; pods pick the change up within 60 s.

## Roll out

1. Provision the flag projects and IAM (David's approval), set
   `OMI_FLAGS_FIRESTORE_PROJECT` on every serving host, and import.
2. Keep the frozen target from lead2 ruling `95e1f1`: `dual` everywhere,
   `omi` on llm-gateway; owner cl2-coordkit, freeze review done_by 2026-11-16.
   Integration/backfill's missing env meant the `posthog` default; explicitly
   provisioning `dual` closes that gap. Dual serves PostHog; Omi is compare-only.
   Re-run the clean gate below after provisioning and scrape coverage are complete.
   Passing the gate is evidence for owner review, not authorization to expand.
   Rollback per service: `OMI_FLAGS_SOURCE=posthog` in
   `backend/deploy/runtime_env/prod.overlay.yaml`, then
   `python3 backend/deploy/compose_runtime_env.py`, align applicable GKE chart env,
   and apply on the next approved roll. For llm-gateway, first restore its approved
   `PROACTIVITY_V2_POSTHOG_TOKEN` and `PROACTIVITY_V2_POSTHOG_HOST` bindings.
3. Before releasing Omi-only clients, verify the flag rules and approve the chat /
   replay targeting changes. There is no dual-read escape hatch: rollback is the
   previous client build, or a store rule restoring the required value. Missing
   `screen_task_jev_gate` keeps screen-task admission on; no rule is required.

### 24-hour dual-read clean gate

Start a new full 24-hour window after provisioning and scrape coverage are verified.
Build the expected evaluator inventory independently of metric presence: backend,
backend-sync, backend-sync-backfill, backend-integration, desktop-backend,
backend-listen and pusher. Map each to its actual `(job, service_name)` labels and
all expected scrape instances. llm-gateway remains `omi`, so it cannot supply dual
comparison evidence. Unknown label mappings or missing scrape coverage block the
gate; never infer the inventory from the series that happen to be present.

At the same window end, require a returned row for **every expected dual evaluator**
in both queries, with zero bad outcomes and a strictly positive match increase:

```promql
sum by (job, service_name) (
  increase(omi_flag_dual_read_total{
    flag="proactivity_v2", outcome=~"mismatch|omi_absent|omi_error"
  }[24h])
) == 0
```

```promql
sum by (job, service_name) (
  increase(omi_flag_dual_read_total{
    flag="proactivity_v2", outcome="match"
  }[24h])
) > 0
```

Additionally require successful scrapes throughout that window for **every expected
scrape instance**. Substitute its verified labels and configured scrape interval
in seconds in these query templates (the `$` variables are operator inputs):

```promql
min_over_time(up{job="$job", service_name="$service_name", instance="$instance"}[24h]) == 1
```

```promql
count_over_time(up{job="$job", service_name="$service_name", instance="$instance"}[24h])
  >= (86400 / $scrape_interval_seconds)
```

Require both queries to return that instance; also check the scrape timeline for
gaps against the configured cadence, since a sample count alone cannot prove
continuity. Target turnover or a cadence change restarts the evidence window.
Verify all four outcome series are present throughout the window on each instance,
and require `omi_fallback_total{component="feature_flags"}` to remain flat.
Missing/partial windows and zero comparisons fail the gate even when all exported
bad-outcome counters are zero. These are review queries, not an automatic rollout.

Check the store against the emulator:

```bash
firebase emulators:exec --only firestore --project demo-omi-flags \
  "backend/.venv/bin/python backend/scripts/omi_flags_emulator_test.py"
```
