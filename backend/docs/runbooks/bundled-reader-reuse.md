# Reusing bounded reader work

These independent kill switches ship on unless their value is `false`.
The lead owns merge and deployment. No account-data migration, client change,
new index, rate-limit reduction, or runtime-env literal change is required.

| Switch | Behavior | Rollback |
| --- | --- | --- |
| `OMI_CANONICAL_DEMAND_WINDOW_ENABLED` | Fetch canonical raw rows in page-sized batches, refilling rejected candidates through the existing keyset | Set `false` to restore previous batch sizing |
| `OMI_ROLLOUT_MEMBERSHIP_SHARED_CACHE_ENABLED` | Reuse encrypted membership observations across replicas within the original 60-second lease | Set `false` to restore per-process membership reads |
| `OMI_EXTERNAL_LIST_SINGLE_FLIGHT_ENABLED` | Coalesce simultaneous identical external-list cache misses after each request passes its authorization and validation gates | Set `false` to restore independent misses |

## Canonical lists

The previous raw reader requested 50 rows even for a small first page, while
adaptive batch sizing was coupled to the separate default-off indexed-query
rollout. Demand sizing now also works with the existing raw query. It changes
only the raw batch limit (the indexed path retains its existing 500-row cap): candidate policy, identity validation, lineage, device and
archive scope, historical merging, signed cursors and visible offset slicing
remain authoritative. Filtered rows advance the raw keyset and trigger refill.
After observing filtered candidates, raw scans resume their original 50-row
batches for the rest of the request, so sparse prefixes cannot multiply tiny RPCs.
The existing deadline and total-row caps remain in force. A page can still be
truncated under those caps; smaller RPCs are not a promise of identical timing
under concurrent mutation or provider failure.

## Shared cohorts

The existing cohort runtime already accepts a 60-second positive, negative and
error cache per process. The new shared layer stores only successful observations
(including a valid absent-document result). It never shares errors or malformed
documents. The key hashes the Firestore project, database and UID. Values use
AES-GCM with a dedicated HKDF key and bind that scope as associated data; Redis
does not receive a plaintext UID or membership payload.

Redis time anchors the expiry before the source read. Publication deducts the
read and serialization time. Every shared hit carries the remaining original
lease into the local runtime: a second replica cannot start another 60 seconds.
Expiry is the invalidation mechanism, preserving the existing maximum cohort
revocation delay. This is not immediate revocation and must not be extended to
fresh account-generation or privacy authority. Redis faults, missing encryption
configuration, unknown data-plane identity and corrupt ciphertext use the source
reader. Emulator reads bypass shared entries, so separate local stacks cannot
collide through a reused project/database/UID. No shared payload can extend the
existing process-cache error behavior.

Source reads now appear as `database.rollout_cohorts:_read_memberships` in the
caller probe. Compare the sum of old/new caller labels across the deployment,
and `firestore_cache_requests_total{namespace="rollout_membership_shared"}`
hit/miss/error outcomes.

## External lists

The original encrypted response cache remains authoritative for reuse eligibility,
scope and freshness. An identical miss may join one of at most 32 process-local
in-flight reads, with at most eight waiting followers globally. Excess followers
immediately use their original source path. Only sync route workers wait, for at most one second; async
callers and saturated/expired/timed-out followers use their own source read.
The route adapter releases waiters in `finally`, including validation errors and
exceptions. Only final successful, complete, size-bounded response bytes and the
existing pagination header allowlist are shared. Each follower keeps its own
request headers and rechecks any captured action-item writer version. There is
no additional response TTL or new rate limit. Authentication and grants run for
every request, including followers. Kill switches are checked again before reuse.

Measure `omi_external_list_cache_total{outcome="coalesced"}` against miss volume,
origin read rates, error/truncation rates and latency. Coalescing saves only
overlapping identical misses; the total developer-API read pool is not a savings
claim. Sequential requests outside the existing cache TTL still read the source.

## Excluded findings

Per lead ruling `06ff36` (2026-10-26), task-control caching is excluded: the
account generation is revocation authority, and polling intervals do not prove
that a stale value is equivalent. Migration helper streams have no measured
caller or route series in the investigated production windows. Their output
contract still requires complete migration inventories; no truncation or
unmeasured savings is introduced here.

## Verification and rollout

Use the focused backend unit shard through `backend/test.sh`. Fixtures compare
mixed-memory cursor/offset outputs with demand sizing on/off, prove filtered
prefix refill, model cross-replica cohort expiry/revocation, reject ciphertext
scope swaps, and exercise follower errors, writer races, deadlines, capacity and
event-loop bypass. These are local correctness and modeled-read checks.

After deployment, verify the release SHA of every traffic-serving revision and
the new cache outcomes, then compare a full post-deploy lookback with the prior
diurnal window. Keep 5xx, list truncation, latency and cohort admission outcomes
clean. Book savings only after source-read reductions are observed; a merged PR
or the size of the addressable read pool is not realized savings.
