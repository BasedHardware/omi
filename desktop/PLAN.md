# Implementation Plan: Flutter Feature Parity for Tasks

## Features to Implement

### 1. Drag-and-Drop Reordering
**Goal:** Allow users to reorder tasks within categories by dragging

**Implementation:**
- Add `@State` for tracking drag state in TaskRow
- Use SwiftUI's `.draggable()` and `.dropDestination()` modifiers (macOS 13+)
- Store custom order per category in UserDefaults (like Flutter's SharedPreferences)
- Add `categoryOrder: [TaskCategory: [String]]` to TasksViewModel
- Visual feedback: opacity reduction on dragged item, highlight on drop target

**Files to modify:**
- `TasksPage.swift` - Add drag/drop to TaskRow and TaskCategorySection
- `TasksViewModel` - Add order persistence and reorder methods

### 2. ~~Swipe-to-Delete~~ (SKIPPED - not suitable for macOS)
**Reason:** Swipe gestures are designed for touchscreens. On macOS, hover-to-reveal delete button already exists and works better with mouse/trackpad.

### 3. Task Indentation (Sub-tasks)
**Goal:** Visual hierarchy with 0-3 indent levels

**Implementation:**
- Add `@State var indentLevels: [String: Int]` to TasksViewModel (task ID -> indent level)
- Visual: 28pt indent per level + vertical line indicator
- Horizontal swipe on indented items to change indent level
- Store in UserDefaults for persistence

**Files to modify:**
- `TasksPage.swift` - Add indent visual and gesture handling
- `TasksViewModel` - Add indent state management

## Implementation Order

1. **Phase 1: Drag-and-Drop** (highest impact)
2. **Phase 2: Swipe-to-Delete**
3. **Phase 3: Task Indentation**

## Technical Notes

- No backend changes needed - all state stored locally like Flutter
- Must handle conflict with multi-select mode (disable drag in multi-select)
- Disable drag-drop when not sorting by Due Date (only makes sense for categorized view)
- Use spring animations for smooth UX
