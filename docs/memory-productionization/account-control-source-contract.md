# Coherent application account-control source contract

Status: pre-registered production-neutral P7 contract. No route, Firebase
adapter, grant lookup, PostgreSQL query, worker, or runtime composition is
implemented here.

## Problem

The shared application-admission decision now interprets the complete
`AccountControlProjection`, but the current local service still reads a
separate lifecycle-only QA store during token resolution and reads the control
projection again inside selected task/chat paths. That split is deliberate
compatibility scaffolding, not a production authorization design.

A production request must not combine lifecycle from one observation with
generation, epoch, activation, or conflict from another. It also cannot treat a
typed JavaScript object returned by a driver as structurally trusted, or treat
an unreadable/stale source as current authority.

## Decision

Add one asynchronous, read-only application source boundary. An injected
adapter returns exactly one of four closed source states for the requested
opaque account coordinate:

- `current` with one complete account-control projection;
- `absent` when no subordinate projection exists;
- `stale` when the adapter cannot prove the projection current against its
  authoritative source/freshness contract; or
- `unavailable` when current state cannot be read.

The boundary calls the source exactly once per inspection. It strictly parses
and detaches a `current` projection, rejects extras, accessors, proxies,
classes, malformed nested activation/conflict objects, and an account id that
does not exactly match the requested coordinate, then invokes the shared pure
application-admission decision.

The content-safe result is either:

- admitted, carrying only `account_epoch`, `control_revision`, and
  `destination_activation_revision`; or
- denied with one closed reason: the existing application-admission reasons,
  `control_source_stale`, `control_source_unavailable`, or
  `control_source_invalid`.

The result carries no account id, source row, conflict detail, deletion epoch,
free-form exception, or adapter metadata. A source throw/rejection is
`control_source_unavailable`; its exception is never copied into the result.
`absent` preserves `control_state_absent`. A malformed or cross-account
`current` result is invalid rather than absent.

This inspection is not an authorized context or a capability. It authenticates
no principal, checks no application credential/grant/entitlement, and grants no
repository, model, worker, migration, export, or cleanup access. A caller that
eventually emits positive bytes or performs an external effect must inspect
again at its already-required final fence; this unit does not claim a
long-lived snapshot remains current.

## Compatibility boundary

No current QA or product route switches to this source in this unit. Doing so
would deny the historical fixture service because its read routes intentionally
work before the separate QA control store is seeded. The lifecycle-only QA
source and writable projection store remain explicit compatibility fixtures
until a coherent exact identity/control composition replaces both.

The production source adapter remains blocked on the real PostgreSQL runtime
and the exact Firebase/application authorization composition. This contract
does not choose a Firebase library, PostgreSQL client, freshness interval,
deployment mode, or credential policy.

## Pre-registered tests

1. A current active, non-conflicting, activated-new projection admits and
   returns exactly the three owner-free coordinates.
2. `absent`, `stale`, `unavailable`, a source throw, and a rejected promise each
   deny with their exact closed reason after one source invocation.
3. Current conflict, every non-new generation, unactivated new, pending
   deletion, and deleted preserve the shared admission reason.
4. Cross-account, extra-key, accessor, proxy, class, malformed activation,
   malformed conflict, unsafe counter, and invalid lifecycle/deletion pairs are
   `control_source_invalid` without raw detail.
5. Input and nested-object mutation after inspection cannot change the frozen
   result; denied results contain no source or account bytes.
6. The source is asynchronous and inspected once. No clock, environment,
   filesystem, network, database, model, route, credential, grant, entitlement,
   or mutable global state enters the boundary.
7. No source result can activate an epoch, clear a conflict, resurrect
   lifecycle, construct `AuthorizedContext`, or grant deleted-account scanner
   authority.
