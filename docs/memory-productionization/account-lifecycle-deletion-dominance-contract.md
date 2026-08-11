# Account lifecycle and deletion-dominance planner contract

Status: pre-registered production-neutral P7 contract. No persistent action,
runtime composition, policy value, or authority transition is implemented here.

## Purpose and authority boundary

This slice turns the accepted structure in backend ADR-014 into a total, pure
plan that later adapters can execute and prove. It consumes the existing
`AccountControlProjection`, which is a subordinate observation of the legacy
control authority. It never mints an account id, lifecycle state, deletion
epoch, control revision, destination activation, tombstone, export receipt, or
retention decision.

The only legal lifecycle is:

```text
active -> deletion_pending -> deleted
```

Lifecycle dominates generation. Missing, conflicted, malformed, stale, or
restore-incomplete control state is unavailable and denies. The QA-local
`apps/service/auth/account-lifecycle.ts` behavior that treats a missing row as
active is explicitly outside this contract and cannot be used as production
authority.

## Inputs

The planner accepts exact detached plain data containing:

- one validated subordinate account-control projection, or `null` when the
  projection is missing;
- the observed terminal-control tombstone, if any;
- the immutable terminal-deletion export receipt, if any;
- the latest restore-replay checkpoint, if the account is being recovered;
- a runtime-verified complete-source inventory produced by the separately
  pre-registered deletion cleanup inventory contract, or `null`; and
- only the approval coordinates of retention/disposition and recovery-objective
  policy, never policy values inferred by the planner.

Every present artifact is account-, control-revision-, lifecycle-, and
deletion-epoch-bound. Cross-account, future-revision, stale-epoch, mismatched,
duplicate, decorated, accessor-bearing, proxy, sparse, non-finite, or
unexpected input fails closed before a plan is returned.

## Closed modes

- `control_unavailable`: the control projection is missing or conflicted. No
  destination traffic or cleanup execution may proceed.
- `legacy_active`: lifecycle is active and legacy is authoritative.
- `migration_fenced`: lifecycle is active and generation is migrating.
- `destination_fenced`: lifecycle is active and generation is new but the
  exact epoch is not activated.
- `destination_active`: lifecycle is active, generation is new, and the exact
  observed epoch is activated.
- `stranded_fenced`: lifecycle is active but generation is
  `rolled_back_stranded`.
- `deletion_pending`: deletion has begun. Reads, writes, sessions,
  credentials, new jobs, model work, leases, outbox effects, migration resume,
  projection rebuild, and index rebuild are fenced regardless of generation.
  Irreversible disposal does not begin from this state.
- `deleted_blocked`: terminal control is present, but tombstone replay,
  terminal export, verified cleanup inventory, retention/disposition approval,
  recovery-objective approval, or artifact consistency is incomplete.
- `deleted_cleanup_ready`: terminal tombstone, immutable export receipt, and
  complete held-fence inventory are exact, restore replay is safe, and the
  required human-approved policy coordinates are present. This is eligibility
  only; the pure planner performs no deletion.
- `deleted_complete`: the same terminal prerequisites hold and the supplied
  inventory reports no remaining disposable surfaces.

## Dominance and restore rules

1. `deletion_pending` and `deleted` always clear destination activation in the
   plan and deny every data-plane and background-work surface.
2. Cleanup never treats a missing control row as active and never uses product
   row status as lifecycle authority.
3. A terminal account tombstone is retained. It is the redacted terminal state
   of the one control record, not a second deletion authority.
4. A restored generation is not traffic-eligible until a checkpoint proves the
   complete tombstone set was replayed through at least this account's deletion
   epoch. A checkpoint from another account, an earlier epoch, or an earlier
   control revision is insufficient.
5. A restore-shaped `deleted -> active` observation remains illegal in
   `account-control.ts`; the planner cannot heal or reinterpret it.
