import XCTest

@testable import Omi_Computer

@MainActor
final class TasksStoreMergeWithoutAddingTests: XCTestCase {

  private func task(id: String, description: String) -> TaskActionItem {
    TaskActionItem(id: id, description: description, completed: false, createdAt: Date(timeIntervalSince1970: 0))
  }

  /// Regression for the #6506 crash class: a source list with duplicate ids must not
  /// trap. `Dictionary(uniqueKeysWithValues:)` crashed here; the lookup now uses
  /// last-write-wins.
  func testDuplicateSourceIdsDoNotCrashAndLastWriteWins() {
    let source = [
      task(id: "a", description: "old"),
      task(id: "a", description: "new"),
      task(id: "b", description: "b"),
    ]
    let current = [task(id: "a", description: "current-a")]

    let merged = TasksStore.mergeWithoutAdding(source: source, current: current)

    // Only ids already present in `current` are kept, updated from the source.
    XCTAssertEqual(merged.count, 1)
    XCTAssertEqual(merged.first?.id, "a")
    // Last occurrence of the duplicate id wins.
    XCTAssertEqual(merged.first?.description, "new")
  }
}
