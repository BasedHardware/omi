# Canonical memory rollout flags

This is the operator contract for enrolling a canonical-memory cohort. The
code-owned cohort is the product entitlement; runtime env values are readiness
declarations plus job-level kill switches. A runtime env value must never make
an unentitled user canonical.

## Minimal contract

| Control | Owner | Purpose |
| --- | --- | --- |
| `CANONICAL_MEMORY_USERS` in `backend/config/canonical_memory_cohort.py` | Code review | Entitles a UID to canonical memory, task intelligence, and Chat-first. Removing a UID is the product-path kill switch. |
| `MEMORY_MODE` | Request paths and maintenance job | Declares deployment readiness: `off` is the dark contract and `read` is the ready contract. Request routing does not read this env. The checked-in deploy contract uses only `off` and `read`; internal persisted rollout state still understands `shadow` and `write` for convergence and rollback. |
| `MEMORY_ENABLED_USERS` | Request paths and maintenance job | Duplicated, redacted rollout inventory used by deploy validation. In `read` mode it must be non-empty and identical on request paths and the maintenance job. It does not grant product entitlement or enumerate maintenance users. |
| `MEMORY_V3_GET_ENABLED` | Request paths | Declares that the v3 GET proof has passed. Request routing does not read this env; code entitlement plus persisted control/head/grant/projection state decide the route. The job carries the same value as readiness metadata but does not serve GET. |
| `MEMORY_CANONICAL_MAINTENANCE_ENABLED` | Maintenance job only | Master switch for canonical onboarding, guarded write enrollment, bounded legacy staging, normalization, TTL settlement, consolidation, and the projection outbox. It must be false on request-path services. Cloud Scheduler owns cadence. |
| `MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED` | Maintenance job only | Separately enables the bounded historical graph-enrichment page after a cohort user's staging checkpoint is read-ready. It defaults to false and must be enabled only with maintenance; it never grants entitlement or opens reads. |
| `MEMORY_CANONICAL_CONSOLIDATION_ENABLED` | Maintenance job only | Independently disables the L2 consolidation/model step while leaving required processing, TTL settlement, and outbox repair available. This is an incident/cost switch, not a rollout stage. |

`MEMORY_TYPESENSE_COLLECTION`, `TYPESENSE_HOST_PORT`, `PINECONE_INDEX_NAME`,
and their secrets are infrastructure bindings, not rollout gates. Cursor
secret/version/TTL settings are API integrity bindings, not enrollment flags.

The following names are retired and forbidden as runtime bindings:

- `MEMORY_CANONICAL_PROMOTION_CRON_ENABLED` — replaced by
  `MEMORY_CANONICAL_MAINTENANCE_ENABLED`.
- `MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS` — Cloud Scheduler owns the
  interval.
- `MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED` — no replacement; every
  enabled pass processes its deterministic bounded selection.

Deploy workflows retain these names only in `--remove-env-vars` so stale live
bindings are deleted. `validate-backend-runtime-env.py` rejects them if they
return in a manifest, rendered workflow, GKE values file, or observed Cloud Run
environment.

## Checked-in matrix

| Environment / surface | `MEMORY_MODE` | `MEMORY_ENABLED_USERS` | v3 GET | Maintenance | Consolidation |
| --- | --- | --- | --- | --- | --- |
| Dev request paths | `read` | Current dogfood UID list | `true` | `false` | Not bound |
| Dev maintenance job | `read` | Same dogfood UID list | `true` (metadata) | `true` | `true` |
| Prod request paths | `off` | Empty | `false` | `false` | Not bound |
| Prod maintenance job template | `off` | Empty | `false` | `false` | `true` (dormant) |

The prod template does not prove that a live Cloud Run Job exists. Verify live
resources separately before any approved production activation.

## Rollout order

1. **Enroll.** Approve the UID addition to `CANONICAL_MEMORY_USERS` and mirror
   it in `MEMORY_ENABLED_USERS` for the intended environment. Deploying the
   code cohort is the product-path selection; the env inventory does not keep
   that user dark.
2. **Backfill or stage.** Before deploying a new entitlement, run the
   single-user inventory with `--dry-run` and review counts. Once the code
   entitlement is deployed and the maintenance switch is on, the scheduled
   lifecycle creates only its exact inert control record, advances it to the
   guarded write stage, and resumes one bounded checkpointed staging page per
   run. At the terminal checkpoint it reconciles only its scheduler-owned write
   control to the independently trusted state-head generation, then permits
   graph enrichment for that user. It never opens read gates or grants default
   memory reads. If staging a
   non-cohort UID, use only the CLI's explicit one-user admin-override ceremony.
   Apply only the approved bucket and never delete legacy data.
3. **Start maintenance.** In a coordinated activation, deploy the code cohort
   and dedicated job, verify its rendered env and IAM/index dependencies, then
   set its mode declaration to `read` and maintenance to `true`. An entitled
   user whose persisted controls are not ready fails closed; plan this window.
4. **Turn reads on.** Advance the approved persisted control/head/grant and
   projection state, then set request-path readiness declarations to
   `MEMORY_MODE=read` and `MEMORY_V3_GET_ENABLED=true` for the same inventory.
   Run the bounded ST→LT proof, v3, search, tasks/What Matters, and grounding
   smokes.

For production, each step requires the production proof order and explicit go;
do not infer approval from the checked-in template.

## Rollback

1. Remove the UID from `CANONICAL_MEMORY_USERS` and redeploy. This restores the
   legacy product path even if a stale readiness declaration remains.
2. Revoke/disable the persisted canonical read and write controls through the
   approved rollback path, then set request-path `MEMORY_V3_GET_ENABLED=false`,
   `MEMORY_MODE=off`, and remove the UID from `MEMORY_ENABLED_USERS`.
3. After request paths are dark, set the job's maintenance switch false and its
   mode off. Preserve canonical and legacy records for diagnosis; rollback does
   not delete either store.

Validate the checked-in contract with:

```bash
python backend/scripts/validate-backend-runtime-env.py --env dev --check-workflows --check-rendered-cloud-run
python backend/scripts/validate-backend-runtime-env.py --env prod --check-workflows --check-rendered-cloud-run
```
