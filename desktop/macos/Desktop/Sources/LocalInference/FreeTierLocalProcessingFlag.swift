import Foundation

/// Client gate for S11 local projection attach. Default off (dark).
///
/// Mirrors the backend `FREE_TIER_LOCAL_PROCESSING` boolean and the S9
/// env-or-UserDefaults kill-switch pattern. Flag off keeps today's
/// segments-only from-segments upload.
struct FreeTierLocalProcessingFlag: Sendable, Equatable {
  static let environmentKey = "OMI_FREE_TIER_LOCAL_PROCESSING"
  static let defaultsKey = "freeTierLocalProcessing"

  static func isEnabled(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    defaults: UserDefaults = .standard
  ) -> Bool {
    isTruthy(environment[environmentKey]) || defaults.bool(forKey: defaultsKey)
  }

  static func isTruthy(_ raw: String?) -> Bool {
    guard let raw else { return false }
    switch raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
    case "1", "true", "yes":
      return true
    default:
      return false
    }
  }
}
