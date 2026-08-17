# Belief-native derived-group dream contract

Status: production-neutral planner plus consolidation-service admission; no
scheduler, model default, threshold, or activation (2026-08-14).

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

`apps/service/workers/derived-group-dream-contract.ts` names the
`derived_group_dream` work kind and input manifest. PostgreSQL sealed input
persistence, generic durable-work acceptance, atomic success (`0043`), and
sorted `CONSOLIDATION_WORK_KINDS` admit the kind to the consolidation-work
service lease set. `defineDerivedGroupDreamConsolidationAdapter` wraps the inert
planner as a consolidation adapter. There is still **no** polling worker,
scheduler, route, grant issuer, or model default.

## Deliberate production gap

No overnight scheduler, model pipeline, promotion adapter, worker activation,
or query product route is activated. Query recall remains dark until a live
composition actually runs honest grouped beliefs.
