import XCTest

@testable import Omi_Computer

final class DesktopDeveloperSecretStoreTests: XCTestCase {
  private var tempRoot = FileManager.default.temporaryDirectory
  private var store = DesktopDeveloperSecretStore(
    rootDirectory: FileManager.default.temporaryDirectory, bundleIdentifier: "unset")

  override func setUpWithError() throws {
    try super.setUpWithError()
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("developer-secrets-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    store = DesktopDeveloperSecretStore(
      rootDirectory: tempRoot,
      bundleIdentifier: "com.omi.omi-secret-store-tests"
    )
  }

  override func tearDownWithError() throws {
    try? FileManager.default.removeItem(at: tempRoot)
    try super.tearDownWithError()
  }

  func testRoundTripReadWrite() throws {
    XCTAssertNil(store.readString(service: "svc", account: "acct"))
    XCTAssertTrue(store.setString("secret-value", service: "svc", account: "acct"))
    XCTAssertEqual(store.readString(service: "svc", account: "acct"), "secret-value")
  }

  func testOverwriteReplacesValue() throws {
    XCTAssertTrue(store.setString("first", service: "svc", account: "acct"))
    XCTAssertTrue(store.setString("second", service: "svc", account: "acct"))
    XCTAssertEqual(store.readString(service: "svc", account: "acct"), "second")
  }

  func testDeleteRemovesValue() throws {
    XCTAssertTrue(store.setString("secret-value", service: "svc", account: "acct"))
    store.delete(service: "svc", account: "acct")
    XCTAssertNil(store.readString(service: "svc", account: "acct"))
  }

  func testMissingFileReadsAsEmpty() throws {
    let missing = DesktopDeveloperSecretStore(
      rootDirectory: tempRoot.appendingPathComponent("absent", isDirectory: true),
      bundleIdentifier: "com.omi.omi-missing"
    )
    XCTAssertNil(missing.readString(service: "svc", account: "acct"))
  }

  func testCorruptFileReadsAsEmpty() throws {
    let directory = store.secretsDirectoryURL()
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    try Data("{not-json".utf8).write(to: store.fileURL())
    XCTAssertNil(store.readString(service: "svc", account: "acct"))
    XCTAssertTrue(store.setString("recovered", service: "svc", account: "acct"))
    XCTAssertEqual(store.readString(service: "svc", account: "acct"), "recovered")
  }

  func testSeparateServiceAndAccountKeys() throws {
    XCTAssertTrue(store.setString("one", service: "svc-a", account: "acct"))
    XCTAssertTrue(store.setString("two", service: "svc-b", account: "acct"))
    XCTAssertTrue(store.setString("three", service: "svc-a", account: "other"))
    XCTAssertEqual(store.readString(service: "svc-a", account: "acct"), "one")
    XCTAssertEqual(store.readString(service: "svc-b", account: "acct"), "two")
    XCTAssertEqual(store.readString(service: "svc-a", account: "other"), "three")
  }

  func testSeparateBundleFilesDoNotShareValues() throws {
    let other = DesktopDeveloperSecretStore(
      rootDirectory: tempRoot,
      bundleIdentifier: "com.omi.omi-other-bundle"
    )
    XCTAssertTrue(store.setString("mine", service: "svc", account: "acct"))
    XCTAssertTrue(other.setString("theirs", service: "svc", account: "acct"))
    XCTAssertEqual(store.readString(service: "svc", account: "acct"), "mine")
    XCTAssertEqual(other.readString(service: "svc", account: "acct"), "theirs")
    XCTAssertNotEqual(store.fileURL(), other.fileURL())
  }

  func testFileModeIsOwnerReadWriteAndDirectoryIsOwnerOnly() throws {
    XCTAssertTrue(store.setString("secret-value", service: "svc", account: "acct"))
    let fileAttributes = try FileManager.default.attributesOfItem(atPath: store.fileURL().path)
    let directoryAttributes = try FileManager.default.attributesOfItem(
      atPath: store.secretsDirectoryURL().path)
    let fileMode = try XCTUnwrap(fileAttributes[.posixPermissions] as? NSNumber).intValue
    let directoryMode = try XCTUnwrap(directoryAttributes[.posixPermissions] as? NSNumber).intValue
    XCTAssertEqual(fileMode & 0o777, 0o600)
    XCTAssertEqual(directoryMode & 0o777, 0o700)
  }

  /// `scripts/omi-auth-seed.sh` writes this file for a bundle from a Background
  /// session; the app must read it as its own. Pin the on-disk shape the script
  /// produces (a JSON object whose key is service, NUL, account) so a drift in
  /// either side shows up here instead of as a slot that boots signed out.
  func testReadsAFileWrittenInTheSeedScriptShape() throws {
    let bundleID = "com.omi.omi-seeded"
    let fileURL = DesktopDeveloperSecretStore.fileURL(rootDirectory: tempRoot, bundleIdentifier: bundleID)
    try FileManager.default.createDirectory(
      at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    let service = "com.omi.desktop.firebase-rest-session.v2.team.adhoc.\(bundleID).bundle.\(bundleID)"
    let payload = #"{"idToken":"id","refreshToken":"refresh","expiryTime":1800000000.0,"tokenUserId":"uid"}"#
    let object: [String: String] = ["\(service)\u{0}firebase-rest-tokens": payload]
    let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: fileURL)

    let seeded = DesktopDeveloperSecretStore(rootDirectory: tempRoot, bundleIdentifier: bundleID)
    XCTAssertEqual(seeded.readString(service: service, account: "firebase-rest-tokens"), payload)
    XCTAssertNil(seeded.readString(service: service, account: "other"))
  }

  func testStorageKeyJoinsServiceAndAccountWithNUL() {
    XCTAssertEqual(
      DesktopDeveloperSecretStore.storageKey(service: "svc", account: "acct"),
      "svc\u{0}acct")
  }
}
