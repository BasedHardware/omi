# Recover reset-clock sync uploads

V2 now accepts well-formed pre-2024 filename stamps under the default-on
`SYNC_EARLY_CAPTURE_CLAMP_ENABLED` kill switch. Malformed and implausibly future
stamps keep their existing rejection policy. No client change is required to
admit a retry; clients with the old nonworking Retry button still need an update.

The raw filename remains the content/dedupe identity and ordering source.
Stored early-clock spans pack in raw order, ending at server receipt time,
preserving audio duration while discarding untrustworthy wall-clock gaps (even
between different reset years). Early/normal clocks stay in separate units;
client time bounds from reset clocks do not drive temporal session lookup.
Coverage derivatives, VAD and split-unit starts inherit their original file's
clock policy, including repeated trimming across the 2024 cutoff. Full and late
cap holds retain their normalized offset into manifest dates, frozen recovery
pieces and lineage comparisons; raw timestamps remain the hold identity.
Their age remains untrusted and their work uses backfill
pacing. Both the batch and legacy sync paths consume the normalized clock.

Deploy through the backend and backend-sync Cloud Run train (including the
backfill worker). Update processing/recovery roles before admission services,
since old processors ignore receipt-clock metadata. Observe
`omi_sync_capture_time_total{outcome="accepted_early_clamped"}`
and the content-free `event=sync_capture_time` log. Roll back admission with
`SYNC_EARLY_CAPTURE_CLAMP_ENABLED=false`; retained raw filenames remain retryable.
Already admitted retained work keeps its frozen normalization after admission
is switched off. The flag-budget owner is the earlyclamp/two-lane transcription
lead, with review due 2026-11-17.

Contract: [sync admission](../../listen_pusher_pipeline.mdx).
