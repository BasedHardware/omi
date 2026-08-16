import XCTest

@testable import Omi_Computer

@MainActor
final class LegacyVoiceJournalImporterTests: XCTestCase {
  private var defaults: UserDefaults!
  private var suiteName: String!

  override func setUp() async throws {
    suiteName = "LegacyVoiceJournalImporterTests.\(UUID().uuidString)"
    defaults = UserDefaults(suiteName: suiteName)
    defaults.removePersistentDomain(forName: suiteName)
  }

  override func tearDown() async throws {
    defaults.removePersistentDomain(forName: suiteName)
    defaults = nil
    suiteName = nil
  }

  func testImportIsBoundedOwnerScopedAndOnlyDeletesAcknowledgedEntries() throws {
    let key = "legacy"
    let entries = [
      entry(owner: "a", key: "a-1"),
      entry(owner: "b", key: "b-1"),
      entry(owner: "a", key: "a-2"),
    ]
    defaults.set(try JSONEncoder().encode(entries), forKey: key)
    let store = LegacyVoiceJournalImportStore(
      defaults: defaults, storageKey: key, batchLimit: 1)

    XCTAssertEqual(store.nextBatch(ownerID: "a")?.map(\.idempotencyKey), ["a-1"])
    store.acknowledge(ownerID: "a", idempotencyKeys: ["a-1"])
    XCTAssertEqual(store.nextBatch(ownerID: "a")?.map(\.idempotencyKey), ["a-2"])
    XCTAssertEqual(store.nextBatch(ownerID: "b")?.map(\.idempotencyKey), ["b-1"])
  }

  func testUnreadableLegacyPayloadIsReportedWithoutMutation() {
    let key = "legacy"
    let raw = Data("not-json".utf8)
    defaults.set(raw, forKey: key)
    let store = LegacyVoiceJournalImportStore(defaults: defaults, storageKey: key)

    XCTAssertNil(store.nextBatch(ownerID: "a"))
    XCTAssertEqual(defaults.data(forKey: key), raw)
  }

  private func entry(owner: String, key: String) -> LegacyVoiceJournalImportEntry {
    LegacyVoiceJournalImportEntry(
      ownerID: owner,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefID: "default",
      idempotencyKey: key,
      userText: "user",
      assistantText: "assistant",
      interrupted: false,
      createdAtMs: 1)
  }
}
