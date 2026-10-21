import XCTest

@testable import Omi_Computer

final class TaskActionItemRetirementAuthorityTests: XCTestCase {
  private let createdAt = Date(timeIntervalSince1970: 1_700_000_000)

  func testCanonicalStatusRetiresTaskAcrossTaskSurfaces() {
    for status in ["cancelled", "superseded"] {
      let task = TaskActionItem(
        id: status,
        description: status,
        completed: false,
        createdAt: createdAt,
        dueAt: createdAt,
        deleted: nil,
        taskStatus: status
      )

      XCTAssertTrue(task.isRetired)
      XCTAssertTrue(TaskFilterTag.removedByAI.matches(task))
      XCTAssertFalse(TaskFilterTag.removedByMe.matches(task))
      XCTAssertTrue(TasksStore.activeDatedOnly([task]).isEmpty)
    }
  }

  func testUserRetirementProvenanceStillSelectsRemovedByMe() {
    let task = TaskActionItem(
      id: "removed-by-user",
      description: "removed-by-user",
      completed: false,
      createdAt: createdAt,
      deleted: true,
      deletedBy: "user"
    )

    XCTAssertTrue(task.isRetired)
    XCTAssertTrue(TaskFilterTag.removedByMe.matches(task))
    XCTAssertFalse(TaskFilterTag.removedByAI.matches(task))
  }

  func testPrivateLegacyMarkerKeepsTheDeletedWireKey() throws {
    let task = TaskActionItem(
      id: "legacy-deleted",
      description: "legacy-deleted",
      completed: false,
      createdAt: createdAt,
      deleted: true
    )

    let encoded = try JSONEncoder().encode(task)
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])

    XCTAssertEqual(object["deleted"] as? Bool, true)
    XCTAssertNil(object["legacyDeleted"])
    XCTAssertTrue(try JSONDecoder().decode(TaskActionItem.self, from: encoded).isRetired)
  }
}
