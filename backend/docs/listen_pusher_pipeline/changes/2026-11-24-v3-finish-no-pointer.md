# Finish a live v3 window after capture rotation

Quiet finalization can close the recording while its derived conversation is
still live. When the existing in-progress recording lookup misses, Finish uses
the same owner-scoped lookup as the live tile. A transaction verifies the window
is still live before storing the manual end on its newest linked recording.
An optional owner-scoped live window ID targets the window the user tapped.
A stale or foreign ID falls back to live discovery. A closed audio-only batch
recording carries the request until admission, single-unit projection, or the
whole-record projection transaction can apply the cut. A repeat tap after
a whole-record completion can also apply the cut. A partial archive or ledger
cannot authorize it.

The existing HTTP response carries the window ID and processing status.
`CONVERSATIONS_V3_FINISH_NO_POINTER=off` restores the lookup-miss 404.
Use `omi_conversations_v3_finish_no_pointer_total` to compare unique acceptances with successful first
settlements for the accepted windows. [Pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
