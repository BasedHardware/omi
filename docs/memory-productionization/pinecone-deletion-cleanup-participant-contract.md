# Pinecone deletion-cleanup participant (P7 contract)

This is a route-free, activation-off participant contract. It does not contain
credentials, schedule work, choose policy, or call a live Pinecone index. A
qualified adapter may later inject the authenticated transport and an honest
per-account source-write fence.

## Fixed ownership coordinate

The registry is branded and immutable. It binds index `memories-backend` to
exactly these semantic roles and provider namespaces:

| role | namespace |
| --- | --- |
| `conversation_vectors` | `ns1` |
| `memory_vectors` | `ns2` |
| `screen_activity_vectors` | `ns3` |
| `action_item_vectors` | `ns4` |
| `transcript_chunk_vectors` | `ns_tchunks` |
| `x_post_vectors` | `ns_x` |
| `workstream_association_vectors` | `workstream-association-v1` |

Ownership is provider metadata `uid == account_id`, not an ID prefix. This
covers canonical hashed memory IDs and stale/legacy IDs in the same namespace.
The durable receipt key repeats `index_name`, semantic `role`, and
`namespace_name`; a receipt cannot be replayed under a different mapping.

## Scan and delete behavior

The transport seam uses the raw data-plane `POST /vectors/fetch_by_metadata`
and `POST /vectors/delete` operations with API version `2025-10` bound in every
request. Scans send the exact metadata filter. Pinecone returns a vector map;
the client requires every map key to equal its contained `id`, returns IDs only,
and discards values and metadata. Each page is at most 10,000
IDs and each namespace is bounded at 100,000 IDs. Empty, malformed, duplicate,
cross-coordinate, token-cycle, token-drift, over-limit, proxy, or accessor
responses fail closed. Receipts contain only count, sorted-ID-set hash, and
provider/receipt digests; errors never echo provider content.

Pinecone's filter delete has no deleted-count response. Therefore the
participant rescans immediately before every delete and records that exact
pre-delete count and sorted-ID-set hash. It deletes all seven namespaces and
stores one durable receipt per namespace. Replays always issue the delete
again, so a row resurrected after an earlier receipt is removed. A later
composite scan must observe zero remaining vectors.

## Fence and replay invariants

The injected fence must suppress or serialize all writes for the account and
provide source-generation and fence-receipt digests. The participant captures
dependency methods at construction, permits exactly one held callback, tracks
all pending provider work, drains it before release, and denies late calls.
Receipt recording is idempotent and conflict-checked by the repository; no
dead-letter or retry policy is selected here.

## Qualification boundary

The client intentionally does not claim Pinecone credentials, IAM, host
configuration, API-version availability, index topology, or production
deletion safety. The transport and fence adapters remain the qualification
seams. This slice has no route/default/activation integration and makes no
provider calls in tests.

Pinecone documents data operations as eventually consistent. A concrete
adapter must therefore keep the source-write fence valid while it performs a
bounded freshness-aware zero-rescan (or fail the cleanup attempt for retry);
an immediate nonzero observation is never reclassified as successful
deletion. The production qualification must also prove response byte/time
limits because `fetch_by_metadata` returns full provider records even though
this client retains IDs only.
