# Account lifecycle authentication fail-closed contract

Status: pre-registered production-neutral P7 correction. No production
identity provider, control source, route, grant, or deployment is added here.

## Problem

ADR-014 requires missing or stale lifecycle state to deny. The current service
port instead maps a missing account lifecycle row to `active`. The app-wide
authentication guard correctly admits only the literal `active` value, but the
adapter manufactures that value when it has no source evidence. A dropped,
uninitialized, reset, or lagging lifecycle projection can therefore reopen
every authenticated route for an account whose state is unknown.

This is independent of the deletion-cleanup scanner boundary. Inventory and
cleanup need a separately ratified deleted-account operator authority; the
ordinary application authentication path must remain closed for
`deletion_pending`, `deleted`, and missing lifecycle state.

## Contract

The application-facing lifecycle port returns one of:

- `active` only when the subordinate source has an explicit active row;
- `deletion_pending` or `deleted` when explicitly observed; or
- `null` when the source has no row.

The authentication guard admits only an explicit `active`. `null`,
`deletion_pending`, and `deleted` are indistinguishable authorization denials
at the route boundary. No downstream route, memory loader, write fence, model,
store mutation, or QA reset handler runs after that denial.

The in-memory local/QA composition remains usable by explicitly seeding the
configured owner account as active during service seeding. Reset removes every
lifecycle row; reseed then restores only the configured owner row. An unrelated
or unseeded account never inherits active state from absence.

Lifecycle remains a subordinate projection. This unit does not mint a control
observation, infer active state from an identity-provider token, weaken the
account-epoch fence, introduce a deleted-account operator capability, or
decide retention, disposition, recovery, RPO, or RTO.

## Compatibility and activation

This is a fail-closed correctness change, not a new policy class. Existing
local-service callers that construct stores explicitly must seed lifecycle
state for every account they expect to authenticate. The canonical service
factory owns the configured QA owner's seed. A future production adapter must
load lifecycle from the single account-control authority and return `null` for
missing, unreadable, or unverified state.

## Pre-registered tests

1. A fresh in-memory lifecycle store returns `null` for an unknown account.
2. Explicit active, deletion-pending, and deleted rows round-trip exactly;
   invalid states are refused.
3. A configured local-service owner is explicitly active after initial seed
   and after reseed.
4. Clearing the lifecycle source makes a still-valid token receive the same
   401 on every authenticated route as deletion-pending and deleted.
5. A missing lifecycle denial occurs before memory loading, route mutation,
   write-fence accounting, model/provider access, or QA reset side effects.
6. Reset clears unrelated lifecycle rows and reseed restores only the
   configured owner.
7. Existing route-wide deletion-pending/deleted denial, active-account flows,
   write fencing, authorization noninterference, and full platform tests remain
   green.
8. No runtime default, raw identifier, reason detail, lifecycle state, account
   epoch, or deletion epoch is disclosed in the denial response.
