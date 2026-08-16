import Foundation
import XCTest

@testable import Omi_Computer

/// `AIUserProfileRecord` captures its rowid in a `mutating didInsert`, which only
/// witnesses `MutablePersistableRecord`. Under `PersistableRecord` a direct
/// `record.insert(db)` picked the non-mutating overload, so the empty default ran
/// and `id` stayed nil — silently disabling every `WHERE id = ?` consumer, notably
/// the profile row Settings → Advanced hands to Save and Delete right after
/// Regenerate, and the `backendSynced = 1` update after a successful sync.
final class AIUserProfileRowIDCaptureTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "ai-user-profile-rowid")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testInsertProfileReturnsRowIDThatIDConsumersResolve() async throws {
    let inserted = try await AIUserProfileService.shared.insertProfile(
      AIUserProfileRecord(
        profileText: "- User writes Swift",
        dataSourcesUsed: 3,
        backendSynced: false,
        generatedAt: Date()
      ))

    let rowID = try XCTUnwrap(inserted.id, "insertProfile must return the persisted rowid")
    let persisted = await AIUserProfileService.shared.getLatestProfile()
    let latest = try XCTUnwrap(persisted)
    XCTAssertEqual(latest.id, rowID, "the reported rowid must be the row that was persisted")

    // Every consumer of the returned record passes `id` to a `WHERE id = ?`
    // statement. Deleting by it proves the reported rowid actually resolves.
    let remaining = await AIUserProfileService.shared.deleteProfile(id: rowID)
    XCTAssertNil(remaining, "deleteProfile(id:) must remove the row the insert reported")
  }
}
