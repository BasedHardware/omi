import Foundation
import XCTest

@testable import Omi_Computer

final class ExtensionInstallSessionTests: XCTestCase {
  @MainActor
  private final class InstallGate {
    private var continuation: CheckedContinuation<ExtensionCatalogService.InstallReceipt, Error>?
    private var startedWaiters: [CheckedContinuation<Void, Never>] = []
    private(set) var callCount = 0

    func run() async throws -> ExtensionCatalogService.InstallReceipt {
      callCount += 1
      return try await withCheckedThrowingContinuation { continuation in
        self.continuation = continuation
        let waiters = startedWaiters
        startedWaiters.removeAll()
        for waiter in waiters { waiter.resume() }
      }
    }

    func waitUntilStarted() async {
      guard continuation == nil else { return }
      await withCheckedContinuation { startedWaiters.append($0) }
    }

    func finish(_ result: Result<ExtensionCatalogService.InstallReceipt, Error>) {
      guard let continuation else {
        XCTFail("Expected a suspended install")
        return
      }
      self.continuation = nil
      continuation.resume(with: result)
    }
  }

  @MainActor
  private final class RefreshGate {
    private var continuation: CheckedContinuation<Void, Never>?
    private var startedWaiters: [CheckedContinuation<Void, Never>] = []
    private(set) var callCount = 0

    func run() async {
      callCount += 1
      await withCheckedContinuation { continuation in
        self.continuation = continuation
        let waiters = startedWaiters
        startedWaiters.removeAll()
        for waiter in waiters { waiter.resume() }
      }
    }

    func waitUntilStarted() async {
      guard continuation == nil else { return }
      await withCheckedContinuation { startedWaiters.append($0) }
    }

    func finish() {
      guard let continuation else {
        XCTFail("Expected a suspended refresh")
        return
      }
      self.continuation = nil
      continuation.resume()
    }
  }

  private enum InstallError: LocalizedError {
    case rejected

    var errorDescription: String? { "Installation was rejected" }
  }

  private static func entry(install: ExtensionCatalog.Install? = nil) -> ExtensionCatalog.Entry {
    ExtensionCatalog.Entry(
      id: "com.example/test",
      name: "Example",
      subtitle: "HTTP",
      detail: "Publisher-managed tools",
      install: install ?? .mcpRemote(url: "https://example.test/mcp", transport: "http", secretHeader: nil))
  }

  private static let installedServer = LocalMcpStore.Entry(
    name: "example-2", summary: "https://example.test/mcp", isCommand: false)

  @MainActor
  func testServerReceiptBecomesExactSetupTargetAndRefreshesOnce() async {
    let entry = Self.entry()
    let secrets = ["Authorization": "test-only-value"]
    var installCalls = 0
    var refreshCalls = 0
    let session = ExtensionInstallSession(
      install: { receivedEntry, receivedSecrets in
        installCalls += 1
        XCTAssertEqual(receivedEntry, entry)
        XCTAssertEqual(receivedSecrets, secrets)
        return .mcpServer(Self.installedServer)
      },
      refresh: { refreshCalls += 1 })

    XCTAssertEqual(session.phase, .ready)
    XCTAssertTrue(session.canInstall)
    XCTAssertNil(session.installedServer)
    await session.install(entry, secrets: secrets)

    XCTAssertEqual(session.phase, .serverSetup(Self.installedServer))
    XCTAssertEqual(session.installedServer?.name, "example-2", "Use the receipt, not the marketplace display name")
    XCTAssertFalse(session.canInstall)
    XCTAssertFalse(session.isInstalling)
    XCTAssertEqual(installCalls, 1)
    XCTAssertEqual(refreshCalls, 1)

    await session.install(entry, secrets: secrets)
    XCTAssertEqual(installCalls, 1, "An already committed install cannot create another suffixed server")
    XCTAssertEqual(refreshCalls, 1)
  }

