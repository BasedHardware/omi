# Unreferenced audio investigation (2026-11-17)

Source-only investigation for Lane C. No production account data was accessed;
all reproductions use a temporary Documents directory and fake preferences.
The supplied diagnostic counts and cadence are observations from the task,
not measurements made by this change. Existing orphan files are not deleted,
adopted by filename, or scanned by the new recovery code.

## Attribution

The strongest matching mechanism is a reproduced startup race. While the first
index load/recovery is pending, an early flush can start a delta worker seeded
from the still-empty in-memory inventory. It overwrites the index with an empty
snapshot. When load finally admits old rows, they receive disk tokens and are
considered already indexed; later saves send only new deltas. Previously indexed
files silently lose their active references without file deletion or quarantine.
A real-ledger barrier test reproduces this ordering and leaves only the new row.
Startup admission now fences buffer work, external registration and index saves
before a worker can establish its token namespace.

Live and device producers also have a distinct file-before-index window. Their
length-prefixed `audio_<device>_...bin` file can be fsynced before an index failure
or process exit loses the row. The regressions reproduce live flush, device
registration interruption and failed commits. New write intents close that gap.
Both mechanisms match the reported filename family; repeated startup loss can
strand an entire interval of captures rather than requiring one write failure
per orphan file.

The summary alone does not prove which failure created the reported daily
population. There is no per-file index-write failure history or source SHA for
the exported binary in the assignment. In particular, falling row counts do
not distinguish legitimate synced-file retention from loss. Do not claim this
PR has measured a reduction in device storage or stopped the observed cadence.

## Owner/path audit

Paths below are in `app/lib/` unless specified otherwise.

| Owner/path | Row/file behavior and disposition |
| --- | --- |
| `services/wals/local_wal_sync.dart::_flush` | Confirmed gap: audio fsync precedes index commit. New per-file intent precedes creation and carries exact row metadata, owner, length and SHA-256. Incomplete/uncertain files remain tracked by the intent. |
| `services/wals/device_chunk_persistence.dart::persistDeviceChunk`, `persistEmptyRingRecords` | Same confirmed gap, including interruption before `addExternalWal`. Both now use the same intent transaction. Device ACK still requires a real index commit. |
| `utils/wal_file_manager.dart::_decodeIndex`, `_loadIndex`, `_quarantineIndex` | Invalid rows are omitted from active admission and retired in the original `wals*.json.corrupt-*` archive. Previously a failed rename allowed repair and later saves to overwrite the only references. A flushed copy fallback is now mandatory; if both fail, load fails without publishing a partial repair. Unknown/missing storage on a file-backed row is quarantined rather than silently converted to an empty memory WAL whose next flush replaces the old filename. |
| `utils/wal_file_manager.dart::_loadFromBackup` | Valid backup rows remain indexed; rejected main/backup bytes are archived before fallback. No arbitrary merge from old archives: that could resurrect user-deleted or completed rows. New write intents recover only exact complete new transactions, alongside existing index tokens. |
| `services/wals/wal_index_inventory.dart`, `wal_index_persistence.dart` | Confirmed startup race: saves could establish an empty worker before load admission. Admission now fences producers and saves, preserving the loaded token namespace. Repaired/token-less rows remain dirty and dead-worker rebuild includes every bucket; the 70k-history, mixed-token and blocked-startup tests exercise these boundaries. |
| `services/wals/local_wal_sync.dart::_admitLoadedWals`, `wal_account_purge.dart::_reconcileCurrentOwnerSync`, `clearUserData` | Owner partition/reconciliation/logout move rows across active, foreign and retired buckets, all included by the index owner. Replayed intents retain their captured owner and foreign records stay parked. Deduped restoration keeps a matching file reference. |
| `services/wals/local_wal_sync.dart::_removeExpiredSyncedCopies`, `_deleteWal`; `wal_discard.dart`; `wal_account_purge.dart` | Indexed retention, explicit user discard and account purge use `_deleteWal`: delete file before row, preserve rows on failure, protect shared references. Audio deletion precedes intent retirement; a failed audio delete retains both row and intent. A failed retirement retains the row and missing-file retry retires only metadata. Replay never publishes an intent whose audio is missing. |
| `utils/wal_file_manager.dart::clearAll`; `utils/auth/finish_account_deletion.dart` | Confirmed gap: after an owner purge, unconditional index deletion loses rows for other owners or failed file deletions. Cleanup now removes indexes only when no indexed rows remain, under the same writer lock. This is an occasional path, not evidence of daily capture-cadence loss. |
| `services/wals/wal_policy.dart` | Count cap is warning-only; pending rows are not evicted. Terminal invalid-capture-time and outside-recovery-window states retain original files and rows. These log tokens do not explain an orphan on their own. |
| `services/wals/pendant_ring_custody.dart` | Prunes ring/live proof references and checkpoints, not the WAL ledger. Ring/SD/flash audio producers use `persistDeviceChunk`; proof acceptance still checks flushed file plus committed index. |
| `services/wals/mobile_batch_buffer.dart` | Existing `.batch-journal` precedes audio creation; replay preserves a torn original in `.torn`. Journal retirement follows indexed publication. This path already has a separate recovery owner; no new writer or generic cleanup was added. |
| `services/wals/native_recording_intake.dart` | Native finalized-file discovery retries admission/save failures. Legacy jobs/owners references retire only after durable row confirmation. Watch deletion requires owner-scoped coverage. Deferred owner files remain with native receipts/owners; these names differ from the sample's ordinary device prefix. |
| `ios/Runner/Batch/BaseBatchAudioWriter.swift`, `ios/Runner/WatchRecordingStore.swift` | `.bin.part` has a native producer until finalization/recovery. Watch recovery preserves `.bin.part.torn` on a torn suffix; mobile batch preserves `.bin.torn`. These are intentional recovery evidence, not permission to delete. Current Dart WAV playback/export uses `getTemporaryDirectory` (`utils/audio_player_utils.dart`, `utils/audio/wav_bytes.dart`); historical Documents WAVs and unknown filename classes cannot be assigned safe deletion authority from this summary. |
| `utils/wal_file_manager.dart::migrateLegacyLimitlessFiles` | Saves the merged rows before clearing legacy preferences. A throwing save leaves preferences intact. A false return is theoretically ignored, but `saveWals` cannot ordinarily return false after successful `init`; no supported false-return loss was reproduced. Legacy recovery is distinct from the sample device prefix. |

