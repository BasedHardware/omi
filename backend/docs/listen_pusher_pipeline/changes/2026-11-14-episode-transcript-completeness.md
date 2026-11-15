# Closed episode transcript completeness

A retained visible member can be `completed` while its batch transcription is
pending. The composer now waits when `home_transcription_pending_at` is set and
there is no nonblank transcript. The deadline is that original stamp plus
`EPISODE_COMPOSE_TRANSCRIPT_WAIT_SECONDS` (default 1200, bounded 0..86400).
After expiry it composes available speech. Force/read requests do not bypass
this gate. Hidden, deleted, discarded and duplicate members do not hold it.

The existing process-local settle queue wakes at the deadline without occupying
a compose worker; `compose_pending_since` also lets a read recover the debt
after a restart. Ordinary unfinished processing keeps its existing wait rule.

Immediately after a successful batch assignment commits, before playback or
notes enrichment, `transcript_projected` signals the existing composer. The
speech/name/membership evidence comparison and paid-once lease deduplicate
repeat projections. An already composed partial episode catches up even when
capture is older than the normal late-compose threshold. Ordinary sync
finalization still signals through `schedule_after_finalization` ->
`on_conversation_finalized` -> `after_finalized` -> `schedule_for_conversation`.

Rollback: set `EPISODE_COMPOSE_TRANSCRIPT_WAIT_ENABLED=false` to restore the
completed-status-only gate; independently set
`EPISODE_COMPOSE_TRANSCRIPT_READY_ENABLED=false` to remove the projection signal.
No composer version or fingerprint input changes; deployment alone does not
request regeneration of old episodes. Runtime/deployment is not qualified here.

The legacy `episode_transcription_pending_at` receipt also holds an empty member
when no Home stamp exists. The projection signal respects the global
`EPISODES_ENABLED` switch before looking up an episode. Owner-context rendering
accepts stored non-string metadata without losing composition.

Batch replacement also stamps `episode_transcript_updated_at` in the same
transaction as new speech. Home's existing bounded member-metadata read carries
that receipt. A newer visible retained-member receipt re-arms an older compose,
so a crash between transcript commit and the in-process signal cannot hide the
late transcript permanently. This adds no query or account scan and keeps the
read-side scheduling/throttle limits. The private read observation is not stored
on the episode or returned to clients. The READY kill switch covers the receipt,
signal and read recovery. Unchanged old rows have no receipt and do not recompose.
