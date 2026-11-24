import Foundation

/// One flag answered by Omi's own flag store (`GET /v1/flags`).
struct OmiFlag: Sendable, Equatable {
  let key: String
  let enabled: Bool
  var variant: String?
  var payloadJson: String?
}

/// The only client flag authority. Missing keys are nil so callers retain their
/// existing defaults. Refreshes ride identify and the 30-minute screen-task tick;
/// failures keep the last answer for this account.
final class OmiFlagStore: @unchecked Sendable {
  static let shared = OmiFlagStore()

  private let lock = NSLock()
  private var flags: [String: OmiFlag] = [:]
  private var generation = 0
  private var inFlightGeneration: Int?

  func flag(_ key: String) -> OmiFlag? {
    lock.withLock { flags[key] }
  }

  /// PostHog-shaped value: the variant when set, else the boolean.
  func value(_ key: String) -> Any? {
    guard let flag = flag(key) else { return nil }
    if flag.enabled, let variant = flag.variant { return variant }
    return flag.enabled
  }

  func payload(_ key: String) -> Any? {
    guard let flag = flag(key), flag.enabled, let json = flag.payloadJson, let data = json.data(using: .utf8)
    else { return nil }
    return (try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed])) ?? json
  }

  /// Sign-out or account switch: another account's answers must not survive.
  func reset() {
    let changed = lock.withLock {
      let changed = !flags.isEmpty
      generation += 1
      flags = [:]
      return changed
    }
    if changed {
      Task { @MainActor in
        NotificationCenter.default.post(name: PostHogManager.featureFlagsDidLoad, object: nil)
      }
    }
  }

  var currentGeneration: Int { lock.withLock { generation } }

  /// Replace the snapshot unless an account change happened since `generation` was read. True when values changed.
  @discardableResult
  func apply(_ fetched: [OmiFlag], generation: Int) -> Bool {
    var next: [String: OmiFlag] = [:]
    for flag in fetched { next[flag.key] = flag }
    return lock.withLock {
      guard generation == self.generation else { return false }
      let changed = next != flags
      flags = next
      return changed
    }
  }

  func refresh() {
    let generation: Int? = lock.withLock {
      guard inFlightGeneration != self.generation else { return nil }
      inFlightGeneration = self.generation
      return self.generation
    }
    guard let generation else { return }
    Task {
      defer {
        lock.withLock {
          if inFlightGeneration == generation { inFlightGeneration = nil }
        }
      }
      // A failed fetch keeps the last answer for this account.
      guard let fetched = try? await APIClient.shared.clientFlags() else { return }
      if apply(fetched, generation: generation) {
        await MainActor.run { NotificationCenter.default.post(name: PostHogManager.featureFlagsDidLoad, object: nil) }
      }
    }
  }
}
