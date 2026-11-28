# Home

Home is v3 only (David, 2026-11-27; SCA-5226). What it shows is a pure function,
`buildHome` in `lib/pages/conversations/home/home_model.dart`, of plain inputs: the
server's conversation list, the conversation in progress, the capture and call state,
recordings saved on this phone, held audio and pending deletes. The page turns each
`HomeRow` into exactly one widget, so the list of row kinds below is the whole of Home.

## Rows

| Row | Widget | Shown when |
| --- | --- | --- |
| Live | `HomeLiveRowView` | Anything is capturing. At most one, first in Today. The server's conversation in progress is drawn as its own `ConversationListItem` (live tile, "Listening" until titled, its length, no snippet); a call, Transcribe Later or a capture the server has not named yet get their own row. |
| Finishing up… | `HomeFinishingRowView` | After End, until the server's row for it is listed or the finish settles. Follows the live row. Tapping opens the conversation once it exists, and says it will otherwise. |
| Conversation | `ConversationListItem` | A listed conversation that is done, transcribing or writing. |
| Saved recording | `RecordingListItem` | A recording from this phone while it is being sent or the server is processing it. |
| Locked | `HomeLockedRowView` | A day's conversations and held audio over the plan's limit, as one row with their count and Unlock. |

One prompt sits above the list at most: payment, then firmware, then voice profile,
then Review (`HomePromptSlot`). When none of those applies, the slot may hold the
quiet-payer row ("No recordings in 5 days", `QuietPayerRow`), which decides for itself.

## Rules

- Days are newest first; rows within a day are newest first by start time.
- A step that runs past its deadline says "Taking longer than usual", never "failed"
  (`HomeDeadlines`: 15 minutes for a conversation step, measured from when it finished;
  30 minutes for a saved recording the server accepted). Server work has no client timeout.
- Home holds what is capturing, in progress, done or locked. Anything that needs the reader
  is in Activity instead (`ActivityPage`):
  - **Needs attention** lists a failed conversation with Try Again (`NeedsAttentionSection`).
  - **On this phone** lists recordings kept only on this phone, waiting to be transcribed or
    that could not be sent, in the same rows Home uses, with Transcribe all
    (`OnThisPhoneSection`).
- The bell's warning dot lights for a failed conversation until Activity has shown it, and
  for as long as any recording is only on this phone (it may be the only copy).
- A row that fails while Home is on screen leaves with one toast, "Couldn't finish …", whose
  View opens Activity.
- Live, Finishing up…, saved recordings and locked rows show only in Home's own view: no
  search, filter or selection. Showing short or discarded conversations widens the list;
  it is not a filter.
- Every row has one geometry: one card, one 36 pt tile, title, one subtitle line in one
  style, and an optional trailing action (`HomeRowAction`). Most rows are a `HomeRowShell`;
  conversation rows (`ConversationListItem`) draw the same geometry themselves. No row
  carries a chevron. Exceptions that add height: Transcribe Later's live card keeps its
  Pause, New recording and Stop controls (`ConversationCaptureWidget`); a conversation adds
  a line for a search or discarded snippet, an on-device provenance chip, a deferred marker
  or a pending-transcription note.
- Every row deletes with one swipe (`HomeSwipeDelete`): a conversation confirms and offers
  Undo; a recording on this phone confirms and cannot be undone, and cannot be swiped while
  the server is working on it.
- The page shell does not rebuild for a list update: a `Selector2` over an identity snapshot
  rebuilds the list below it (`test/perf/home_after_detail_perf_test.dart`).

## Not on Home any more

The compact card feed (`/v1/home/feed`), the episode projection and the legacy list
fallback are gone from the client; it no longer reads the feed endpoint. Background-recap
hiding and the offline-sync "adding from your Omi" label only ran with episodes on, and
v3 suppresses episodes, so neither had run since v3 reached every account.

The opt-in Daily Recaps row on Home and its Developer Settings toggle are gone; recaps are
on Activity (`ActivityPage`). `HomeDailyRecaps` stays only because Activity and the frozen
visual-audit compat suites import it.

Coverage: `test/unit/home_model_test.dart` (the model), `test/pages/conversations/home_v3_test.dart`
(the page, including the `Home rows render` evidence group, written when
`HOME_ROWS_RENDER_OUTPUT` names a directory).
