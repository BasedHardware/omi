# INV-CHAT-2: Chat launch placement and reading position

**Status:** locked
**Statement:** A newly presented macOS chat transcript starts at the live edge; explicit reader movement then owns the viewport until the reader chooses to return to the live edge.

This invariant was added after a QA regression where Home's launch transition
canceled the delayed bottom placement and the next transcript appearance stayed
at the top. A second live QA trace caught a different failure class: lazy row
height estimation changed a rich transcript's document height from about 32,900
to 57,600 points during one upward gesture, which made AppKit preserve the wrong
visual anchor and appear to jump toward the bottom.

## MUST

- Start a new app-launch transcript presentation at the bottom/latest content.
- Retry initial bottom placement if the transcript view disappears transiently
  before launch placement settles.
- Treat explicit wheel, trackpad, keyboard, mouse, or prompt-rail movement as
  reader authority and preserve that viewport across later content/layout
  updates.
- Keep the scroll document's geometry stable throughout reader-owned movement.
  Off-screen transcript rows must have their real measured heights before a
  gesture; fast traversal must not materialize rows that re-estimate the
  document height underneath AppKit.
- Let a reader who deliberately returns to the live edge resume live following.
  The end-of-input signal (AppKit's `didEndLiveScroll`, or the bounded settle
  timer for discrete input) is the authority for "the gesture finished"; a
  wall-clock activity latch must be released by that signal, never consulted as
  a veto against it.
- Reset launch placement only for a genuinely new conversation presentation.

## MUST NOT

- Mark launch placement complete before the bottom placement has executed.
- Let streaming, layout, or SwiftUI view replacement pull a reader away from
  an explicitly selected position.
- Use estimated-height transcript virtualization that changes the scroll
  document's height while a reader traverses already-loaded messages.
- Persist a second scroll-position authority outside the transcript view's
  lifecycle state.
- Let a send the reader did not initiate (poll, sync, or another surface
  flipping `isSending`) seize a viewport while the reader's gesture is still in
  flight.

## Surfaces

- macOS main Chat transcript
- macOS Home inline Chat transcript
- macOS shared Task Chat transcript
- macOS floating/notch transcript where the shared scroll behavior is used

## Guard tests

- `desktop/macos/Desktop/Tests/ChatTranscriptGestureHarnessTests.swift` —
  mounts the real transcript in an `NSHostingView` and drives it with real
  `NSEvent` scroll wheels through `NSApplication.sendEvent`. The coordinator-
  level suites below cannot see a regression that lives in the transcript's own
  `@State`, because they never instantiate the view. It also traverses a
  120-message transcript through repeated fast bursts and asserts that its
  native scroll document height remains stable.
- `desktop/macos/Desktop/Tests/ChatScrollLiveEdgeTests.swift`
- `desktop/macos/Desktop/Tests/DesktopChatDriftGuardTests.swift`
- `desktop/macos/Desktop/Tests/AgentPillLifecycleTests.swift`

## Path globs

- `desktop/macos/Desktop/Sources/MainWindow/Components/ChatMessagesView.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Components/ChatScrollBehavior.swift`
- `desktop/macos/Desktop/Tests/ChatScrollLiveEdgeTests.swift`
- `desktop/macos/Desktop/Tests/DesktopChatDriftGuardTests.swift`
- `desktop/macos/Desktop/Tests/ChatTranscriptGestureHarnessTests.swift`

## PR rule

Name `INV-CHAT-2` in the PR body if you touch the path globs above.
