# Durable playback projection debt (phase 5C)

After the bounded close rebuild retries fail, pusher hands playback-only debt
into `record_projection_rebuild_jobs/{sha256([uid,cid])}` before discarding its
socket state. Socket cleanup also hands off outstanding debt. Terminal batch
projection failures persist by exact owner even if the bounded close cache is full. The marker kind
is `record_projection_rebuild_due`; its only other fields are owner ID,
conversation ID and request time. Repeated handoffs coalesce by owner.
Ordinary flushes add no reads or writes. A failed marker write retains the
in-memory obligation for another close/cleanup attempt and emits a sanitized
warning plus the existing projection failure counter. A process kill or a
persistent Firestore outage can still prevent handoff; this is not a WAL.

The existing record-seal-repair CronJob runs a separate 60-second pass before
seal work, selecting at most 128 markers by request time. It uses a fresh,
socket-independent full metadata rebuild even if the incremental optimization
is disabled. Successful rebuild or revoked owner clears only the observed
marker version. Existing nonempty producer fences retain the marker after a
metadata update: a retained worker may still upload a later tail. This reads
the existing map and never clears a token or grants seal authority. Incomplete discovery or failure retains and rotates the
marker; malformed markers also rotate. Concurrent replacement wins over cleanup. Preview mode never rebuilds
or writes. Reports contain aggregate dispositions, never owner IDs or paths.
The existing CronJob suspension/runtime settings still govern execution; no
CronJob is unsuspended by this code change.

`projection_owner_gone` refuses a tombstone or absent row before discovery.
The cold projection transaction rechecks account/conversation privacy,
tombstones, soft deletion, sync opt-out and the prior audio-files revision
before updating only `audio_files`. A deletion or another projection arriving
during discovery cannot recreate the owner or overwrite a newer projection.
Raw-index failure cannot count as successful durable repair, including forced
socket close. Empty close discovery hands off its obligation too. Empty live
inventory retains the marker for a later pass.

`PUSHER_PROJECTION_DEBT_DURABLE_ENABLED` defaults **on**; `0`, `false`, or `off`
disables both handoff and consumption. Rollback disables the consumer runtime
first (`recordSealRepair.projectionDebtDurableEnabled=false`), then pusher; existing markers remain inert. Restoring on resumes them.
A normal socket close does not probe or clear a preexisting marker: the cold
consumer clears it after its own full rebuild, avoiding hot-path writes.

This adds no seal authority, producer token changes, entry clock, heartbeat,
dead-letter, audio-object mutation or PCM reads. Object discovery reads metadata
only, including the existing raw-pack index. No production measurements, IAM
checks, cloud access, live CronJob activation, end-user playback acceptance or
cost/latency claims are included. Hermetic unit tests and lifecycle emulator
scenarios exercise exhaustion, eviction, deletion during discovery and marker
replacement. Phase 5 A/B simulator changes remain outside this lane.
