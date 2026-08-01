import Foundation
import XCTest

@testable import Omi_Computer

/// Regression coverage for the Rewind store shipping 0755 directories and 0644
/// files against its own stated 0700 invariant: `withIntermediateDirectories`
/// creates `Omi`, `Omi/users`, and `Omi/users/<uid>` with the process umask, and
/// tightening only the database's leaf directory left every ancestor and every
/// capture file readable by other local accounts.
final class RewindStorePermissionsTests: XCTestCase {
  private var storeRoot: URL?
  private var testUserId: String?
  private var userDir: URL?

  override func setUpWithError() throws {
    try super.setUpWithError()
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("rewind-store-permissions-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    storeRoot = root
  }

  override func tearDown() async throws {
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    if testUserId != nil {
      RewindDatabase.currentUserId = nil
      await RewindStorage.shared.reset()
    }
    if let storeRoot { try? FileManager.default.removeItem(at: storeRoot) }
    try await super.tearDown()
  }

  func testEveryCreatedDirectoryInTheChainBecomesOwnerOnly() throws {
    let root = try XCTUnwrap(storeRoot)
    let userDirectory =
      root
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent("uid-1", isDirectory: true)
    let screenshots = userDirectory.appendingPathComponent("Screenshots", isDirectory: true)
    let videos = userDirectory.appendingPathComponent("Videos", isDirectory: true)

    // Exactly what the production call sites do before routing through the helper.
    try FileManager.default.createDirectory(at: screenshots, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: videos, withIntermediateDirectories: true)
    RewindStorePermissions.secureDirectory(at: screenshots, storeRoot: root)
    RewindStorePermissions.secureDirectory(at: videos, storeRoot: root)

    for directory in [root, root.appendingPathComponent("users"), userDirectory, screenshots, videos] {
      XCTAssertEqual(try mode(of: directory), 0o700, "\(directory.lastPathComponent) must be owner-only")
    }
  }

  func testRepairPassTightensATreeLeftBehindByAnOlderBuild() throws {
    let root = try XCTUnwrap(storeRoot)
    let userDirectory =
      root
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent("uid-legacy", isDirectory: true)
    let dayDirectory =
      userDirectory
      .appendingPathComponent("Screenshots", isDirectory: true)
      .appendingPathComponent("2026-08-01", isDirectory: true)
    try FileManager.default.createDirectory(
      at: dayDirectory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o755])
    let capture = dayDirectory.appendingPathComponent("screenshot_120000_000.jpg")
    XCTAssertTrue(
      FileManager.default.createFile(
        atPath: capture.path, contents: Data("ocr".utf8), attributes: [.posixPermissions: 0o644]))

    RewindStorePermissions.repairStoreTree(at: userDirectory, storeRoot: root)

    XCTAssertEqual(try mode(of: root), 0o700)
    XCTAssertEqual(try mode(of: userDirectory), 0o700)
    XCTAssertEqual(try mode(of: dayDirectory), 0o700)
    XCTAssertEqual(try mode(of: capture), 0o600, "plaintext OCR captures must not stay group/world readable")
  }

  func testRepairRunsOnceAndNeverWeakensAStricterMode() throws {
    let root = try XCTUnwrap(storeRoot)
    let userDirectory =
      root
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent("uid-strict", isDirectory: true)
    try FileManager.default.createDirectory(at: userDirectory, withIntermediateDirectories: true)

    RewindStorePermissions.repairStoreTreeIfNeeded(at: userDirectory, storeRoot: root)
    try FileManager.default.setAttributes([.posixPermissions: 0o500], ofItemAtPath: userDirectory.path)

    RewindStorePermissions.secureDirectory(at: userDirectory, storeRoot: root)
    RewindStorePermissions.repairStoreTreeIfNeeded(at: userDirectory, storeRoot: root)

    XCTAssertEqual(
      try mode(of: userDirectory), 0o500,
      "the helper only clears permission bits, so an already-stricter path keeps its mode")
  }

  func testRewindStorageInitializationLeavesTheWholeChainOwnerOnly() async throws {
    await RewindStorage.shared.reset()
    let userId = "rewind-store-permissions-\(UUID().uuidString)"
    testUserId = userId
    RewindDatabase.currentUserId = userId

    let appSupport = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first)
    let omiDir = appSupport.appendingPathComponent("Omi", isDirectory: true)
    let usersDir = omiDir.appendingPathComponent("users", isDirectory: true)
    let userDirectory = usersDir.appendingPathComponent(userId, isDirectory: true)
    userDir = userDirectory

    try await RewindStorage.shared.initialize()

    for directory in [
      omiDir,
      usersDir,
      userDirectory,
      userDirectory.appendingPathComponent("Screenshots", isDirectory: true),
      userDirectory.appendingPathComponent("Videos", isDirectory: true),
    ] {
      XCTAssertEqual(try mode(of: directory), 0o700, "\(directory.path) must be owner-only")
    }
  }

  private func mode(of url: URL) throws -> Int {
    let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
    return try XCTUnwrap(attributes[.posixPermissions] as? NSNumber).intValue & 0o777
  }
}
