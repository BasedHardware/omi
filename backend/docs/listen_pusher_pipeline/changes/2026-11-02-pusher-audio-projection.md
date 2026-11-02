# Pusher: refresh live audio projections without per-flush prefix discovery

Owner: planscost. `PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED=0` restores per-flush
listing; default `1` enables this optimization. Contract: [live audio projection](../../listen_pusher_pipeline.mdx#live-audio-projection).

A 300-second debounce of the whole update is unsafe: it postpones the deleted
owner signal and makes speaker learning, playback and capture coverage consume
old audio. Instead, each flush still groups and persists `audio_files`, schedules
person-learning retries, and admits the conversation to completed identity
retries. Only discovery changes: a socket caches the full encoded inventory and
reads metadata for the exact paths returned by the successful upload. The same
parser, coverage grouping, source fingerprint and alias retention serve both
paths. No guessed duration, synthetic source identity or new persisted schema.

Full listing happens on the first flush, after 300 seconds measured from the
last full listing (appends never reset that clock), on a changed stored
projection or failed optimistic revision precondition, and on exact-metadata
read failure. Raw archive READ cohorts keep listing: pack overlays can subtract
and split encoded coverage. Mutable/spanless or non-batch sources, replays/equal clocks, missing immutable identities, cache capacity limits
(128 conversations / 2,048 total cached chunks per socket), missing upload paths and
new connections also retain full rebuilding. Two pods exchanging projection
updates invalidate each other's caches instead of overwriting a known newer
inventory. Full rebuilds capture the stored projection before LIST and fence the
write against that view, including first flush and conflict recovery. The
incremental update uses the existing Firestore document read. Each eligible full
rebuild adds one small projection snapshot read; no Firestore writes are saved.

Explicit recording close, conversation switch and socket disconnect rebuild even
when the final audio batch was already flushed. Close-time rebuild attempts precede the
record seal and inline-drain notification. Shutdown uses the same existing
tracked socket/drain lifecycle; abrupt process death cannot run cleanup. It does
not introduce a five-minute unprojected tail: every successful flush has already
projected its own exact uploaded objects. Existing durable raw-live media and
generation-pinned outbox manifests remain independently discoverable after a
crash; failed projection retries retain their existing custody/failure behavior.
Close-only failures retry twice; deterministic InvalidArgument is terminal and
other exhausted rediscovery failures report degraded raw recovery without
aborting the custody seal. Every successful flush already publishes its own
current audio; this additional listing is optional rediscovery, not a custody
barrier. Finalization is supplementary, not a proof: process_conversation skips recovery,
reprocess and sync-off cases and catches rebuild failures; sync pipeline rebuilds
only its assigned response conversations.

A false `update_conversation` result still latches deleted-conversation state on
every projected flush. Both upload workers honor it, including batches already
queued; subsequent raw custody windows also honor the gone-owner decision.
The underlying raw write, digest ledger, replay-reconcile listing,
`safety_wal_coverage`, record seal and reconcile/repair implementations are
unchanged. `audio_files` is a derived playback/coverage view, not a custody
receipt; coverage consumers still require fresh projection data, which is why
only prefix discovery is amortized.

Measurement: `omi_pusher_audio_file_projection_total{mode="full"|"incremental"}`
counts discovery choices. Compare its full fraction and bucket ListObjects per
successful flush before/after a roll, with close traffic, archive cohorts and
metadata Class B GETs included. The evidence ceiling is roughly 80% of 5.4M
lists/day, or $39/day gross at $9/M, before first/close rebuilds and fallback
cohorts. This is a ceiling, not booked savings. No Firestore savings are claimed.
Custody slice 4 already books $16–19/day for manifest-first GET: never add that
amount to this lane's modeled reduction. Measure this lane's incremental change
against whichever slice-4 state is actually serving, then book only that delta.

Rollback: set `PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED=0` and roll the pusher via
the normal release path. No data migration or cleanup is needed. This PR does
not merge, deploy, or change production configuration.
