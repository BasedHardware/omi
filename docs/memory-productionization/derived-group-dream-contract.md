# Belief-native derived-group dream contract

Status: production-neutral pure planner plus durable-work preregistration; no
worker, model default, threshold, or activation (2026-08-13).

`core/consolidate/derived-group-dream.ts` is the belief-native alternative to
the rejected SQLite `drivers/sqlite/dream.ts` promotion path.

## Invariants

1. Every original claim revision id is retained in the outcome; dream never
   rewrites, collapses, or deletes originals.
2. Related facts merge only through rebuildable `ProductGroupProjection` rows.
3. People clustering emits probabilistic `claim_subject` attribution beliefs;
   it never mints binary identity authority, owner grants, or cross-account
   sharing.
4. Groups and beliefs bind an exact `input_frontier` and
   `projection_contract_digest` for deterministic rebuild.

## Durable-work slot

`apps/service/workers/derived-group-dream-contract.ts` names the future
`derived_group_dream` work kind and input manifest. It is **not** admitted to
`CONSOLIDATION_WORK_KINDS`, PostgreSQL acceptance, or any lease loop.

## Deliberate production gap

No overnight scheduler, model pipeline, promotion adapter, or query route is
activated. Query recall remains dark until honest grouped beliefs exist.
