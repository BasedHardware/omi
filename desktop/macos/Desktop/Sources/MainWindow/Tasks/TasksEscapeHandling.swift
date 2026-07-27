extension TasksViewModel {
  func handleEscape() -> Bool {
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
