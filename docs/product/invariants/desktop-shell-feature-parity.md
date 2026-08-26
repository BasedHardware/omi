# INV-NAV-1: Feature parity across desktop shells

**Status:** locked
**Statement:** Changing desktop navigation chrome must not replace an established product destination with a reduced copy; every shell routes to the same feature-complete owner for that destination.

## MUST

- Route Tasks to the established Tasks page that owns editing, drag/reorder, indentation, keyboard controls, suggested tasks, task details, and task threads.
- Route Conversations to the established Conversations page that owns search, filters, folders, starring, merge, edit, delete, refresh, pagination, and full-row selection.
- Preserve the selected Memory destination while the shell transitions routes, including Brain Map.
- Resolve Brain Map through `MemoryGraphPresentationMode`: canonical-lifecycle users receive the canonical atlas and other established users receive the legacy graph.
- Present top-bar menus above the active page in every shell.
- Keep every destination in `ShellDestination` reachable by the mechanism its `reach` names — a top-bar pill, a chip in Activity's row, or a row of the Settings list a pill reaches. `ShellDestination.unreachable()` must stay empty.
- Keep the chip row and the reachability model reading one value. `Reach.activityChipRow` is checked against `ActivityDestinationChip.reachableHubDestinations`, which is also what the row renders from, so a hub page dropped from the row fails `unreachable()` instead of becoming a page nobody can open. The retired `memoryHubView` case named the hub's switcher but checked only that a pill existed, so deleting that switcher would have stranded three pages with every test still green.
- Keep one rule per control row. Activity's chips all navigate; none narrows the list in place. A row where some chips filter and some leave the page teaches a rule and then breaks it.

## MUST NOT

- Introduce a shell-specific Tasks or Conversations page with a reduced feature set.
- Collapse Brain Map into Memories during route synchronization.
- Let a destination page occlude controls presented by the top navigation layer.

## Surfaces

- macOS chat-first shell
- macOS legacy shell
- Desktop top navigation
- Tasks, Conversations, Memories, Brain Map, and Apps destinations

## Guard tests

- `desktop/macos/Desktop/Tests/TopNavigationBarLayoutTests.swift`
- `desktop/macos/Desktop/Tests/ChatFirstDestinationParityTests.swift`
- `desktop/macos/Desktop/Tests/ChatFirstShellTests.swift`
- `desktop/macos/Desktop/Tests/MemoryHubBrainMapRoutingTests.swift`
- `desktop/macos/Desktop/Tests/TaskReorderMirroredArraysTests.swift`
- `desktop/macos/Desktop/Tests/ConversationMergeSelectionTests.swift`

## Path globs

- `desktop/macos/Desktop/Sources/MainWindow/ChatFirst/**`
- `desktop/macos/Desktop/Sources/MainWindow/DesktopTopBar.swift`
- `desktop/macos/Desktop/Sources/MainWindow/TopNavigationDestinations.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Components/HubDestinationSwitcher.swift`
- `desktop/macos/Desktop/Sources/MainWindow/DesktopHomeView.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/TasksPage.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/ConversationsPage.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Components/ConversationRowView.swift`

## PR rule

Name `INV-NAV-1` in the PR body if you touch the path globs above.
