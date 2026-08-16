import XCTest

@testable import Omi_Computer

/// Behavioral regression coverage for the T2 Rewind artifact/recovery gauntlet.
///
/// The bridge invokes this same production-facing helper on a named non-production
/// bundle. XCTest gives it an isolated Rewind owner so it can prove the whole
/// artifact lifecycle without touching a developer's actual timeline.
final class RewindArtifactGauntletTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "rewind-artifact-gauntlet")
    try await RewindIndexer.shared.initialize()
  }

  override func tearDown() async throws {
    await RewindIndexer.shared.reset()
    await RewindStorage.shared.reset()
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testSyntheticArtifactSurvivesDatabaseReopenAndProtectedFrameNeverPersists() async throws {
    let result = try await RewindArtifactGauntlet.run(nonce: "xctest-\(UUID().uuidString)")

    XCTAssertTrue(result.protectedFrameBlocked)
    XCTAssertEqual(result.protectedRowCount, 0)
    XCTAssertEqual(result.persistedFrameCount, 2)
    XCTAssertEqual(result.readbackColors, ["red", "green"])
    XCTAssertTrue(result.databaseReopened)
    XCTAssertTrue(result.rowsSurvivedReopen)
    XCTAssertEqual(result.cleanupRemovedRows, 2)
    XCTAssertTrue(result.artifactFileRemoved)
  }
}
