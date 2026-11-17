# Remove same-call duplicate sync metadata GETs

The [durable projection recovery contract](../../listen_pusher_pipeline.mdx#durable-playback-projection-rebuild-debt)
retains decoded original coverage, privacy preflight and commit-time audio_files
CAS. Each attempt snapshots before its own fresh strict LIST, and re-reads live
media and manifest metadata. No new cache or flag remains; main's existing index
and process proof-cache behaviour are unchanged.

The only optimization passes metadata already fetched in this call chain to the
immediate read: validation supplies its media blob to decoding, and gapped
manifest listing supplies its manifest blob. Every download pins generation and
metageneration; hash, decrypt, frame and size checks remain. Strict recovery fails
closed on an in-flight object change. Non-strict discovery excludes only that
pack and continues.

The [operations runbook](../../runbooks/sync-gcs-operations.md) gives per-attempt
counts and a GMP-only query with a guarded denominator. Fresh framed proofs save
one GET, gapped proofs save three, but framed warm proof hits save zero. Under a
strict one-GET-per-pack-per-attempt threshold, recommend closing this PR. No
runtime saving is claimed. Rollback is a normal reviewed revert/release.
Tests isolate metageneration-only download races, live manifest reads on retry
and across calls, and peer-committed coverage. No wire/payload change, deploy,
production config change or merge is performed.
