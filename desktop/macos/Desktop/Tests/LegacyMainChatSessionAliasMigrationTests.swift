import Foundation
import XCTest

@testable import Omi_Computer

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

  private func makeDefaults() -> (UserDefaults, String) {
    let suiteName = "LegacyMainChatSessionAliasMigrationTests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defaults.removePersistentDomain(forName: suiteName)
    return (defaults, suiteName)
  }
}
