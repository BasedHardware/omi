import XCTest

@testable import Omi_Computer

final class SingleInstanceGuardTests: XCTestCase {
  private var tempDir: String!

  override func setUpWithError() throws {
    try super.setUpWithError()
    tempDir = NSTemporaryDirectory().appending("omi-single-instance-tests-\(UUID().uuidString)/")
    try FileManager.default.createDirectory(
      atPath: tempDir, withIntermediateDirectories: true)
  }

  override func tearDownWithError() throws {
    if let tempDir {
      try? FileManager.default.removeItem(atPath: tempDir)
    }
    try super.tearDownWithError()
  }

  // MARK: - Lock path derivation

  func testLockPathIsDeterministicForSameInputs() {
    let first = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.computer-macos", launchMode: .full, directory: tempDir)
    let second = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.computer-macos", launchMode: .full, directory: tempDir)
    XCTAssertEqual(first, second)
  }

  func testLockPathDiffersByBundleID() {
    // Parallel named dev/test bundles must not contend with each other or production.
    let prod = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.computer-macos", launchMode: .full, directory: tempDir)
    let dev = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.desktop-dev", launchMode: .full, directory: tempDir)
    let named = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.omi-fix-rewind", launchMode: .full, directory: tempDir)
    XCTAssertNotEqual(prod, dev)
    XCTAssertNotEqual(prod, named)
    XCTAssertNotEqual(dev, named)
  }

  func testLockPathDiffersByLaunchMode() {
    // Rewind-only mode and the full app it spawns via `open -n` must not evict each other.
    let full = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.computer-macos", launchMode: .full, directory: tempDir)
    let rewind = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.computer-macos", launchMode: .rewind, directory: tempDir)
    XCTAssertNotEqual(full, rewind)
  }

  func testLockPathSanitizesUnsafeCharacters() {
    let path = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi/../evil id", launchMode: .full, directory: tempDir)
    let filename = (path as NSString).lastPathComponent
    // No path separators or spaces survive into the filename, so an unusual bundle id
    // can neither escape the directory nor break the path.
    XCTAssertFalse(filename.contains("/"))
    XCTAssertFalse(filename.contains(" "))
    // The lock stays inside the requested directory.
    XCTAssertEqual(
      (path as NSString).deletingLastPathComponent, (tempDir as NSString).standardizingPath)
  }

  // MARK: - Lock acquisition mechanism

  func testFirstAcquirerWinsSecondSeesConflict() {
    let path = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.test", launchMode: .full, directory: tempDir)

    // First instance takes the lock.
    guard case .acquired(let descriptor) = SingleInstanceGuard.acquireExclusiveLock(at: path) else {
      return XCTFail("first acquirer should win the lock")
    }
    XCTAssertGreaterThanOrEqual(descriptor, 0)

    // A concurrent second instance (separate file description on the same path) is rejected.
    XCTAssertEqual(
      SingleInstanceGuard.acquireExclusiveLock(at: path),
      .heldByAnotherInstance)

    SingleInstanceGuard.releaseLock(descriptor)
  }

  func testAcquiredLockRecordsOwnerProcessIdentifier() {
    let path = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.test", launchMode: .full, directory: tempDir)

    guard case .acquired(let descriptor) = SingleInstanceGuard.acquireExclusiveLock(at: path) else {
      return XCTFail("lock should be acquirable")
    }
    defer { SingleInstanceGuard.releaseLock(descriptor) }

    XCTAssertEqual(
      SingleInstanceGuard.lockOwnerProcessIdentifier(at: path),
      ProcessInfo.processInfo.processIdentifier)
  }

  func testAcquiredLockDescriptorIsCloseOnExec() {
    let path = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.test", launchMode: .full, directory: tempDir)

    guard case .acquired(let descriptor) = SingleInstanceGuard.acquireExclusiveLock(at: path) else {
      return XCTFail("lock should be acquirable")
    }
    defer { SingleInstanceGuard.releaseLock(descriptor) }

    XCTAssertTrue(
      SingleInstanceGuard.descriptorHasCloseOnExec(descriptor),
      "Child processes must not inherit the app-lifetime lock descriptor")
  }

  func testLockOwnerProcessIdentifierIsModeScopedByLockPath() {
    let full = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.test", launchMode: .full, directory: tempDir)
    let rewind = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.test", launchMode: .rewind, directory: tempDir)

    guard case .acquired(let fullDescriptor) = SingleInstanceGuard.acquireExclusiveLock(at: full)
    else {
      return XCTFail("full-mode lock should be acquirable")
    }
    defer { SingleInstanceGuard.releaseLock(fullDescriptor) }

    XCTAssertNotNil(SingleInstanceGuard.lockOwnerProcessIdentifier(at: full))
    XCTAssertNil(
      SingleInstanceGuard.lockOwnerProcessIdentifier(at: rewind),
      "Reading owner PID from the same lock path used for contention keeps activation scoped to launch mode")
  }

  func testLockIsReacquirableAfterRelease() {
    let path = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.test", launchMode: .full, directory: tempDir)

    guard case .acquired(let firstDescriptor) = SingleInstanceGuard.acquireExclusiveLock(at: path)
    else {
      return XCTFail("first acquire should succeed")
    }
    SingleInstanceGuard.releaseLock(firstDescriptor)

    // Once the holder releases (mirrors process exit dropping the flock), the next
    // launch may take the lock again.
    guard case .acquired(let secondDescriptor) = SingleInstanceGuard.acquireExclusiveLock(at: path)
    else {
      return XCTFail("lock should be re-acquirable after release")
    }
    SingleInstanceGuard.releaseLock(secondDescriptor)
  }

  func testDifferentModesDoNotContend() {
    let full = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.test", launchMode: .full, directory: tempDir)
    let rewind = SingleInstanceGuard.lockFilePath(
      bundleID: "com.omi.test", launchMode: .rewind, directory: tempDir)

    guard case .acquired(let fullDescriptor) = SingleInstanceGuard.acquireExclusiveLock(at: full)
    else {
      return XCTFail("full-mode lock should be acquirable")
    }
    // A rewind-mode instance uses a distinct lock file, so it can run alongside full.
    guard
      case .acquired(let rewindDescriptor) = SingleInstanceGuard.acquireExclusiveLock(at: rewind)
    else {
      SingleInstanceGuard.releaseLock(fullDescriptor)
      return XCTFail("rewind-mode lock should be acquirable while full mode holds its own lock")
    }

    SingleInstanceGuard.releaseLock(rewindDescriptor)
    SingleInstanceGuard.releaseLock(fullDescriptor)
  }
}
