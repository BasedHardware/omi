# Durable playback projection debt (phase 5C)

After the bounded close rebuild retries fail, pusher hands playback-only debt
into `record_projection_rebuild_jobs/{sha256([uid,cid])}` before discarding its
socket state. Socket cleanup also hands off outstanding debt. Terminal transient/InvalidArgument batch
projection failures persist by exact owner even if the bounded close cache is full. The marker kind
is `record_projection_rebuild_due`; its only other fields are owner ID,
conversation ID and request time. Repeated handoffs coalesce by owner.
Ordinary flushes add no reads or writes. Terminal marker handoffs enqueue into
one bounded background task. A separate metadata-only retry inventory preserves
overflow outside the close cache; marker failure cannot change recording-close
success. Socket cleanup has one three-second total deadline for batched writes
and retries, independent of debt count. `marker_write_failed` and bounded-list
saturation emit sanitized logs and counter outcomes. Temporary privacy holds
retain markers without a metadata update.

The [owning contract](../../listen_pusher_pipeline.mdx#durable-playback-projection-rebuild-debt)
defines payloads, ordering, limits, gauges, flag bindings and rollback. Process
kill, persistent Firestore failure, or saturation can still prevent handoff;
this marker is not a WAL.

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
inventory retains the marker until seven days from Firestore creation, then
retires as `retired_no_objects`. A 10,000-marker maintenance ceiling also retires
confirmed empty work under pressure, never useful or privacy-held debt. Per-pass
work stays capped at 128; the collection scan caps at 10,001. Aggregate logs and
Prometheus gauges expose bounded count, observed oldest age and capacity state.
No retirement deletes audio. Empty-marker retirement checks the observed marker
version and the conversation's explicit empty producer map transactionally at
retirement time, not discovery time. Unknown or nonempty producer maps retain
and rotate debt, including under collection pressure. A late tail still has a
marker to repair its playback metadata. The pressure-blocked gauge and aggregate
fenced count make an all-fenced maintenance pass alertable. No producer token
or seal field is written.

`PUSHER_PROJECTION_DEBT_DURABLE_ENABLED` defaults **on**; `0`, `false`, or `off`
disables both handoff and consumption. Rollback disables the consumer runtime
first (`recordSealRepair.projectionDebtDurableEnabled=false`), then pusher; existing markers remain inert. Re-enabling the flag resumes retained markers.
A normal socket close does not probe or clear a preexisting marker: the cold
consumer clears it after its own full rebuild, avoiding hot-path writes.

This adds no seal authority, producer token changes, entry clock, heartbeat,
dead-letter, audio-object mutation or PCM reads. Object discovery reads metadata
only, including the existing raw-pack index. No production measurements, IAM
checks, cloud access, live CronJob activation, end-user playback acceptance or
cost/latency claims are included. Hermetic unit tests and lifecycle emulator
scenarios exercise exhaustion, eviction, deletion during discovery and marker
replacement. Phase 5 A/B simulator changes remain outside this lane.
