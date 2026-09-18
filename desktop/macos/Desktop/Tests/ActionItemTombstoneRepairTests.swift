import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

/// The repair for the tombstones the Removed lane manufactured over live tasks.
///
/// `TasksStore.fetchDeletedPage` asked for retired rows with a `deleted=true`
/// query item that `GET /v1/action-items` never had. FastAPI drops an unknown
/// query item and that handler skips soft-deleted documents outright, so the
/// page it answered with was the owner's live tasks — stamped retired and
/// synced into `action_items` a hundred at a time. Completing one of them from
/// a chat task card read the tombstone back and rendered "Task is no longer
/// available" over the task the reader had just ticked.
///
/// The migration has to undo exactly those and nothing else, so the two halves
/// of this file are equally load-bearing: a repair that over-reaches
/// resurrects tasks the owner deliberately deleted.
final class ActionItemTombstoneRepairTests: XCTestCase {
  private func makeDatabase() throws -> DatabaseQueue {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.execute(
        sql: """
          CREATE TABLE action_items (
            id INTEGER PRIMARY KEY,
            backendId TEXT,
            description TEXT NOT NULL,
            completed BOOLEAN NOT NULL DEFAULT 0,
            deleted BOOLEAN NOT NULL DEFAULT 0,
            deletedBy TEXT,
            taskStatus TEXT
          )
          """)
    }
    return queue
  }

  private func insert(
    _ queue: DatabaseQueue,
    id: String,
    deleted: Bool,
    deletedBy: String?,
    taskStatus: String?
  ) throws {
    try queue.write { db in
      try db.execute(
        sql: """
          INSERT INTO action_items (backendId, description, completed, deleted, deletedBy, taskStatus)
          VALUES (?, ?, 0, ?, ?, ?)
          """,
        arguments: [id, id, deleted, deletedBy, taskStatus])
    }
  }

  private func isDeleted(_ queue: DatabaseQueue, id: String) throws -> Bool {
    try queue.read { db in
      try Bool.fetchOne(db, sql: "SELECT deleted FROM action_items WHERE backendId = ?", arguments: [id]) ?? false
    }
  }

  private func migrate(_ queue: DatabaseQueue) throws {
    var migrator = DatabaseMigrator()
    RewindDatabase.registerFabricatedActionItemTombstoneRepair(on: &migrator)
    try migrator.migrate(queue)
  }

  /// The row the lane fabricated: retired by the stamp alone, with a canonical
  /// status that still says the task is the owner's to do.
  func testAFabricatedTombstoneIsCleared() throws {
    let queue = try makeDatabase()
    try insert(queue, id: "live-task", deleted: true, deletedBy: nil, taskStatus: "active")
    try migrate(queue)
    XCTAssertFalse(
      try isDeleted(queue, id: "live-task"),
      "a tombstone with no deleter and no retired status was written by nothing but the lane stamp")
  }

  /// An empty `deletedBy` is the same absence of a witness as a null one — the
  /// column is text and both shapes exist in the field.
  func testAnEmptyDeletedByCountsAsNoWitness() throws {
    let queue = try makeDatabase()
    try insert(queue, id: "live-task", deleted: true, deletedBy: "", taskStatus: nil)
    try migrate(queue)
    XCTAssertFalse(try isDeleted(queue, id: "live-task"))
  }

  /// The half that matters most: a deletion the owner actually performed
  /// records who did it, and must survive the repair untouched.
  func testAUserDeletionIsLeftAlone() throws {
    let queue = try makeDatabase()
    try insert(queue, id: "removed-by-me", deleted: true, deletedBy: "user", taskStatus: "active")
    try migrate(queue)
    XCTAssertTrue(
      try isDeleted(queue, id: "removed-by-me"),
      "resurrecting a task the owner deleted is the failure this repair must not cause")
  }

  /// A server-side retirement carries no `deletedBy` (the backend has no such
  /// field) but does carry canonical status, which is witness enough.
  func testAServerRetirementIsLeftAlone() throws {
    let queue = try makeDatabase()
    try insert(queue, id: "cancelled", deleted: true, deletedBy: nil, taskStatus: "cancelled")
    try insert(queue, id: "superseded", deleted: true, deletedBy: nil, taskStatus: "superseded")
    try migrate(queue)
    XCTAssertTrue(try isDeleted(queue, id: "cancelled"))
    XCTAssertTrue(try isDeleted(queue, id: "superseded"))
  }

  func testALiveRowIsNotDisturbed() throws {
    let queue = try makeDatabase()
    try insert(queue, id: "ordinary", deleted: false, deletedBy: nil, taskStatus: "active")
    try migrate(queue)
    XCTAssertFalse(try isDeleted(queue, id: "ordinary"))
  }
}
