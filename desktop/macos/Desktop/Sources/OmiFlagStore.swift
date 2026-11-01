import Foundation

/// One flag answered by Omi's own flag store (`GET /v1/flags`).
struct OmiFlag: Sendable, Equatable {
  let key: String
  let enabled: Bool
  var variant: String?
  var payloadJson: String?
}

/// Flags served by Omi's own flag store, read ahead of PostHog.
///
/// A key the store does not list is `nil` here, so the caller keeps PostHog's answer:
/// flags move off PostHog one at a time as the operator writes them, and deleting a
/// rule hands the key back. Refreshes ride the existing PostHog reload points (launch
/// identify and the 30-minute screen-task reload), so this adds one backend call per
/// PostHog reload and no PostHog requests. Docs: `backend/docs/runbooks/omi-flags.md`.
final class OmiFlagStore: @unchecked Sendable {
  static let shared = OmiFlagStore()

  private let lock = NSLock()
  private var flags: [String: OmiFlag] = [:]
  private var generation = 0
  private var refreshInFlight = false

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
    lock.withLock {
      generation += 1
      flags = [:]
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
      guard !refreshInFlight else { return nil }
      refreshInFlight = true
      return self.generation
    }
    guard let generation else { return }
    Task {
      defer { lock.withLock { refreshInFlight = false } }
      // A failed fetch keeps the last answer; unknown keys still fall back to PostHog.
      guard let fetched = try? await APIClient.shared.clientFlags() else { return }
      if apply(fetched, generation: generation) {
        await MainActor.run { NotificationCenter.default.post(name: PostHogManager.featureFlagsDidLoad, object: nil) }
      }
    }
  }
}
