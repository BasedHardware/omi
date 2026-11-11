# INV-TASK-1: Complete dated task buckets with bounded No Deadline paging

**Status:** locked
**Statement:** The active Tasks view always presents the complete Today, Tomorrow, and Later buckets while loading No Deadline tasks in bounded pages at the true scroll bottom.

## MUST NOT

- Truncate Today, Tomorrow, or Later to make the initial Tasks load smaller.
- Append a dated task from a later pagination page.
- Require a manual load-more control to reach additional No Deadline tasks.
- Preload the entire No Deadline universe solely to render the Tasks page.

## Surfaces

- macOS Tasks page
- task list API and local task projection

## Guard tests

- `desktop/macos/Desktop/Tests/TasksStoreTaskPaginationTests.swift`

## Path globs

- `desktop/macos/Desktop/Sources/MainWindow/Pages/TasksPage.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/ActionItemStorage.swift`
- `desktop/macos/Desktop/Sources/Stores/APIClient+Tasks.swift`
- `desktop/macos/Desktop/Sources/Stores/TasksStore.swift`

## PR rule

Name INV-TASK-1 in the PR body if you touch the path globs above.
