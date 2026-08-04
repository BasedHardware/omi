import XCTest

@testable import Omi_Computer

@MainActor
final class TaskBulkOperationCoordinatorTests: XCTestCase {
  func testMarkDoneUsesExplicitStateOnceAndSkipsAlreadyDoneRows() async {
    let open = task(id: "open", completed: false)
    let done = task(id: "done", completed: true)
    var calls: [(String, Bool)] = []

    let coordinator = TaskBulkOperationCoordinator(
      hooks: TaskBulkOperationHooks(
        setCompletion: { task, completed in
          calls.append((task.id, completed))
        })
    )

    let report = await coordinator.perform(
      .markDone,
      targets: [TaskBulkTarget(task: open), TaskBulkTarget(task: open), TaskBulkTarget(task: done)]
    )

    XCTAssertEqual(report.orderedTaskIDs, ["open", "done"], "duplicate selected IDs are de-duplicated")
    XCTAssertEqual(report.succeededIDs, ["open"])
    XCTAssertEqual(report.skippedIDs, ["done"])
    XCTAssertEqual(calls.count, 1)
    XCTAssertEqual(calls[0].0, "open")
    XCTAssertTrue(calls[0].1)
  }

  func testPartialFailuresKeepStableOrderAndReportTheFailedRows() async {
    enum FixtureError: Error { case rejected }
    let first = task(id: "first", completed: false)
    let second = task(id: "second", completed: false)
    let third = task(id: "third", completed: false)
    var calls: [String] = []

    let coordinator = TaskBulkOperationCoordinator(
      hooks: TaskBulkOperationHooks(
        indent: { task in
          calls.append(task.id)
          if task.id == "second" { throw FixtureError.rejected }
        })
    )

    let report = await coordinator.perform(
      .indent,
      targets: [
        TaskBulkTarget(task: first, indentLevel: 0),
        TaskBulkTarget(task: second, indentLevel: 1),
        TaskBulkTarget(task: third, indentLevel: 3),
      ]
    )

    XCTAssertEqual(calls, ["first", "second"], "the max-indent row is skipped before mutation")
    XCTAssertEqual(report.succeededIDs, ["first"])
    XCTAssertEqual(report.failures.map(\.taskID), ["second"])
    XCTAssertEqual(report.skippedIDs, ["third"])
    XCTAssertFalse(report.completedWithoutErrors)
  }

  func testDeleteUsesExactlyOneConfirmationAndCanBeCancelledSafely() async {
    let first = task(id: "first", completed: false)
    let second = task(id: "second", completed: false)
    var confirmationCalls = 0
    var deleteCalls: [String] = []

    let coordinator = TaskBulkOperationCoordinator(
      hooks: TaskBulkOperationHooks(
        delete: { task in
          deleteCalls.append(task.id)
        })
    )

    let report = await coordinator.perform(
      .delete,
      targets: [TaskBulkTarget(task: first), TaskBulkTarget(task: second)],
      confirmDelete: { _ in
        confirmationCalls += 1
        return false
      }
    )

    XCTAssertTrue(report.cancelled)
    XCTAssertTrue(report.confirmationRequested)
    XCTAssertEqual(confirmationCalls, 1)
    XCTAssertTrue(deleteCalls.isEmpty, "a cancelled destructive operation never mutates")
  }

  func testDeleteRequiresAConfirmationHookAndReportsPerRowErrors() async {
    let first = task(id: "first", completed: false)
    let second = task(id: "second", completed: false)
    var deleteCalls: [String] = []

    let coordinator = TaskBulkOperationCoordinator(
      hooks: TaskBulkOperationHooks(
        delete: { task in
          deleteCalls.append(task.id)
          if task.id == "second" {
            throw NSError(domain: "TaskBulk", code: 7, userInfo: [NSLocalizedDescriptionKey: "delete failed"])
          }
        })
    )

    let missingConfirmation = await coordinator.perform(
      .delete,
      targets: [TaskBulkTarget(task: first)]
    )
    XCTAssertTrue(missingConfirmation.confirmationRequired)
    XCTAssertTrue(deleteCalls.isEmpty)

    let report = await coordinator.perform(
      .delete,
      targets: [TaskBulkTarget(task: first), TaskBulkTarget(task: second)],
      confirmDelete: { _ in true }
    )
    XCTAssertEqual(deleteCalls, ["first", "second"])
    XCTAssertEqual(report.succeededIDs, ["first"])
    XCTAssertEqual(report.failures.map(\.taskID), ["second"])
    if case .failed(let message) = report.failures[0].status {
      XCTAssertEqual(message, "delete failed")
    } else {
      XCTFail("second delete must be reported as failed")
    }
  }

  private func task(id: String, completed: Bool) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: id,
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 0)
    )
  }
}
