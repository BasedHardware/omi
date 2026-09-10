import Foundation

struct LocalEmbeddingKillSwitches: Sendable, Equatable {
  var isDisabled: Bool
  var isEnabled: Bool
  var forcedEngineRaw: String?
  static let enabled = Self(isDisabled: false, isEnabled: true, forcedEngineRaw: nil)

  init(isDisabled: Bool, isEnabled: Bool = true, forcedEngineRaw: String?) {
    self.isDisabled = isDisabled
    self.isEnabled = isEnabled
    self.forcedEngineRaw = forcedEngineRaw
  }

  static func resolve(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    defaults: UserDefaults = .standard,
    isNonProduction: Bool = AppBuild.isNonProduction
  ) -> Self {
    func trimmed(_ value: String?) -> String? {
      guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
      return value
    }
    func boolFlag(_ raw: String?) -> Bool? {
      guard let raw = trimmed(raw)?.lowercased() else { return nil }
      if ["1", "true", "yes", "on"].contains(raw) { return true }
      if ["0", "false", "no", "off"].contains(raw) { return false }
      return nil
    }
    let defaultsEnabled: Bool?
    if defaults.object(forKey: DefaultsKey.localEmbeddingsEnabled) != nil {
      defaultsEnabled = defaults.bool(forKey: .localEmbeddingsEnabled)
    } else {
      defaultsEnabled = nil
    }
    return Self(
      isDisabled: environment["OMI_DISABLE_LOCAL_EMBEDDINGS"] == "1"
        || defaults.bool(forKey: .disableLocalEmbeddings),
      isEnabled: boolFlag(environment["OMI_LOCAL_EMBEDDINGS"]) ?? defaultsEnabled ?? isNonProduction,
      forcedEngineRaw: trimmed(environment["OMI_FORCE_LOCAL_EMBEDDING_ENGINE"])
        ?? trimmed(defaults.string(forKey: .forceLocalEmbeddingEngine)))
  }
}
