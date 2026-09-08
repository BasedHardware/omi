# Memory Graph Architecture

This package owns the macOS Memories graph and Brain Map. Keep graph policy out of SwiftUI views so layout and selection behavior stay deterministic and testable.

## Owners

- `MemoryGraphPage.swift`: page-level loading and navigation.
- `CanonicalMemoryAtlasView.swift`: view state, gestures, canvas drawing, and automation notifications.
- `MemoryAtlasModels.swift`: shared snapshot, cluster, edge, and render-plan value types.
- `MemoryAtlasRenderPlanner.swift`: derives the visible and interactive render plan from a snapshot and viewport.
- `MemoryAtlasLayoutEngine.swift`: converts backend graph data into the canonical snapshot.
- `MemoryAtlasInspector.swift`: selection hit testing and inspector presentation.
- `MemoryAtlas*Policy.swift`, `MemoryAtlas*Layout.swift`, and caches: single-purpose policy and performance helpers used by the canonical owners above.

## Dependency direction

Backend graph data flows through `MemoryAtlasLayoutEngine`, then `MemoryAtlasRenderPlanner`, then `CanonicalMemoryAtlasView`. UI code may consume models and policies; models, layout, and render planning must not depend on the page or view.

Add a new rule to its existing owner instead of branching in the view. Add a new file only for a distinct policy, state owner, or independently testable transformation; do not add forwarding wrappers or re-export aliases.

## Verification

Run the focused `MemoryAtlas` and `MemoryGraph` Swift tests, then the full desktop suite. Exercise `desktop/macos/e2e/flows/memories.yaml` in a named dev bundle and verify load, selection, navigation back, and the empty/error path.
