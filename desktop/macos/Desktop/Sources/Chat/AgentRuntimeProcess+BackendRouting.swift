extension AgentRuntimeProcess {
  /// Preserve the complete app-selected backend tuple in the Node child while
  /// adding the desktop `/v2` base consumed by the agent bridge. This helper is
  /// intentionally testable so a named QA bundle cannot appear correctly
  /// routed in Swift while its agent child inherits a different authority.
  static func childBackendRoutingEnvironment(
    baseEnvironment: [String: String],
    rustBase: String
  ) -> [String: String] {
    var environment = baseEnvironment
    if rustBase.isEmpty {
      environment.removeValue(forKey: "OMI_API_BASE_URL")
    } else {
      environment["OMI_API_BASE_URL"] =
        rustBase.hasSuffix("/")
        ? "\(rustBase)v2"
        : "\(rustBase)/v2"
    }
    return environment
  }
}
