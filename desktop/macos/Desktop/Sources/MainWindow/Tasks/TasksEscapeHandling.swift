extension TasksViewModel {
  func handleEscape() -> Bool {
    if multiSelection.isActive {
      mutateMultiSelection { $0.exit() }
      return true
    }
    if isInlineCreating {
      isInlineCreating = false
      inlineCreateAfterTaskId = nil
      return true
    }
    if keyboardSelectedTaskId != nil {
      keyboardSelectedTaskId = nil
      return true
    }
    return false
  }
}
