# Capture-group join fences on the stored window, not the recorded span

**What changed.** `utils.conversations.duplicate_capture._group_confirmed_captures` now builds the join's
`expected_windows` from the freshly read rows' stored `started_at`/`finished_at`, which is what
`database.capture_groups.join_capture_group` re-checks in its transaction. Before, it passed `CaptureRecord`'s window,
which is the recorded span (`recorded_start`/`recorded_end` via `conversation_span`). The two differ on most phone and
desktop rows, so every confirmed same-speech pair failed the fence as `conflict`.

The join now abstains, and counts `capture_group_joined outcome=abstained`, when a row's fresh recorded span no longer
equals the span the overlap was proven on, or the row is gone. A window that moves after discovery still never
groups.

**Why.** In prod from 2026-11-27 12:00Z to 11-28 03:00Z, joins applied 2 times and conflicted 47 times. Flutter and
macOS collapse only on `capture_group`, so a pendant card and the Mac meeting row of one call stayed as two Home cards
with only the advisory `duplicate_capture_of` hint (SCA-5295).

**Reach.** New confirmed pairs only: on the order of tens of joins a day fleet-wide. Existing groups do not change,
and there is no backfill. Reads are unchanged: the window comes from the snapshot the shared-speech check already reads.

**Kill switch and rollback.** The existing thresholds stop automatic grouping (for example
`CROSS_DEVICE_GROUP_MIN_WORDS=1000000`). Users can still Separate a grouped card. Rollback: revert the PR.

**Check.** `omi_product_event_total{event="capture_group_joined"}`: `applied` at least as often as `conflict` over
24 h after serving, with `abstained` small.
