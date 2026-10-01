# Runtime dependency security patch contract

Status: pre-registered inert P8 dependency patch. This unit updates no route,
wire contract, persistence behavior, authority, runtime selection,
infrastructure, credential, deployment, or production traffic.

## Observed audit state

On 2026-08-11, `bun audit --production` against the frozen lock reports eight
findings:

- seven direct Hono findings (six moderate, one low) because the exact
  `hono@4.12.26` pin is below the audit's fixed `4.12.34` floor; and
- one moderate uuid finding under
  `firebase-admin -> google-auth-library -> gcp-metadata -> gaxios -> uuid`.

The service imports Hono's core router, Bun adapter/websocket, and Hono types.
It does not currently import the specifically named CORS, JSX, memo, proxy, or
language middleware affected by several findings. Absence of a direct call is
not a reason to retain a vulnerable direct dependency in a production artifact.

## Bounded patch

Update only the direct Hono pin from exact `4.12.26` to exact `4.12.34`, the
minimum version that the current audit marks fixed, and regenerate the frozen
Bun lock. Do not take the current `4.13.x` minor in this security-only unit and
do not relax the exact-pin policy.

No source import, route, middleware, header, websocket, error, response,
startup, or shutdown behavior is intentionally changed. Any required source
change stops this patch and receives a separate pre-registration.

The uuid advisory is not fixed here. Do not force a semver-breaking transitive
override into Firebase Admin. The exact production artifact must later prove
that the optional storage chain is absent, upstream-fixed, or explicitly
accepted before the dependency closure can be called clean.

## Pre-registered verification

1. `package.json` and `bun.lock` resolve exactly one Hono version, `4.12.34`,
   and a frozen install changes no bytes.
2. Bun 1.3.14 and the installed Node 22 control can import Hono core; Bun can
   construct the actual service and Bun websocket adapter without binding a
   production port.
3. Focused app/service, route, websocket, and contract tests pass with no
   snapshot or byte changes.
4. The broad hermetic suite excluding the already occupied fixed-port test and
   the separately isolated epoch-fence suite passes; epoch-fence passes alone.
5. Contract TypeScript/tests, import-graph lint, and `git diff --check` pass.
6. `bun audit --production` contains no Hono finding and reports only the
   separately recorded Firebase Admin transitive uuid finding.
7. The evidence explicitly says this is a local dependency qualification, not
   a production Linux image, runtime selection, deployment, or clean-closure
   claim.
