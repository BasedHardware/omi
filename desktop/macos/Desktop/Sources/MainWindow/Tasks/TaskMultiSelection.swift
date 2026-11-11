import Foundation

/// Modifier state supplied by a task row or keyboard event.
///
/// The selection model deliberately receives modifiers as data. This keeps
/// AppKit/SwiftUI event handling out of the selection rules and makes the same
/// semantics available to mouse, trackpad, and keyboard integrations.
struct TaskMultiSelectionModifiers: OptionSet, Sendable {
  let rawValue: UInt8

  static let command = Self(rawValue: 1 << 0)
  static let shift = Self(rawValue: 1 << 1)
}

enum TaskMultiSelectionKeyCommand: Equatable, Sendable {
  case escape
  case selectAll
  case toggleFocused
  case extendFocused
}

/// Deterministic, ID-based selection state for the Tasks surface.
///
/// The model intentionally stores IDs rather than `TaskActionItem` values. A
/// refresh, reorder, filter, or category change can replace task values without
/// invalidating a selection. Callers provide an optional complete task-ID set
/// when rows are deleted or ownership changes so stale IDs can be pruned while
/// filtered-out but still-existing selections remain selected.
struct TaskMultiSelectionState: Equatable, Sendable {
  private(set) var isActive = false
  private(set) var selectedIDs: Set<String> = []
  private(set) var anchorID: String?

  /// Selection order is retained independently from the set so bulk actions
  /// remain stable even when a selected row is temporarily filtered out.
  private var selectionOrder: [String] = []
  private var visibleIDs: [String] = []

  var selectionCount: Int { selectedIDs.count }

  var visibleTaskIDs: [String] { visibleIDs }

  /// Entering the explicit mode never changes an existing selection.
  mutating func enter() {
    isActive = true
  }

  /// Escape and the explicit Select control both use this path. Exiting mode
  /// clears the selection so a later mode entry cannot act on stale rows.
  mutating func exit() {
    isActive = false
    selectedIDs.removeAll()
    selectionOrder.removeAll()
    anchorID = nil
  }

  /// Reconcile the current visual order after filtering, reordering, refresh,
  /// or a category/section change. Without `availableTaskIDs`, hidden rows are
  /// retained. With it, IDs absent from the authoritative task universe are
  /// removed from both selection and anchor state.
  mutating func reconcile(visibleIDs: [String], availableTaskIDs: Set<String>? = nil) {
    let uniqueVisibleIDs = Self.unique(visibleIDs)
    if let availableTaskIDs {
      self.visibleIDs = uniqueVisibleIDs.filter { availableTaskIDs.contains($0) }
      selectedIDs = selectedIDs.intersection(availableTaskIDs)
      selectionOrder = selectionOrder.filter { availableTaskIDs.contains($0) }
      if let currentAnchorID = self.anchorID, !availableTaskIDs.contains(currentAnchorID) {
        self.anchorID = nil
      }
    } else {
      self.visibleIDs = uniqueVisibleIDs
    }

    selectionOrder = Self.unique(selectionOrder.filter { selectedIDs.contains($0) })
    if let currentAnchorID = self.anchorID, !selectedIDs.contains(currentAnchorID) {
      self.anchorID = nil
    }
  }

  /// Applies familiar row-click semantics while explicit multi-select mode is
  /// active:
  ///
  /// - plain click selects only the clicked row;
  /// - Command-click toggles one row;
  /// - Shift-click adds the inclusive range from the anchor to the clicked row.
  ///
  /// Shift takes precedence when both modifiers are present. A range whose
  /// anchor is not visible (for example, after filtering) falls back to a
  /// deterministic single-row selection rather than guessing across sections.
  @discardableResult
  mutating func click(
    _ taskID: String,
    modifiers: TaskMultiSelectionModifiers = [],
    visibleIDs: [String]
  ) -> Bool {
    guard isActive else { return false }
    reconcile(visibleIDs: visibleIDs)
    guard self.visibleIDs.contains(taskID) else { return false }

    if modifiers.contains(.shift) {
      return extendSelection(to: taskID)
    }

    if modifiers.contains(.command) {
      anchorID = taskID
      if selectedIDs.contains(taskID) {
        remove(taskID)
      } else {
        add(taskID)
      }
      return true
    }

    let changed = selectedIDs != Set([taskID])
    replaceSelection(with: [taskID], anchor: taskID)
    return changed
  }

