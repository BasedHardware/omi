import XCTest

@testable import Omi_Computer

/// BL-024 / SET-06: the app log must not be world-readable. These tests pin the
/// permission-normalization helper the logger uses on every first write.
final class LoggerPermissionsTests: XCTestCase {
  private var tempDir: URL!

  override func setUpWithError() throws {
    try super.setUpWithError()
    tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("logger-perms-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
  }

  override func tearDownWithError() throws {
    if let tempDir { try? FileManager.default.removeItem(at: tempDir) }
    try super.tearDownWithError()
  }

  func testEnsureLogFileOwnerOnlyCreatesFileWith0600() throws {
    let path = tempDir.appendingPathComponent("omi-new.log").path
    XCTAssertFalse(FileManager.default.fileExists(atPath: path))

    XCTAssertTrue(ensureLogFileOwnerOnly(atPath: path))

    XCTAssertTrue(FileManager.default.fileExists(atPath: path))
    XCTAssertEqual(try posixPermissions(of: path), 0o600)
  }

  func testEnsureLogFileOwnerOnlyTightensExistingWorldReadableFile() throws {
    let path = tempDir.appendingPathComponent("omi-existing.log").path
    // Simulate a log created by an older build with default (world-readable) perms.
    XCTAssertTrue(
      FileManager.default.createFile(
        atPath: path, contents: Data("prior line\n".utf8),
        attributes: [.posixPermissions: 0o644]))
    XCTAssertEqual(try posixPermissions(of: path), 0o644)

    XCTAssertTrue(ensureLogFileOwnerOnly(atPath: path))

    XCTAssertEqual(try posixPermissions(of: path), 0o600)
    // Existing content is preserved — only the mode changes.
    XCTAssertEqual(try String(contentsOfFile: path, encoding: .utf8), "prior line\n")
  }

  private func posixPermissions(of path: String) throws -> Int {
    let attributes = try FileManager.default.attributesOfItem(atPath: path)
    let number = try XCTUnwrap(attributes[.posixPermissions] as? NSNumber)
    return number.intValue
  }
}
