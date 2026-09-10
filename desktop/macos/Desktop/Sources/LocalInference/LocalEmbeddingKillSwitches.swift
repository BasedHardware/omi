import Foundation

struct LocalEmbeddingKillSwitches: Sendable, Equatable {
  var isDisabled: Bool
  var forcedEngineRaw: String?
  static let enabled = Self(isDisabled: false, forcedEngineRaw: nil)

  static func resolve(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    defaults: UserDefaults = .standard
  ) -> Self {
    func trimmed(_ value: String?) -> String? {
      guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
      return value
    }
    return Self(
      isDisabled: environment["OMI_DISABLE_LOCAL_EMBEDDINGS"] == "1" || defaults.bool(forKey: "disableLocalEmbeddings"),
      forcedEngineRaw: trimmed(environment["OMI_FORCE_LOCAL_EMBEDDING_ENGINE"])
        ?? trimmed(defaults.string(forKey: "forceLocalEmbeddingEngine")))
  }
}
