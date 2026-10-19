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
