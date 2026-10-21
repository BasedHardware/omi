import Foundation

/// On-device summary attachment defaults on in every channel. The funding decision
/// is separate: users with allowance keep cloud processing. Explicit off remains
/// available through environment or UserDefaults in shipped builds.
struct FreeTierLocalProcessingFlag: Sendable, Equatable {
  static let environmentKey = "OMI_FREE_TIER_LOCAL_PROCESSING"
  static let defaultsKey = "freeTierLocalProcessing"

  static func isEnabled(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    defaults: UserDefaults = .standard,
    isBetaProductionBundle _: Bool = AppBuild.isBetaProductionBundle,
    remoteDisabled: Bool = LocalCapabilityRemoteKill.isDisabled
  ) -> Bool {
    guard !remoteDisabled else { return false }
    if let raw = environment[environmentKey], !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      return isTruthy(raw)
    }
    // `object(forKey:)` rather than `bool(forKey:)`: an explicit stored `false`
    // has to be distinguishable from "never set", or Beta could not be turned
    // off without a rebuild.
    if defaults.object(forKey: defaultsKey) != nil {
      return defaults.bool(forKey: defaultsKey)
    }
    return true
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
