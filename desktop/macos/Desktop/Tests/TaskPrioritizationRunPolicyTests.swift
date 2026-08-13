import XCTest

@testable import Omi_Computer

final class TaskPrioritizationRunPolicyTests: XCTestCase {
  private let policy = TaskPrioritizationRunPolicy(
    successfulRunInterval: 3600,
    failedAttemptBackoff: 3600,
    maxTasksPerRequest: 100,
    maxRequestsPerRun: 2
  )

  func testLargeCatalogProducesOnlyBoundedRequests() {
    let tasks = Array(0..<1_520)

    let window = policy.window(from: tasks, startingAt: 0)
    let requests = policy.requestBatches(from: window.items)

    XCTAssertEqual(window.items, Array(0..<200))
    XCTAssertEqual(window.nextStartIndex, 200)
    XCTAssertEqual(requests.count, 2)
    XCTAssertTrue(requests.allSatisfy { $0.count <= 100 })
    XCTAssertEqual(requests.flatMap { $0 }, window.items)
  }

  func testCursorRotatesThroughTailThenWrapsToBeginning() {
    let tasks = Array(0..<1_520)

    let tail = policy.window(from: tasks, startingAt: 1_400)

    XCTAssertEqual(tail.items, Array(1_400..<1_520))
    XCTAssertEqual(tail.startIndex, 1_400)
    XCTAssertEqual(tail.endIndex, 1_520)
    XCTAssertEqual(tail.nextStartIndex, 0)
    XCTAssertEqual(policy.requestBatches(from: tail.items).map(\.count), [100, 20])
  }

  func testCursorFromLargerPreviousCatalogRestartsSafely() {
    let tasks = Array(0..<50)

    let window = policy.window(from: tasks, startingAt: 1_400)

    XCTAssertEqual(window.items, tasks)
    XCTAssertEqual(window.startIndex, 0)
    XCTAssertEqual(window.nextStartIndex, 0)
  }

  func testFailedAttemptCannotRetryAtFiveMinuteSchedulerCheck() {
    let now = Date(timeIntervalSince1970: 10_000)
    let fiveMinutesAgo = now.addingTimeInterval(-300)

    XCTAssertFalse(
      policy.shouldStartScheduledRun(
        now: now,
        lastSuccessfulRun: nil,
        lastAttempt: fiveMinutesAgo
      )
    )
  }

  func testFailedAttemptCanRetryAfterBackoff() {
    let now = Date(timeIntervalSince1970: 10_000)
    let oneHourAgo = now.addingTimeInterval(-3600)

    XCTAssertTrue(
      policy.shouldStartScheduledRun(
        now: now,
        lastSuccessfulRun: nil,
        lastAttempt: oneHourAgo
      )
    )
  }

  func testRecentSuccessStillControlsHourlyCadence() {
    let now = Date(timeIntervalSince1970: 10_000)

    XCTAssertFalse(
      policy.shouldStartScheduledRun(
        now: now,
        lastSuccessfulRun: now.addingTimeInterval(-1_800),
        lastAttempt: now.addingTimeInterval(-7_200)
      )
    )
  }
}
