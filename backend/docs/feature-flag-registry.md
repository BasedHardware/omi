<!-- feature-flag-registry as-of: 2026-10-22 -->

# Feature-flag authority registry

GENERATED from `config/feature-flags.yaml` by `scripts/render_feature_flag_registry.py`; do not edit.

Boolean `fail` fields for migrated switches are generated from the shared parser's
missing-value policy. `CAPTURE_COVERAGE_MODE` off/shadow preserves the legacy token
grammar; serve uses `refactor_modes.default_on/default_off`. Explicit child settings
override repeat-work inheritance only in serve mode. Check with `--check-parsers`.

Flipping a row here does not turn a feature on; PostHog / bundle identity /
`runtime_env` remain the live levers. This file is a catalog of *which* lever
owns each gate, not the switch itself.

`terminal` records the reviewed end state: `on` graduates a feature, `off`
kills it, `keep` retains an ops kill or config switch, and `undecided` means
no terminal ruling is recorded yet.

## Contributing registry rows

Edit `config/feature-flags.yaml`, then regenerate this document with
`python3 scripts/render_feature_flag_registry.py`. A `ramp` object is optional
for existing rows. It is required for `lifecycle: rollout` rows that are
pending (`decision: pending` or `terminal: undecided`) and created on or after
2026-10-21. Include every field below; `done_by` must be on or before
`review_by`.

- `cohorts`: ordered rollout steps, ending in the full intended cohort;
  a single-user step such as `David-only` cannot be terminal.
- `clean_metric`: the metric that must stay clean before expansion.
- `expander`: the session, role, or person responsible for each expansion.
- `done_by`: the date the ramp reaches its final cohort.

Example:

```yaml
ramp:
  cohorts: ["release-probe", "1%", "5% 3h", "25%", "100%"]
  clean_metric: "checkout_error_rate"
  expander: "release-owner session"
  done_by: "2026-11-15"
```

Rows created before the cutoff stay grandfathered when `ramp` is absent;
the checker warns and reports their count. Do not backfill plans into them.

This is **not** a second classification of deployment wiring. Secret vs config
vs `public_build` still lives only in
[`config/deployment-setting-classification.json`](../../config/deployment-setting-classification.json)
and [`deployment-setting-classification.mdx`](deployment-setting-classification.mdx).
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

(none)

## Overdue for a decision

None as of 2026-10-22.

## Flags

`_base`, `dev`, and `prod` show declared literals from `runtime_env`
(`dev`/`prod` are `_base` inheritance plus the environment overlay). Chart
values and deploy-action env overlays appear as extra sources suffixed
`(chart)` and `(action)` and never mask runtime
differences; differing values list their hosts. A declaration without a
literal (`config_map`, `env_var`, `secret`, `valueFrom`) counts as declared,
and an explicit empty literal renders as `''`.

### experiment

(none)

### rollout

| key | summary | surfaces | kind | fail | _base | dev | prod | PostHog row | decision | terminal | review_by | owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `EPISODE_BOUNDARIES_MODE` | Hard meeting evidence for episodes and occasion conversations; off\|shadow\|serve, default shadow | backend | env | closed | — | — | — | — | pending | undecided | 2026-10-26 | dazheng |
| `EPISODE_BOUNDARIES_MODE_SERVE_PERCENT` | Serve cohort percentage in shadow mode, default 0 | backend | env | closed | — | — | — | — | pending | undecided | 2026-10-26 | dazheng |
| `EPISODE_BOUNDARIES_MODE_SERVE_UID_SHA256S` | Serve cohort account digests in shadow mode, default empty; never raw account identifiers | backend | env | closed | — | — | — | — | pending | undecided | 2026-10-26 | dazheng |
| `LIFECYCLE_V2_MODE` | Separate speech clocks, recovery head probes and bounded finalization executor lanes; off\|shadow\|serve, default shadow | backend | env | closed | — | — | — | — | pending | undecided | 2026-10-26 | dazheng |
| `LIFECYCLE_V2_MODE_SERVE_PERCENT` | Serve cohort percentage in shadow mode, default 0 | backend | env | closed | — | — | — | — | pending | undecided | 2026-10-26 | dazheng |
| `LIFECYCLE_V2_MODE_SERVE_UID_SHA256S` | Serve cohort account digests in shadow mode, default empty; never raw account identifiers | backend | env | closed | — | — | — | — | pending | undecided | 2026-10-26 | dazheng |

### ops_kill

(none)

### config_switch

(none)

## Rollout ramp plans

| key | cohorts | clean metric | expander | done_by |
| --- | --- | --- | --- | --- |
| `EPISODE_BOUNDARIES_MODE` | shadow observation → runtime digest canary → 5 percent → 25 percent → 100 percent | omi_lifecycle_refactor_shadow_total errors stay zero; no stuck merging, empty-row data loss or lost committed acknowledgements | dazheng | 2026-10-26 |
| `EPISODE_BOUNDARIES_MODE_SERVE_PERCENT` | shadow observation → runtime digest canary → 5 percent → 25 percent → 100 percent | omi_lifecycle_refactor_shadow_total errors stay zero; no stuck merging, empty-row data loss or lost committed acknowledgements | dazheng | 2026-10-26 |
| `EPISODE_BOUNDARIES_MODE_SERVE_UID_SHA256S` | shadow observation → runtime digest canary → 5 percent → 25 percent → 100 percent | omi_lifecycle_refactor_shadow_total errors stay zero; no stuck merging, empty-row data loss or lost committed acknowledgements | dazheng | 2026-10-26 |
| `LIFECYCLE_V2_MODE` | shadow observation → runtime digest canary → 5 percent → 25 percent → 100 percent | omi_lifecycle_refactor_shadow_total errors stay zero; no stuck merging, empty-row data loss or lost committed acknowledgements | dazheng | 2026-10-26 |
| `LIFECYCLE_V2_MODE_SERVE_PERCENT` | shadow observation → runtime digest canary → 5 percent → 25 percent → 100 percent | omi_lifecycle_refactor_shadow_total errors stay zero; no stuck merging, empty-row data loss or lost committed acknowledgements | dazheng | 2026-10-26 |
| `LIFECYCLE_V2_MODE_SERVE_UID_SHA256S` | shadow observation → runtime digest canary → 5 percent → 25 percent → 100 percent | omi_lifecycle_refactor_shadow_total errors stay zero; no stuck merging, empty-row data loss or lost committed acknowledgements | dazheng | 2026-10-26 |

## Undeclared env flags

Env flags with no declaration in `runtime_env` or any chart; they run on
their code default (`fail` tells you which way a missing value resolves).

- `EPISODE_BOUNDARIES_MODE` — Hard meeting evidence for episodes and occasion conversations; off|shadow|serve, default shadow (fail: closed)
- `EPISODE_BOUNDARIES_MODE_SERVE_PERCENT` — Serve cohort percentage in shadow mode, default 0 (fail: closed)
- `EPISODE_BOUNDARIES_MODE_SERVE_UID_SHA256S` — Serve cohort account digests in shadow mode, default empty; never raw account identifiers (fail: closed)
- `LIFECYCLE_V2_MODE` — Separate speech clocks, recovery head probes and bounded finalization executor lanes; off|shadow|serve, default shadow (fail: closed)
- `LIFECYCLE_V2_MODE_SERVE_PERCENT` — Serve cohort percentage in shadow mode, default 0 (fail: closed)
- `LIFECYCLE_V2_MODE_SERVE_UID_SHA256S` — Serve cohort account digests in shadow mode, default empty; never raw account identifiers (fail: closed)

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

## Retired names — do not reuse

None.
