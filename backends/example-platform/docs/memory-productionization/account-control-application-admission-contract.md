# Single-control application admission contract

Status: pre-registered production-neutral P7 contract. No route, identity
provider, control adapter, grant, database, worker, or runtime composition is
implemented here.

## Problem

The canonical write fence already interprets the full subordinate
`AccountControlProjection`, but application authentication currently consumes
a separate QA lifecycle-only store. Lifecycle absence now fails closed, yet a
future production read can still drift from the write path by checking only
`active` while ignoring conflict, generation, account epoch, or destination
activation.

ADR-007, ADR-010, and ADR-014 define one shared order: control must be present
and non-conflicting; lifecycle must be active; authority must be on the new
generation; and the destination must have activated the exact account epoch.
Reads, writes, model work, leases, projection rebuild, migration, and outbox
cannot each reimplement that order independently.

## Decision

Add one pure internal decision over `AccountControlProjection | null`:

- missing projection denies as `control_state_absent`;
- poisoned/conflicting projection denies as `control_state_conflicting`;
- deletion-pending or deleted denies as `account_lifecycle_not_active` before
  generation or activation is considered;
- legacy, migrating, and rolled-back-stranded deny with their existing
  generation reason;
- new without an account epoch or matching destination activation denies as
  `control_state_not_activated`; and
- only active, non-conflicting, activated-new returns the exact account epoch.

The reason is internal and content-free. A caller decides its already-ratified
wire behavior. In particular, the write fence continues mapping lifecycle
denial to authorization and all other control-admission denials to its existing
availability class. No new HTTP status, response body, retry instruction, or
user-visible distinction is introduced.

The existing write fence must delegate its common control checks to this one
decision before it evaluates the request-carried epoch. This mechanically
prevents read/background consumers from being specified against logic that has
already drifted from writes.

## Scope and honesty

This decision does not authenticate a principal, authorize an application
grant, check entitlement, read a database, establish projection freshness,
mint control state, activate an epoch, or route a legacy account. A future
source adapter is responsible for translating missing, unreadable, or
unverified/stale source state into no admissible projection. The pure function
cannot infer staleness from a structurally current row with no external source
frontier.

No QA or production route is composed in this unit. The lifecycle-only QA
store remains explicit compatibility scaffolding until exact Firebase identity
and the single control projection can be wired together without disrupting the
test fixture service.

## Pre-registered tests

1. Exactly one state admits: active, non-conflicting, new generation, non-null
   account epoch, and matching destination activation.
2. Missing, conflict, all three non-new generations, null epoch, null
   activation, mismatched activation, deletion-pending, and deleted each return
   the exact closed reason.
3. Lifecycle dominates every generation and activation permutation.
4. Changing account id or unrelated control revision does not enter the
   account-free result; changing an admission coordinate changes the decision.
5. Output is frozen, deterministic, bounded, and contains no account id,
   deletion epoch, conflict detail, or free-form source data.
6. The refactored write fence remains byte-identical for every projection and
   request-epoch combination in its exhaustive matrix, including the sole
   `preserve_envelope` straggler case.
7. The core imports no service, driver, environment, clock, filesystem,
   database, network, model, route, worker, or QA store.
8. No decision can activate an epoch, clear conflict, resurrect lifecycle,
   authorize a grant, open a route, or grant deleted-account scanner authority.