6. Migration item tombstones are consulted on every resumed copy. Account
   lifecycle does not replace item-level tombstones, and item tombstones do not
   replace account lifecycle.

## Terminal export and cleanup boundary

Exactly one immutable terminal-deletion export record is required for the
exact `(account_id, deletion_epoch)` transition. It carries the terminal
control revision, transition time, generation, stranded-data indicator,
contract version, and content digest. A later adapter may mark cleanup eligible
only after it proves that exact record is durable in the retention-locked sink.

The planner enumerates closed cleanup surfaces instead of executing them:

- durable work payloads and leases;
- staged model/grounding results and isolated experiment results;
- product projections and payloads;
- search documents, vector embeddings, and rebuildable groups/indexes;
- migration mappings and item-copy state, subject to the approved disposition;
- stranded new-generation product data; and
- external objects recorded by a complete per-account inventory.

Raw counts are never accepted. The inventory verifier requires one
frontier/authorization/fence/set-bound scanner receipt for every fixed surface,
including an explicit receipt for a zero count. A missing or forged inventory
adds `cleanup_inventory_unverified`; it never becomes an empty inventory.

Append-only ledger history, legal-hold behavior, disclosure copies, support
recovery data, and the exact fate of each listed surface are not decided by
this planner. The output reports policy-blocked cleanup until a caller supplies
separately ratified, versioned approval coordinates. It never invents default
retention or disposal.

## Output and content safety

The frozen output contains only the contract version, closed mode, explicit
lifecycle-fence booleans,
bounded counts, closed obligation/surface codes, exact non-content coordinates,
and content digests. It contains no transcript, memory, prompt, answer, model
output, evidence excerpt, user-facing account state, provider error, SQL, path,
or free-form reason. A `false` fence means only that lifecycle does not block
that surface; it never grants application authority.

The plan is deterministic and byte-stable for the same detached input. It does
not read the clock, environment, filesystem, database, network, or model.

## Human and runtime gates

David still decides retention duration, disposition by surface, legal basis,
disclosure copy, legal-hold precedence, recovery authority, stranded-data
retention, selective restore ownership, and RPO/RTO. A `ratified` policy input
means only that an external authorized composition supplied a bounded version
coordinate; this core does not validate the substance of the policy.

No database client, role grant, route, worker, infrastructure, export sink,
restore, delete, purge, credential operation, or production default lands in
this slice. Real execution requires the supported PostgreSQL/runtime decision,
named-operation repositories, crash/replay tests, retention-locked export sink,
restore drills, and David's data-disposition and RPO/RTO approvals.

## Pre-registered acceptance tests

1. Missing and conflicted projections deny all activity and cannot become an
   empty no-op plan.
2. Active legacy, migrating, exact activated new, unactivated new, and stranded
   generations produce their distinct closed modes.
3. Lifecycle dominates generation and activation for both
   `deletion_pending` and `deleted`.
4. A terminal lifecycle without an exact deletion epoch, matching tombstone,
   and matching export receipt cannot become cleanup-ready.
5. Restore replay from another account, an earlier deletion epoch, or an older
   control revision remains blocked; exact-or-newer replay is accepted.
6. Stranded data is included in terminal cleanup inventory regardless of the
   current generation.
7. Missing/unverified inventory and unratified retention/disposition or
   recovery objectives block irreversible cleanup even when every caller would
   otherwise supply zero.
8. Terminal tombstone retention is always an obligation and never a disposable
   surface.
9. Cross-account and mismatched control/deletion coordinates, unexpected keys,
   accessors, proxies, forged/JSON-round-tripped inventory capabilities, and
   unbounded strings fail closed. Receipt-level sparse/decorated arrays, unsafe
   counts, and duplicate surface codes are rejected by the inventory contract.
10. Input mutation after planning cannot change the frozen output; equal input
    produces equal canonical output.
11. The core has no environment, filesystem, network, database, model, route,
    or QA lifecycle-store dependency.
