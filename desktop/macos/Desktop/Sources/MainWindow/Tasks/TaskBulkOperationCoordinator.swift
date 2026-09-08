import Foundation

enum TaskBulkAction: Equatable, Sendable {
  case indent
  case outdent
  case delete
  case markDone
  case reopen
  case move(categoryID: String)
}

struct TaskBulkTarget {
  let task: TaskActionItem
  /// The effective UI indent, including any unsaved TasksViewModel override.
  let indentLevel: Int

  init(task: TaskActionItem, indentLevel: Int? = nil) {
    self.task = task
    self.indentLevel = min(max(indentLevel ?? task.indentLevel ?? 0, 0), 3)
  }

  var id: String { task.id }
}

enum TaskBulkTaskStatus: Equatable, Sendable {
  case succeeded
  case skipped(reason: String)
  case failed(message: String)
}

struct TaskBulkTaskResult: Equatable, Sendable {
  let taskID: String
  let status: TaskBulkTaskStatus
}

struct TaskBulkOperationReport: Equatable, Sendable {
  let action: TaskBulkAction
  let orderedTaskIDs: [String]
  let results: [TaskBulkTaskResult]
  let confirmationRequested: Bool
  let confirmationRequired: Bool
  let cancelled: Bool
  let rejected: Bool

  var succeededIDs: [String] {
    results.compactMap { result in
      if case .succeeded = result.status { return result.taskID }
      return nil
    }
  }

  var skippedIDs: [String] {
    results.compactMap { result in
      if case .skipped = result.status { return result.taskID }
      return nil
    }
  }

  var failures: [TaskBulkTaskResult] {
    results.filter {
      if case .failed = $0.status { return true }
      return false
    }
  }

  var completedWithoutErrors: Bool {
    !cancelled && !confirmationRequired && !rejected && failures.isEmpty
  }
}

typealias TaskBulkTaskMutation = @MainActor (TaskActionItem) async throws -> Void
typealias TaskBulkCompletionMutation = @MainActor (TaskActionItem, Bool) async throws -> Void
typealias TaskBulkMoveMutation = @MainActor (TaskActionItem, String) async throws -> Void
typealias TaskBulkDeleteConfirmation = @MainActor ([TaskBulkTarget]) async -> Bool

/// Operation closures are the integration boundary for TasksPage. The
/// coordinator owns selection snapshotting, applicability, ordering, one-time
/// delete confirmation, re-entrancy, and per-row error reporting; the page
/// supplies the existing TasksViewModel/TasksStore mutations.
struct TaskBulkOperationHooks {
  var indent: TaskBulkTaskMutation?
  var outdent: TaskBulkTaskMutation?
  var setCompletion: TaskBulkCompletionMutation?
  var delete: TaskBulkTaskMutation?
  var move: TaskBulkMoveMutation?

  init(
    indent: TaskBulkTaskMutation? = nil,
    outdent: TaskBulkTaskMutation? = nil,
    setCompletion: TaskBulkCompletionMutation? = nil,
    delete: TaskBulkTaskMutation? = nil,
    move: TaskBulkMoveMutation? = nil
  ) {
    self.indent = indent
    self.outdent = outdent
    self.setCompletion = setCompletion
    self.delete = delete
    self.move = move
  }
}

@MainActor
final class TaskBulkOperationCoordinator {
  private let hooks: TaskBulkOperationHooks
  private(set) var isExecuting = false

  init(hooks: TaskBulkOperationHooks) {
    self.hooks = hooks
  }

