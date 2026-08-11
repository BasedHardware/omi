import AppKit

@MainActor
extension TasksViewModel {
  func invalidateSelectionOperation() {
    selectionOperationGeneration &+= 1
    isSelectingAllTasks = false
    activeSelectionAllOperationToken = nil
    bulkDeleteInFlight = false
    activeBulkDeleteOperationToken = nil
  }

  func clearMultiSelectionForScopeChange() {
    invalidateSelectionOperation()
    guard multiSelection.isActive else { return }
    mutateMultiSelection(fencesOperation: false) { state in
      state.deselectAll()
    }
    authoritativeSelectionTaskIDs.removeAll()
    selectedAllScope = nil
    selectedAllScopeTaskIDs.removeAll()
    bulkTaskErrorMessage = nil
  }

  func mutateMultiSelection(
    fencesOperation: Bool = true,
    _ mutation: (inout TaskMultiSelectionState) -> Void
  ) {
    var next = multiSelection
    mutation(&next)
    if fencesOperation, next != multiSelection {
      selectionOperationGeneration &+= 1
    }
    multiSelection = next
  }

  func reconcileMultiSelection() {
    guard multiSelection.isActive else { return }
    let visibleIDs = visibleTaskIDsForSelection
    mutateMultiSelection(fencesOperation: false) { state in
      state.reconcile(visibleIDs: visibleIDs, availableTaskIDs: allAvailableTaskIDs)
    }
  }

  func toggleMultiSelectMode() {
    invalidateSelectionOperation()
    let wasActive = multiSelection.isActive
    mutateMultiSelection(fencesOperation: false) { state in
      if state.isActive {
        state.exit()
      } else {
        state.enter()
        state.reconcile(visibleIDs: visibleTaskIDsForSelection)
      }
    }
    if wasActive {
      authoritativeSelectionTaskIDs.removeAll()
      selectedAllScope = nil
      selectedAllScopeTaskIDs.removeAll()
      bulkTaskErrorMessage = nil
    }
  }

  func toggleTaskSelection(
    _ task: TaskActionItem,
    modifiers: TaskMultiSelectionModifiers = .command
  ) {
    mutateMultiSelection { state in
      _ = state.click(task.id, modifiers: modifiers, visibleIDs: visibleTaskIDsForSelection)
    }
  }

  private func taskIDsForSelectionScope(_ scope: SelectionScope) async throws -> [String] {
    switch scope {
    case .search:
      // Search already queries the complete local FTS result set and only caps
      // presentation afterward. Select the full result, not its first 100 rows.
      return allFilteredDisplayTasks.map(\.id)
    case .taskBucket(let completed):
      return try await selectionSnapshotLoader(completed)
    }
  }

  func selectAllTasks() async {
    guard multiSelection.isActive, !isSelectingAllTasks, !bulkDeleteInFlight else { return }
    selectionOperationGeneration &+= 1
    let scope = currentSelectionScope
    let operationGeneration = selectionOperationGeneration
    selectionAllOperationToken &+= 1
    let operationToken = selectionAllOperationToken
    activeSelectionAllOperationToken = operationToken
    isSelectingAllTasks = true
    bulkTaskErrorMessage = nil
    defer {
      if activeSelectionAllOperationToken == operationToken {
        activeSelectionAllOperationToken = nil
        isSelectingAllTasks = false
      }
    }

    do {
      let taskIDs = try await taskIDsForSelectionScope(scope)
      guard
        selectionOperationGeneration == operationGeneration,
        multiSelection.isActive,
        currentSelectionScope == scope
      else { return }

      authoritativeSelectionTaskIDs.formUnion(taskIDs)
      selectedAllScope = scope
      selectedAllScopeTaskIDs = Set(taskIDs)
      mutateMultiSelection { state in
        state.selectAll(visibleIDs: taskIDs)
      }
    } catch {
      guard
        selectionOperationGeneration == operationGeneration,
        multiSelection.isActive,
        currentSelectionScope == scope
      else { return }
      bulkTaskErrorMessage =
        "Could not reach your complete task list. No additional tasks were selected. Please retry."
      logError("TasksViewModel: Failed to select complete task scope", error: error)
    }
  }

