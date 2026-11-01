# 0005. Ratified rulings live in ADRs, not in scripts

- Status: Accepted
- Date: 2026-10-25
- Deciders: product owner GO for the architecture-review items (2026-10-25 ~11:40Z, lead ruling `76d3e0`)
- Owner: infra (rollout tooling); every lane that encodes a ruling
- Review by: 2026-11-15 (end of the post-launch debt sprint)

## Context

The rulings that shape the transcription pipeline (the two-lane design, the
T1–T6 trip set, the 10-19 target architecture) lived in agent memory, a chat bus
and operator scripts. A script keeps enforcing a ruling after the ruling is
retired, and nobody reading the repo can see why a value is what it is.

Example, 2026-10-25: a train script still carried a step that set
`SYNC_LINEAGE_RESOLVE_ENABLED=false` on the integration service (a P31-era
ruling that had been retired). The lead's train applied it at 06:33Z, and
lineage resolution was off on the batch serving and recovery service for 7
minutes until an operator caught it and it was restored at 06:40Z. Batch was at
PERCENT=0, so no users were affected, but the next step was the 5% apply.

## Decision

- A ratified ruling that changes code, a trip, a threshold, a flag or an
  operator script is recorded as an ADR in this directory, with a review-by date.
- Scripts, trip registries (`trips.toml`), flag allowlists
  (`config/flag_budget.json`, `config/feature-flags.yaml`) and ramp packets
  cite the ADR id next to the value it fixes.
- A ruling with no ADR is not durable: it holds for the step it was given for,
  and a script may not re-apply it later.
- Retiring a ruling means superseding or retiring its ADR; the citing scripts
  are then found by grepping the id and changed in the same change set.

## Consequences

- One grep (`ADR-0001`) finds every place a decision is encoded.
- Writing a ruling takes one more step; bus rulings stay the fast path for a
  single ramp step.
- Existing scripts carry uncited rulings today. Backfilling citations is
  follow-up work for infra, starting with `trips.toml` (ADRs 0001, 0002).

## Implemented in

This directory; [ADR index](README.md). Enforcement is review-time today; a
checker that fails a registry row without an ADR citation is a possible follow-up.
