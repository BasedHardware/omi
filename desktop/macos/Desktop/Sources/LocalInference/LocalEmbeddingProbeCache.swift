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
  private var inFlight: [Key: Task<LocalEmbeddingProbe, Never>] = [:]

  func get(_ key: Key, ttl: Duration, now: ContinuousClock.Instant) -> LocalEmbeddingProbe? {
    guard let entry = entries[key], now - entry.storedAt <= ttl else { return nil }
    return entry.probe
  }

  func store(_ key: Key, probe: LocalEmbeddingProbe, now: ContinuousClock.Instant) {
    entries[key] = (probe, now)
  }

  func getOrCompute(
    _ key: Key,
    ttl: Duration,
    now: ContinuousClock.Instant,
    compute: @escaping @Sendable () async -> LocalEmbeddingProbe
  ) async -> LocalEmbeddingProbe {
    if let cached = get(key, ttl: ttl, now: now) { return cached }
    if let existing = inFlight[key] {
      return await existing.value
    }
    let task = Task { await compute() }
    inFlight[key] = task
    let probe = await task.value
    inFlight[key] = nil
    if probe.reason != "cancelled" {
      store(key, probe: probe, now: now)
    }
    return probe
  }

  func invalidate() {
    entries.removeAll()
  }
}
