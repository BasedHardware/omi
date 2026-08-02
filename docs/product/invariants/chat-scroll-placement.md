# INV-CHAT-2: Chat launch placement and reading position

**Status:** proposed
**Statement:** A newly presented macOS chat transcript starts at the live edge; explicit reader movement then owns the viewport until the reader chooses to return to the live edge.

This invariant was added after a QA regression where Home's launch transition
canceled the delayed bottom placement and the next transcript appearance stayed
at the top.

## MUST

- Start a new app-launch transcript presentation at the bottom/latest content.
- Retry initial bottom placement if the transcript view disappears transiently
  before launch placement settles.
- Treat explicit wheel, trackpad, keyboard, mouse, or prompt-rail movement as
  reader authority and preserve that viewport across later content/layout
  updates.
- Reset launch placement only for a genuinely new conversation presentation.

## MUST NOT

- Mark launch placement complete before the bottom placement has executed.
- Let streaming, layout, or SwiftUI view replacement pull a reader away from
  an explicitly selected position.
- Persist a second scroll-position authority outside the transcript view's
  lifecycle state.

## Surfaces

- macOS main Chat transcript
- macOS Home inline Chat transcript
- macOS shared Task Chat transcript
- macOS floating/notch transcript where the shared scroll behavior is used

## Guard tests

- `desktop/macos/Desktop/Tests/ChatScrollLiveEdgeTests.swift`
- `desktop/macos/Desktop/Tests/DesktopChatDriftGuardTests.swift`
- `desktop/macos/Desktop/Tests/AgentPillLifecycleTests.swift`

## Path globs

- `desktop/macos/Desktop/Sources/MainWindow/Components/ChatMessagesView.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Components/ChatScrollBehavior.swift`
- `desktop/macos/Desktop/Tests/ChatScrollLiveEdgeTests.swift`
- `desktop/macos/Desktop/Tests/DesktopChatDriftGuardTests.swift`

## PR rule

Name `INV-CHAT-2` in the PR body if you touch the path globs above.
