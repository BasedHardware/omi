/// Effects an automation action may have, including work it starts asynchronously.
/// Registration must declare the union of all supported parameter paths. An empty
/// set means a read-only observation; a name containing `probe` proves nothing.
/// Incidental diagnostic logging/analytics is outside this product-effect contract.
enum DesktopAutomationActionEffect: String, Codable, CaseIterable, Sendable {
  case localState = "local_ui_state"
  case localArtifact = "local_artifact"
  case networkOrModel = "network_or_model"
  case remoteWrite = "remote_write"

  var description: String {
    switch self {
    case .localState: return "mutates local app, UI, or stored state"
    case .localArtifact: return "writes local artifact file"
    case .networkOrModel: return "may call agent runtime, model, or backend services"
    case .remoteWrite: return "may mutate remote user data"
    }
  }

  /// Preserve the coarse discovery field while exposing every effect separately.
  static func safety(for effects: Set<Self>) -> String {
    for effect in [Self.remoteWrite, .networkOrModel, .localArtifact, .localState] {
      if effects.contains(effect) { return effect.rawValue }
    }
    return "read_only"
  }
}
