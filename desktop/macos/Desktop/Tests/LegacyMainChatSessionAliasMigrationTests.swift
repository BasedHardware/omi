import Foundation
import XCTest

@testable import Omi_Computer

private final class MigrationAuthorizationFlag: @unchecked Sendable {
  private let lock = NSLock()
  private var current = true

  func revoke() {
    lock.withLock { current = false }
  }

  func isCurrent() -> Bool {
    lock.withLock { current }
  }
}

private actor DelayedLegacyAliasImporter {
  private var entries: [LegacyMainChatSessionAliasEntry]?
  private var startedWaiter: CheckedContinuation<Void, Never>?
  private var importContinuation:
    CheckedContinuation<LegacyMainChatSessionImportReceipt, Error>?

  func importEntries(
    _ entries: [LegacyMainChatSessionAliasEntry]
  ) async throws -> LegacyMainChatSessionImportReceipt {
    self.entries = entries
    startedWaiter?.resume()
    startedWaiter = nil
    return try await withCheckedThrowingContinuation { continuation in
      importContinuation = continuation
    }
  }

  func waitUntilStarted() async {
    if entries != nil { return }
    await withCheckedContinuation { continuation in
      startedWaiter = continuation
    }
  }

  func complete(ownerID: String) -> Bool {
    guard let entries, let importContinuation else { return false }
    self.importContinuation = nil
    importContinuation.resume(returning: LegacyMainChatSessionImportReceipt(
      ownerId: ownerID,
      acceptedEntries: entries,
      importedCount: entries.count))
    return true
  }
}

private actor HeldAliasOwnerTransition {
  private var entered = false
  private var enteredWaiter: CheckedContinuation<Void, Never>?
  private var releaseContinuation: CheckedContinuation<Void, Never>?

  func enterAndWait() async {
    entered = true
    enteredWaiter?.resume()
    enteredWaiter = nil
    await withCheckedContinuation { continuation in
      releaseContinuation = continuation
    }
  }

  func waitUntilEntered() async {
    if entered { return }
    await withCheckedContinuation { continuation in
      enteredWaiter = continuation
    }
  }

  func release() -> Bool {
    guard let releaseContinuation else { return false }
    self.releaseContinuation = nil
    releaseContinuation.resume()
    return true
  }
}

final class LegacyMainChatSessionAliasMigrationTests: XCTestCase {
  private let defaultsKey = LegacyMainChatSessionAliasMigration.defaultsKey

  func testDeletesOnlyAcknowledgedOwnerAliasesAfterExactKernelReceipt() async throws {
    let (defaults, suiteName) = makeDefaults()
    defer { defaults.removePersistentDomain(forName: suiteName) }
    defaults.set([
      "owner-a|default": "ses-a",
      "owner-b|default": "ses-b",
    ], forKey: defaultsKey)

    let outcome = await LegacyMainChatSessionAliasMigration.migrate(
      ownerId: "owner-a",
      defaults: defaults
    ) { entries in
      LegacyMainChatSessionImportReceipt(
        ownerId: "owner-a",
        acceptedEntries: entries,
        importedCount: 1
      )
    }

    XCTAssertEqual(outcome, .acknowledged(removedCount: 1))
    XCTAssertEqual(
      defaults.dictionary(forKey: defaultsKey) as? [String: String],
      ["owner-b|default": "ses-b"]
    )
  }

  func testProcessExitRetainsAliasesForRestartRetry() async throws {
    let (defaults, suiteName) = makeDefaults()
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let original = ["owner-a|default": "ses-a"]
    defaults.set(original, forKey: defaultsKey)

    let outcome = await LegacyMainChatSessionAliasMigration.migrate(
      ownerId: "owner-a",
      defaults: defaults
    ) { _ in
      throw BridgeError.processExited
    }

    XCTAssertEqual(outcome, .retained(reason: "kernel_import_failed"))
    XCTAssertEqual(defaults.dictionary(forKey: defaultsKey) as? [String: String], original)
  }

  func testTimeoutRetainsAliasesForRestartRetry() async throws {
    let (defaults, suiteName) = makeDefaults()
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let original = ["owner-a|default": "ses-a"]
    defaults.set(original, forKey: defaultsKey)

    let outcome = await LegacyMainChatSessionAliasMigration.migrate(
      ownerId: "owner-a",
      defaults: defaults
    ) { _ in
      throw BridgeError.timeout
    }

    XCTAssertEqual(outcome, .retained(reason: "kernel_import_failed"))
    XCTAssertEqual(defaults.dictionary(forKey: defaultsKey) as? [String: String], original)
  }

  func testInvalidAliasRetainsWholeOwnerBatchWithoutCallingKernel() async throws {
    let (defaults, suiteName) = makeDefaults()
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let original = [
      "owner-a|default": "ses-a",
      "owner-a|other": "   ",
    ]
    defaults.set(original, forKey: defaultsKey)

    let outcome = await LegacyMainChatSessionAliasMigration.migrate(
      ownerId: "owner-a",
      defaults: defaults
    ) { _ in
      throw BridgeError.agentError("unexpected importer call")
    }

    XCTAssertEqual(outcome, .retained(reason: "invalid_alias_entry"))
    XCTAssertEqual(defaults.dictionary(forKey: defaultsKey) as? [String: String], original)
  }

