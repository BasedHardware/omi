# Chat UX

Chat on every v5 surface is one transcript, one composer and one set of
rules. Desktop Chat is a destination beside Activity; phone chat is a pushed
page. The message history lives in the orchestrator, so it survives
navigation.

## Decision (second pass, September 2026)

The first pass (below, "History") fixed the structure: Chat stopped being a
modal overlay and became a destination with its own composer. Its visual
execution still read as a sheet: an opaque white or near-black card with its
own border and radius inset in the glass window, a "Chat" title in the
omnibar, an "Activity" text button beside the composer, and a dotted Omi mark,
timestamp and copy icon under every reply. This pass makes Chat part of the
window and adopts established AI-chat patterns.

### Library evaluation

| Library | What it does well | Fit for v5 | Verdict |
| --- | --- | --- | --- |
| **assistant-ui** (`@assistant-ui/react`, `@assistant-ui/react-native` 0.1.x, MIT) | Headless Thread / Viewport / Composer / Message / ActionBar primitives; stick-to-bottom viewport with a scroll-to-bottom button; action bar that auto-hides except on the last message (`autohide="not-last"`); composer with Enter to send and auto-resize | The React Native package is 0.1.x and pulls `assistant-cloud`, `assistant-stream`, `@assistant-ui/core`/`store`/`tap`; web needs the separate DOM package (Radix, zustand). Its runtime owns thread state and "reload" semantics (regenerate a branch); our orchestrator owns the legacy `/v2/messages` wire, history cursors, stop and resend-to-retry, so we would bridge two state machines through `ExternalStoreRuntime`. No macOS (RN 0.79) support is claimed or tested. | Reference only |
| **Vercel ai-chatbot / AI SDK UI** (`useChat`, Apache-2.0 / MIT) | Reference patterns: suggested actions that fill the input, hover message actions, `use-stick-to-bottom`, auto-growing textarea, streaming Markdown (Streamdown, which we already use on web) | Web/Next only; `useChat` expects the AI SDK stream protocol and transport, so adopting it would change what is sent (fails the wire constraint) | Reference only |
| **react-native-gifted-chat** 3.x (MIT) | Mature messenger UI | Peer-depends on `react-native-reanimated`, `react-native-gesture-handler` and `react-native-keyboard-controller` (native pods/Gradle modules); bubble-on-both-sides messenger look with avatars and per-message times, the opposite of our design language | Rejected |
| **Flyer Chat** (`@flyerhq/react-native-chat-ui` 1.x, Apache-2.0) | Clean messenger UI | Depends on a keyboard-accessory view, link previews (network fetches of message URLs) and an image viewer; messenger bubbles on both sides; no macOS or web target | Rejected |

**Decision: no new dependency.** None of the libraries runs on React Native
macOS 0.79, iOS, Android and react-native-web without native modules while
fitting the legacy wire and our design language. We implement their patterns
in our own components instead:

- `src/ui/ChatThread.tsx`: the scrolling transcript (stick-to-bottom, Jump to
  Latest, day separators, grouping, reply-finished announcement).
- `src/ui/ChatTranscript.tsx`: message rows, the thinking indicator, the action
  bar, day separators.
- `src/ui/ChatComposer.tsx`: the desktop composer capsule (the phone composer
  is `src/mobile/MobileOmnibar.tsx`, one field instance shared with the Home
  dock so the keyboard survives the push).
- `src/ui/ChatCodeBlock.tsx` (+ the web `pre` in `ChatMessageContent.web.tsx`):
  code blocks with a language label, Copy and horizontal scroll.
- `src/ui/chatTimeline.ts`: pure day-label and grouping rules.

### Desktop: part of the window

- **No panel.** The transcript draws on the same glass as Activity, in a
  centered chat column (680 + gutters, the same column logic as the Activity
  list) and scrolls within the stage under the chrome. No background, border
  or radius of its own.
- **Composer** anchored at the bottom of that column: a capsule with `fill` +
  hairline, a multiline field that grows to eight lines, Enter sends,
  Shift+Enter inserts a line (on macOS plain Enter is handed to JS through
  `keyDownEvents`, so no newline is inserted), Esc leaves the field, the ink
  send circle becomes Stop while Omi answers, and the draft persists (it is
  orchestrator state). The Live voice control, when present, sits inside the
  capsule.
