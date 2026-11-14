# Backend runtime manifest versions

Edit `_base.yaml` and the environment overlays, then regenerate
`backend/deploy/runtime_env.yaml` with `backend/deploy/compose_runtime_env.py`.

Pre-recorded Modulate credit/breaker failover to Soniox is declared on every
runtime host beside `STT_PRERECORDED_MODEL`. `PRERECORDED_SONIOX_FAILOVER_ENABLED`
defaults to `true`; rollback sets it to `false` on those same hosts and charts.

Batch admission percentage is runtime-owned in `rollout_cohorts/_ramp`; these
deploy inputs and listen charts deliberately omit `BATCH_PIPELINE_PERCENT`.
Keep it out of deployment defaults and use the
[runtime ramp migration](../../docs/runbooks/batch-runtime-ramp.md) for the
one-time zero seed, controller/guard cutover and rollback. Existing env values
are fallback only, never evidence of effective admission after that seed.

Version 2 requires the backend voice route's staging bucket as an explicit
literal: `syncing-local-development` in dev and `syncing-local` in prod. Normal
admission and the existing prebuild preflight reject missing, blank, implicit,
or wrong-environment bindings.

Historical version 1 releases inherited this binding from Cloud Run. Current
controls must still replay those admitted releases during rollback.
`backend/scripts/runtime_env_compat.py` materializes the reviewed literal only
when that version's binding is missing. Explicit invalid bindings remain
invalid. The renderer and validator share this migration; it neither changes
the source document nor requires an operator bypass. Unknown versions fail.

The captured voice-storage projection of production source `8ad1d75cc9df`
and the real prebuild entry point are covered by
`backend/tests/unit/test_runtime_env_manifest_compat.py`.

The desktop renderer also accepts an optional secret resource descriptor using
the existing `env_var` / `default` syntax inside a `secrets` entry:

```yaml
SCREEN_VECTOR_STRIPE_API_KEY:
  env_var: SCREEN_VECTOR_STRIPE_READ_SECRET
  default: ''
  version: latest
```

The variable carries a non-secret Secret Manager name or
`projects/<project>/secrets/<name>` reference, never a payload or version suffix.
`render_backend_runtime_env.py` owns parsing, strict resource grammar, omission
of empty optional references and structured resource-reference state. Both literal and
dynamic resource names pass the same metadata-only grammar and credential-prefix
rejection before state/workflow output; runtime credential values are never read
by this renderer. Invalid references fail without echoing their contents. Valid
existing literal `secret` / `version` bindings retain their output. Desktop
resource references are not copied through `GITHUB_OUTPUT`: after the validation
step succeeds, the deploy action binds the same selected-environment variable
directly, omitting the entire assignment when it is empty. This dynamic
form is currently desktop-only; the managed Cloud Run services' validator still owns their literal
secret bindings. Mixed desktop ladder configuration requires the restricted
reference before output. With no incoming prices or reference, no new credential
is required. Explicit references are mounted even if price inputs are omitted.

The six Cloud Run price descriptors use existing `provisional: true` semantics:
unset inputs are omitted from deploy env and expected-state constraints so env
merge preserves existing commercial identity. There is no implicit clear operation.
Desktop workflows map `vars.DESKTOP_LADDER_V1_*_PRICE_ID` to the six runtime
`LADDER_V1_*_PRICE_ID` names and `vars.DESKTOP_SCREEN_VECTOR_STRIPE_READ_SECRET`
to the renderer reference above. They deliberately do not share main-dev bindings:
dev desktop reads production customer subscriptions. No realm or key permission
can be inferred from a reference name. Before deploying desktop with effective
mixed ladder configuration (including preserved values), an operator must ensure
the customer-realm subscription-read-only key and runtime access are separately
provisioned. Source-only rendering cannot inspect omitted live values; it enforces
the precondition on supplied prices and runtime authority remains unavailable if
mixed identity cannot be established. No actual resource is configured here.

## Firestore read train (#23797, 2026-10-27)

`FIRESTORE_READ_LEVERS` is a **replacement JSON literal**, not a patch. All
surfaces explicitly declare all 20 current keys. The guard flag-offs leave
`memory_list_index_window:0`,
`people_scan_dedupe:0`, and `finjob_candidate_queries:0`.

Monthly-total enablement and epoch deliberately remain split:

| Surface | `usage_month_total` | `FSR_USAGE_MONTH_TOTAL_EPOCH` |
| --- | --- | --- |
| Prod Cloud Run: backend-sync, backend-integration | 100 | `c2fs_20261026_r1` |
| Prod Cloud Run: backend, backend-sync-backfill | 0 | `c2fs_20261026_r1` |
| Base, both GKE charts/environments, jobs, desktop backend, all dev services | 0 | `v1` |

The Cloud Run overrides preserve the previously qualified serving scope. An off
reader never seeds a total, so the inactive `v1` declarations cannot overwrite
Cloud Run's ready epoch. This train does not qualify or enable additional
monthly-total readers. Never copy the Cloud Run literal into the base or charts.

