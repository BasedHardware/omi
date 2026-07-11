import XCTest

@testable import Omi_Computer

/// Regression test for the catastrophic Rewind data-loss bug: video-based
/// screenshots persist `imagePath` as "" (NOT NULL coalescing in
/// `RewindDatabase.insertScreenshot`), and retention cleanup handed those empty
/// strings to `RewindStorage.deleteScreenshot(relativePath:)`.
/// `root.appendingPathComponent("")` resolves to the Screenshots directory
/// itself, so `removeItem` would recursively wipe the entire screenshot store —
/// permanently deleting every legacy JPEG regardless of age.
///
/// `screenshotDeletionURL` is the durable guard: it must return nil for any path
/// that resolves to (or above) the storage root so the store is never deleted.
final class RewindScreenshotDeletionSafetyTests: XCTestCase {

  private func makeRoot() throws -> URL {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-rewind-del-\(UUID().uuidString)", isDirectory: true)
      .appendingPathComponent("Screenshots", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    return root
  }

  func testEmptyRelativePathIsRefused() throws {
    let root = try makeRoot()
    defer { try? FileManager.default.removeItem(at: root.deletingLastPathComponent()) }

    // The exact value stored for video-based screenshots — must not resolve to
    // a deletable URL (that URL would be the Screenshots root).
    XCTAssertNil(RewindStorage.screenshotDeletionURL(relativePath: "", in: root))
    XCTAssertNil(RewindStorage.screenshotDeletionURL(relativePath: "   ", in: root))
    XCTAssertNil(RewindStorage.screenshotDeletionURL(relativePath: "\n", in: root))
  }

  func testPathResolvingToRootIsRefused() throws {
    let root = try makeRoot()
    defer { try? FileManager.default.removeItem(at: root.deletingLastPathComponent()) }

    // A path that normalizes back to the root itself must also be refused.
    XCTAssertNil(RewindStorage.screenshotDeletionURL(relativePath: ".", in: root))
    XCTAssertNil(RewindStorage.screenshotDeletionURL(relativePath: "day/..", in: root))
  }

  func testLegitimateRelativePathIsResolved() throws {
    let root = try makeRoot()
    defer { try? FileManager.default.removeItem(at: root.deletingLastPathComponent()) }

    let resolved = RewindStorage.screenshotDeletionURL(
      relativePath: "2026-04-09/120000_001.jpg", in: root)
    XCTAssertEqual(
      resolved?.standardizedFileURL,
      root.appendingPathComponent("2026-04-09/120000_001.jpg").standardizedFileURL)
  }

  func testDeleteScreenshotWithEmptyPathDoesNotWipeStore() async throws {
    let root = try makeRoot()
    defer { try? FileManager.default.removeItem(at: root.deletingLastPathComponent()) }

    // Seed the store with a real screenshot file to prove it survives an empty-path
    // delete request routed through the guarded resolution.
    let dayDir = root.appendingPathComponent("2026-04-09", isDirectory: true)
    try FileManager.default.createDirectory(at: dayDir, withIntermediateDirectories: true)
    let file = dayDir.appendingPathComponent("120000_001.jpg")
    try Data([0xFF, 0xD8, 0xFF]).write(to: file)

    // The empty path must be refused, so neither the file nor the root is removed.
    XCTAssertNil(RewindStorage.screenshotDeletionURL(relativePath: "", in: root))
    XCTAssertTrue(FileManager.default.fileExists(atPath: file.path))
    XCTAssertTrue(FileManager.default.fileExists(atPath: root.path))
  }
}
