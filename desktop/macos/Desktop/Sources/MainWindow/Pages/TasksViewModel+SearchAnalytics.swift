import Foundation

extension TasksViewModel {
  func selectTaskFromSearch(_ task: TaskActionItem) {
    SearchAnalytics.resultOpened(
      surface: .tasks, resultIndex: searchResults.firstIndex { $0.id == task.id },
      searchIsActive: !normalizedSearchQuery.isEmpty)
    keyboardSelectedTaskId = task.id
  }
}