  func testMismatchedKernelReceiptRetainsAliasesForRestartRetry() async throws {
    let (defaults, suiteName) = makeDefaults()
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let original = ["owner-a|default": "ses-a"]
    defaults.set(original, forKey: defaultsKey)

    let outcome = await LegacyMainChatSessionAliasMigration.migrate(
      ownerId: "owner-a",
      defaults: defaults
    ) { entries in
      LegacyMainChatSessionImportReceipt(
        ownerId: "owner-b",
        acceptedEntries: entries,
        importedCount: 1
      )
    }

    XCTAssertEqual(outcome, .retained(reason: "invalid_kernel_receipt"))
    XCTAssertEqual(defaults.dictionary(forKey: defaultsKey) as? [String: String], original)
  }

  func testPartialKernelAcceptanceRetainsWholeOwnerBatchForRestartRetry() async throws {
    let (defaults, suiteName) = makeDefaults()
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let original = [
      "owner-a|default": "ses-a",
      "owner-a|other": "ses-other",
    ]
    defaults.set(original, forKey: defaultsKey)

    let outcome = await LegacyMainChatSessionAliasMigration.migrate(
      ownerId: "owner-a",
      defaults: defaults
    ) { entries in
      LegacyMainChatSessionImportReceipt(
        ownerId: "owner-a",
        acceptedEntries: [entries[0]],
        importedCount: 1
      )
    }

    XCTAssertEqual(outcome, .retained(reason: "invalid_kernel_receipt"))
    XCTAssertEqual(defaults.dictionary(forKey: defaultsKey) as? [String: String], original)
  }

  func testSameOwnerSessionReplacementDuringImportRetainsAliases() async throws {
    let (defaults, suiteName) = makeDefaults()
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let original = ["owner-a|default": "ses-a"]
    defaults.set(original, forKey: defaultsKey)
    let authorization = MigrationAuthorizationFlag()
    let importer = DelayedLegacyAliasImporter()

    let migration = Task {
      await LegacyMainChatSessionAliasMigration.migrate(
        ownerId: "owner-a",
        defaults: defaults,
        isAuthorizationCurrent: { authorization.isCurrent() }
      ) { entries in
        try await importer.importEntries(entries)
      }
    }

    await importer.waitUntilStarted()
    authorization.revoke()
    let completed = await importer.complete(ownerID: "owner-a")
    XCTAssertTrue(completed)

    let outcome = await migration.value
    XCTAssertEqual(
      outcome,
      .retained(reason: "owner_authorization_revoked"))
    XCTAssertEqual(defaults.dictionary(forKey: defaultsKey) as? [String: String], original)
  }

  func testQueuedOwnerTransitionBlocksAndRevokesFinalAliasCommit() async throws {
    let (defaults, suiteName) = makeDefaults()
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let original = ["owner-a|default": "ses-a"]
    defaults.set(original, forKey: defaultsKey)
    let authorization = MigrationAuthorizationFlag()
    let importer = DelayedLegacyAliasImporter()
    let transitionGate = HeldAliasOwnerTransition()

    let migration = Task {
      await LegacyMainChatSessionAliasMigration.migrate(
        ownerId: "owner-a",
        defaults: defaults,
        isAuthorizationCurrent: { authorization.isCurrent() }
      ) { entries in
        try await importer.importEntries(entries)
      }
    }
    await importer.waitUntilStarted()

    let transition = Task {
      await EffectiveOwnerTransitionFence.shared.performEffectiveOwnerTransition(
        currentOwner: { authorization.isCurrent() ? "owner-a" : "owner-b" },
        plannedNextOwner: { _ in "owner-b" },
        beginAuthorizationRevocation: { _ in authorization.revoke() },
        quiescePreviousOwner: { _, _ in
          await transitionGate.enterAndWait()
        },
        transition: {},
        retargetLocalStorage: { _, _ in },
        ownerDidChange: {})
    }
    await transitionGate.waitUntilEntered()
    let importerCompleted = await importer.complete(ownerID: "owner-a")
    XCTAssertTrue(importerCompleted)
    await EffectiveOwnerTransitionFence.shared.waitUntilMutationIsPending()

    XCTAssertEqual(defaults.dictionary(forKey: defaultsKey) as? [String: String], original)
    let transitionReleased = await transitionGate.release()
    XCTAssertTrue(transitionReleased)
    await transition.value

    let outcome = await migration.value
    XCTAssertEqual(outcome, .retained(reason: "owner_authorization_revoked"))
    XCTAssertEqual(defaults.dictionary(forKey: defaultsKey) as? [String: String], original)
  }

  private func makeDefaults() -> (UserDefaults, String) {
    let suiteName = "LegacyMainChatSessionAliasMigrationTests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defaults.removePersistentDomain(forName: suiteName)
    return (defaults, suiteName)
  }
}