  @MainActor
  func testRepeatedInstallWhileOperationIsSuspendedRunsOnlyOnce() async {
    let gate = InstallGate()
    var refreshCalls = 0
    let session = ExtensionInstallSession(
      install: { _, _ in try await gate.run() }, refresh: { refreshCalls += 1 })
    let pending = Task { await session.install(Self.entry(), secrets: [:]) }
    await gate.waitUntilStarted()

    XCTAssertTrue(session.isInstalling)
    XCTAssertFalse(session.canInstall)
    await session.install(Self.entry(), secrets: [:])
    XCTAssertEqual(gate.callCount, 1)

    gate.finish(.success(.mcpServer(Self.installedServer)))
    await pending.value
    XCTAssertEqual(session.phase, .serverSetup(Self.installedServer))
    XCTAssertEqual(refreshCalls, 1)
  }

  @MainActor
  func testRejectedInstallExposesFailureAndAllowsOneDeliberateRetry() async {
    var installCalls = 0
    var refreshCalls = 0
    let session = ExtensionInstallSession(
      install: { _, _ in
        installCalls += 1
        if installCalls == 1 { throw InstallError.rejected }
        return .mcpServer(Self.installedServer)
      },
      refresh: { refreshCalls += 1 })

    await session.install(Self.entry(), secrets: [:])
    XCTAssertEqual(session.phase, .failed("Installation was rejected"))
    XCTAssertEqual(session.errorText, "Installation was rejected")
    XCTAssertTrue(session.canInstall)
    XCTAssertFalse(session.isInstalling)
    XCTAssertEqual(refreshCalls, 0)

    await session.install(Self.entry(), secrets: [:])
    XCTAssertEqual(session.phase, .serverSetup(Self.installedServer))
    XCTAssertNil(session.errorText)
    XCTAssertEqual(installCalls, 2)
    XCTAssertEqual(refreshCalls, 1)
  }

  @MainActor
  func testCloseDuringInstallIgnoresLateCommittedReceiptWithoutRefreshing() async {
    let gate = InstallGate()
    var refreshCalls = 0
    let session = ExtensionInstallSession(
      install: { _, _ in try await gate.run() }, refresh: { refreshCalls += 1 })
    let pending = Task { await session.install(Self.entry(), secrets: [:]) }
    await gate.waitUntilStarted()

    session.close()
    session.close()
    gate.finish(.success(.mcpServer(Self.installedServer)))
    await pending.value

    XCTAssertEqual(session.phase, .closed)
    XCTAssertNil(session.installedServer)
    XCTAssertNil(session.errorText)
    XCTAssertEqual(refreshCalls, 0)
    await session.install(Self.entry(), secrets: [:])
    XCTAssertEqual(gate.callCount, 1, "A dismissed sheet cannot start another install")
  }

  @MainActor
  func testCloseDuringInstallIgnoresLateErrorWithoutRefreshing() async {
    let gate = InstallGate()
    var refreshCalls = 0
    let session = ExtensionInstallSession(
      install: { _, _ in try await gate.run() }, refresh: { refreshCalls += 1 })
    let pending = Task { await session.install(Self.entry(), secrets: [:]) }
    await gate.waitUntilStarted()

    session.close()
    gate.finish(.failure(InstallError.rejected))
    await pending.value

    XCTAssertEqual(session.phase, .closed)
    XCTAssertNil(session.errorText)
    XCTAssertFalse(session.canInstall)
    XCTAssertEqual(refreshCalls, 0)
  }

  @MainActor
  func testCloseDuringRefreshDoesNotReopenSetupWhenRefreshFinishes() async {
    let gate = RefreshGate()
    var installCalls = 0
    let session = ExtensionInstallSession(
      install: { _, _ in
        installCalls += 1
        return .mcpServer(Self.installedServer)
      },
      refresh: { await gate.run() })
    let pending = Task { await session.install(Self.entry(), secrets: [:]) }
    await gate.waitUntilStarted()

    XCTAssertEqual(session.phase, .installing)
    session.close()
    gate.finish()
    await pending.value

    XCTAssertEqual(session.phase, .closed)
    XCTAssertNil(session.installedServer)
    XCTAssertEqual(installCalls, 1)
    XCTAssertEqual(gate.callCount, 1)
  }