The rollout lead ships **listen → pusher → Cloud Run** after the batch soak.
Read back each serving artifact and its complete literal/epoch before advancing.
Start the people 5% clock only once the last relevant service serves this config;
hold at least three hours and two clean evaluator ticks. Require no deletion or
privacy violations, speaker/transcript/Free-plan changes, 5xx or live-p95
regression. The lead then expands people to 100 with a complete-literal change
across the same surfaces, targeted by **2026-10-28 12:00Z**; report a failed gate
instead of expanding. Kill switch: change only `people_scan_dedupe` to 0 in every
applicable full literal, retaining all other keys and the monthly-total split.

Additional monthly-total reader scope is gated separately by
[the writer/epoch qualification contract](../../docs/monthly-usage-totals.md).
By **2026-10-28 12:00Z**, the lead must either attest every serving writer and
operator path, align new readers to `c2fs_20261026_r1` while still off, and admit
5%, or record the qualification blocker. After zero synthetic equivalence
mismatches, no accounting/Free allowance, contention, 5xx or p95 regressions for
two hours, the lead may expand that scope to 100 by **2026-10-29 12:00Z**.
Never enable a `v1` reader against the shared production totals. Rollback readers
with `usage_month_total:0` while leaving maintenance on; after any old writer,
keep readers off until all writers qualify and a new common epoch is selected.
Count net reads plus writes and seed scans in D+1 billing; this config alone
establishes no realized savings.

Batch worker control-loop settings are declared in the worker chart (including
explicit prod values): candidate fanout 16, parallel admission true, idle max 10s,
and `firestoreReadLevers: '{}'` outside prod. Prod uses backend-integration's
complete lever map except `usage_month_cache:0` and `usage_month_total:0`,
including `bpp_decision_cache:100` and `batch_timeliness_leader:100`, and enables held-poll
skip; its kill switch is setting `heldPollSkipEnabled` to false.
Projection finish backoff remains at its code default, off (SCA-2024).
The three control knobs
also have matching base declarations on serving batch hosts; pusher does not run
the batch scheduler/pump and the co-host contract classifies them listen-only.
The retired WQ12 privacy lever is absent from worker and serving-role literals.
Worker rollback: 64 / false / 2 / `{}` respectively. See
[the worker runbook](../../docs/batch-pipeline-worker.md) for the lead's soak gates.


## Generated read-lever evidence (M7)

`python3 backend/deploy/generate_read_lever_manifest.py` (from the repository
root) writes [`../firestore_read_levers_manifest.json`](../firestore_read_levers_manifest.json).
Use `--check` for freshness and offline validation. It calls the existing
`compose_runtime_env.compose_manifest()` in memory and reuses the compose YAML
loader/merge and runtime validator's literal extraction. It records each source's
explicit values, every inherited code default (including the implicit zero), and
the effective values; it is not live-state evidence or authority to change a rollout.
The existing backend unit selector runs these checks when any source changes.
`check_runtime_env_compose.sh` continues to verify the runtime artifact itself.

`firestore_read_lever_policy.lever_expiry` in `_base.yaml` is a surface-keyed
map: each partial `(surface, lever)` entry binds the exact `value` to an ISO UTC
`expires` date. Dates must be today through seven days out. Current approvals
end on 2026-11-17; this is an expiry deadline, not permission to expand the rollout.
Renewal requires an explicit reviewed source change. `base/` and `overlay/`
identify raw input paths; `runtime/<env>/` identifies both the generated and
in-memory composed surface; `chart/<env>/` includes Helm default inheritance;
`code/defaults` covers partial defaults even if an explicit literal overrides them.
No broad exception grants expiry coverage to another surface or percentage.

RESOLVED (SCA-2173, 2026-11-14): the prod worker and the prod Cloud Run
services pin `batch_timeliness_leader:100` and `lifecycle_record_pending_head:100`,
and set `privacy_checks_shadow:0`; `backend-sync-backfill` keeps its ec191a row 3
pins (`batch_timeliness_leader:0`, `privacy_checks_shadow:100`,
`lifecycle_record_pending_head:5`). `privacy_ttl60` remains 0. Integration, sync
and backend pin both `usage_month_cache` and `usage_month_total` to 100 (SCA-2222
Train 1); backfill and the worker keep both at 0. Every other lever and epoch is
unchanged.
These source values ride each surface's next train; no worker roll is requested.
The generator's `REVIEWED_INHERITANCE` constant preserves `{}` on default/dev
worker surfaces and enumerates the remaining unresolved inherited differences.
The pending 5% monthly-reader proposal is not a compose input; its refreshed
preimage now includes integration at 100%, while its proposed target remains 5%.

UNRESOLVED: README-vs-base triple: `memory_list_index_window`,
`people_scan_dedupe`, and `finjob_candidate_queries` are documented as 0 in the
historical train text above, while `_base.yaml` carries 100. Both source claims
are preserved pending a human ruling. The generator's `UNRESOLVED_NOTES` constant
supplies the manifest notes; neither evidence structure lives in `_base.yaml`,
whose `firestore_read_lever_policy` contains only `lever_expiry`. The offline guard
extracts each historical train claim and compares it with every base declaration.
It rejects missing or ambiguous claims, agreement with a stale UNRESOLVED note,
and a missing note while the sources disagree.
