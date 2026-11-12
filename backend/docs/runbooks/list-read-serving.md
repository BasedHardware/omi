# Memory, task, and conversation list reads

## Decision and contract

Use an indexed **candidate** gate over existing required canonical fields, with
page-sized keyset batches. Do not create a second visibility authority or a
separately maintained list collection. The released row policy, identity checks,
device/archive scope, lineage resolution, historical suppression, and response
serialization remain authoritative (INV-MEM-1, INV-MEM-3, INV-MEM-5).

The default-off `OMI_INDEXED_LIST_READS_ENABLED` switch enables the candidate gate,
adaptive canonical batch sizing, and the main conversation list's slim field mask.
An unset/false switch restores the previous query builders and batch sizes.
Deadline enforcement and sibling-route budget coverage are correctness fixes and
remain enabled independently of this optimization switch.

Released canonical candidates are the sorted union of:

- Active, processed Short-term/Long-term rows whose source state is active **or missing**.
- When pending processing is requested: active, source-active, pending Short-term
  rows with `promotion.required == true`.

Each branch uses an explicit repository query spec and composite index. Merge at
most one bounded window from each branch by `updated_at DESC, __name__ ASC`, then
apply the unchanged row policy. Both queries resume from the same existing raw
keyset. Mutations moving an item between branches cannot duplicate its identity
within a window. Partial branches contribute only a prefix proven by every branch's
frontier; an unread branch cannot establish a complete prefix.

**Expiry is not a query exclusion.** Current released policy retains processed
Short-term rows after expiry pending adjudication. A pending expired row with
required processing also remains eligible. An expiry-only gate would silently
change visibility. Source `missing` is also readable under the existing policy;
source tombstones and purges are excluded. Absent required fields already fail
MemoryItem validation; optional missing promotion fields still admit processed rows.

Explicit Archive and temporal history/all views retain the existing raw query.
Archive can admit pending Archive rows without required processing, so it must
not use the default candidate gate. Ledger history keeps
its separate reader. The developer memory adapter and `_parity_memory_payload`
are unchanged. Existing signed `uml` tokens, JSON arrays, legacy visible offsets,
capability headers, and next-cursor/truncation rules remain in place. Legacy
`limit=5000` still receives the existing 500-row route cap; offsets retain their
existing 5000-row compatibility window and visible-row slicing.

## Read and write economics

For the measured 1,878 stored / 348 visible account, full raw enumeration has
5.40x amplification; 100 uniformly distributed visible rows would require about
540 raw reads. Holding 348 visible rows in a 2,600-row account raises that to
7.47x, or about 747 reads per 100 visible rows. A hidden prefix can be worse:
2,252 rejected candidates before 348 visible rows costs 2,352 raw downloads to
reach the first 100 visible rows.

The hermetic 2,600-row regression has 1,913 expired pending rows without required
processing, 339 tombstones, and 348 processed visible rows. Complete canonical
enumeration downloads 348 documents instead of 2,600 (86.6% fewer). A 100-row
canonical cursor page plus lookahead downloads 101 candidates; an empty pending
query adds Firestore's one-read minimum, for 102 document-read charges before
historical, authority, and lineage reads. Index-entry read charges, where
applicable, add one read per 1,000 index entries; confirm the actual plan with
Query Explain during rollout. These are document-read economics, not a claim
of complete request billing. See [Firestore pricing](https://firebase.google.com/docs/firestore/pricing). With both branches populated a window can download
up to twice its requested candidate count. Remaining review, archive, device,
malformed-payload, and lineage exclusions can still amplify candidate reads:
348 is fixture evidence, not a guarantee that every account costs exactly its
visible count. Processed expired rows are deliberately retained.

A new materialized `list_gate` would require complete mutation coverage, state
repair/backfill, and a stale-gate migration protocol while preserving account
availability. Existing required fields already express this safe coarse gate,
so that additional document-write and migration burden is unnecessary. The two
composites add up to two scalar index entries per document with the indexed
fields; Firestore maintains them on existing mutations. There are no additional
application document writes, projection writes, or scheduled expiry writes.
Index storage/fan-out still has a cost. Existing documents enter indexes through
Firestore's index build, without an application backfill prerequisite.

A separate canonical slim projection would add write synchronization and
validation risk while the released memory response still needs full content and
provenance. Cursor protocol changes would strand old clients. Budget tuning
alone would retain scan amplification and cannot stop SDK retries from extending
a per-attempt timeout. These are not the chosen solution.

## Sibling paths and deadlines

Developer API/MCP caching, offset bounds and route outcome measurement are documented in
[external list reads](external-list-reads.md); their default-on kill switches are independent of the
indexed-list rollout above.

Every budgeted Firestore stream, batch get, document get, and action-item count
RPC disables SDK retries; the supplied remaining timeout must bound the whole
attempt. Completed stream prefixes are retained when a deadline interrupts a
materialized read. Other provider failures retain their existing error behavior.

Developer action-item lists and both action-item ID modes now share the same
request-start deadline and document allowance as the other list routes. Their
existing bare-array/object bodies stay unchanged; partial results carry
`X-Omi-List-Truncated: true`. ID consumers must not treat a marked partial census
as proof of deletion. Unbudgeted export/deletion callers retain complete scans.

With the switch on, only the main conversation list requests a field projection
containing all Conversation response fields except transcript blobs/encoding,
plus the server metadata needed for visibility and user-title overrides. This
uses the existing list contract allowing unloaded transcript detail. It avoids
transcript decompression and correction-overlay point reads entirely. Detail,
export, MCP, and developer conversation reads keep their existing reader mode.
A malformed transcript cannot cause list response validation to fail in this mode;
other malformed response fields remain outside that guarantee.

## Coordinator rollout

1. Apply the generated index manifest through the repository's schema workflow;
   require both new composites READY before enabling the switch.
2. Ship the backend with the switch unset. Then enable the switch through the
   normal coordinated config rollout; no client upgrade or data backfill is needed.
3. Compare list latency, 504/500 counts, truncation rate, and documents read for
   first pages, legacy offsets, and cursor pages on large accounts. Verify the
   deployed release SHA and a user-facing canary separately from these local tests.
4. Roll back the optimization by unsetting the switch. Leave additive indexes
   in place; index deletion is neither necessary nor part of this change.

This implementation provides hermetic query/route evidence, not production
latency or deployment acceptance. No production reads, writes, index creation,
remote Git operations, or deployment are required for its local verification.
