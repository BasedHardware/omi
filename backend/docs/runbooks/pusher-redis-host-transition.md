# Pusher `REDIS_DB_HOST` ConfigMap transition

## Status and root cause

PR #9758 made `REDIS_DB_HOST` explicit in the pusher `env` list with a
`configMapKeyRef`. Earlier chart values removed the historical explicit
`secretKeyRef` while introducing `envFrom` for the backend ConfigMap. A live
Deployment that still has the old named env item can therefore differ from the
Helm release manifest.

Kubernetes strategically merges `containers[].env` by `name` and merges the
nested `valueFrom` map by field. A regular upgrade that adds only
`configMapKeyRef` to the historical Secret-backed item preserves
`secretKeyRef`; API validation then rejects the resulting item because
`valueFrom` has both sources. This is a rollout-contract failure, not evidence
of an outage while the previous Deployment remains available.

The dev pusher values retain `secretKeyRef: null` next to the ConfigMap source.
That declaratively clears the legacy field in the strategic merge patch. A
fresh dev install has only the ConfigMap source; an upgrade from the historical
Secret-backed item clears that source before Deployment validation.
`REDIS_DB_PASSWORD` remains an explicit Secret key. The existing rolling
strategy (`maxUnavailable: 0`, `maxSurge: 1`) is unchanged. Production is not
changed by this dev repair; it requires its own reviewed transition after the
read-only gate below.

## Production readiness: read-only gate

Production has the same historical chart transition, so it may carry the same
legacy risk. Do not deploy merely because this repair merged. Before a future
prod pusher deployment, an operator must read-only verify all of the following
without reading Secret values:

1. Inspect the live `prod-omi-pusher` `REDIS_DB_HOST` env item's `valueFrom`
   object and the Helm release manifest to determine whether either still has
   the historical `secretKeyRef`.
2. Check only key presence for `REDIS_DB_HOST` in
   `prod-omi-backend-config` and `REDIS_DB_PASSWORD` in
   `prod-omi-backend-secrets`; do not print their values.
3. Render the repair revision and confirm the host is
   `configMapKeyRef: prod-omi-backend-config/REDIS_DB_HOST`, the legacy
   `secretKeyRef` is null, and the password is
   `secretKeyRef: prod-omi-backend-secrets/REDIS_DB_PASSWORD`.
4. Confirm the live Deployment still uses the normal rolling-update strategy
   before using the ordinary Helm upgrade. Do not use `--force` or a manual
   patch as a transition workaround.

The regression fixture in
`backend/tests/unit/test_verify_pusher_config_references.py` executes the
historical named-env strategic merge locally: the unguarded manifest produces
both sources, while this repair leaves only the ConfigMap source.
