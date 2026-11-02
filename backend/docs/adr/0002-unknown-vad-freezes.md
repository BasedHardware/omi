# 0002. Unknown VAD freezes the ramp; measured loss rolls back

- Status: Accepted
- Date: 2026-10-25
- Deciders: two-lane rollout lead, ruling `2771ba` (classification), applied in `ded370` and corrected by `eff46b` (10:39Z rollback)
- Owner: batch ramp observer owner; the closed VAD receipt producer is the batch quality lane
- Review by: 2026-11-01, or when every `failed_held` unit carries a closed VAD receipt

## Context

T2 counts unrecovered *speech*. A `failed_held` unit whose VAD result was never
recorded has unknown speech content, but its audio is in custody and redrivable.
Treating unknown as lost would roll back on held, recoverable audio; treating it
as zero would hide real loss.

On 10-25 the observer reported 110.6 failed_held speech-seconds from six
`empty_asr` units with no VAD receipt. The lead first ruled it UNKNOWN → freeze
(`ded370`). That premise was wrong for the trip that fired: the same tick carried
a *measured* terminal-empty loss of 7.594s / 3,741.468s = 0.203%, above 0.2% with
the floor qualified. `eff46b` applied the rollback at 10:39Z (PERCENT=0 on all
four services, verified 10:46Z).

## Decision

- **Measured** speech loss (VAD-measured or terminal-empty) is T2: rollback,
  with the 120s single-unit bound, the 0.2% / 3,600s floor ([ADR 0001](0001-trip-floors-t2-t3-t5.md)) and T5.
- A `failed_held` unit **without a VAD receipt** is UNKNOWN: BLIND / FREEZE, not rollback.
- Two guards keep the hard bound: (1) unknown-VAD held audio above 5% of the
  speech denominator over 1h rolls back anyway; (2) every `failed_held` unit
  has a named redrive owner in the ramp packet.
- An unknown classification never cancels a measured trip in the same window.

## Consequences

- Held audio waiting for redrive no longer rolls the ramp back.
- The observer must report measured and unknown separately
  (`held_vad_unknown_units`, measured held VAD speech seconds).
- Producer gap: the closed VAD receipt on every held unit is still owed. Until
  it lands the 5% backstop is the only bound on unknowns.

## Implemented in

The batch ramp observer (`watch.py`, omi-workspace scratch; UNVERIFIED that the
classification is in `trips.toml`, which has no explicit unknown-VAD row today).
Moving the classification into the registry with an `ADR-0002` citation is a
follow-up for infra.
