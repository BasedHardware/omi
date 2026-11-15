# Exact native-record WAL custody, phase 1

The [native record WAL custody contract](../../listen_pusher_pipeline.mdx#native-record-wal-custody-handoff-phase-1)
replaces repeated strict PCM coverage refusals with an exact original-byte
handoff under the existing owner. Independently decoded Opus files and native
PCM cannot generally compare byte-for-byte, and phone WALs can include frames
never sent live. This phase keeps every submitted original durable and leaves
its processing obligation pending; it does not plan gaps or dispatch paid STT.

Bundle receipts and stable per-file receipt rows use the existing stage-qualified
intake collection, with explicit kinds. Each file row carries its pending
obligation and outbox wake atomically; `wal_pending_since` provides indexed
discovery. Ordinary job dispatch never consumes them.

One default-on admission switch, `RECORD_WAL_HANDOFF_ENABLED`, rolls back to
strict refusal for new bundles. Accepted receipts and their polling handles
survive rollback. Do not deploy a reader-incapable artifact while obligations
remain. Original objects use the existing private archive bucket's encryption,
create-only and tombstone discipline, plus generation/size/checksum/plaintext
verification. Account/protection erasure sweeps orphan originals; conversation
erasure discovers the dedicated prefix in each relevant bucket and the new bundle/file rows in the existing intake collection. These objects are excluded from the live inventory and
routine batch artifact cleanup.

Use a reader-first deployment. Before any handoff admission, set this one
admission switch off for the rollout and promote the receipt-capable artifact
to all sync/status traffic. Verify every active serving revision can read the
protocol. Then create an admission-on revision from the same artifact and ramp
its traffic against the receipt-capable admission-off base. Older artifacts
must never receive new polling handles; disabling admission does not teach an
old binary how to read them. Rollback shifts traffic to, or disables admission
on, a receipt-capable artifact while accepted obligations remain.

Before serving promotion, the release owner must validate private-bucket
lifecycle rules retain `record-wal/` originals while work is pending, then prove
mixed-version status, erasure, and 503 to 202 behavior with synthetic staging
capture. The implementing engineer supplies custody evidence; the quality lead
reviews it; the existing release owner controls traffic. Proposed traffic ramp:
1% for one complete 60-minute lookback, then 10%, 50%, 100%, each after another
clean 60-minute lookback, completed within 24 hours of the first promotion.
Stop expansion on any custody violation, unexpected provider reservation,
missing status, or increasing unresolved age beyond the approved phase-1 hold
window. Quality lead and release owner must agree that hold window before the
first promotion. No deploy or fleet measurement is part of this local change.

Phase 2 adds proven source-frame overlap/gap planning, original/in-flight
coverage seeding, same-owner interval reservations and projection, and terminal
status only after every original's obligation settles. Phase 1 improves custody
and upload status; it makes no claim of recovered transcript or paid deduplication.
