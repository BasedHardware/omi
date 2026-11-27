# Finish cuts a capture that sealed after the live window's last speech

SCA-4434. Recording A seals, then recording B seals a couple of minutes later.
B is a pendant or server-batch capture, so its transcript is still pending and
no window lists it in `v3_recording_ids`. A's derived window is still live (idle
far less than `live.MAX_IDLE`), so the person's Finish resolved to that window
and `request_finish` cut its tail, A. B got neither the manual-end cut nor a
fast finish. When B's projection landed it had no `v3_manual_end`, so a short B
stayed hidden under the Home word floor. The single-recent-capture fallback
(#26288) and the named-window path (#26361) run only when no window is live.
Reproduced by the pipeline-lab scenario `finish_after_second_close`.

## The newer capture

When Finish resolves to a live window (empty body or the named live window),
the `request_finish` transaction also runs the existing recent-source scan
(`_recent_finish_sources`, newest first, at most `RECENT_FINISH_LIMIT` = 8
documents). A capture qualifies when it:

- is a sealed Listen capture that ended after the window's `finished_at`;
- is not one of the window's sources;
- carries `has_content` (a projection that landed empty clears it);
- passes `_capture_ineligible` like the recording fallback: sealed within
  `RECENT_FINISH_AGE`, unclaimed, not marked for another window, and not
  private, deleted, discarded, locked, merged, a partial archive or a failed
  upload.

The newest qualifying capture wins, as in `_latest_capture`. The same
account-deletion check as the recording fallback runs before any write.

A holdout Finish (`named_only=True`, used while a legacy row is in progress)
never redirects: it passes `newer_capture=False` and cuts only the named window.

## What Finish stores

- **The capture's speech has landed**: it takes the recording-scoped cut
  through `_finish_capture` instead of the window tail. That is the same write,
  batch request and empty resolution the fallback uses, and the response names
  the capture. "Landed" depends on the lane:
  - A live-lane capture: `has_finish_content`.
  - A server-batch capture: `_batch_speech_landed`, which is
    `record_projection_revision` plus `has_content`. A fast-finish provisional
    transcript never sets `record_projection_revision`, so such a B takes the
    stored-both path below. `has_finish_content` cannot be used for batch
    captures: `create_in_progress_conversation` → `mark_new` stamps
    `v3_speech_landed_at` when the recording is created, and audio custody sets
    `has_content` on any committed audio, so it is true for nearly every batch
    capture before any speech.
- **A server-batch capture whose speech has not landed.** The session's last
  capture is often only silence: after the quiet timeout the listen loop seals
  A and opens B, then the device stops and seals B. Audio custody sets
  `has_content` on any committed audio, so B qualifies either way. The
  transaction stores both:
  - the window-tail cut on A, exactly as before this change;
  - B's recording-scoped request.

  Both ledger reads (B's, and A's when A is a batch capture) come before either
  write; StrictFirestore enforces that order in the tests. The response names
  A's window, because the cut landed there. If B is silent, its request clears
  at whole-record completion (`_v3_finish_update`) and A's cut already stands.
  If B has speech, the request becomes B's own manual end, so B shows as its
  own card instead of hiding under the word floor.
- **The window-tail cut alone** runs as before when:
  - no capture qualifies;
  - two captures tie exactly on `finished_at` (a 404 here would read as "already
    closed" to the app and cut nothing);
  - the scan is full and its oldest row is still newer than the window;
  - `_finish_capture` declines or finds the capture already empty. It writes
    nothing in those cases. The decline is counted with its reason (see
    Metrics), and the answer is the tail's.

A qualifying capture is strictly newer than the window, so the tail cut's rule
that an older overlapping source never cuts through visible speech still holds.

**Resulting behaviour.** One Finish may end two cards: A's window is cut at once; if the pending newer capture B later lands with speech, B's request becomes its own manual end and B surfaces as its own card. The response names A's window. Latency is measured once per Finish, to the response target's first visible card (see Metrics).

`test_one_finish_cuts_a_at_once_and_consumes_b_once_across_resolution_and_retry`
pins this end to end under StrictFirestore. It runs Finish, B's projection and the
real whole-record completion (with speech, and silent), then the same Finish
again: A is cut once, B's request is consumed once, and the retry answers A's
window with `already_cut` and no writes.

## Retries

A retry never cuts A twice. If the window's tail already carries this window's
Finish (the stored-both case), the tail path answers (`already_cut` /
`already_requested`) and B is not touched again.

Otherwise, a newer capture that an earlier recording-scoped Finish marked
(`v3_finish_no_pointer_recording`) answers through `_finish_capture`, even after
a window claimed it between taps:

- If the marked capture can no longer answer (private, locked, deleted,
  discarded, merged, a partial archive, a failed upload, or `_finish_capture`
  declines, for example an unavailable ledger), the window tail is cut. The app
  reads a 404 as "already closed", so a 404 would leave A uncut.
- If that Finish resolved empty (`v3_manual_end_requested` false, no cut), the
  mark no longer holds the Finish: the window's speech is the last speech again,
  so the next tap cuts the tail.
- Unmarked captures older than an active mark do not qualify; the person
  already finished after their speech.
- If B joined A's window in between, B is the tail and the window-tail path
  answers.

## Reads and writes

Every live-window Finish reads the window and its tail recording, as before.
With the switch on it adds one query, at most 8 documents (one billed read when
it is empty). When a capture qualifies, add the account-deletion marker, then by
path:

| Path | Extra reads after the marker |
| --- | --- |
| Live-lane capture moved to (`newer_recording_cut`, ...) | none |
| Server-batch capture whose speech landed (`newer_recording_*`) | B's native ledger, once (`_finish_capture` reads it: `newer_state` is None) |
| Marked capture, pending-retry (a later tap on a still-requested batch B, `newer_already_requested` / `newer_consumed`) | B's native ledger, once (`_finish_capture`, as above) |
| Stored both (`newer_dual_*`) | B's ledger, then A's when A is a batch capture; A's is the read the tail cut always made |
| Selected, then declined (window tail answers) | the ledger reads above for that path; the tail's own batch ledger read is unchanged |

Targeted tests pin these sequences (`test_server_batch_redirect_reads_the_capture_ledger_once`,
`test_marked_pending_retry_reads_the_capture_ledger_once`,
`test_stored_both_reads_each_ledger_once_before_any_write`). Writes: at most one
recording per transaction, except the stored-both case, which writes two (A's
cut and B's request). The Finish stamp rides in the write the transaction
already makes; it adds no write. With the switch off, nothing extra is read and
the transaction is exactly the tail cut (still stamped `tail`).

Provider cost: storing B's request makes B a fast-finish candidate. That adds at
most one fast-finish pass per stored-both Finish, even when B turns out silent.
With chunking on (`CONVERSATIONS_V3_FAST_FINISH_CHUNKED`, default and production
`on`, #26344), the pass splits each unit into chunks of at most 5 minutes with
3 seconds of overlap and sends them concurrently. A B of up to 20 minutes
(`MAX_SECONDS`) is therefore at most a few prerecorded requests; the lab's
80-second B is one (STT 0 → 1 in `finish_after_second_close`). With chunking off
it is one request per unit, at most `MAX_UNITS` (8), up to 20 minutes. Bounds:
- `CONVERSATIONS_V3_FAST_FINISH`: `cohort` by default; production runs `on` for
  the services that serve Finish and admission, so the cohort does not limit it
  there.
- A B over 20 minutes is admitted only for the long canary:
  `CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT` of owners (25 in production) and at
  most `CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS` of such audio per UTC day
  across the fleet (7200 in production). This is the only fast-finish daily cap;
  a long pass reserves its planned seconds from it before any spend.
- The shared funding gate every pass passes before provider spend
  (`fast_finish.funded` → `sync_admission(lane='batch')`): consent and the
  owner's funded STT plan allowance.

## Metrics and switch

A Finish that answered from a newer capture is counted with a `newer_` prefix in
`omi_conversations_v3_finish_no_pointer_total`, apart from the tail path's
outcomes. All of these labels are pre-initialised and reachable:

- Moved to the capture: `newer_recording_cut`, `newer_recording_requested`,
  `newer_already_cut`, `newer_already_requested`, `newer_resolved_empty`,
  `newer_consumed`, and `newer_recording_ineligible` (the account is being
  deleted; nothing is written).
- Stored both, by the tail's outcome: `newer_dual_cut`, `newer_dual_requested`,
  `newer_dual_consumed`, `newer_dual_already_cut`, `newer_dual_already_requested`,
  `newer_dual_already_empty`, `newer_dual_resolved_empty`.

A newer capture that was selected but declined the cut (`_finish_capture` wrote
nothing) leaves the window tail to answer, so `finish_no_pointer_total` counts
the tail's outcome. The decline is counted once, after the commit, in
`omi_conversations_v3_finish_newer_declined_total{reason}` with `reason` one of
`already_empty`, `batch_unavailable`, `batch_disabled`, `recording_ineligible`
(all pre-initialised). No candidate at all counts nothing there. (The earlier
`newer_already_empty`, `newer_batch_unavailable` and `newer_batch_disabled`
labels could never be returned and are removed.)

Finish-to-visible latency: `omi_conversations_v3_finish_to_visible_seconds`, a
histogram with one fixed label, `path` = `tail`, `newer` or `newer_dual`
(buckets 5 s to 2 h). There is no separate correlation store:

- The first write the Finish transaction stores on its response target's source
  carries `v3_finish_requested = {at, path}`: the tail recording for `tail` and
  `newer_dual`, B for `newer`. In the stored-both case B's request is not
  stamped, so B's own card never samples; when the stored-both tail has nothing
  to cut and the answer names B, B's request is stamped `newer` instead. A
  consuming cut of an earlier request, and every `already_*` answer, writes no
  stamp, so a retried Finish keeps the first stamp.
- The planner carries the stamp from the cut recording to the derived row that
  shows it, once: a row keeps the first stamp it got.
- That row's first manual-end settlement as a visible Home card (the
  `v3_manual_end_home_counted` transition that `manual_end_home_total` already
  counts once per row) observes `now - at`. A later re-settlement, a hidden row,
  or a stamp older than 2 hours (`FINISH_STAMP_MAX_AGE`) records nothing.
  `first_speech_to_visible_seconds` cannot be reused here: it fires when a row
  is first created, and a live window's row exists before its Finish.
- The sync scrape profile keeps the histogram (`deploy/cloud_run_gmp_sync.yaml`).

`CONVERSATIONS_V3_FINISH_NEWER_CAPTURE=off` restores the window-tail cut and
skips the scan. Cuts already stored stay.

## Lab

The pipeline lab's batch lane now writes `has_content` with
`server_batch_audio_end` at seal, as production's audio custody does in the same
transaction.
[Pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
