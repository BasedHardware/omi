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

  func testEnsureLogFileOwnerOnlyRejectsSymlinkAndDoesNotTouchTarget() throws {
    // An attacker in world-writable /tmp pre-creates the log path as a symlink to
    // a victim file. We must not chmod the victim or write through the link.
    let victim = tempDir.appendingPathComponent("victim.txt").path
    XCTAssertTrue(
      FileManager.default.createFile(
        atPath: victim, contents: Data("victim content\n".utf8),
        attributes: [.posixPermissions: 0o644]))

    let path = tempDir.appendingPathComponent("omi-symlinked.log").path
    try FileManager.default.createSymbolicLink(atPath: path, withDestinationPath: victim)

    XCTAssertTrue(ensureLogFileOwnerOnly(atPath: path))

    // The symlink was replaced by a real owner-only file — the path is no longer
    // a link (destinationOfSymbolicLink throws once it isn't one).
    XCTAssertThrowsError(try FileManager.default.destinationOfSymbolicLink(atPath: path))
    XCTAssertEqual(try posixPermissions(of: path), 0o600)

    // The victim was neither tightened to 0600 nor overwritten through the link.
    XCTAssertEqual(try posixPermissions(of: victim), 0o644)
    XCTAssertEqual(try String(contentsOfFile: victim, encoding: .utf8), "victim content\n")
  }

  func testNamedNonProductionLaunchesResolveToSeparateOwnerOnlyLogPaths() {
    let first = OmiLogPathResolver.logPath(
      isNonProduction: true,
      bundleIdentifier: "com.omi.qa-one",
      processID: 101)
    let second = OmiLogPathResolver.logPath(
      isNonProduction: true,
      bundleIdentifier: "com.omi.qa-two",
      processID: 202)

    XCTAssertNotEqual(first, second)
    XCTAssertEqual(first, "/private/tmp/omi-dev-com.omi.qa-one-101.log")
    XCTAssertEqual(second, "/private/tmp/omi-dev-com.omi.qa-two-202.log")
    XCTAssertEqual(
      OmiLogPathResolver.logPath(
        isNonProduction: false,
        bundleIdentifier: "com.omi.computer-macos",
        processID: 303),
      "/tmp/omi.log")
  }

  func testEnsureLogDirectoryOwnerOnlyCreatesDirectoryWith0700() throws {
    let path = tempDir.appendingPathComponent("owner-only-logs").path

    XCTAssertTrue(ensureLogDirectoryOwnerOnly(atPath: path))
    XCTAssertEqual(try posixPermissions(of: path), 0o700)
  }

  private func posixPermissions(of path: String) throws -> Int {
    let attributes = try FileManager.default.attributesOfItem(atPath: path)
    let number = try XCTUnwrap(attributes[.posixPermissions] as? NSNumber)
    return number.intValue
  }
}
