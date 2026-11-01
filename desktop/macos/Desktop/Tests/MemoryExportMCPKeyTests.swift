import XCTest

@testable import Omi_Computer

private actor MCPKeyCreationProbe {
  private(set) var count = 0
  // Retain every pending mint: a scheduling regression that starts a second
  // concurrent create() must not overwrite (and strand) the first continuation.
  private var pending: [CheckedContinuation<String, Never>] = []
  private var startedWaiters: [CheckedContinuation<Void, Never>] = []
  private var finished = false
  let suspended: Bool

  init(suspended: Bool = false) {
    self.suspended = suspended
  }

  func create() async -> String {
    count += 1
    // A mint that starts after finish() is itself the regression the test
    // asserts on; return immediately so the failure is a clean count
    // mismatch instead of a suspended-forever test hang.
    if !suspended || finished { return "test-key" }
    return await withCheckedContinuation { continuation in
      pending.append(continuation)
      startedWaiters.forEach { $0.resume() }
      startedWaiters.removeAll()
    }
  }

  func waitUntilStarted() async {
    if !pending.isEmpty { return }
    await withCheckedContinuation { startedWaiters.append($0) }
  }

  func finish() {
    finished = true
    let waiters = pending
    pending = []
    waiters.forEach { $0.resume(returning: "test-key") }
  }
}

final class MemoryExportMCPKeyTests: XCTestCase {
  // These names mirror MemoryExportService's private defaults keys.
  private enum MemoryExportDefaultsKeyName {
    static let mcpKey = "memoryExportMCPApiKey"
    static let mcpKeyOwner = "memoryExportMCPApiKeyOwnerUserId"
  }

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
  private func fixture(suspended: Bool = false) throws -> (
    UserDefaults, MemoryExportService, MCPKeyCreationProbe
  ) {
    let suiteName = "mcp-key-tests-\(UUID().uuidString)"
    suiteNames.append(suiteName)
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defaults.set("owner-a", forKey: .authUserId)
    let probe = MCPKeyCreationProbe(suspended: suspended)
    // Transfer a separate defaults instance to the service actor. The test
    // retains only its own instance of the same disposable preferences domain,
    // modelling auth writes without sharing a non-Sendable object across actors.
    let service = MemoryExportService(
      defaults: try XCTUnwrap(UserDefaults(suiteName: suiteName)),
      createMCPKey: { await probe.create() })
    return (defaults, service, probe)
  }

  func testStatusChecksDoNotCreateAKey() async throws {
    let (_, service, probe) = try fixture()
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
    let (_, service, probe) = try fixture()
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
    let (defaults, service, probe) = try fixture()
    defaults.set("cached-key", forKey: MemoryExportDefaultsKeyName.mcpKey)
    defaults.set("owner-a", forKey: MemoryExportDefaultsKeyName.mcpKeyOwner)
    let key = try await service.mcpKeyForLocalConnectorSetup()
    let hasStored = await service.hasStoredMCPKey
    let count = await probe.count
    XCTAssertEqual(key, "cached-key")
    XCTAssertTrue(hasStored)
    XCTAssertEqual(count, 0)
  }

  func testExplicitSetupDoesNotReuseAnotherOwnersKey() async throws {
    let (defaults, service, probe) = try fixture()
    defaults.set("other-owner-key", forKey: MemoryExportDefaultsKeyName.mcpKey)
    defaults.set("owner-b", forKey: MemoryExportDefaultsKeyName.mcpKeyOwner)
    let key = try await service.mcpKeyForLocalConnectorSetup()
    let count = await probe.count
    XCTAssertEqual(key, "test-key")
    XCTAssertEqual(count, 1)
    XCTAssertEqual(defaults.string(forKey: MemoryExportDefaultsKeyName.mcpKeyOwner), "owner-a")
  }

  func testConcurrentExplicitSetupsCreateOnlyOneKey() async throws {
    let (_, service, probe) = try fixture(suspended: true)
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

  func testAccountSwitchDuringCreationRejectsAndDoesNotStoreKey() async throws {
    let (defaults, service, probe) = try fixture(suspended: true)
    let setup = Task { try await service.mcpKeyForLocalConnectorSetup() }
    await probe.waitUntilStarted()
    defaults.set("owner-b", forKey: .authUserId)
    await probe.finish()
    do {
      _ = try await setup.value
      XCTFail("An account switch must reject the completed key")
    } catch {
      XCTAssertTrue(error.localizedDescription.contains("account changed"))
    }
    XCTAssertNil(defaults.string(forKey: MemoryExportDefaultsKeyName.mcpKey))
    XCTAssertNil(defaults.string(forKey: MemoryExportDefaultsKeyName.mcpKeyOwner))
  }

  func testAccountSwitchDuringExplicitRotationRejectsKey() async throws {
    let (defaults, service, probe) = try fixture(suspended: true)
    let setup = Task { try await service.createNewMCPKey() }
    await probe.waitUntilStarted()
    defaults.set("owner-b", forKey: .authUserId)
    await probe.finish()
    do {
      _ = try await setup.value
      XCTFail("An account switch must reject the replacement key")
    } catch {
      XCTAssertTrue(error.localizedDescription.contains("account changed"))
    }
    XCTAssertNil(defaults.string(forKey: MemoryExportDefaultsKeyName.mcpKey))
  }

  func testRevokedLocalKeyDoesNotRemintDuringStatusCheck() async throws {
    let (defaults, service, probe) = try fixture()
    // Drive the claimed transition: a key was genuinely stored, then cleared
    // (revoked/removed externally). A status check must observe the cleared
    // state without minting a replacement.
    defaults.set("stored-key", forKey: MemoryExportDefaultsKeyName.mcpKey)
    defaults.set("owner-a", forKey: MemoryExportDefaultsKeyName.mcpKeyOwner)
    let storedBefore = await service.storedMCPKey()
    XCTAssertEqual(storedBefore, "stored-key")

    defaults.removeObject(forKey: MemoryExportDefaultsKeyName.mcpKey)
    _ = await service.status(for: .obsidian)
    let stored = await service.storedMCPKey()
    let count = await probe.count
    XCTAssertNil(stored)
    XCTAssertEqual(count, 0)
  }
}
