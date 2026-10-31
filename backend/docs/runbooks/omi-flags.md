# Omi flags (PostHog flag replacement)

Runtime feature flags move from PostHog `/flags` to Omi's own store, one key at a
time. PostHog stays for analytics and for the running experiments.

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
- **Absent means "not ours":** a key with no rule resolves to nothing, and the caller
  keeps PostHog (clients) or its registry fail value (`OMI_FLAGS_SOURCE=omi`). Deleting
  a rule hands the key back to PostHog.
- **Clients:** `GET /v1/flags?surface=macos|mobile|web-app|windows` returns the caller's
  resolved values for keys whose `surfaces` include that surface. macOS
  (`OmiFlagStore`), Flutter (`PostHogAnalyticsAdapter.omiFlags`) and web
  (`lib/omiFlags.ts`) answer those keys first and read PostHog for the rest. They
  refresh at the existing PostHog reload points, so no new polling.
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
2. `OMI_FLAGS_SOURCE=dual` for 24 h with zero mismatches, then `omi`; then drop
   `PROACTIVITY_V2_POSTHOG_TOKEN`. Rollback: `OMI_FLAGS_SOURCE=posthog`.
3. Clients pick keys up as soon as a rule exists. A later client release turns PostHog
   flag loading off (`preloadFeatureFlags=false`, posthog-js
   `advanced_disable_feature_flags`) once only experiments remain there.

Check the store against the emulator:

```bash
firebase emulators:exec --only firestore --project demo-omi-flags \
  "backend/.venv/bin/python backend/scripts/omi_flags_emulator_test.py"
```
