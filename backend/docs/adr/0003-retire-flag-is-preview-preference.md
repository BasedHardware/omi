# 0003. The 25% live-STT retire flag is a preview preference shift

- Status: Accepted
- Date: 2026-10-25
- Deciders: two-lane rollout lead, ruling `dce444`, under the product owner's approval #6
- Owner: live STT lane (watch and kill switch); the operator lane applies it with the 25% packet
- Review by: 2026-11-01, or before the retire percent goes above 25%

## Context

`BATCH_LIVE_STT_RETIRE_PERCENT` (registry row in `config/feature-flags.yaml`,
nested inside the batch cohort) changes which live STT leg serves a retire-cohort
session. Calling it "vendor retirement" overstated it: the vendor stays as
fallback, and the transcript of record is still the batch result.

## Decision

- At 25%, the retire flag is a **live-preview preference shift**: the Parakeet
  TDT window leg first, vendor fallback second. It is not a full vendor
  retirement. Every record, packet and dashboard calls it that.
- The transcript of record stays batch, covered by the post-admission T1/T2.
- Added watch (an alert, not a trip): for the retire cohort against control, live
  preview failure/empty rate and vendor-fallback rate.
- Kill switch: retire percent to 0 if retire-cohort failure/empty is more than
  2× control for 15 minutes.

## Consequences

- Vendor cost moves only as far as the preference shift does; claims of vendor
  savings from this flag need vendor usage data, not the flag value.
- A preview regression does not roll back batch; it flips the retire kill switch.
- A real retirement (no vendor fallback) needs a new ADR.

## Implemented in

`config/feature-flags.yaml` row `BATCH_LIVE_STT_RETIRE_PERCENT` (the policy guard,
`config/policy/guard.py:registry_violations`, requires its nested-cohort note);
the 25% ramp packet. UNVERIFIED: whether the 2× kill-switch watch is
automated or manual today.
