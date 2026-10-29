# Architecture decision records

A ratified ruling that shapes code, a trip, a script or a flag lives here, one
page per decision. Scripts, trip registries and allowlists cite the ADR id; a
ruling with no ADR is not durable ([ADR 0005](0005-rulings-live-in-adrs.md)).

Every ADR carries a **Review by** date. On that date the owner renews it with
evidence, supersedes it, or retires it. A passed date is a finding to report, not
silent permission.

| ADR | Title | Status | Review by |
| --- | --- | --- | --- |
| [0001](0001-trip-floors-t2-t3-t5.md) | Batch ramp trip floors for T2, T3 and T5 | Accepted | 2026-11-01 |
| [0002](0002-unknown-vad-freezes.md) | Unknown VAD freezes the ramp; measured loss rolls back | Accepted | 2026-11-01 |
| [0003](0003-retire-flag-is-preview-preference.md) | The 25% live-STT retire flag is a preview preference shift | Accepted | 2026-11-01 |
| [0004](0004-sync-off-speaker-centroids.md) | Speaker evidence for sync-off batch units | Accepted | 2026-10-27 |
| [0005](0005-rulings-live-in-adrs.md) | Ratified rulings live in ADRs, not in scripts | Accepted | 2026-11-15 |
| [0006](0006-pipeline-flag-budget.md) | A CI flag budget for the pipeline env surface | Accepted | 2026-11-15 |

Related contracts: [batch record lane](../../utils/batch_pipeline/CONTRACT.md),
[deletion map](../deletion-map.md).

## Adding an ADR

Copy the template to `NNNN-short-slug.md` with the next number, keep it to one
page, and add a row above. Cite the source ruling (date, who, and the bus or PR
id), not a paraphrase from memory. Mark anything you could not verify
`UNVERIFIED`. To change a decision, add a new ADR that supersedes the old one and
set the old one's status to `Superseded by NNNN`; never rewrite history.

```markdown
# NNNN. Title

- Status: Proposed | Accepted | Superseded by NNNN | Retired
- Date: YYYY-MM-DD
- Deciders: who ratified it (role, and the ruling id)
- Owner: the lane or role that renews it
- Review by: YYYY-MM-DD (or the event that ends it, whichever is first)

## Context
What forced a decision, with evidence.

## Decision
The rule, stated so a script can implement it.

## Consequences
What gets easier, what gets harder, what must be watched.

## Implemented in
Paths, scripts and registries that encode the decision (each cites this ADR).
```
