import Foundation

struct LegacyVoiceJournalCompatibilityMetadata: Equatable {
  static let owner = "desktop-realtime-voice"
  static let removalCondition =
    "all supported desktop versions have drained the retired realtime voice outbox into the kernel journal"
  static let removeBy = "2026-10-01"
}

/// Decode-only shape for the bounded upgrade import from the retired Swift
/// voice queue. New voice turns never write this format.
struct LegacyVoiceJournalImportEntry: Codable, Equatable, Sendable {
  let ownerID: String
  let surfaceKind: String
  let externalRefKind: String
  let externalRefID: String
  let idempotencyKey: String
  let userText: String
  let assistantText: String
  let interrupted: Bool
  let createdAtMs: Int64
}

/// Bounded, owner-scoped reader for the retired UserDefaults queue. Its only
/// mutation is deleting entries after the kernel journal accepts them.
@MainActor
final class LegacyVoiceJournalImportStore {
  static let shared = LegacyVoiceJournalImportStore()

  private let defaults: UserDefaults
  private let storageKey: String
  private let batchLimit: Int

  init(
    defaults: UserDefaults = .standard,
    storageKey: String = "realtimeVoiceTurnOutbox.v1",
    batchLimit: Int = 200
  ) {
    self.defaults = defaults
    self.storageKey = storageKey
    self.batchLimit = max(1, batchLimit)
  }

  /// `nil` means the legacy payload is unreadable; an empty array means there
  /// is no remaining work for this owner.
  func nextBatch(ownerID: String) -> [LegacyVoiceJournalImportEntry]? {
    guard let data = defaults.data(forKey: storageKey) else { return [] }
    guard let entries = try? JSONDecoder().decode([LegacyVoiceJournalImportEntry].self, from: data)
    else { return nil }
    return Array(entries.lazy.filter { $0.ownerID == ownerID }.prefix(batchLimit))
  }

  func acknowledge(ownerID: String, idempotencyKeys: Set<String>) {
    guard !idempotencyKeys.isEmpty,
      let data = defaults.data(forKey: storageKey),
      var entries = try? JSONDecoder().decode([LegacyVoiceJournalImportEntry].self, from: data)
    else { return }
    entries.removeAll {
      $0.ownerID == ownerID && idempotencyKeys.contains($0.idempotencyKey)
    }
    if entries.isEmpty {
      defaults.removeObject(forKey: storageKey)
    } else if let remaining = try? JSONEncoder().encode(entries) {
      defaults.set(remaining, forKey: storageKey)
    }
  }
}
