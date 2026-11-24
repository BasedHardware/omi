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

## Mobile Home conversation compatibility

The existing `/v1/home/feed` card uses a bounded preview from the notes gist or
overview. The conversation list's discarded and deferred previews show the
spoken words. The Home list uses the same encrypted display codec for a separate
revision-bound receipt with owner speech, speech span, and a preview prefix
when needed. The list formatter continues to apply the existing 160-character
preview rule. Home requires explicit negative owner-speech evidence before moving
a background row to Daily Recap. Missing segments or evidence leave it visible.

With the switch on, only a Home request carrying
`X-Omi-Home-List-Transcript: 1` can use the Firestore projection. A compact row
omits `transcript_segments` and includes `home_list_transcript_evidence`.
Missing or stale receipts, older rows, corrected text, and sources whose
presentation or retention requires the transcript use the full reader.
A mixed page hydrates its legacy rows by document ID and requires the same
Firestore revision before returning them. A revision mismatch or a page with
no compatible rows uses the existing full page query. Storage advances and
opaque cursor scope remain based on the existing list scan, including the
full-page fallback. Detail fetches still hydrate the full transcript. Receipt
construction is limited to inline private transcripts, and locked rows keep
the existing redaction.

Published builds without this capability send the legacy wire:

| Platform | Evidence | List contract |
| --- | --- | --- |
| iOS | U.S. App Store lookup reported 1.0.597 on 2026-11-24. The tagged 1.0.577/1520 source at `e2924da5a762` uses transcript segments for both owner speech and previews. | Full |
| Android | The Nov 23 Release investigation records 1.0.573 production with 1.0.595 staged at 1% in its observation window. The 1.0.573/1502 and /1504 tags at `a98115af12f5` and the 1.0.577/1516 tag at `54584f3d7e2e` use transcript segments for both. | Full |
| Candidate iOS and Android builds | Build from source containing the Home capability and verify its exact version, build ID and serving revision in Release. | Eligible for a canary after verification |
| Other callers and unknown builds | No recognized capability. The [support policy](../../../contracts/client-compat/support-policy.json) has no enforced minimum build. | Full |

The public [App Store listing](https://apps.apple.com/us/app/omi-smart-meeting-notes/id6502156163)
does not identify the binary build. The public [Google Play listing](https://play.google.com/store/apps/details?id=com.friend.ios)
does not identify the production or staged build codes. Use App Store Connect
and Play Console receipts before graduating the rollout.

## Coordinator rollout

1. Apply the generated index manifest through the repository's schema workflow;
   require both new composites READY before enabling the switch.
2. Ship the backend with the switch unset. Verify the flag-off full response and
   use only a confirmed capability build for the 5% serving canary.
3. Compare list latency, 504/500 counts, truncation rate, and documents read for
   first pages, legacy offsets, and cursor pages on large accounts. Use
   `compact_rows` on the existing list meter to verify that the canary exercised
   projected reads. Record the deployed SHA and check legacy, owner-spoken,
   discarded, deferred and older rows on the serving revision.
4. Keep the global 100% gate and legacy-path retirement tied to supported-client
   coverage. Turning on the backend switch does not upgrade installed callers.
   Roll back by unsetting the switch.

This implementation provides hermetic query/route evidence, not production
latency or deployment acceptance. No production reads, writes, index creation,
remote Git operations, or deployment are required for its local verification.

## Default Home for v3 owners (SCA-4102)

The collection index for `discarded`, `status`, `home_list_visible`, and descending
`created_at` filters out raw recordings and hidden v3 windows before reading
conversation documents. The API still checks row visibility after the query.
The rollout is independent of `OMI_INDEXED_LIST_READS_ENABLED`.

1. Deploy the index and the backend writers with `OMI_HOME_VISIBILITY_INDEX_OWNERS`
   empty. Confirm the index is ready and all conversation writers have rolled.
2. From `backend/`, use the approved project and owner scope to plan a page:
   `PYTHONPATH=. python scripts/backfill_home_visibility_index.py --project PROJECT --uid OWNER > plan.json`.
   The command scans up to 1,000 documents in ID order, with a mask for the
   candidate bit and its two source flags. Publish the rows scanned, missing and
   mismatched counts, expected reads and writes, and retry ceiling before applying.
3. Apply an approved plan by adding `--apply plan.json` to the command and saving
   the output separately. Each transaction re-reads the current flags. If the
   page exceeds the reviewed read or write scope, generate a fresh plan. Resume
   planning with `--after NEXT_AFTER` until `next_after` is null. If interrupted,
   re-plan the same range before applying again.
4. Reconcile from the first page in dry-run mode. After every page reports zero
   missing or mismatched bits, add the owner to the comma-separated
   `OMI_HOME_VISIBILITY_INDEX_OWNERS` allowlist. Only clients that negotiate
   `X-Omi-Home-Page-Mode` can use the index. Use an updated mobile build for canary
   verification.
5. Compare ordered IDs and page boundaries with the legacy query. Check
   `conversation_list_read` for `indexed_home=True`, and confirm `docs` is close
   to `rows` on full 50-row first and cursor pages. Remove the owner from the
   allowlist to roll back. Indexed continuations then restart on page one.
