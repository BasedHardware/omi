# Pusher: refresh live audio projections without per-flush prefix discovery

Owner: planscost. `PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED=0` restores per-flush
listing; default `1` enables the optimization. Contract:
[live audio projection](../../listen_pusher_pipeline.mdx#live-audio-projection).

Debouncing the entire update for 300 seconds would delay the deleted-owner
signal and speaker learning, playback and capture coverage. Each flush instead
still groups and persists current `audio_files`, schedules person learning and
admits completed identity retries. Only encoded-prefix discovery is amortized.
A socket caches encoded inventory and reads metadata for the exact objects just
uploaded. The unchanged parser, grouping, source fingerprint and alias retention
provide playback identity; no guessed duration or new persisted schema.

Archive READ is **on by default fleet-wide** (`config/audio_archive.py`), so it
must benefit too. Raw fragments cannot be cached as append-only: new encoded
coverage can shrink or split them. Every incremental flush therefore recomputes
`uncovered_raw_packs(list_packs(...), encoded_inventory)` through the existing
raw index, preserving its 120-second cross-instance TTL and local write
invalidation. No raw-index listing, proof or cache invalidation is removed.
STOP_PCM/raw-only uploads use that same index and can cache an empty encoded
inventory; they do not trigger encoded-prefix discovery on every raw flush.
Submillisecond fragment selectors and source fingerprints match full listing.
A raw-index failure triggers full encoded discovery and preserves the existing
encoded-only fallback; that incomplete raw view is never cached.

Full encoded listing happens on first flush, after 300 seconds measured from
last full discovery (appends do not reset it), changed stored projection,
revision conflict, replay/equal clocks, metadata uncertainty, mutable/spanless or
non-batch encoded sources, missing identity, limits, close and disconnect.
Limits are 128 conversations and 2,048 total referenced chunk entries in cached
projections. Full rebuilds capture the stored projection before LIST; both paths
compare expected identity and fence the write against the read revision. Every
refresh invalidates the prior inventory before doing I/O, so a failed forced
rebuild cannot lend stale state to the next flush. Incremental writes reuse the
existing Firestore read; full rebuilds add one small snapshot read. No Firestore
writes are saved.

Close, switch and ordinary shutdown/disconnect rebuild even without a buffered
tail or cache admission. Independent close debt survives terminal per-flush
retry exhaustion and is repaired even for failed records before retirement.
Successful close discovery is not repeated while only sealing metadata retries;
a later real flush reopens it. Close-only discovery errors retry twice;
InvalidArgument is terminal. Exhaustion reports degraded raw recovery without
crashing supervision or aborting clean custody sealing. Abrupt death cannot run
cleanup, but no timer suppresses the successfully flushed tail. Existing
immutable raw-live media and generation-pinned outbox manifests remain the crash
custody authority. Finalization is supplementary: process_conversation has
recovery/reprocess/sync-off guards and catches rebuild errors; sync finalization
only covers its response conversations.

A false update result still latches deleted conversations each flush. Both
workers, already queued batches and future raw windows honor that result.
Enabled full rebuilds check owner existence before listing, including empty
fallbacks. Raw writes, successful-upload digest ledger, replay-reconcile lists,
safety-WAL coverage, record seal and reconcile/repair implementations stay.
`audio_files` is a derived playback/coverage projection, not a custody receipt;
its readers still need current audio, which is why updates are not debounced.

Measure `omi_pusher_audio_file_projection_total{mode="full"|"incremental"}` and
bucket operations per successful flush. Incremental mode still consults the raw
index; it means encoded-prefix discovery was avoided. At 60-second cadence the
input-evidence ceiling is ~4.3M fewer lists/day, ~$39/day gross at $9/M, before
cold/close/fallback work and added Class B metadata / full-snapshot reads. This
is unmeasured, not booked savings. Custody slice 4 already books $16–19/day for
manifest-first GET: do not sum the forecasts. Measure this lane's marginal delta
against the slice-4 state actually serving, leaving raw-index/proof/reconcile
costs attributed to their existing owners.

Rollback: set the flag to `0` and roll pusher through the approved release path.
No schema migration, deletion or cleanup is needed. This PR does not merge,
deploy or alter production configuration.
