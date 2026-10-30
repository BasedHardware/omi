# Batch admission percentage survives deploys

The admission source of truth is the existing Firestore control document
`rollout_cohorts/_ramp`, field `envs.prod.percents.batch-pipeline` (or the
corresponding environment). `database/rollout_cohorts.py` validates it and
revision-checks writes with atomic history. `utils/rollout/runtime_percent.py`
caches it for 30 seconds, bounds reads to one second without SDK retries, and
keeps the last good value on errors. Cold reads with no usable document use
`BATCH_PIPELINE_PERCENT`, defaulting to zero. Explicit policy replay flags stay
hermetic. The existing `BATCH_PIPELINE_ENABLED` master switch still applies.

`utils/rollout_cohorts.py` warms the percentage and membership caches before
admission, including HTTP worker preloads and async listen/sync warmups. Async
warmup shares a 1.25-second budget and never blocks the event loop. An unavailable
read can still use the documented fallback after failure is confirmed. While a
cold read is pending, the effective percentage stays at zero; a stale env
fallback cannot admit traffic before the remote value arrives.

Deploy manifests and listen charts omit `BATCH_PIPELINE_PERCENT`. Cloud Run's
merge update preserves any old env value solely as a fallback. A fresh install
uses the code's zero default. Neither a deploy nor its post-deploy env restore
is a ramp operation. Do not add this key back to rendered deployment config.

Allowlist membership is already independent runtime config:
`rollout_cohorts/{uid}.cohorts.prod.batch-pipeline`, read through the bounded
60-second membership cache. Use `backend/scripts/rollout_cohort.py` and the
[cohort migration runbook](rollout-cohorts.md); do not move or union memberships
as part of seeding a percentage. Explicit stored denials beat retained env
fallbacks. A percentage rollback does not revoke separately granted members.
The cohort migration verifier validates `_ramp`, `stt-cap-dispatch`, and
`held-content` control documents separately and retains its full member-inventory
bound after seeding.

## One-time migration (rollout lead)

The code change does not write production or enable a ramp. The brief's intended
seed is **0%**. Verify the current effective percentage on every traffic-serving
artifact and read the existing document before applying that seed; historical
ladder comments are not live evidence. Preserve unrelated percents, environments,
membership and locks. In particular, do not lower `first-summary` from its
existing quality floor. No new credential or collection setup is required.

Use the existing `backend/scripts/rollout/ramp_set.py`. With the appropriate
read-only GCP tier, inspect `--env prod --show`. For the lead's authorized write,
select `prod-operator`, then dry-run:

```bash
backend/.venv/bin/python backend/scripts/rollout/ramp_set.py \
  --env prod --percent batch-pipeline=0 --expected-revision <observed-revision> \
  --actor lead --reason seed
```

Review the plan, then add `--apply` to perform the CAS write. If a populated
entry already exists, follow the tool's operator-lock protocol first; never
clear someone else's lock or retry a stale revision blindly. Read back with
`--show`. This lane performs no seed or other production write.

## Controller, train and guard cutover

There are two controllers: public `backend/scripts/rollout/ramp_controller.py`
already writes this document; the workspace `infra/rollout/bin/ramp_controller.py`
prepares external operator packets which still edit Cloud Run env. Retain the
approved controller's authority, attribution, hold and epoch checks while moving
its final write to `write_ramp`: expected revision, actor, reason, and gate verdict
must be recorded together with history. Use the existing public writer instead
of raw Firestore updates. All rollback writers must use the same document too.

Before any positive remote ramp, the lead must migrate and qualify these
workspace-owned tools together (outside this public PR):

| Tool | Required change |
| --- | --- |
| `infra/rollout/bin/ramp_apply.py`, ladder operator packets | Replace percent env/traffic edits with a guarded remote CAS write. Keep unrelated service settings under their existing owners. |
| `infra/rollout/ops_env.py`, `bin/train.sh` | Stop saving/restoring the percentage as ramp intent. A train never writes `_ramp`. |
| `serving_revision.py`, controller/observer, `paired_gate.py`, ladder C | Compare effective runtime percent and config revision; env entries alone cannot prove apply or rollback. Preserve serving-artifact and epoch checks. |
| External rollback/paired packets | Change the remote percentage, retain paired mobile ordering and verify the runtime readback. |

The public in-cluster guard (`charts/incluster-guards/files/batch_guard.py`)
also rolls back **env only**, and its snapshot requires an env entry. Its
checked-in release is disabled pending separate qualification. It cannot be
activated or relied on after this cutover without a reviewed remote rollback
path and the separately approved access it needs. Verify its installed state;
do not infer it from Git. Preserve an effective safety owner throughout migration.

After each config write, wait at least the cache TTL plus the bounded read,
then verify effective percentage/config revision in the serving processes.
`omi_runtime_percent{name="batch-pipeline"}` reports the cached remote value;
`omi_runtime_percent_source` and `omi_runtime_percent_read_error_seconds` identify
fallback/LKG and read outages. A document read alone proves intent, not runtime
acceptance. Check every receiving artifact's release identity and a new admission
metric or log; repeat after a deploy and require the effective percentage to stay
unchanged. A stale or unknown runtime readback holds expansion.

## Rollback

Revert the PR to restore manifest defaults and the previous warmup behavior;
the existing env fallback still works when no remote percentage is usable.
Keep a verified private fallback snapshot through migration. Remote config
already wins in the previous backend too, so an env-only rollback **cannot**
override a seeded document. To stop new percentage admission, the authorized
operator must CAS-write the remote value to zero and verify it after the TTL
(or use the existing master kill switch). Restore verified fallback env when
rolling back to an artifact that lacks the remote reader. Already admitted
obligations drain under their persisted policies.