## New transaction and retirement

`.wal-pending/<exact-audio-name>.json` is fsynced and atomically renamed before
creating audio. It stores the normal WAL row plus expected byte count and hash.
Name reservations include interrupted metadata temporaries. Recovery visits
only `.wal-pending`, verifies the complete bytes and preserves row metadata;
it does not infer owner, capture time or proof from an audio filename.

Recovered rows are explicitly **not** confirmed index durability. Normal delta
or full-snapshot commit precedes intent retirement. A crash after main commit
is deduplicated against the authoritative row, and a subsequent load retires
the leftover intent. Partial, missing, malformed and hash-mismatched files keep
their intents and bytes for explicit recovery. Reverting this change leaves the
metadata and audio intact, but an older binary cannot replay the new intents.

## Later GC: required proof (not implemented or authorized here)

Absence from `wals.json`, age, count pressure, status inferred from a filename,
and an invalid-capture-time 400 are never deletion proof. A later GC must first
obtain David's explicit sign-off, then enumerate all current/backup/quarantined
indexes, owner buckets, `.wal-pending`, batch journals, native owners/receipts,
partial/torn artifacts and any still-running producer before proposing a file.

Potentially safe classes require owner-scoped, immutable content evidence:

- An exact WAL/file confirmed by its server upload job, with durable successful
  completion and file identity/content binding. A server job ID alone, or a
  `synced` label without an acknowledgement, is insufficient.
- A `capture_committed` receipt whose owner, device/root, clock epoch, channel,
  source-frame interval and content proof cover the entire candidate. A loose
  timestamp overlap does not prove equivalence.
- A Watch recovery file with its original owner receipt and complete durable
  server-reachable live coverage, using the existing dedupe contract.
- A partial/torn duplicate only after byte-exact complete coverage by a retained,
  owner-matched committed copy. Preserve unmatched tails and undecodable files.

A future GC must record candidate identity, exact proof and retained substitute,
revalidate all references and file metadata immediately before action, and use
one owner-aware transaction/tombstone so interruption cannot delete new bytes
or resurrect a deliberately deleted row. Unknown owner/content/receipt means
retain. Produce a dry-run evidence manifest for review before enabling deletion.
