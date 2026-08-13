# Typesense account-deletion cleanup participant contract

Status: production-neutral and activation-off. No route, scheduler, provider
credential, environment lookup, or live Typesense call is composed here.

## Owned surface

The participant owns the complete `search_documents` cleanup surface for the
source-identified legacy `conversations` collection and the configured
canonical-memory collection (currently `canonical_memory_atoms`). Construction
requires the literal legacy collection plus one distinct, bounded canonical
collection and mints a process-local branded registry receipt. The participant
and HTTP client both require that receipt; the client rejects a role/collection
pair that does not exactly match it before transport. It is invalid to register
either collection through a second cleanup participant.

## Required authority and fence

Every scan and deletion runs inside an injected account-write fence. The
concrete fence adapter must suppress or serialize every producer that can write
either collection for the account, return a content-free source-generation and
fence receipt, await the callback, and drain operations started by the callback
before releasing. A no-op callback wrapper is not a fence and cannot be used in
production composition.

The participant also requires an injected durable per-collection receipt
repository. An exact receipt binds account, terminal control revision, deletion
epoch, cleanup operation, eligibility, collection registry, collection role,
result, affected count, and provider response digest. Existing receipts are
validated rather than trusted. Provider deletion is still reissued on replay;
this is deliberate so an incorrectly late legacy write cannot hide behind an
old receipt. The composite's held-fence zero-rescan is the final completion
proof.

## Inventory and disposition

The provider adapter receives only the exact account and fixed collection
coordinate. It owns correct Typesense `userId` filter escaping and must return
ID-only pages. The participant requests at most 250 IDs per page, rejects more
than 100,000 documents per collection, rejects gaps, duplicate IDs, drifting
totals, malformed pages, and cross-account or cross-collection results, and
hashes the sorted IDs. Document IDs and provider payloads never appear in the
inventory receipt, disposition receipt, or errors.

The route-free HTTP client implements the source-identified API shape without a
Typesense package dependency. It issues wildcard searches with the legacy or
canonical schema's known query fields, the exact account filter,
`include_fields=id`, no highlights or cache, and at most 250 hits. Deletion uses
the identical account filter and a bounded batch size. The client accepts an
already-authenticated JSON transport capability; it never accepts, reads, logs,
or returns an API key.

Deletion is an account-filter operation for both collections. Partial success
never produces a complete surface receipt. Retrying replays stored collection
receipts, reissues idempotent provider deletion, and remains incomplete until a
fresh scan of both collections is exactly zero while the source fence and outer
terminal-eligibility fence are still held.

## Bounded exclusions

This unit does not claim that a real legacy write fence, durable receipt store,
authenticated transport, provider credential, IAM binding, collection
existence, or live inventory has been qualified. It does not cover Pinecone,
object storage, or Firestore. Those remain separate participants because their
provider consistency and deletion semantics differ. Production activation
remains blocked until the authenticated transport and source fence are
qualified against the live registry.
