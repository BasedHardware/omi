import Foundation

struct RealtimeVoiceTurnOutboxEntry: Codable, Equatable, Sendable {
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

/// Small durable handoff between the realtime controller and the kernel-owned
/// transcript. Entries survive an agent-runtime or app restart, replay with the
/// same idempotency key, and are removed only after `turn_recorded` is received.
@MainActor
final class RealtimeVoiceTurnOutbox {
  static let shared = RealtimeVoiceTurnOutbox()

  private let defaults: UserDefaults
  private let storageKey: String
  private(set) var entries: [RealtimeVoiceTurnOutboxEntry]

  init(
    defaults: UserDefaults = .standard,
    storageKey: String = "realtimeVoiceTurnOutbox.v1"
  ) {
    self.defaults = defaults
    self.storageKey = storageKey
    if let data = defaults.data(forKey: storageKey),
      let decoded = try? JSONDecoder().decode([RealtimeVoiceTurnOutboxEntry].self, from: data)
    {
      entries = decoded
    } else {
      entries = []
    }
  }

  func enqueue(_ entry: RealtimeVoiceTurnOutboxEntry) {
    guard !entries.contains(where: { $0.idempotencyKey == entry.idempotencyKey }) else { return }
    entries.append(entry)
    persist()
  }

  func acknowledge(idempotencyKey: String) {
    let oldCount = entries.count
    entries.removeAll { $0.idempotencyKey == idempotencyKey }
    guard entries.count != oldCount else { return }
    persist()
  }

  func entries(ownerID: String) -> [RealtimeVoiceTurnOutboxEntry] {
    entries.filter { $0.ownerID == ownerID }
  }

  func entries(ownerID: String, surface: AgentSurfaceReference) -> [RealtimeVoiceTurnOutboxEntry] {
    entries.filter {
      $0.ownerID == ownerID
        && $0.surfaceKind == surface.surfaceKind
        && $0.externalRefKind == surface.externalRefKind
        && $0.externalRefID == surface.externalRefId
    }
  }

  func seedContext(
    ownerID: String,
    surface: AgentSurfaceReference,
    excludingIdempotencyKeys: Set<String> = [],
    maxCharacters: Int = 24_000
  ) -> String {
    var newestFirst: [String] = []
    var remaining = max(0, maxCharacters)
    for entry in entries(ownerID: ownerID, surface: surface).reversed()
    where remaining > 0 && !excludingIdempotencyKeys.contains(entry.idempotencyKey) {
      let user = entry.userText.trimmingCharacters(in: .whitespacesAndNewlines)
      let assistant = entry.assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
      var lines: [String] = []
      if !user.isEmpty { lines.append("User: \(user)") }
      if !assistant.isEmpty {
        lines.append("Omi\(entry.interrupted ? " (interrupted)" : ""): \(assistant)")
      }
      let block = lines.joined(separator: "\n")
      guard !block.isEmpty else { continue }
      newestFirst.append(String(block.prefix(remaining)))
      remaining -= min(block.count, remaining) + 1
    }
    return newestFirst.reversed().joined(separator: "\n")
  }

  private func persist() {
    guard let data = try? JSONEncoder().encode(entries) else { return }
    defaults.set(data, forKey: storageKey)
  }
}
