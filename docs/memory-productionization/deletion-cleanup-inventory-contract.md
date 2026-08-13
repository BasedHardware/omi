# Deletion cleanup inventory completeness contract

Status: implemented production-neutral P7 v2 contract. No scanner, persistence,
cleanup, deletion, export, or runtime composition is implemented here.

## Problem

The deletion-dominance planner currently understands a closed list of cleanup
surfaces and their remaining counts. A raw zero is not evidence: it can mean
“the scanner proved empty” or “the scanner was absent/failed.” Calling the
second case complete would leave resurrectable data while producing a clean
deletion receipt.

This unit makes zero honest. Cleanup eligibility may consume only a verified
inventory assembled from one exact receipt for every required surface.

## Fixed required surfaces

The versioned source set is:

- durable work;
- staged model/grounding results;
- authoritative memory ledger content, including evidence, claims, mentions,
  identities, authorizations, adjacency, liveness, and derivation history;
- isolated experiment results;
- product projections and payloads;
- search documents;
- vector embeddings;
- rebuildable groups/indexes;
- migration mappings/item-copy state;
- stranded new-generation product data; and
- externally inventoried objects.

Version 2 adds `authoritative_memory`; version 1 is not accepted because it
could report complete while the canonical ledger still retained user-derived
content. The terminal control tombstone and terminal export/replay receipts are not
cleanup surfaces and can never appear in this list. Adding or removing a
surface requires a new inventory contract version and re-verification.

## Source receipts

Every receipt is exact detached plain data bound to:

- inventory contract and scanner contract versions;
- opaque account id, terminal control revision, and deletion epoch;
- one required surface code;
- the scanner's exact source frontier digest;
- a source-specific authorization digest;
- a scan-fence state and receipt digest;
- remaining item count; and
- the digest of the exact remaining set, including the canonical empty set.

The future adapter must issue these receipts from named authorized scanners.
This pure core validates shape and closure; it cannot self-attest database,
object-store, VM/disk/token, or legacy-system truth.

## Verification

Receipts may arrive incrementally, but:

- duplicates, unknown surfaces, cross-account coordinates, wrong
  control/deletion epochs, or impossible receipt shapes fail structurally;
- every missing surface emits `source_missing` and no verified inventory;
- every non-held scan fence emits `source_fence_not_held` and no verified
  inventory;
- a zero count still requires a valid remaining-set digest and held fence; and
- only a complete held set produces one branded, frozen verified inventory.

The verified inventory contains the exact terminal coordinates, canonical
surface/count rows, and an aggregate digest covering all scanner/frontier/
authorization/fence/set receipts. The deletion planner accepts `null` or this
runtime-verified artifact only. For terminal cleanup, `null` becomes the closed
`cleanup_inventory_unverified` blocker; it never becomes eleven zeroes.

The runtime brand is a composition fence, not persistence authority. After a
process restart, stored receipts must be reloaded from the future authorized
repository and reverified to mint a new local artifact. Plain-object forgery or
JSON round-trip loses the brand and remains blocked.

## Fence semantics

All scan fences must be held while cleanup eligibility is computed. A future
executor must either perform deletion inside the same source fences or rescan
and mint a new inventory before claiming completion. A verified inventory never
opens product traffic and never grants scanner or deletion authority.

## Content safety and cost

Reports expose versions, counts, closed surface/blocker codes, and digests only;
they contain no account id, object id, path, memory, evidence, prompt, model
output, provider/database error, or free-form reason. Work is bounded by the
fixed eleven-source set and deterministic canonical ordering. Core reads no clock,
environment, filesystem, database, network, model, route, worker, or QA store.

## Human and runtime gates

David still decides disposition, retention, legal hold, recovery authority,
deletion objective, and RPO/RTO. Scanner receipts describe what remains; they do
not decide what may be disposed. Real adapters, source locks, deletion actions,
external-object inventory, roles, and infrastructure remain gated.

## Pre-registered tests

1. Exactly one held receipt for every fixed surface produces a verified
   inventory; order does not change its digest.
2. A missing source and a released fence remain distinct blockers and produce
   no verified inventory.
3. Every zero count still requires a remaining-set digest and source receipt.
4. Duplicate/unknown surfaces, cross-account, stale/future control or deletion
   epochs, swapped frontier/set/fence fields, and malformed receipts fail.
5. Changing count, remaining-set, frontier, authorization, scanner contract, or
   fence receipt changes the aggregate inventory digest.
6. Proxies, accessors, classes, extras, symbols, sparse/decorated arrays,
   unsafe counts, unbounded strings, and malformed digests are rejected without
   invoking hostile code.
7. The verified artifact and report are deeply frozen and detached; report
   bytes contain no account ids or item identifiers.
8. A forged or JSON-round-tripped inventory is rejected by the deletion
   planner.
9. A terminal plan with no verified inventory is blocked, even when every raw
   caller-supplied count would have been zero.
10. A verified inventory with remaining surfaces can be cleanup-ready only
    after the separately gated policy/export/restore prerequisites; a complete
    verified zero inventory can become complete under those same prerequisites.