  /// Selects all currently visible rows, leaving selected rows hidden by a
  /// filter untouched. This is the scope expected from Command+A in a filtered
  /// task list.
  mutating func selectAll(visibleIDs: [String]) {
    guard isActive else { return }
    reconcile(visibleIDs: visibleIDs)
    for id in self.visibleIDs {
      add(id)
    }
    if anchorID == nil {
      anchorID = self.visibleIDs.last
    }
  }

  /// Toggles only the visible scope. This is useful for a toolbar Select All
  /// control while preserving selections that are currently filtered out.
  mutating func toggleSelectAll(visibleIDs: [String]) {
    guard isActive else { return }
    reconcile(visibleIDs: visibleIDs)
    guard !self.visibleIDs.isEmpty else { return }
    if self.visibleIDs.allSatisfy({ selectedIDs.contains($0) }) {
      for id in self.visibleIDs {
        remove(id)
      }
      if let anchorID, self.visibleIDs.contains(anchorID) {
        self.anchorID = nil
      }
    } else {
      selectAll(visibleIDs: self.visibleIDs)
    }
  }

  /// Clears the complete selection while keeping explicit multi-select mode
  /// active. The Tasks toolbar uses this for an honest "Deselect All": hidden
  /// paginated rows must not remain selected after the count returns to zero.
  mutating func deselectAll() {
    guard isActive else { return }
    selectedIDs.removeAll()
    selectionOrder.removeAll()
    anchorID = nil
  }

  /// Removes rows that completed a bulk action or disappeared from the store.
  /// The mode remains active when other rows or failures remain selected.
  mutating func removeSelectedIDs(_ taskIDs: Set<String>) {
    selectedIDs.subtract(taskIDs)
    selectionOrder.removeAll { taskIDs.contains($0) }
    if let anchorID, taskIDs.contains(anchorID) {
      self.anchorID = nil
    }
  }

  /// Returns selected IDs in the supplied visual order, followed by selected
  /// IDs that are hidden from that order in their original selection order.
  /// This is the canonical input order for bulk operations.
  func selectedIDs(in order: [String]? = nil) -> [String] {
    let preferredOrder = Self.unique(order ?? visibleIDs)
    var result: [String] = []
    var seen = Set<String>()
    for id in preferredOrder where selectedIDs.contains(id) && seen.insert(id).inserted {
      result.append(id)
    }
    for id in selectionOrder where selectedIDs.contains(id) && seen.insert(id).inserted {
      result.append(id)
    }
    return result
  }

  /// Handles the keyboard surface that TasksPage can map from NSEvent or
  /// SwiftUI key presses. Arrow navigation stays owned by the page; it calls
  /// `extendFocused` for Shift+Arrow and `toggleFocused` for Space/Enter.
  @discardableResult
  mutating func handleKeyboard(
    _ command: TaskMultiSelectionKeyCommand,
    focusedID: String? = nil,
    visibleIDs: [String]
  ) -> Bool {
    guard isActive else { return false }
    switch command {
    case .escape:
      exit()
      return true
    case .selectAll:
      selectAll(visibleIDs: visibleIDs)
      return true
    case .toggleFocused:
      guard let focusedID else { return false }
      return click(focusedID, modifiers: .command, visibleIDs: visibleIDs)
    case .extendFocused:
      guard let focusedID else { return false }
      return click(focusedID, modifiers: .shift, visibleIDs: visibleIDs)
    }
  }

  @discardableResult
  private mutating func extendSelection(to taskID: String) -> Bool {
    guard let anchorID,
      let anchorIndex = visibleIDs.firstIndex(of: anchorID),
      let targetIndex = visibleIDs.firstIndex(of: taskID)
    else {
      replaceSelection(with: [taskID], anchor: taskID)
      return true
    }

    let lower = min(anchorIndex, targetIndex)
    let upper = max(anchorIndex, targetIndex)
    for index in lower...upper {
      add(visibleIDs[index])
    }
    return true
  }

  private mutating func replaceSelection(with ids: [String], anchor: String?) {
    let uniqueIDs = Self.unique(ids)
    selectedIDs = Set(uniqueIDs)
    selectionOrder = uniqueIDs
    anchorID = anchor
  }

  private mutating func add(_ taskID: String) {
    guard selectedIDs.insert(taskID).inserted else { return }
    selectionOrder.append(taskID)
  }

  private mutating func remove(_ taskID: String) {
    selectedIDs.remove(taskID)
    selectionOrder.removeAll { $0 == taskID }
    if anchorID == taskID {
      anchorID = nil
    }
  }

  private static func unique(_ ids: [String]) -> [String] {
    var seen = Set<String>()
    return ids.filter { !$0.isEmpty && seen.insert($0).inserted }
  }
}
