# Mobile chat

Chat opens as a full-screen popup through `openChatSheet`. It keeps the existing app theme,
composer, streaming renderer, citations, attachments and microphone controls. Close or a
downward pull from the top handle returns to the original caller. The popup owns no Home
instance or bottom navigation bar.

## Ownership

| Component | Responsibility |
|---|---|
| `chat_route.dart` | Shared popup transition and header pull-to-dismiss for every entry point. |
| `page.dart` | Focus, editable draft, conversation context and existing send/voice behavior. |
| `widgets/chat_entrance.dart` | One disposable entrance timeline per popup. |
| `widgets/chat_starters.dart` | Localized greeting and editable question chips. |
| `widgets/chat_chrome.dart` | Close, centered dismissal handle, selected app and loading feedback. |
| `providers/chat_history_state.dart` | Existing current-thread loading and cache; shared session compatibility. |

## Thread and draft rules

All mobile entry points resume the current conversation. Opening or closing the popup never
creates a chat session, clears messages or changes an active send's target. An empty provider
loads the server-current transcript through the existing current-chat path and cache.
Typed questions and composer microphone transcripts continue that same conversation.
The mobile popup has no Past chats or New Chat controls.

Existing server sessions and stored messages remain intact. Shared session APIs stay available
for their other consumers; this change does not merge or delete previously saved sessions.
Selected chat apps retain their existing scoped behavior. The composer microphone keeps
Stop → transcribe → edit, direct Send and Discard. Clear Chat still requires the existing
destructive confirmation.

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
Reloading the current conversation derives its suggestion from the latest reply without changing
stored content blocks. Suggestions are hidden during loading, streaming, voice work and offline use.

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
readers receive only the final count. Closing and reopening the popup does not reset the conversation.

## Verification

- `test/backend/chat_sessions_api_test.dart`: failed versus empty history, malformed identity,
  encoded explicit targeting, pagination and delete failures.
- `test/providers/chat_history_state_test.dart`: delayed results, session creation failure and
  retry, single-flight creation, switching during sends, scoped cache behavior, pagination,
  deletion and disposal.
- `test/widgets/chat_continuity_navigation_test.dart`: reopen continuity, current-thread initial
  loading, active sends, absent history controls, centered handle, starter editing, follow-ups
  and header-only swipe dismissal.
- `test/widgets/chat_presentation_test.dart`: stable draft/focus across rebuilds, deliberate
  replay, reduced motion, small-screen large text, and popup/history return navigation.
- `test/widgets/chat_greeting_count_test.dart`: exact text and stagger timing, count-up easing,
  stable post-animation geometry, provider updates, discarded/local-day filtering and reduced motion.
- Existing voice controls, microphone arbitration, late-result discard, failed-reply, citations,
  message layout and seeded journeys remain required regression coverage.

Run `bash app/test.sh`, the analyzer ratchet, applicable hermetic journeys, localization
freshness and repository preflight. Visual audit scenarios use the synthetic loopback backend;
physical microphone, keyboard and device evidence must be reported separately from those tests.
