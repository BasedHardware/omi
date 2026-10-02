import XCTest

@testable import Omi_Computer

private actor MCPKeyCreationProbe {
  private(set) var count = 0
  private var continuation: CheckedContinuation<String, Never>?
  private var startedWaiter: CheckedContinuation<Void, Never>?
  let suspended: Bool

  init(suspended: Bool = false) {
    self.suspended = suspended
  }

  func create() async -> String {
    count += 1
    if !suspended { return "test-key" }
    return await withCheckedContinuation { continuation in
      self.continuation = continuation
      startedWaiter?.resume()
      startedWaiter = nil
    }
  }

  func waitUntilStarted() async {
    if continuation != nil { return }
    await withCheckedContinuation { startedWaiter = $0 }
  }

  func finish() {
    continuation?.resume(returning: "test-key")
    continuation = nil
  }
}

final class MemoryExportMCPKeyTests: XCTestCase {
  private var suiteNames: [String] = []

  override func tearDown() {
    for suiteName in suiteNames {
      UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName)
    }
    suiteNames.removeAll()
    super.tearDown()
  }

  // Each fixture uses a disposable preferences domain and an injected mint
  // operation. No test can issue a real credential or use a signed-in session.
  private func fixture(suspended: Bool = false) -> (UserDefaults, MemoryExportService, MCPKeyCreationProbe) {
    let suiteName = "mcp-key-tests-\(UUID().uuidString)"
    suiteNames.append(suiteName)
    let defaults = UserDefaults(suiteName: suiteName)!
    defaults.set("owner-a", forKey: "auth_userId")
    let probe = MCPKeyCreationProbe(suspended: suspended)
    // Transfer a separate defaults instance to the service actor. The test
    // retains only its own instance of the same disposable preferences domain,
    // modelling auth writes without sharing a non-Sendable object across actors.
    let service = MemoryExportService(
      defaults: UserDefaults(suiteName: suiteName)!, createMCPKey: { await probe.create() })
    return (defaults, service, probe)
  }

  func testStatusChecksDoNotCreateAKey() async {
    let (_, service, probe) = fixture()
    let stored = await service.storedMCPKey()
    let hasStored = await service.hasStoredMCPKey
    // Obsidian status avoids local MCP config scanning and cloud grant requests.
    _ = await service.status(for: .obsidian)
    let count = await probe.count
    XCTAssertNil(stored)
    XCTAssertFalse(hasStored)
    XCTAssertEqual(count, 0)
  }

  func testExplicitSetupWithoutCachedKeyCreatesExactlyOnce() async throws {
    let (_, service, probe) = fixture()
    let first = try await service.mcpKeyForLocalConnectorSetup()
    let second = try await service.ensureMCPKey()
    let stored = await service.storedMCPKey()
    let count = await probe.count
    XCTAssertEqual(first, "test-key")
    XCTAssertEqual(second, first)
    XCTAssertEqual(stored, first)
    XCTAssertEqual(count, 1)
  }

  func testExplicitSetupReusesKeyForSameOwner() async throws {
    let (defaults, service, probe) = fixture()
    defaults.set("cached-key", forKey: "memoryExportMCPApiKey")
    defaults.set("owner-a", forKey: "memoryExportMCPApiKeyOwnerUserId")
    let key = try await service.mcpKeyForLocalConnectorSetup()
    let hasStored = await service.hasStoredMCPKey
    let count = await probe.count
    XCTAssertEqual(key, "cached-key")
    XCTAssertTrue(hasStored)
    XCTAssertEqual(count, 0)
  }

  func testExplicitSetupDoesNotReuseAnotherOwnersKey() async throws {
    let (defaults, service, probe) = fixture()
    defaults.set("other-owner-key", forKey: "memoryExportMCPApiKey")
    defaults.set("owner-b", forKey: "memoryExportMCPApiKeyOwnerUserId")
    let key = try await service.mcpKeyForLocalConnectorSetup()
    let count = await probe.count
    XCTAssertEqual(key, "test-key")
    XCTAssertEqual(count, 1)
    XCTAssertEqual(defaults.string(forKey: "memoryExportMCPApiKeyOwnerUserId"), "owner-a")
  }

  func testConcurrentExplicitSetupsCreateOnlyOneKey() async throws {
    let (_, service, probe) = fixture(suspended: true)
    let first = Task { try await service.mcpKeyForLocalConnectorSetup() }
    await probe.waitUntilStarted()
    let second = Task { try await service.mcpKeyForLocalConnectorSetup() }
    await probe.finish()
    let firstKey = try await first.value
    let secondKey = try await second.value
    let count = await probe.count
    XCTAssertEqual(firstKey, secondKey)
    XCTAssertEqual(count, 1)
  }

  func testAccountSwitchDuringCreationRejectsAndDoesNotStoreKey() async {
    let (defaults, service, probe) = fixture(suspended: true)
    let setup = Task { try await service.mcpKeyForLocalConnectorSetup() }
    await probe.waitUntilStarted()
    defaults.set("owner-b", forKey: "auth_userId")
    await probe.finish()
    do {
      _ = try await setup.value
      XCTFail("An account switch must reject the completed key")
    } catch {
      XCTAssertTrue(error.localizedDescription.contains("account changed"))
    }
    XCTAssertNil(defaults.string(forKey: "memoryExportMCPApiKey"))
    XCTAssertNil(defaults.string(forKey: "memoryExportMCPApiKeyOwnerUserId"))
  }

  func testAccountSwitchDuringExplicitRotationRejectsKey() async {
    let (defaults, service, probe) = fixture(suspended: true)
    let setup = Task { try await service.createNewMCPKey() }
    await probe.waitUntilStarted()
    defaults.set("owner-b", forKey: "auth_userId")
    await probe.finish()
    do {
      _ = try await setup.value
      XCTFail("An account switch must reject the replacement key")
    } catch {
      XCTAssertTrue(error.localizedDescription.contains("account changed"))
    }
    XCTAssertNil(defaults.string(forKey: "memoryExportMCPApiKey"))
  }

  func testRevokedLocalKeyDoesNotRemintDuringStatusCheck() async {
    let (defaults, service, probe) = fixture()
    defaults.set("owner-a", forKey: "memoryExportMCPApiKeyOwnerUserId")
    defaults.removeObject(forKey: "memoryExportMCPApiKey")
    _ = await service.status(for: .obsidian)
    let stored = await service.storedMCPKey()
    let count = await probe.count
    XCTAssertNil(stored)
    XCTAssertEqual(count, 0)
  }
}
