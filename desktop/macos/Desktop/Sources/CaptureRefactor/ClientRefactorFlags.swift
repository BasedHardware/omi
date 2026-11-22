/// PostHog selects the serving cohort; absent/non-boolean values keep the old path.
enum ClientRefactorFlags {
  static let chunksFlag = "clients_from_segments_chunks"
  @MainActor static var chunks: Bool { enabled(chunksFlag) }
  @MainActor static func enabled(_ key: String) -> Bool {
    PostHogManager.shared.getFeatureFlag(key) as? Bool == true
  }
}
