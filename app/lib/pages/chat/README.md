# Mobile chat

Chat opens as a full-screen popup through `openChatSheet`. It keeps the existing app theme,
composer, streaming renderer, citations, attachments and microphone controls. Past chats
is a pushed page above the popup; Back returns to that exact Chat page and Close or a
downward pull from the top handle returns
to the original caller. The popup owns no Home instance or bottom navigation bar.

## Ownership

| Component | Responsibility |
|---|---|
| `chat_route.dart` | `openChatSheet` and `ChatSheetRoute`: one popup transition and the header pull-to-dismiss for Home, quick actions, app detail, conversation detail and deep links. |
| `page.dart` | Focus, editable draft, quoted/conversation context and integration with existing send/voice behavior. |
| `widgets/chat_entrance.dart` | A single disposable entrance timeline; only an explicit new-chat revision replays it. |
| `widgets/chat_starters.dart` | Localized greeting and editable question chips; never sends a message. |
| `widgets/chat_chrome.dart` | Close, history, selected app and connection/loading feedback. |
| `past_chats_page.dart` | Server history projection, pagination, refresh/retry, app choice and confirmed deletion. Returns a selection to the existing page. |
| `providers/chat_history_state.dart` | MessageProvider's selected thread and history lifecycle. No separate persistent transcript or new cache. |
| `backend/http/api/chat_sessions.dart` | Existing authenticated session endpoints, with explicit typed success/failure outcomes. |

## Thread and draft rules

Normal user entry requests a fresh thread; rendering `ChatPage` alone does not erase an
existing transcript. App-detail entry retains the selected app. If a send or voice operation
is already active, fresh entry cannot replace that operation's thread.

Opening a fresh screen does not create a server record. Its first typed or transcribed
question creates the session once, then sends with that explicit ID. Creation failure leaves
a retryable failed reply and **does not fall back to the server-current thread**. Retry keeps
the original question, attachment IDs and context. Titles are derived through the existing
title endpoint after a completed reply; a title failure does not fail the reply.

Opening history alone preserves the draft. Choosing a different thread with text or
attachments asks before discarding them. A history read replaces the current thread only
after success. Text typed while that read is pending is retained; completing a switch only
clears the draft that existed before it started. Every history load captures a revision: a slow earlier result cannot replace
a newer selection, a fresh thread or a disposed provider. Thread changes are blocked during
message sending, voice work, file upload and destructive mutations.

Session reads never fall back to the old unscoped message cache. The legacy current-chat
path retains its existing cache for compatibility. History list failures show Retry rather
than an empty-history claim; failed refreshes retain visible rows. A successful empty list
shows the localized empty state. Both history and older messages paginate.

Deletion uses the shared row menu and destructive confirmation. The row stays until the
server succeeds. Deleting the selected session starts a fresh thread only after success.
Deleting another session leaves the visible transcript alone.

The composer microphone retains Stop → transcribe → edit, direct Send and Discard. It sends
the resulting text through the same explicitly targeted path. Pendant-button voice uses a
separate, existing server-current voice endpoint; its playback may continue while history
is being viewed, but its reply is not appended to an explicitly selected past thread.

## Motion and accessibility

The popup rises on a 420 ms curve and closes in 280 ms. The 1.1 s entrance staggers the
greeting at 0 ms, count line at 120 ms, composer at 150 ms, suggestions at 350 ms and question
at 500 ms. Text rises 10 points over 500 ms; the composer takes 450 ms. The greeting uses
28-point semibold type and the question 20-point medium type, matching the reference.
Streamed tokens, focus changes and provider
rebuilds never restart it or replace the text controller. Suggestions stay editable.

Reduce Motion renders the popup and entrance in their final position and stops the typing
indicator's repeating ticker. Enabling it mid-animation completes the entrance immediately;
turning it off does not replay the greeting. Controls retain shared 44-point minimum touch
targets and localized semantics. Starter questions scroll horizontally. The latest follow-up
stays within the available width, wraps to two lines and uses an ellipsis for longer text.
When the keyboard leaves less than 400 points of visible height, it uses one line to preserve reading space.
Generated whitespace is collapsed for display; tapping still sends the complete original
question. Text scaling remains enabled. The greeting can scroll independently above the composer.

Follow-up suggestions match the starter questions: an unfilled, rounded outline and regular
callout text, distinct from the user's filled message bubble. They retain a
44-point minimum touch target and the existing send callback and analytics.
Only the latest completed AI reply can supply that suggestion, in the fixed area above the
composer and keyboard. Historical answers never render their own chips. Sending a new turn
hides the old suggestion immediately; a newer answer without one leaves the area empty.
Opening a saved chat derives the suggestion from its latest reply, without changing stored
content blocks. Suggestions are hidden during history loading, streaming, voice work and offline use.

The top handle drives the route position directly while dragging. A short or cancelled pull
settles back with its draft and focus intact. A pull past 22% of the screen or a downward
flick (at least 32 points and 900 points/second) continues smoothly offscreen from the release
position. Upward flings cancel. Transcript scrolling cannot dismiss chat. The route balances
Navigator gesture notifications even if it is removed during a drag; Reduce Motion skips movement.

The greeting derives today's non-discarded total from the already-loaded conversation provider,
matching the supplied V3 design without a second network request or a late layout change. The
number starts counting at 250 ms over 650 ms with the prototype's cubic power easing, driven by
the same 1.1-second entrance as the three text lines. Provider updates change the settled number
without replaying the greeting. Reduce Motion shows the final number immediately, and screen
readers receive only the final count. The Chat Apps management shortcut is absent from Past chats;
New Chat and saved-thread actions remain.

## Verification

- `test/backend/chat_sessions_api_test.dart`: failed versus empty history, malformed identity,
  encoded explicit targeting, pagination and delete failures.
- `test/providers/chat_history_state_test.dart`: delayed results, session creation failure and
  retry, single-flight creation, switching during sends, scoped cache behavior, pagination,
  deletion and disposal.
- `test/widgets/past_chats_page_test.dart`: retry, selection, deletion confirmation and pagination.
- `test/widgets/chat_history_navigation_test.dart`: actual ChatPage-to-history navigation,
  read-only selection, failed reads, delayed-read draft preservation, starter editing,
  follow-up sends and header-only swipe dismissal.
- `test/widgets/chat_presentation_test.dart`: stable draft/focus across rebuilds, deliberate
  replay, reduced motion, small-screen large text, and popup/history return navigation.
- `test/widgets/chat_greeting_count_test.dart`: exact text and stagger timing, count-up easing,
  stable post-animation geometry, provider updates, discarded/local-day filtering and reduced motion.
- Existing voice controls, microphone arbitration, late-result discard, failed-reply, citations,
  message layout and seeded journeys remain required regression coverage.

Run `bash app/test.sh`, the analyzer ratchet, applicable hermetic journeys, localization
freshness and repository preflight. Visual audit scenarios use the synthetic loopback backend;
physical microphone, keyboard and device evidence must be reported separately from those tests.