  func toggleSelectAllTasks() async {
    if allTasksInSelectionScopeSelected {
      mutateMultiSelection { state in
        state.deselectAll()
      }
      authoritativeSelectionTaskIDs.removeAll()
      selectedAllScope = nil
      selectedAllScopeTaskIDs.removeAll()
      return
    }
    await selectAllTasks()
  }

  var allTasksInSelectionScopeSelected: Bool {
    guard selectedAllScope == currentSelectionScope, !selectedAllScopeTaskIDs.isEmpty else {
      return false
    }
    return selectedAllScopeTaskIDs.allSatisfy { multiSelection.selectedIDs.contains($0) }
  }

  func deleteSelectedTasks() async {
    guard !bulkDeleteInFlight, !isSelectingAllTasks else { return }
    let orderedIDs = multiSelection.selectedIDs(in: visibleTaskIDsForSelection)
    guard !orderedIDs.isEmpty else { return }
    guard bulkDeleteConfirmation(orderedIDs.count) else { return }
    selectionOperationGeneration &+= 1
    let operationGeneration = selectionOperationGeneration
    let scope = currentSelectionScope
    let ownerGeneration = selectionOwnerGeneration
    bulkDeleteOperationToken &+= 1
    let operationToken = bulkDeleteOperationToken
    activeBulkDeleteOperationToken = operationToken
    bulkDeleteInFlight = true
    defer {
      if activeBulkDeleteOperationToken == operationToken {
        activeBulkDeleteOperationToken = nil
        bulkDeleteInFlight = false
      }
    }

    for id in orderedIDs {
      removeFromDisplay(id)
    }
    let outcome = await bulkDeleteOperation(orderedIDs)
    guard
      selectionOperationGeneration == operationGeneration,
      multiSelection.isActive,
      currentSelectionScope == scope,
      selectionOwnerGeneration == ownerGeneration
    else {
      if currentSelectionScope == scope, selectionOwnerGeneration == ownerGeneration {
        recomputeDisplayCaches()
      }
      return
    }
    switch outcome {
    case .localFailure:
      recomputeDisplayCaches()
      bulkTaskErrorMessage =
        "The tasks could not be deleted from this Mac. Nothing was deleted from your account. Please retry."
      return
    case .remoteFailure(let confirmedIDs):
      for id in orderedIDs {
        chatCoordinator?.purgeState(for: id)
      }
      let localOnlyIDs = Set(
        orderedIDs.filter { ActionItemTaskIdentity(surfacedId: $0).isLocalOnly }
      )
      let settledIDs = confirmedIDs.union(localOnlyIDs)
      if !settledIDs.isEmpty {
        mutateMultiSelection { state in
          state.removeSelectedIDs(settledIDs)
        }
        authoritativeSelectionTaskIDs.subtract(settledIDs)
        selectedAllScopeTaskIDs.subtract(settledIDs)
        if selectedAllScopeTaskIDs.isEmpty {
          selectedAllScope = nil
        }
      }
      bulkTaskErrorMessage =
        "The tasks were removed from this Mac, but could not be deleted from your account. "
        + "They remain selected so you can retry."
      return
    case .ownerChanged:
      return
    case .deletedEverywhere:
      for id in orderedIDs {
        chatCoordinator?.purgeState(for: id)
      }
    }

    mutateMultiSelection { state in
      state.removeSelectedIDs(Set(orderedIDs))
      if state.selectionCount == 0 {
        state.exit()
      }
    }
    let deletedIDs = Set(orderedIDs)
    authoritativeSelectionTaskIDs.subtract(deletedIDs)
    selectedAllScopeTaskIDs.subtract(deletedIDs)
    if selectedAllScopeTaskIDs.isEmpty {
      selectedAllScope = nil
    }
  }

  static func confirmBulkDelete(count: Int) -> Bool {
    let alert = NSAlert()
    alert.messageText = "Delete \(count) tasks?"
    alert.informativeText = "This cannot be undone."
    alert.alertStyle = .warning
    alert.addButton(withTitle: "Delete")
    alert.addButton(withTitle: "Cancel")
    return alert.runModal() == .alertFirstButtonReturn
  }
}
