# Backend runtime manifest versions

Edit `_base.yaml` and the environment overlays, then regenerate
`backend/deploy/runtime_env.yaml` with `backend/deploy/compose_runtime_env.py`.

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
surfaces explicitly declare all 19 current keys. The three train changes are
`memory_list_index_window:0`, `batch_privacy_memoize:0`, and
`people_scan_dedupe:5`; `finjob_candidate_queries` stays at 5.

Monthly-total enablement and epoch deliberately remain split:

| Surface | `usage_month_total` | `FSR_USAGE_MONTH_TOTAL_EPOCH` |
| --- | --- | --- |
| Four prod Cloud Run services: backend, backend-sync, backend-sync-backfill, backend-integration | 100 | `c2fs_20261026_r1` |
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
