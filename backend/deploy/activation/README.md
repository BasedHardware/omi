# Feature activation manifests

A manifest says what a feature's lever move needs from **live** serving state, and in what order the
services must move. It is checked, read-only, before a stage or flag move or before each service in the
order rolls. It is not a deploy source: env, queues and scheduler jobs keep their own writers
(`runtime_env/`, `ops/prod.yaml`, `scheduler/jobs.yaml`, the charts).

Why: the conversations-v3 TestFlight activation on 2026-11-17 needed backend Cloud Run, then llm-gateway,
then pusher, then listen, and nothing encoded it. A two-week-stale gateway without the v3 lanes, a pusher
without the Cloud Tasks binding listen has, an 8-day-old pusher image (version skew), and a missing queue
and scheduler jobs were all found in prod or by luck.

## Tools

| Piece | Path | Reads |
| --- | --- | --- |
| Manifest | `backend/deploy/activation/<feature>.yaml` | nothing (data) |
| Collector | `backend/scripts/activation_collect.py` | prod metadata, read-only; writes a state JSON |
| Checker | `backend/scripts/activation_check.py` | manifest + state JSON only (pure, offline) |
| Tests and fixtures | `backend/tests/unit/test_activation_manifest.py`, `backend/tests/unit/fixtures/activation/` | |

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod          # read-only identity; never a human login
git fetch origin                                        # the serving commits must be local for ancestry
python3 backend/scripts/activation_collect.py --manifest backend/deploy/activation/conversations-v3.yaml \
    --cluster prod-omi-gke --promoted-from-gcloud-config ~/.config/gcloud-agent/ro-dev --out /tmp/v3.json
python3 backend/scripts/activation_check.py --manifest backend/deploy/activation/conversations-v3.yaml \
    --state /tmp/v3.json [--before pusher] [--json]
```

Exit codes: `0` READY, `1` BLOCKED (a controlled requirement is missing), `2` UNKNOWN (nothing missing,
but a controlled requirement could not be read), `3` invalid manifest or state.

## Format (schema_version 1)

- `services.<name>`: `kind: cloud_run` (`service`) or `kind: gke` (`namespace`, `deployment`). `contains`
  lists full commit SHAs, each with a `why`; every serving unit must serve a source tree that has the
  commit as an ancestor (not an exact SHA). `promoted_from` names registries that hold a promoted digest's
  commit tag (prod pusher runs a dev-qualified digest).
- `order`: steps of services. `--before <service>` checks only requirements of services in earlier steps;
  that service and later ones are `deferred`. `--before activate` (the default) checks everything.
- `env[]`: `keys` (all must be set) or `any_of` (one must be set) on each of `runtimes`. `equal: true` also
  requires one value across the runtimes. `default` is the code default an absent key takes;
  `unset_values` are placeholders that mean "not configured"; `value` pins a required value.
- `gateway_lanes`: lane ids the named gateway service must serve.
- `queues[]`, `scheduler_jobs[]`: must exist and be `RUNNING` / `ENABLED` (or `state`). They are due at
  every step unless `before: <service>` defers them.
- `controlled: false` marks a requirement the activation does not own. It is reported, never changes the
  exit code. `not_checked[]` names requirements owned by another gate (always reported as unknown, with
  the owner).

## What the collector reads (and does not)

- Cloud Run: the revisions with `percent > 0` in `status.traffic`, never the service spec; each revision's
  application container env (only the keys a manifest names; Secret-backed keys as `name:key` refs).
- Serving identity is the image: the OCI `org.opencontainers.image.revision` label of the running digest,
  else its commit tag. `OMI_BACKEND_RELEASE_SHA` is recorded as `release_env` only: env merges never remove
  a value, so it can name a release the revision does not serve.
- GKE: the Deployment selector and the specs and image digests of its Running pods. Pods with the same
  image and environment evidence share a serving unit. Explicit literal `env` entries take precedence
  over `envFrom`. Required values supplied only by ConfigMaps or `envFrom` report unknown because their
  startup values are unavailable from the pod spec. Required Secret bindings are recorded as references.
  Optional ones report unknown.
- Gateway lanes: declared at the gateway's serving commit (`llm_gateway/config/lanes.yaml` plus the
  feature lanes of `generated_route_overrides.yaml`), read from local git.
- Cloud Tasks queues and Cloud Scheduler jobs: one `list` per location. Absent from a successful list is
  `missing`; a failed list (the read-only bot lacks `cloudtasks.queues.get`, and PERMISSION_DENIED also says
  "may not exist") is `unknown`.
- Every failed read becomes `unknown` in the checker, never `satisfied`.

## Release coordination for conversations-v3 on GKE

Production pusher and backend-listen need a configuration-only rollout before their serving pods can
provide complete startup evidence. Both charts accept a `conversationsV3StartupEnv` Helm values map
with exactly these string keys:

- `SYNC_TASKS_PROJECT`, `SYNC_TASKS_LOCATION`, `SYNC_TASKS_INVOKER_SA`
- `SYNC_TASKS_HANDLER_URL` and `CONVERSATIONS_V3_TASKS_URL`
- `CONVERSATIONS_V3_STAGE` and `CONVERSATIONS_V3`

Set both task URL keys explicitly. Use an empty string for an unused URL. The v3-specific URL takes
precedence when set. The charts place those values directly in each container's pod template, so the
release versions the actual bindings and the ReplicaSet retains them for that generation. The
collector can verify them using its existing pod read. The shared ConfigMap continues to serve
other keys. The values map takes only non-secret inputs.

Release must derive the values from the approved runtime configuration and existing task-target
deployment inputs, preserving the current effective stage, kill switch and task routing on the initial
migration. Record the reviewed values with the release and wire that values layer into the normal
production Helm paths for pusher and backend-listen so subsequent deploys and rollbacks retain the
correct version. Charts render the legacy bindings when the values layer is absent. Schedule the two
workload rollouts in the manifest's order. Before a lever move, rerun the read-only check after the
rollouts converge. Pods still using legacy ConfigMap references can keep the check UNKNOWN during
the rollout. A rollback to a legacy revision also restores that UNKNOWN behavior.

## Adding a manifest

Write `<feature>.yaml` from the feature's code (queue names, task routes, gateway features, env it reads),
add a correct-state and an incident-state fixture if one exists, and extend the tests. Keep `why` on each
requirement pointing at the code or incident that makes it necessary.
