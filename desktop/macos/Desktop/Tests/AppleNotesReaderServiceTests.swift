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

    guard
      case .authorizationDenied(let path) = AppleNotesReaderService.classifyReadError(
        error, path: "/notes/NoteStore.sqlite")
    else {
      return XCTFail("Expected authorizationDenied classification")
    }
    XCTAssertEqual(path, "/notes/NoteStore.sqlite")
  }

  func testIsLikelyAttachmentDoesNotDropOrdinaryNotesContainingExecSubstring() {
    // Regression: a raw `contains("exec")` substring match wrongly classified ordinary
    // notes as attachment/metadata artifacts and silently dropped them from the import.
    for title in ["Q3 execution plan", "Executive summary", "executed the migration", "executive decisions"] {
      XCTAssertFalse(
        AppleNotesReaderService.isLikelyAttachment(title: title, summary: "notes and details"),
        "note titled \"\(title)\" must not be filtered as an attachment"
      )
    }
  }

  func testIsLikelyAttachmentStillFiltersArtifactTokens() {
    // The metadata/artifact tokens the filter targets must still be caught.
    XCTAssertTrue(AppleNotesReaderService.isLikelyAttachment(title: "kMDItemFSName", summary: ""))
    XCTAssertTrue(AppleNotesReaderService.isLikelyAttachment(title: "SOLITE", summary: ""))
    XCTAssertTrue(AppleNotesReaderService.isLikelyAttachment(title: "exec", summary: ""))
    XCTAssertTrue(AppleNotesReaderService.isLikelyAttachment(title: "", summary: ""))
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

  func testReadRecentNotesResolvesLegacyGroupContainersSelection() async throws {
    let root = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let groupContainers = root.appendingPathComponent("Library/Group Containers", isDirectory: true)
    let notesContainer = try makeNotesContainerFixture(in: groupContainers, withSchema: true)
    let store = notesContainer.appendingPathComponent("NoteStore.sqlite")
    let dbQueue = try DatabaseQueue(path: store.path)
    try await dbQueue.write { db in
      try db.execute(
        sql: """
            INSERT INTO ZICCLOUDSYNCINGOBJECT
              (Z_PK, ZTITLE, ZSUMMARY, ZMODIFICATIONDATE, ZNOTE, ZMARKEDFORDELETION)
            VALUES (?, ?, ?, ?, ?, ?)
          """,
        arguments: [1, "Legacy folder import", "Parent folder still works", 42.0, 1, 0]
      )
    }

    let notes = try await AppleNotesReaderService.shared.readRecentNotes(
      maxResults: 10,
      selectedFolderPath: groupContainers.path
    )

    XCTAssertEqual(notes.count, 1)
    XCTAssertEqual(notes.first?.title, "Legacy folder import")
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

  func testReadProbeRejectsInvalidFolderBeforeEnteringReaderActor() throws {
    let root = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let invalidPath = root.appendingPathComponent("not-apple-notes", isDirectory: true).path

    XCTAssertThrowsError(
      try AppleNotesReadProbe.resolveRequestedFolder(
        path: invalidPath,
        homeDirectory: root
      )
    ) { error in
      guard case .invalidSelectedFolder(let path) = error as? AppleNotesReaderError else {
        return XCTFail("Expected invalidSelectedFolder, got \(error)")
      }
      XCTAssertEqual(path, invalidPath)
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

  func testConnectionStatusTreatsZeroNotesAsReadable() async throws {
    let root = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let notesContainer = try makeNotesContainerFixture(in: root, withSchema: true)
    let status = await AppleNotesReaderService.shared.connectionStatus(
      maxResults: 10,
      selectedFolderPath: notesContainer.path
    )

    guard case .connected(let noteCount, _) = status else {
      return XCTFail("Expected connected status, got \(status)")
    }
    XCTAssertEqual(noteCount, 0)
    XCTAssertTrue(status.isConnected)
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

  func testReadOutcomeClassifiesPathFailuresAsNeedsAccess() {
    let outcome = AppleNotesReaderService.classifyReadOutcome(
      noteCount: nil,
      error: .invalidSelectedFolder(path: "/tmp/wrong")
    )

    XCTAssertEqual(
      outcome,
      .needsAccess(
        message: "Choose the Apple Notes folder named group.com.apple.notes.",
        reasonCode: "invalid_selected_folder"
      )
    )
  }

  func testReadOutcomeClassifiesSchemaAndReadFailuresAsErrors() {
    XCTAssertEqual(
      AppleNotesReaderService.classifyReadOutcome(
        noteCount: nil,
        error: .schemaUnavailable(path: "/notes/NoteStore.sqlite")
      ),
      .error(
        message: "Apple Notes data store could not be read because its database format was not recognized.",
        reasonCode: "schema_unavailable"
      )
    )

    XCTAssertEqual(
      AppleNotesReaderService.classifyReadOutcome(
        noteCount: nil,
        error: .storeReadFailed(path: "/notes/NoteStore.sqlite", reason: "disk I/O error")
      ),
      .error(
        message: "Apple Notes data store could not be read: disk I/O error",
        reasonCode: "store_read_failed"
      )
    )
  }

  func testConnectionStatusSurfacesSchemaFailureAsError() async throws {
    let root = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: root) }

    let notesContainer = try makeNotesContainerFixture(in: root, withSchema: false)
    _ = try DatabaseQueue(path: notesContainer.appendingPathComponent("NoteStore.sqlite").path)
    let status = await AppleNotesReaderService.shared.connectionStatus(
      maxResults: 10,
      selectedFolderPath: notesContainer.path
    )

    guard case .error(let message, let reasonCode) = status else {
      return XCTFail("Expected error status, got \(status)")
    }
    XCTAssertEqual(reasonCode, "schema_unavailable")
    XCTAssertTrue(message.contains("database format was not recognized"))
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
