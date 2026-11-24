# Finish a live v3 window after capture rotation

Quiet finalization can close the recording while its derived conversation is
still live. When the existing in-progress recording lookup misses, Finish uses
the same owner-scoped lookup as the live tile. A transaction verifies the window
is still live before storing the manual end on its newest linked recording.
A closed audio-only batch recording carries the request until admission or its
single-unit transcript projection can apply the cut. Repeated taps against
the same live window reuse the intent.

The existing HTTP response carries the window ID and processing status.
`CONVERSATIONS_V3_FINISH_NO_POINTER=off` restores the lookup-miss 404.
Use `omi_conversations_v3_finish_no_pointer_total` and the manual-end settlement
counters to track adoption. [Pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
