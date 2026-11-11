import XCTest

@testable import Omi_Computer

final class DesktopKeychainStoreRoutingTests: XCTestCase {
  private var tempRoot = FileManager.default.temporaryDirectory
  private var fileStore = DesktopDeveloperSecretStore(
    rootDirectory: FileManager.default.temporaryDirectory, bundleIdentifier: "unset")
  private var keychainCalls = CallRecorder()

  override func setUpWithError() throws {
    try super.setUpWithError()
    DesktopKeychainStore.resetTestHooks()
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("keychain-routing-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    fileStore = DesktopDeveloperSecretStore(
      rootDirectory: tempRoot,
      bundleIdentifier: "com.omi.omi-routing-tests"
    )
    DesktopKeychainStore.developerSecretStoreOverride = fileStore
    keychainCalls = CallRecorder()
  }

  override func tearDownWithError() throws {
    DesktopKeychainStore.resetTestHooks()
    try? FileManager.default.removeItem(at: tempRoot)
    try super.tearDownWithError()
  }

  func testProductionFamilyBundleIdentifiersUseKeychainBackend() {
    XCTAssertEqual(
      DesktopKeychainStore.backend(forBundleIdentifier: AppBuild.productionBundleIdentifier),
      .keychain)
    XCTAssertEqual(
      DesktopKeychainStore.backend(forBundleIdentifier: AppBuild.betaProductionBundleIdentifier),
      .keychain)
  }

  func testDeveloperBundleIdentifiersUseFileBackend() {
    XCTAssertEqual(
      DesktopKeychainStore.backend(forBundleIdentifier: AppBuild.desktopDevBundleIdentifier),
      .developerFile)
    XCTAssertEqual(
      DesktopKeychainStore.backend(forBundleIdentifier: "com.omi.omi-fix-rewind"),
      .developerFile)
    XCTAssertEqual(
      DesktopKeychainStore.backend(forBundleIdentifier: "com.example.adhoc"),
      .developerFile)
  }

  func testFileBackendNeverCallsInjectedKeychainOperations() {
    DesktopKeychainStore.backendOverride = .developerFile
    DesktopKeychainStore.keychainOperationsOverride = spyingKeychainOperations()

    XCTAssertTrue(DesktopKeychainStore.setString("file-secret", service: "svc", account: "acct"))
    XCTAssertEqual(DesktopKeychainStore.string(service: "svc", account: "acct"), "file-secret")
    DesktopKeychainStore.delete(service: "svc", account: "acct")
    XCTAssertNil(DesktopKeychainStore.string(service: "svc", account: "acct"))
    XCTAssertTrue(keychainCalls.all.isEmpty)
  }

  func testKeychainBackendUsesInjectedOperationsAndSkipsFileStore() {
    DesktopKeychainStore.backendOverride = .keychain
    let stored = ValueBox<String>()
    let calls = keychainCalls
    DesktopKeychainStore.keychainOperationsOverride = DesktopKeychainStore.KeychainOperations(
      readString: { _, _ in
        calls.record("read")
        if let value = stored.value {
          return .found(value)
        }
        return .missing
      },
      setString: { value, _, _ in
        calls.record("set")
        stored.value = value
        return true
      },
      delete: { _, _ in
        calls.record("delete")
        stored.value = nil
      }
    )

    XCTAssertTrue(DesktopKeychainStore.setString("kc-secret", service: "svc", account: "acct"))
    XCTAssertEqual(DesktopKeychainStore.string(service: "svc", account: "acct"), "kc-secret")
    DesktopKeychainStore.delete(service: "svc", account: "acct")
    XCTAssertNil(DesktopKeychainStore.string(service: "svc", account: "acct"))
    XCTAssertEqual(keychainCalls.all, ["set", "read", "delete", "read"])
    XCTAssertNil(fileStore.readString(service: "svc", account: "acct"))
  }

  private func spyingKeychainOperations() -> DesktopKeychainStore.KeychainOperations {
    let calls = keychainCalls
    return DesktopKeychainStore.KeychainOperations(
      readString: { _, _ in
        calls.record("read")
        return .missing
      },
      setString: { _, _, _ in
        calls.record("set")
        return false
      },
      delete: { _, _ in
        calls.record("delete")
      }
    )
  }
}

private final class CallRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var items: [String] = []

  func record(_ item: String) {
    lock.lock()
    items.append(item)
    lock.unlock()
  }

  var all: [String] {
    lock.lock()
    defer { lock.unlock() }
    return items
  }
}

private final class ValueBox<Value>: @unchecked Sendable {
  private let lock = NSLock()
  private var stored: Value?

  var value: Value? {
    get {
      lock.lock()
      defer { lock.unlock() }
      return stored
    }
    set {
      lock.lock()
      stored = newValue
      lock.unlock()
    }
  }
}
