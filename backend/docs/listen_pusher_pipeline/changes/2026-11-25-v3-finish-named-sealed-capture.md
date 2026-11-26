# Finish the named capture after its window stops being live

A pendant capture seals at a speech pause. The window it fed can then stop
being live: it ends, settles, or is hidden. The app still names that window in
`live_conversation_id` when the person taps Finish. Before this change, a named
window that was no longer live, with no other live window, returned 404. The
recording-scoped fallback was reserved for empty bodies, and it refuses a
recording a window has claimed. Short pendant windows below the Home word floor
then stayed hidden, so the person saw a processing row disappear.

When the named window is not live and no other window is, a transaction reads
the named id. If it is a derived window, the transaction reads that window's
tail source. If it is a capture, it reads the capture itself. The window must
not be deleted, discarded, locked, merged or private.

The transaction then scans the recent sources. A capture that sealed after the
named one is what the person just finished: a later capture can feed a window
that never goes live (hidden under the word floor), so the app keeps naming the
earlier window. The newest such capture is cut instead. If it is claimed, its
single claiming window must list it as the tail. Finish declines without
writing (`named_superseded`, `recording_ambiguous` or `recording_lookup_capped`)
when the newest capture is ineligible, claimed by several windows, not the tail
of its window, tied with another, or past a full scan.

The capture that is cut must be a Listen capture sealed within
`RECENT_FINISH_AGE` (5 min) and pass the recording-Finish checks: not private,
deleted, discarded, locked, merged, a partial archive or a failed upload. A
window tail must carry a claim by that window and no other. A completed window
already on Home (not hidden) is answered as it is (`already_visible`) and
nothing is written, so its notes are not regenerated. Otherwise the same
transaction rechecks the two-hour live horizon and the account-deletion marker
before it writes. A window tail gets the window-scoped cut
(`v3_finish_no_pointer_window_id`), so the planner re-derives the window with
`manual_end`, and the window shows on Home. A bare capture gets the
recording-scoped cut. Naming a capture also resolves a set of recent captures
that the unnamed fallback reports as ambiguous.

A body that carries only `live_conversation_id` is the app's Finish. It may now
use the single recent-capture fallback when the name resolves to nothing.
`{"live_conversation_id": null}` is treated like `{}`. A body with any other
field keeps the previous rule.

Reads per Finish on this path are bounded: at most two transactions. The named
transaction reads the named document and at most two more by reference (the
tail or the later capture's window). It scans at most 8 recent sources, at most
200 windows on the live horizon, and one deletion marker; a batch capture adds
one ledger read. The fallback transaction, for the app's Finish body only, reads
at most 8 recent sources, 200 windows, one deletion marker and one ledger. Each
transaction writes at most one recording and enqueues at most one reconcile.

New `omi_conversations_v3_finish_no_pointer_total` outcomes are
`named_recording_cut`, `named_recording_requested`, `named_not_finishable`,
`named_superseded` and `already_visible`.
`CONVERSATIONS_V3_FINISH_NO_POINTER=off` still restores the lookup-miss 404.
[Pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
