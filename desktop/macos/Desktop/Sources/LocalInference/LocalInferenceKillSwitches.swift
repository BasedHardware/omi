import Foundation

/// Operator kill switches for local inference.
///
/// Mirrors `OMI_FORCE_PARAKEET_FAIL` / `forceParakeetFail`: each switch is
/// readable from the process environment **or** the app's UserDefaults.
///
/// - `OMI_DISABLE_LOCAL_INFERENCE=1` / `defaults write <bundle> disableLocalInference -bool true`
///   skips every engine and fail-closes to the deterministic minimum.
/// - `OMI_FORCE_LOCAL_INFERENCE_ENGINE=<id>` / `defaults write <bundle> forceLocalInferenceEngine -string <id>`
///   pins the engine. Unknown or unimplemented ids fail closed; they never
///   fall through to a cloud LLM.
struct LocalInferenceKillSwitches: Sendable, Equatable {
  static let disableEnvironmentKey = "OMI_DISABLE_LOCAL_INFERENCE"
  static let disableDefaultsKey = "disableLocalInference"
  static let forceEngineEnvironmentKey = "OMI_FORCE_LOCAL_INFERENCE_ENGINE"
  static let forceEngineDefaultsKey = "forceLocalInferenceEngine"
  static let serverURLEnvironmentKey = "OMI_LOCAL_INFERENCE_URL"
  static let serverURLDefaultsKey = "localInferenceServerURL"
  static let modelEnvironmentKey = "OMI_LOCAL_INFERENCE_MODEL"
  static let modelDefaultsKey = "localInferenceModel"

  var isDisabled: Bool
  var forcedEngineRaw: String?

  var forcedEngine: LocalInferenceEngineID? {
    guard let forcedEngineRaw, !forcedEngineRaw.isEmpty else { return nil }
    return LocalInferenceEngineID.parse(forcedEngineRaw)
  }

  static let enabled = LocalInferenceKillSwitches(isDisabled: false, forcedEngineRaw: nil)

  static func resolve(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    defaults: UserDefaults = .standard
  ) -> LocalInferenceKillSwitches {
    let envDisabled = environment[Self.disableEnvironmentKey] == "1"
    let defaultsDisabled = defaults.bool(forKey: Self.disableDefaultsKey)
    let envEngine = trimmed(environment[Self.forceEngineEnvironmentKey])
    let defaultsEngine = trimmed(defaults.string(forKey: Self.forceEngineDefaultsKey))
    return LocalInferenceKillSwitches(
      isDisabled: envDisabled || defaultsDisabled,
      forcedEngineRaw: envEngine ?? defaultsEngine
    )
  }

  static func localServerURL(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    defaults: UserDefaults = .standard
  ) -> URL {
    let raw =
      trimmed(environment[Self.serverURLEnvironmentKey])
      ?? trimmed(defaults.string(forKey: Self.serverURLDefaultsKey))
    if let raw, let parsed = URL(string: raw) {
      return parsed
    }
    return defaultLoopbackURL

  }

  private static let defaultLoopbackURL: URL = {
    var components = URLComponents()
    components.scheme = "http"
    components.host = "127.0.0.1"
    components.port = 11434
    components.path = "/v1"
    return components.url ?? URL(fileURLWithPath: "/v1")
  }()

  static func localServerModel(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    defaults: UserDefaults = .standard
  ) -> String {
    trimmed(environment[Self.modelEnvironmentKey])
      ?? trimmed(defaults.string(forKey: Self.modelDefaultsKey))
      ?? "local"
  }

  private static func trimmed(_ value: String?) -> String? {
    guard let value else { return nil }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }
}