  @MainActor
  func testCancellationBeforeCommitReturnsToReadyWithoutRefresh() async {
    let gate = InstallGate()
    var committedWrites = 0
    var refreshCalls = 0
    let session = ExtensionInstallSession(
      install: { _, _ in
        let receipt = try await gate.run()
        try Task.checkCancellation()
        committedWrites += 1
        return receipt
      },
      refresh: { refreshCalls += 1 })
    let pending = Task { await session.install(Self.entry(), secrets: [:]) }
    await gate.waitUntilStarted()

    pending.cancel()
    gate.finish(.success(.mcpServer(Self.installedServer)))
    await pending.value

    XCTAssertEqual(session.phase, .ready)
    XCTAssertTrue(session.canInstall)
    XCTAssertNil(session.errorText)
    XCTAssertEqual(committedWrites, 0)
    XCTAssertEqual(refreshCalls, 0)
  }

  @MainActor
  func testAlreadyCancelledInstallDoesNotStartAnOperation() async {
    var installCalls = 0
    var refreshCalls = 0
    let session = ExtensionInstallSession(
      install: { _, _ in
        installCalls += 1
        return .mcpServer(Self.installedServer)
      },
      refresh: { refreshCalls += 1 })
    let pending = Task { await session.install(Self.entry(), secrets: [:]) }
    pending.cancel()
    await pending.value

    XCTAssertEqual(session.phase, .ready)
    XCTAssertTrue(session.canInstall)
    XCTAssertEqual(installCalls, 0)
    XCTAssertEqual(refreshCalls, 0)
  }

  @MainActor
  func testCancellationAfterCommitRetainsReceiptAndCannotRetryInstallation() async {
    let gate = InstallGate()
    var committedWrites = 0
    var refreshCalls = 0
    let session = ExtensionInstallSession(
      install: { _, _ in
        committedWrites += 1
        // The store has committed. Cancellation cannot roll back its receipt.
        return try await gate.run()
      },
      refresh: { refreshCalls += 1 })
    let pending = Task { await session.install(Self.entry(), secrets: [:]) }
    await gate.waitUntilStarted()

    XCTAssertEqual(committedWrites, 1)
    pending.cancel()
    gate.finish(.success(.mcpServer(Self.installedServer)))
    await pending.value

    XCTAssertEqual(session.phase, .serverSetup(Self.installedServer))
    XCTAssertFalse(session.canInstall)
    XCTAssertNil(session.errorText)
    XCTAssertEqual(committedWrites, 1)
    XCTAssertEqual(refreshCalls, 0, "Cancellation may skip projection refresh, but cannot erase a committed install")
    await session.install(Self.entry(), secrets: [:])
    XCTAssertEqual(committedWrites, 1)
    XCTAssertEqual(gate.callCount, 1)
  }

  @MainActor
  func testCancellationDuringRefreshStillRetainsCommittedSetup() async {
    let gate = RefreshGate()
    var committedWrites = 0
    let session = ExtensionInstallSession(
      install: { _, _ in
        committedWrites += 1
        return .mcpServer(Self.installedServer)
      },
      refresh: { await gate.run() })
    let pending = Task { await session.install(Self.entry(), secrets: [:]) }
    await gate.waitUntilStarted()

    pending.cancel()
    gate.finish()
    await pending.value

    XCTAssertEqual(session.phase, .serverSetup(Self.installedServer))
    XCTAssertFalse(session.canInstall)
    XCTAssertEqual(committedWrites, 1)
  }

  @MainActor
  func testSkillSuccessRequiresExplicitCloseRatherThanDismissingItself() async {
    let entry = Self.entry(
      install: .skill(source: .init(repo: "example/skills", ref: "main", slug: "research", files: ["SKILL.md"])))
    var installCalls = 0
    var refreshCalls = 0
    let session = ExtensionInstallSession(
      install: { receivedEntry, _ in
        XCTAssertEqual(receivedEntry, entry)
        installCalls += 1
        return .skill(slug: "research")
      },
      refresh: { refreshCalls += 1 })

    await session.install(entry, secrets: [:])

    XCTAssertEqual(session.phase, .skillInstalled)
    XCTAssertNil(session.installedServer)
    XCTAssertFalse(session.canInstall)
    XCTAssertEqual(refreshCalls, 1)
    await session.install(entry, secrets: [:])
    XCTAssertEqual(installCalls, 1)
    session.close()
    session.close()
    XCTAssertEqual(session.phase, .closed)
  }
}
