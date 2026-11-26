# Private-sync inventory manifest body reuse

The Nov 15 Pusher rollout admitted gapped, unframed raw-live packs into the
playback inventory. Their frame offsets come from the writer's custody
manifest. A raw-pack commit invalidates the conversation's inventory, so the
next listing can read the same existing manifest bodies again before encoded
coverage removes entries from the playback projection.

The optimization applies to ordinary Pusher playback inventory. On a hit,
a live metadata lookup requires the listed generation and metageneration
before using the previously verified body. On a miss, the guarded body GET
from PR #25779 can seed the cache. Fresh
and strict inventory requests, source audio and durable receipt readback use
the live proof path. The switch `PRIVATE_SYNC_INVENTORY_MANIFEST_BODY_CACHE_ENABLED`
defaults on. Set it to `false` to restore a body GET for each manifest lookup.
Disabling the listed-manifest fast path also uses the ordinary live proof.

For SCA-3882, Release can set `PUSHER_INVENTORY_MANIFEST_LONG_TTL_ENABLED=true`
on Pusher after custody review. This extends the lifetime from 120 to 900
seconds under the same process-local 8 MiB budget. Set it to `false` for the
120-second control. Entries expire from insertion and enter the cache only
after media binding and gap-count validation. Fresh, strict and deadline-bound
reads bypass manifest body reuse.

Compare native private-sync `ReadObject` requests and `network_sent_bytes_count`
for the `ReadObject` method over matching workload windows. Use the
`playback_inventory` payload counter from PR #25779 to isolate the change once
it is serving. The counter covers shared inventory helpers. Each cache hit
avoids one payload GET and that response's bytes, with the live metadata GET
still required. Compare billed SKU `3C8A-99C5-F47B` across complete UTC days.

For the TTL comparison, match full UTC days, serving code and workload between
flag settings. Measure `omi_pusher_inventory_manifest_cache_events_total`
by `event` for hits, misses and byte-budget evictions, alongside Pusher memory,
CPU, list traffic, playback coverage and custody exclusions. The
`pusher_inventory_manifest` change label on the GCS read reuse counters gives
skipped payload GETs, encoded body bytes and replacement operations. Use native
GCS response-byte metrics for the wire comparison and report the difference
from billed bytes. At D+2, record settled private-sync North America transfer
GiB/day and dollars/day plus bucket ReadObject/day. Debit replacement and
fallback operations and any added compute. Count savings once with SCA-4225
and exclude the effect of the main roll.

## SCA-4225 operation-local reads

The controls below default on. Set the affected variable to `false` and
verify the previous request path on the serving revision.

| Runtime switch | Counter change label | Scope |
|---|---|---|
| `PRIVATE_SYNC_KNOWN_KEY_LIST_REUSE_ENABLED` | `known_key` | Verify the unique custody-manifest key from this operation's inventory before skipping a duplicate per-pack LIST. A stale key returns to discovery. |
| `PRIVATE_SYNC_REQUEST_READ_MEMO_ENABLED` | `manifest_memo`, `pack_memo`, `batch_pack_memo` | Keep up to 16 MiB of verified read data per memo. Preserve the live metadata, checksum, sample coverage and playback publication checks. |
| `BATCH_SOURCE_VERIFIED_METADATA_REUSE_ENABLED` | `source_metadata` | Reuse versioned source metadata from fresh raw inventory or an authenticated retained manifest. Legacy manifests load metadata normally. Only the digest-checked materializer retries a stale metadata precondition. |
| `BATCH_ARTIFACT_METADATA_REUSE_ENABLED` | `staging_metadata` | Reuse the already loaded generation and size proof for recovery result readback, with authorization and bounded decryption. |

Compare `omi_gcs_read_calls_avoided_total` with
`omi_gcs_read_replacement_calls_total` by change and method.
`omi_gcs_read_payload_bytes_avoided_total` counts observed object body bytes.
Use native GCS sent-byte series for LIST and metadata response bytes.
Compare per playback build or projection completion at matched workload and
serving revisions. At D+2 use complete billing days to check net Class A/B
requests and paid outbound bytes, and check for changes in storage precondition
errors, missing playback, raw decode or custody failures, and p95 latency.
Each avoided byte belongs to one savings estimate across SCA-4225 and SCA-3882.

Whole-pack reads still verify the full checksum and decode before slicing.
Range reads require an independently authenticated format.
