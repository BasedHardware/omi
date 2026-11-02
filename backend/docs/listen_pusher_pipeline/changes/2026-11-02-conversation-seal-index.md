# Conversation seal index (dark)

The framed writer cohort also publishes deterministic per-source/part indexes
under the existing conversation `audio-outbox` prefix at the 16 MiB cap and
conversation close/disconnect. A generation-CAS conversation snapshot in
`seal.json` inlines part receipts, frame tables and known PCM projection paths.
Existing conversations seed a baseline inventory once when the index is created.
New frames first mark their writer open. A crashed writer remains open and
forces prefix discovery; another writer cannot close its tail. Old generations
need not survive replacement. The writer refreshes bucket metadata before
its first overwrite and uses generation CAS with versioning on or off.

Part receipts still pin media and manifest generations and plaintext SHA-256s;
their ACK precedes index publication. A failed index leaves its writer open,
without retracting an earlier part receipt. Indexes do not retire source WALs.
Snapshots are bounded at 16 MiB; exceeding the bound leaves prefix discovery
authoritative. No read cohort is admitted in this slice.

This writer is parked as draft #24410 until measurement justifies slice 4,
its only proposed consumer. There is no production index reader; the reported
residual is approximately $3.20–3.80/day. Framed-pack reader/receipt repairs
have moved to #24441 and must land before the framed percent moves from 0.
The index has no scheduled ramp or savings credit. Stop-PCM stays off. The lead
must justify the consumer and a fresh measurement packet before proposing this
writer for merge; no flag, deployment or existing object changes here.
