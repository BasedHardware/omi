# Listen attribution calibration statistics contract

This unit converts an exact blind Listen attribution artifact and its external
`owner | non_owner | unclear` labels into threshold-free calibration sufficient
statistics. It is offline, pure, deterministic, and route-free.

## Inputs and custody

The caller supplies one parsed paired cohort, its exact public sheet and hidden
key, one complete labels artifact, and every runtime-verified belief result named
by the cohort. The analyzer re-parses the portable artifacts, verifies all
sheet/key/label/cohort joins, verifies exact result placement, and revalidates the
normalized belief and calibration receipt. Portable artifact digests provide
self-consistency, not signatures; production use therefore requires artifacts
loaded from the authorized repositories and retained under trusted offline
custody.

## Frozen statistics

`owner` maps to 1,000,000 probability micros and `non_owner` maps to zero.
`unclear` contributes only to coverage counts and is excluded from binary error
and reliability bins. For each repeat and across all repeats, the report emits:

- owner, non-owner, unclear, and total labelled counts;
- exact baseline and candidate Brier numerators and denominators as decimal
  integer strings;
- ten fixed 100,000-micro reliability bins containing count, predicted-owner
  probability sum, and owner-truth count; and
- the paired candidate-minus-baseline Brier numerator.

Squared errors and sums use `bigint` internally. The portable report contains
only decimal strings and safe integers.

## Non-authority boundary

The report contains no transcript, account, result identifier, strategy
identifier, source coordinate, probability threshold, classification, winner,
significance claim, expression band, or deployment recommendation. It cannot
write a graph, mint identity authority, change subject tiers, select a product
phrase, promote a strategy, or activate a runtime. Those decisions require the
separate blind evidence and David-owned product/policy gates.
