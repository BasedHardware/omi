# Native WAL handoff alignment sample

This measurement-only release classifies staged native Opus WAL against the
same record's durable live custody manifests. It emits fixed-vocabulary
aggregate count, byte and 48 kHz tick counters. Phone clock differences are
reported as counts in coarse signed buckets. The sampler never downloads the
live media body and neither logs nor exports packet digests, raw audio,
individual offsets or account and capture identifiers.

The window is off by default. Release can set
`RECORD_WAL_SAMPLE_START_EPOCH` on backend-sync to a UTC epoch divisible by
180, after recording a scoped go-ahead for a window covered by written
approval. Unset the value to stop early. Disable independently of
`RECORD_WAL_HANDOFF_ENABLED`. The sample
expires after 24 hours and does not accept or settle custody or start recovery.

Each candidate has a stable 1-in-1,000 selection by the existing server-derived
upload content identity. The first winning create in each absolute three-minute
slot is the only candidate allowed to run across all instances and revisions.
There are 480 claims per window. Each process attempts at most one create per
slot. Losing contender RPCs are separate from successful claims and point reads.
Restart and indeterminate create outcomes cannot reuse a committed slot.

There are at most 10 Firestore point reads per successful claim, 4,800 per
window, with SDK retries disabled and no scans. Read-only snapshot lifecycle
RPCs and create contenders are separate. Each attempt has up to 8 MiB of
staged WAL, 16 MiB of manifest bodies, bounded single-page object listings
and six possible pinned manifest GETs. The request wait and operation
deadlines are two seconds. There are no vendor requests.

Before a replacement window, verify a dark backend-sync revision at 100%
positive traffic with the future-capture clamp enabled. The sampler exports
four zero-initialized children with the actual Cloud Run revision. Query
`omi_record_wal_handoff_sample_attempts_total{outcome="claimed_slot"}`
and `omi_record_wal_handoff_sample_io_total` for `point_reads`,
`gcs_requests` and `remote_bytes`, all with the exact `revision` label and
backend-sync scrape scope. Require fresh finite zero samples for all four
before Release qualifies a window. Healthy targets alone cannot prove zero work.
Verify the exact activation revision too, including its sampler epoch and
clamp. Missing or stale samples, a reset, or a disappearing target that
obscures cumulative work cannot clear the guard. The I/O limits are 4,800 point reads, 6,720
GCS requests and 8,053,063,680 manifest bytes across at most 480 claims.
Scrapes observe the guard counters; the durable slot and request budgets
enforce the hard ceilings.

The sync scrape also retains `omi_pipeline_record_wait_answers_total` and
`omi_pipeline_record_wait_memo_hits_total` for the record-wait reason readback.
Use Cloud Monitoring request counts for the matched HTTP 503 and 503/(200+202)
readback.

The WAL sample counters distinguish accepted, refused and other replies; the
probe does not change the reply or bypass a coverage memo. Conversation-memo
refusals before staging fall outside this cohort. First-arrival slotting and
retries can weight the results. Report sample counts, slot misses, unreadable
files and attempts that did not finish. Read available durations separately
from bytes for unsupported files. Bracketed positions require exact packet
anchors on both sides, the same positioned stream, an unchanged closed
capture, a complete inventory and no evidence of alternate ownership. The
client upload's ordinal claims do not authenticate the unmatched packets.
These observations go into the distinct ambiguous_bracketed subset, counted
with other ambiguous audio. There is no proved-new fraction from this
sampler. Its observations have no recovery or client acknowledgment authority.
