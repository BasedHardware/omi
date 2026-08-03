# INV-NAV-1: Feature parity across desktop shells

**Status:** proposed
**Statement:** Changing desktop navigation chrome must not replace an established product destination with a reduced copy; every shell routes to the same feature-complete owner for that destination.

## MUST

- Route Tasks to the established Tasks page that owns editing, drag/reorder, indentation, keyboard controls, suggested tasks, task details, and task threads.
- Route Conversations to the established Conversations page that owns search, filters, folders, starring, merge, edit, delete, refresh, pagination, and full-row selection.
- Preserve the selected Memory destination while the shell transitions routes, including Brain Map.
- Resolve Brain Map through `MemoryGraphPresentationMode`: canonical-lifecycle users receive the canonical atlas and other established users receive the legacy graph.
- Present top-bar menus above the active page in every shell.

## MUST NOT

- Introduce a shell-specific Tasks or Conversations page with a reduced feature set.
- Collapse Brain Map into Memories during route synchronization.
- Let a destination page occlude controls presented by the top navigation layer.

## Surfaces

- macOS chat-first shell
- macOS legacy shell
- Desktop top navigation
- Tasks, Conversations, Memories, and Brain Map destinations

## Guard tests

- `desktop/macos/Desktop/Tests/ChatFirstDestinationParityTests.swift`
- `desktop/macos/Desktop/Tests/ChatFirstShellTests.swift`
- `desktop/macos/Desktop/Tests/MemoryHubBrainMapRoutingTests.swift`
- `desktop/macos/Desktop/Tests/TaskReorderMirroredArraysTests.swift`
- `desktop/macos/Desktop/Tests/ConversationMergeSelectionTests.swift`

## Path globs

- `desktop/macos/Desktop/Sources/MainWindow/ChatFirst/**`
- `desktop/macos/Desktop/Sources/MainWindow/DesktopTopBar.swift`
- `desktop/macos/Desktop/Sources/MainWindow/DesktopHomeView.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/TasksPage.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/ConversationsPage.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Components/ConversationRowView.swift`

## PR rule

Name `INV-NAV-1` in the PR body if you touch the path globs above.
