import Foundation
import XCTest

@testable import Omi_Computer

/// `Screenshot` captures its rowid in a `mutating didInsert`, which only
/// witnesses `MutablePersistableRecord`. Under `PersistableRecord` the
/// declaration compiles, is never called, and `insertScreenshot` returns
/// `id == nil` — silently disabling every `if let id = inserted.id` consumer,
/// notably the OCR embedding queue in `RewindIndexer`.
final class RewindScreenshotRowIDCaptureTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "rewind-screenshot-rowid")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testInsertScreenshotReturnsPersistedRowID() async throws {
    let screenshot = Screenshot(
      timestamp: Date(),
      appName: "RowIDCapture",
      windowTitle: "Rowid capture",
      ocrText: "captured ocr text",
      isIndexed: true
    )

    let inserted = try await RewindDatabase.shared.insertScreenshot(screenshot)

    let rowID = try XCTUnwrap(inserted.id, "insertScreenshot must return the persisted rowid")
    let persisted = try await RewindDatabase.shared.getRecentScreenshots(limit: 1)
    XCTAssertEqual(persisted.first?.id, rowID)
  }
}