  /// Executes one action against one stable, de-duplicated task snapshot.
  /// Completion changes use an explicit desired state, never a toggle, so one
  /// selected row cannot be flipped twice by a bulk operation.
  func perform(
    _ action: TaskBulkAction,
    targets: [TaskBulkTarget],
    confirmDelete: TaskBulkDeleteConfirmation? = nil
  ) async -> TaskBulkOperationReport {
    let stableTargets = Self.stableTargets(targets)
    guard !isExecuting else {
      return Self.report(
        action: action,
        targets: stableTargets,
        results: stableTargets.map {
          TaskBulkTaskResult(taskID: $0.id, status: .failed(message: "Another task operation is already running."))
        },
        confirmationRequested: false,
        confirmationRequired: false,
        cancelled: false,
        rejected: true
      )
    }

    isExecuting = true
    defer { isExecuting = false }

    guard !stableTargets.isEmpty else {
      return Self.report(
        action: action,
        targets: [],
        results: [],
        confirmationRequested: false,
        confirmationRequired: false,
        cancelled: false,
        rejected: false
      )
    }

    var confirmationRequested = false
    if action == .delete {
      guard let confirmDelete else {
        return Self.report(
          action: action,
          targets: stableTargets,
          results: [],
          confirmationRequested: false,
          confirmationRequired: true,
          cancelled: false,
          rejected: false
        )
      }
      confirmationRequested = true
      guard await confirmDelete(stableTargets) else {
        return Self.report(
          action: action,
          targets: stableTargets,
          results: [],
          confirmationRequested: true,
          confirmationRequired: false,
          cancelled: true,
          rejected: false
        )
      }
    }

    var results: [TaskBulkTaskResult] = []
    for target in stableTargets {
      if let reason = Self.skipReason(for: action, target: target) {
        results.append(TaskBulkTaskResult(taskID: target.id, status: .skipped(reason: reason)))
        continue
      }

      do {
        try await apply(action, to: target)
        results.append(TaskBulkTaskResult(taskID: target.id, status: .succeeded))
      } catch {
        results.append(
          TaskBulkTaskResult(
            taskID: target.id,
            status: .failed(message: Self.message(for: error))
          )
        )
      }
    }

    return Self.report(
      action: action,
      targets: stableTargets,
      results: results,
      confirmationRequested: confirmationRequested,
      confirmationRequired: false,
      cancelled: false,
      rejected: false
    )
  }

  private func apply(_ action: TaskBulkAction, to target: TaskBulkTarget) async throws {
    switch action {
    case .indent:
      guard let indent = hooks.indent else { throw TaskBulkOperationError.notConfigured(action) }
      try await indent(target.task)
    case .outdent:
      guard let outdent = hooks.outdent else { throw TaskBulkOperationError.notConfigured(action) }
      try await outdent(target.task)
    case .delete:
      guard let delete = hooks.delete else { throw TaskBulkOperationError.notConfigured(action) }
      try await delete(target.task)
    case .markDone:
      guard let setCompletion = hooks.setCompletion else { throw TaskBulkOperationError.notConfigured(action) }
      try await setCompletion(target.task, true)
    case .reopen:
      guard let setCompletion = hooks.setCompletion else { throw TaskBulkOperationError.notConfigured(action) }
      try await setCompletion(target.task, false)
    case .move(let categoryID):
      guard let move = hooks.move else { throw TaskBulkOperationError.notConfigured(action) }
      try await move(target.task, categoryID)
    }
  }

  private static func skipReason(for action: TaskBulkAction, target: TaskBulkTarget) -> String? {
    switch action {
    case .indent where target.indentLevel >= 3:
      return "Already at the maximum indent level."
    case .outdent where target.indentLevel <= 0:
      return "Already at the root indent level."
    case .markDone where target.task.completed:
      return "Already marked done."
    case .reopen where !target.task.completed:
      return "Already open."
    default:
      return nil
    }
  }

  private static func stableTargets(_ targets: [TaskBulkTarget]) -> [TaskBulkTarget] {
    var seen = Set<String>()
    return targets.filter { !$0.id.isEmpty && seen.insert($0.id).inserted }
  }

  private static func report(
    action: TaskBulkAction,
    targets: [TaskBulkTarget],
    results: [TaskBulkTaskResult],
    confirmationRequested: Bool,
    confirmationRequired: Bool,
    cancelled: Bool,
    rejected: Bool
  ) -> TaskBulkOperationReport {
    TaskBulkOperationReport(
      action: action,
      orderedTaskIDs: targets.map(\.id),
      results: results,
      confirmationRequested: confirmationRequested,
      confirmationRequired: confirmationRequired,
      cancelled: cancelled,
      rejected: rejected
    )
  }

  private static func message(for error: Error) -> String {
    if let localized = error as? LocalizedError, let description = localized.errorDescription {
      return description
    }
    return error.localizedDescription
  }
}

private enum TaskBulkOperationError: LocalizedError {
  case notConfigured(TaskBulkAction)

  var errorDescription: String? {
    switch self {
    case .notConfigured(let action):
      return "No integration hook is configured for \(action)."
    }
  }
}