- **Omnibar in Chat is Search only.** The composer is the one place to type a
  message, so in Chat the omnibar hides the Ask/Search switch and becomes a
  single "Search what you've seen and heard…" control that opens Recall with
  its field focused. Hiding the omnibar entirely was rejected: Search must
  stay one click away and the window would lose its familiar top row. The
  Chat chip in the second row stays selected as the destination indicator
  (it now uses the same chip style as the filters and a distinct `forum`
  glyph). The "Activity" text button is gone: the chips, the settings gear
  and Esc already leave Chat.
- **Empty chat**: a quiet centered greeting ("What's on your mind?"), the
  composer directly under it, and four suggestion chips below. Chips fill the
  draft and focus the composer; they never send. The composer instance is
  kept when the first message moves it to the bottom, so focus survives.

### Both platforms: the transcript

- **Your message**: a quiet bubble on the right, at most 75% of the column
  (`fillSelected` on desktop glass, `surfaceRaised` on phones).
- **Omi's reply**: no bubble, no avatar, full column width, Markdown
  (headings, lists, links, inline code, code blocks with language label, Copy
  and horizontal scroll, rules). The Omi mark appears only as the thinking
  indicator ("Thinking…") and as a small writing indicator under a streaming
  reply.
- **Grouping and time**: consecutive messages from one sender within five
  minutes close up; day separators ("Today", "Yesterday", "Wed, Sep 23", with
  the year when it differs) replace per-message timestamps. The time remains
  as a tooltip and an accessibility hint on each message.
- **Actions**: a small action bar under Omi's replies (Copy; phones use the
  share sheet, which offers Copy). It is always visible on the newest reply;
  on desktop and web it appears on hover or keyboard focus for older replies;
  on phones older replies open the same actions with a long press. A failed
  reply shows an inline notice with Try Again when the wire marks it
  retryable.
- **Streaming and scroll**: text renders progressively; the view follows new
  text only while you are at the end. Scrolling away (wheel, drag, scrollbar,
  keys) stops following and a "Jump to Latest" pill floats above the
  composer. Sending (an explicit submission, or a new local message) resumes
  following. Programmatic scroll events never count as leaving the end.
- **Errors**: a failed send keeps the draft and says so in a notice right
  above the composer (the greeting stays if the chat was empty). A failed
  history read shows "Couldn't Load Chat" with Try Again (a new orchestrator
  `chatHistoryFailed` flag and `retryChatHistory`, which re-runs the history
  read only while nothing is in flight); it never renders as an empty chat.
- **Accessibility**: rows carry roles and labels, the pending reply is a
  polite live region marked busy, a finished (or failed, or stopped) reply is
  announced once, every icon button has a label and tooltip, the action bar
  is reachable by keyboard focus, and all motion stops under Reduce Motion.
- **Host mode** is unchanged: no chat UI issues window commands.

### Phone: a pushed page

Back chevron and "Ask Omi" title in a fixed header; the tab bar and the
Ask/Search switch belong to the parent page. The composer is attached to the
bottom edge inside the surface's safe area and `KeyboardAvoidingView`, grows
to eight lines, and keeps 44-pt targets. Return adds a line on the chat page
(the send circle sends, as in Messages); on the Home dock Return still
submits. On web, Enter sends and Shift+Enter adds a line.

### Out of scope

The legacy chat wire is unchanged (`/v2/messages`, streaming, stop, history,
retry by resending the paired question). FC-CHAT-007 (duplicate on retry),
structured citations and thumbs feedback need wire contracts first.

Visual review states: `desktop-chat-{empty,waiting,streaming,stopped,failed,error,history-error,long}` and `mobile-ask-{empty,waiting,streaming,stopped,failed,error,history-error,long}`, each light and dark; the `long` thread spans yesterday and today. Hover and long-press states are covered by tests, not screenshots.

## History: first pass (wrapper cutover)

The first pass replaced a modal overlay with a stage destination. Its audit
(evidence in the `_ux-final` screenshots at lane base `f1567648`) found: a
gray scrim over Activity with no Chat destination selected; two answer
surfaces (`InlineAskCard` and `ChatOverlay`); the only composer in the top
chrome, outside the transcript; a mobile back control labelled "Close chat"
with Ask/Search mode icons and the tab bar still present on the pushed page;
no local Try Again on desktop failed turns; no Jump to Latest; no per-reply
copy; and no Esc path. It made Chat a destination with its own bottom
composer, made mobile chat a pushed page with Back, kept one message history
across navigation, added Try Again, Jump to Latest and copy, and moved
Search to Recall. Those structural decisions stand.
