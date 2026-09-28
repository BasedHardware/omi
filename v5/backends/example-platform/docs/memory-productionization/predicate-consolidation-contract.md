# Predicate identity and bounded consolidation contract

Status: P1 core implemented; P3 exact-input persistence qualified; activation remains blocked, 2026-08-12

## Scope

This unit selectively adapts the measured predicate and settlement mechanisms from
research commits `fc4ec6b7a9`, `34cc4ec93f`, `924ab2ef91`, and `924af4d915` into
production-neutral contracts. It is not a consolidation-quality experiment and it does
not promote any prompt, model, identity policy, subject tier, or product grouping rule.

The measured defects are structural:

- v7 contained 5,575 predicate objects for 2,722 normalized names; one
  `perform_action` relation was fragmented into 217 graph nodes because identity
  included window-local slot ordinals;
- the unbounded alignment call serialized 5,083 predicate revisions into roughly
  765K-801K characters and lost 13 batches/timeouts; the phase consumed 2,850.7s;
- cycle-global identity settlement recorded zero settled clusters on the real graph
  when one cycle also contained 133 retryable reprojection skips.

The zero-call gate for this unit is deterministic contract behavior. No corpus result,
recall improvement, entity-binding gain, or truth improvement is claimed until a later
copied-store replay and paired evaluation exists.

## Invariants frozen before implementation

### Predicate identity

1. Predicate identity is a versioned digest of the normalized relationship name alone.
   Per-window `slot_id` ordinals never enter predicate identity.
2. A predicate may have several immutable revisions. Each `name-v2` revision records one
   observed rendering and the sorted unique semantic argument roles for that occurrence
   in an explicit `observed_roles` field. Legacy `slot_ids` remain uninterpreted window
   ordinals until an expand/backfill/contract migration; a comment-only semantic change
   is forbidden.
3. Revision identity includes the owner and every varying revision field. A later
   observation with a different role set must coexist instead of conflicting with or
   overwriting the first, and two owners can never collide on one physical revision key.
4. Proposition identity does not change in this unit. The measured v7 artifact had zero
   duplicate canonical claims under either proposition key, and ADR-013 keeps product
   proposition identity separate from vocabulary alignment.
5. Existing identifiers are never rewritten in place. Queued claims with a historical
   name-plus-window-slot id persist an explicit `name-slots-v1` compatibility revision
   and are excluded/audited by v2 alignment. The new identity has an explicit version
   namespace; migration/backfill belongs to P2/P4 and must retain an attributable
   old-to-new mapping or derivation.
6. The persisted schema is discriminated: `name-v2` requires unique `observed_roles`
   and an empty legacy `slot_ids` tuple. Alignment additionally verifies the complete
   content-derived v2 revision coordinate before a row can reach the model.

### Predicate alignment

1. The alignment view contains one row per predicate id and unions semantic roles across
   its revisions. The model is never asked to alias a predicate to itself.
2. Rows are ordered by normalized name, then opaque id. Batches contain whole rows and
   are bounded by the exact prompt-shaped cost function, not storage JSON size.
3. Concurrency is bounded. Model latency may not affect result order, assertion ids, or
   settlement order.
4. A proposal is admissible only when both predicate ids occurred in the same successful
   batch and belong to one owner. The model cannot invent ids, cross owners, or alias a
   predicate to itself.
5. Each batch has a typed outcome: success or retryable error. An error is not an empty
   answer, abstention, rejection, or completed presentation, and one failed batch cannot
   discard another batch's assertions.
6. Settlement is scoped to the exact ordered batch question, its owner-local exact-batch
   vocabulary frontier, and the adjudication contract (model, strategy,
   prompt/schema/code versions). Only a successful batch is settleable. Adding vocabulary
   re-asks only new or deterministically regrouped batches; unchanged settled batches do
   not become an owner-wide rescan. A changed contract or batch question is fresh work.
7. Core returns content-safe codes and opaque coordinates; it does not log model text,
   read environment variables, persist state, or select a provider.
8. This selective port preserves the measured name-ordered, batch-local coverage; it is
   not an exhaustive all-pairs synonym search. Cross-batch candidate retrieval or an
   overlap pass was explicitly unmeasured in the research chain and is not silently
   invented here. Production activation remains blocked until P2 defines a bounded
   candidate/coverage job and copied-store evidence measures its recall and cost.

### Identity-cluster settlement

1. A settled cluster digest covers the adjudication contract, complete profiles, and
   current member binding state. Changing the model/prompt contract, cluster membership,
   claim evidence, or entity binding makes a new question.
2. Selection may skip a whole settled cluster but may never prune members from a selected
   cluster.
3. The core reports digest-to-mention membership for every successfully adjudicated
   cluster. A failed batch is retryable and contributes no settleable digest.
4. Settlement is decided per cluster. A cluster touched by a retryable downstream skip
   stays open; unrelated successfully adjudicated clusters may settle in the same cycle.
5. Partition settlement remains cycle-global and separate. Cluster settlement may not
   cause a partition with unfinished retryable work to be marked complete.

### Authority and product boundaries

- Predicate aliases are vocabulary assertions, never person-identity authority.
- No repaired or source-local mention gains producer identity, owner binding,
  `subject:owner`, or second-person rendering through this unit.
- Identity admissions, bystander privacy, `subject:*` policy, compose voice, and product
  grouping remain unchanged and retain their named David gates.
- SQLite may exercise the port as an offline/QA adapter. PostgreSQL durable jobs and
  settlement rows are P2/P3 authority and must preserve these exact outcome states.

## Acceptance tests

- same normalized name with different window slot ids yields one predicate id;
- different normalized names yield different ids;
- two role/rendering revisions coexist under one predicate id without immutable-row
  conflict, and replay is idempotent;
- alignment unions roles, orders by name, respects the prompt budget, and produces stable
  results under reversed model completion order;
- same-batch id validation rejects invented, self, and cross-owner proposals;
- a failed batch is retryable, does not settle, and does not erase successful sibling
  batches;
- a changed alignment contract or exact batch payload misses settlement;
- owner growth is incremental, while a crash after graph append but before settlement
  idempotently restores the same batch without duplicate assertions;
- malformed v2 rows and forged revision coordinates fail closed, and queued legacy
  predicate ids survive both cold-transition and dream-promotion replay;
- identity cluster settlement changes with contract or binding state, reports exact
  membership, and excludes only clusters touched by retryable skips;
- no source/environment/logging import enters `core/`, and the full import-graph and
  contract gates pass;
- existing grounded-formation identity fail-closed tests and the complete `bun test`
  suite remain green.

## Exit and later evidence

This P1 unit exits when the contracts and QA adapter behavior are committed with focused,
full-suite, import-graph, and independent safety review evidence. It does not check the
P1 corpus conservation box: C1-C3 and predicate counters require the first copied-store
replay produced by the P2/P3 vertical slice. The later replay must report distinct
predicate names/revisions, exact settled/open/error batch counts, alias yield, and
byte/version-stable replay under the same coordinates before any performance claim. It
must also pre-register and measure cross-batch candidate coverage before this QA adapter
can become a production consolidation default.
