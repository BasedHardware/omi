import Foundation

/// Client gate for S11 local projection attach. On by default in the Beta app,
/// off everywhere else.
///
/// Mirrors the backend `FREE_TIER_LOCAL_PROCESSING` boolean and the S9
/// env-or-UserDefaults kill-switch pattern. Flag off keeps today's
/// segments-only from-segments upload.
///
/// Beta defaults on because the two halves must be lit together. The backend
/// policy denies managed compute to an identified-basic desktop user and then
/// chooses `store_projection` only when a projection actually arrived; with no
/// projection it lands on the deterministic minimum, which is terminal. A Beta
/// build with this off would therefore take the cloud summary away and deliver
/// nothing in its place. Beta serves through the development plane, so lighting
/// the backend cohort without lighting the client is exactly the combination
/// that produces that outcome.
///
/// Precedence: an explicit environment value or an explicit stored default wins
/// in both directions, so the switch is still a kill switch on Beta. Only the
/// *absence* of both falls through to the per-channel default.
struct FreeTierLocalProcessingFlag: Sendable, Equatable {
  static let environmentKey = "OMI_FREE_TIER_LOCAL_PROCESSING"
  static let defaultsKey = "freeTierLocalProcessing"

  static func isEnabled(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    defaults: UserDefaults = .standard,
    isBetaProductionBundle: Bool = AppBuild.isBetaProductionBundle
  ) -> Bool {
    if let raw = environment[environmentKey], !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      return isTruthy(raw)
    }
    // `object(forKey:)` rather than `bool(forKey:)`: an explicit stored `false`
    // has to be distinguishable from "never set", or Beta could not be turned
    // off without a rebuild.
    if defaults.object(forKey: defaultsKey) != nil {
      return defaults.bool(forKey: defaultsKey)
    }
    return isBetaProductionBundle
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
