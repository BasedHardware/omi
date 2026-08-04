import XCTest

@testable import Omi_Computer

/// Regression coverage for the split task surface. The owner-fence behavior of
/// the existing async store path remains covered by TasksStoreOwnerBoundaryTests;
/// these tests pin the bucket and dedup invariants independently of wall-clock
/// or network state.
@MainActor
final class TasksStoreTaskPaginationTests: XCTestCase {
  private let createdAt = Date(timeIntervalSince1970: 1_700_000_000)

  private func task(id: String, dueAt: Date?) -> TaskActionItem {
    TaskActionItem(
      id: id,
      description: id,
      completed: false,
      createdAt: createdAt,
      dueAt: dueAt
    )
  }

  func testInitialSurfaceKeepsEveryDatedBucketAndOnlyOneBoundedNoDeadlinePage() {
    let dated = [
      task(id: "today", dueAt: Date(timeIntervalSince1970: 1_700_000_100)),
      task(id: "tomorrow", dueAt: Date(timeIntervalSince1970: 1_700_086_500)),
      task(id: "later", dueAt: Date(timeIntervalSince1970: 1_800_000_000)),
    ]
    let firstNoDeadlinePage = (0..<100).map { task(id: "undated-\($0)", dueAt: nil) }

    let visible = TasksStore.stableIncompleteTaskSurfaceItems(
      datedTasks: dated,
      noDeadlineTasks: firstNoDeadlinePage
    )

    XCTAssertEqual(visible.count, 103)
    XCTAssertEqual(Set(visible.prefix(3).map(\.id)), Set(["today", "tomorrow", "later"]))
    XCTAssertEqual(visible.filter { $0.dueAt == nil }.count, 100)
  }

  func testNoDeadlinePageFiltersDatedRowsBeforePublication() {
    let page = [
      task(id: "undated-a", dueAt: nil),
      task(id: "dated-leak", dueAt: Date(timeIntervalSince1970: 1_800_000_000)),
      task(id: "undated-b", dueAt: nil),
    ]

    let accepted = TasksStore.noDeadlineOnly(page)

    XCTAssertEqual(accepted.map(\.id), ["undated-a", "undated-b"])
    XCTAssertTrue(accepted.allSatisfy { $0.dueAt == nil })
  }

  func testTaskSurfaceExcludesRetiredRowsFromBothBuckets() {
    let cancelledDated = TaskActionItem(
      id: "cancelled-dated",
      description: "cancelled-dated",
      completed: false,
      createdAt: createdAt,
      dueAt: Date(timeIntervalSince1970: 1_800_000_000),
      taskStatus: "cancelled"
    )
    let deletedUndated = TaskActionItem(
      id: "deleted-undated",
      description: "deleted-undated",
      completed: false,
      createdAt: createdAt,
      deleted: true
    )

    XCTAssertTrue(TasksStore.activeDatedOnly([cancelledDated]).isEmpty)
    XCTAssertTrue(TasksStore.noDeadlineOnly([deletedUndated]).isEmpty)
    XCTAssertEqual(TasksStore.apiDatedBucketCount(in: [cancelledDated]), 1)
    XCTAssertEqual(
      TasksStore.apiDatedBucketCount(in: TasksStore.activeDatedOnly([cancelledDated])),
      0
    )
  }

  func testApiDatedBucketCountIncludesRetiredRowsForNullDueBoundary() {
    let active = task(id: "active", dueAt: Date(timeIntervalSince1970: 1_700_000_100))
    let retired = TaskActionItem(
      id: "retired",
      description: "retired",
      completed: false,
      createdAt: createdAt,
      dueAt: Date(timeIntervalSince1970: 1_800_000_000),
      taskStatus: "cancelled"
    )

    XCTAssertEqual(TasksStore.apiDatedBucketCount(in: [active, retired]), 2)
    XCTAssertEqual(TasksStore.activeDatedOnly([active, retired]).count, 1)
  }

  func testStableDeduplicationKeepsFirstOccurrenceAcrossBuckets() {
    let original = task(id: "duplicate", dueAt: Date(timeIntervalSince1970: 1_700_000_100))
    let duplicate = task(id: "duplicate", dueAt: nil)
    let other = task(id: "other", dueAt: nil)

    let merged = TasksStore.stableIncompleteTaskSurfaceItems(
      datedTasks: [original, original],
      noDeadlineTasks: [duplicate, other, other]
    )

    XCTAssertEqual(merged.map(\.id), ["duplicate", "other"])
    XCTAssertEqual(merged.first?.dueAt, original.dueAt)
  }

  func testEmptyNoDeadlinePageDoesNotCreateAFalseDatedSurface() {
    let dated = [task(id: "dated", dueAt: Date(timeIntervalSince1970: 1_800_000_000))]

    let merged = TasksStore.stableIncompleteTaskSurfaceItems(
      datedTasks: dated,
      noDeadlineTasks: TasksStore.noDeadlineOnly([])
    )

    XCTAssertEqual(merged.map(\.id), ["dated"])
    XCTAssertEqual(merged.filter { $0.dueAt == nil }.count, 0)
  }

  func testStableIncompleteSurfacePreservesEveryNoDeadlineInput() {
    let page = (0..<100).map { task(id: "undated-\($0)", dueAt: nil) }
    let visible = TasksStore.stableIncompleteTaskSurfaceItems(datedTasks: [], noDeadlineTasks: page)

    XCTAssertEqual(visible.count, 100)
    XCTAssertEqual(visible.filter { $0.dueAt == nil }.count, 100)
  }
}
