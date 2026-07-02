import GRDB
import XCTest

@testable import Omi_Computer

final class AppleNotesReaderServiceTests: XCTestCase {
  func testClassifiesSqliteAuthorizationDeniedAsPermissionError() {
    let error = NSError(
      domain: "GRDB",
      code: 23,
      userInfo: [NSLocalizedDescriptionKey: "SQLite error 23: authorization denied"]
    )

    guard case .authorizationDenied(let path) = AppleNotesReaderService.classifyReadError(error, path: "/notes/NoteStore.sqlite") else {
      return XCTFail("Expected authorizationDenied classification")
    }
    XCTAssertEqual(path, "/notes/NoteStore.sqlite")
  }

  func testResolveSelectedFolderAcceptsAndInfersNotesContainer() throws {
    let root = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let home = root.appendingPathComponent("home", isDirectory: true)
    let groupContainers = home.appendingPathComponent("Library/Group Containers", isDirectory: true)
    let notesContainer = groupContainers.appendingPathComponent("group.com.apple.notes", isDirectory: true)
    try FileManager.default.createDirectory(at: notesContainer, withIntermediateDirectories: true)

    XCTAssertEqual(
      try AppleNotesReaderService.resolveSelectedFolder(groupContainers, homeDirectory: home).path,
      notesContainer.path
    )
    XCTAssertEqual(
      try AppleNotesReaderService.resolveSelectedFolder(notesContainer, homeDirectory: home).path,
      notesContainer.path
    )
  }

  func testResolveSelectedFolderRejectsUnrelatedFolder() throws {
    let root = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let unrelated = root.appendingPathComponent("Documents", isDirectory: true)
    try FileManager.default.createDirectory(at: unrelated, withIntermediateDirectories: true)

    XCTAssertThrowsError(try AppleNotesReaderService.resolveSelectedFolder(unrelated, homeDirectory: root)) { error in
      guard case .invalidSelectedFolder(let path) = error as? AppleNotesReaderError else {
        return XCTFail("Expected invalidSelectedFolder, got \(error)")
      }
      XCTAssertEqual(path, unrelated.path)
    }
  }

  func testReadRecentNotesFromSelectedFolderFixture() async throws {
    let root = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let notesContainer = try makeNotesContainerFixture(in: root, withSchema: true)
    let store = notesContainer.appendingPathComponent("NoteStore.sqlite")
    let dbQueue = try DatabaseQueue(path: store.path)
    try await dbQueue.write { db in
      try db.execute(
        sql: """
          INSERT INTO ZICCLOUDSYNCINGOBJECT
            (Z_PK, ZTITLE, ZSUMMARY, ZMODIFICATIONDATE, ZNOTE, ZMARKEDFORDELETION)
          VALUES (?, ?, ?, ?, ?, ?)
        """,
        arguments: [1, "Launch checklist", "Ship Notes connector", 42.0, 1, 0]
      )
    }

    let notes = try await AppleNotesReaderService.shared.readRecentNotes(
      maxResults: 10,
      selectedFolderPath: notesContainer.path
    )

    XCTAssertEqual(notes.count, 1)
    XCTAssertEqual(notes.first?.title, "Launch checklist")
    XCTAssertEqual(notes.first?.summary, "Ship Notes connector")
  }

  func testReadRecentNotesClampsNegativeLimit() async throws {
    let root = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let notesContainer = try makeNotesContainerFixture(in: root, withSchema: true)

    let notes = try await AppleNotesReaderService.shared.readRecentNotes(
      maxResults: -1,
      selectedFolderPath: notesContainer.path
    )

    XCTAssertTrue(notes.isEmpty)
  }

  func testValidateSelectedFolderClassifiesSchemaFailure() async throws {
    let root = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let notesContainer = try makeNotesContainerFixture(in: root, withSchema: false)
    _ = try DatabaseQueue(path: notesContainer.appendingPathComponent("NoteStore.sqlite").path)

    do {
      _ = try await AppleNotesReaderService.shared.validateSelectedFolder(path: notesContainer.path, remember: false)
      XCTFail("Expected schema validation to fail")
    } catch let error as AppleNotesReaderError {
      XCTAssertEqual(error.reasonCode, "schema_unavailable")
    }
  }

  private func makeNotesContainerFixture(in root: URL, withSchema: Bool) throws -> URL {
    let notesContainer = root.appendingPathComponent("group.com.apple.notes", isDirectory: true)
    try FileManager.default.createDirectory(at: notesContainer, withIntermediateDirectories: true)
    let store = notesContainer.appendingPathComponent("NoteStore.sqlite")
    let dbQueue = try DatabaseQueue(path: store.path)
    if withSchema {
      try dbQueue.write { db in
        try db.execute(
          sql: """
            CREATE TABLE ZICCLOUDSYNCINGOBJECT (
              Z_PK INTEGER PRIMARY KEY,
              ZTITLE TEXT,
              ZSUMMARY TEXT,
              ZMODIFICATIONDATE REAL,
              ZNOTE INTEGER,
              ZMARKEDFORDELETION INTEGER
            )
          """
        )
      }
    }
    return notesContainer
  }

  private func makeTemporaryDirectory() throws -> URL {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("AppleNotesReaderServiceTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
  }
}
