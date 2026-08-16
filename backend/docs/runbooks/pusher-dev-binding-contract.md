# Pusher dev binding contract

## Scope

This is a development-only reconciliation. It does not change the production
pusher chart, production runtime manifest, Secret Manager, or any live GKE
object.

`backend/deploy/runtime_env.yaml` owns the complete direct dev pusher binding
inventory: every `secretKeyRef` and `configMapKeyRef` in the rendered pusher
container. `backend/scripts/verify_pusher_config_references.py` compares that
inventory to the rendered chart before either dev pusher workflow runs. It then
checks only Kubernetes object existence and `.data` key names; it never reads or
prints ConfigMap or Secret values.

`TYPESENSE_HOST` is configuration from `dev-omi-backend-config`, consistent
with `config/deployment-setting-classification.json` and
`backend/scripts/deploy-backend-config.sh`. `TYPESENSE_API_KEY` and
`GOOGLE_CLIENT_SECRET` remain direct keys from `dev-omi-backend-secrets`.

## Historical Secret-to-ConfigMap transitions

Kubernetes strategically merges a Deployment's `containers[].env` entries by
name. When a historical named item used `secretKeyRef`, merely adding a
`configMapKeyRef` retains the old nested field and can leave an invalid
dual-source item. The dev source contract marks `REDIS_DB_HOST`,
`GOOGLE_CLIENT_ID`, and `TYPESENSE_HOST` as transitions. Their values retain
`secretKeyRef: null` so an ordinary Helm upgrade removes the historical Secret
source.

The focused regression test exercises that strategic merge for all three names
without a cluster. The preflight also checks every declared key before Helm
runs, preventing a later `CreateContainerConfigError` for an omitted direct
binding.

## Separate future production audit — read-only first

Do not copy this dev change to production mechanically. A future prod audit
must first, without reading values:

1. Inventory the live `prod-omi-pusher` Deployment and Helm release's direct
   `secretKeyRef`/`configMapKeyRef` names and keys.
2. Classify each source against the deployment-setting policy and the prod
   runtime ConfigMap publisher; explicitly distinguish public configuration
   from true credentials.
3. Compare the rendered prod chart with the live key names for
   `prod-omi-backend-config` and `prod-omi-backend-secrets` using metadata-only
   key listing.
4. For every confirmed Secret-to-ConfigMap migration, add and locally exercise
   an explicit `secretKeyRef: null` strategic-merge fixture before any reviewed
   production chart change or rollout.
