import Foundation

/// In-process probe verdict cache keyed by engine/model plus thermal and kill-switch state.
actor LocalEmbeddingProbeCache: Sendable {
  static let shared = LocalEmbeddingProbeCache()
  struct Key: Hashable, Sendable {
    var engineID: String
    var modelID: String
    var thermalState: Int
    var disabled: Bool
    var forcedEngine: String
  }

  private var entries: [Key: (probe: LocalEmbeddingProbe, storedAt: ContinuousClock.Instant)] = [:]

  func get(_ key: Key, ttl: Duration, now: ContinuousClock.Instant) -> LocalEmbeddingProbe? {
    guard let entry = entries[key], now - entry.storedAt <= ttl else { return nil }
    return entry.probe
  }

  func store(_ key: Key, probe: LocalEmbeddingProbe, now: ContinuousClock.Instant) {
    entries[key] = (probe, now)
  }

  func invalidate() {
    entries.removeAll()
  }
}
