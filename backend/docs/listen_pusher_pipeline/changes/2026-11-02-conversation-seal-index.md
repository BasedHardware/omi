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

The same `AUDIO_CUSTODY_FRAMED_PERCENT=0` holds writes dark. Lead owns the later
train after batch holds 100 through Monday peak: matched hour after the GKE
roll, 5% for at least 12 h, then 100%. Refuse missing raw-read counter, rising
window_tail would-drop/custody failures, playback/batch STT errors or a staged
WAL release without a receipt. Restart if batch percent or playback-on-demand
changes. Infracost posts writes/object creation per step and verifies next-day
settled billing. Index write credit is included in slice 4, not booked separately.
