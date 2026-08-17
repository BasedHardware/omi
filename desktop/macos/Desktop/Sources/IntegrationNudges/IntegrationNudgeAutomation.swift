import Foundation

/// Automation-bridge bodies for the integration-nudge feature.
///
/// These live here rather than inline in `DesktopAutomationBridge` so the
/// bridge keeps only the thin registration, and so an agent verifying this
/// feature reads the recognition logic next to the catalog it depends on.
///
/// Both are QA surfaces: the bridge auto-enables on non-production bundles
/// only, so neither is reachable in a shipped build.
@MainActor
enum IntegrationNudgeAutomation {
  /// Read-only: which integration a given frontmost app/window maps to, and
  /// whether a nudge would fire right now. Runs the real matcher, the real
  /// connection inspector, and the real policy — nothing is simulated except
  /// the window being described.
  static func evaluate(bundleID: String?, windowTitle: String?) async -> [String: String] {
    let window = IntegrationNudgeMatcher.Window(
      bundleIdentifier: bundleID,
      windowTitle: windowTitle
    )
    guard let match = IntegrationNudgeMatcher.match(window) else {
      return ["matched": "false"]
    }

    let isConnected = await IntegrationConnectionInspector.isConnected(match.entry.route)
    let decision = IntegrationNudgeCoordinator.shared.decide(
      entry: match.entry,
      isConnected: isConnected,
      dwell: IntegrationNudgePolicy.requiredDwell
    )

    return [
      "matched": "true",
      "integration": match.entry.displayName,
      "telemetry_id": match.entry.telemetryID,
      "trigger_id": match.trigger.id,
      "trigger_kind": match.trigger.kind.rawValue,
      "is_connected": isConnected ? "true" : "false",
      "would_nudge": decision.isDeliver ? "true" : "false",
      "suppression_reason": decision.suppression?.rawValue ?? "",
    ]
  }

  /// Present the connect card for one catalog entry through the real
  /// floating-bar path, so the card itself can be inspected without waiting for
  /// the user to open the matching app.
  static func present(telemetryID: String) -> [String: String] {
    guard let entry = IntegrationNudgeCatalog.all.first(where: { $0.telemetryID == telemetryID }) else {
      return [
        "presented": "false",
        "error": "unknown telemetry_id",
        "known": IntegrationNudgeCatalog.allTelemetryIDs.joined(separator: ","),
      ]
    }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else {
      return ["presented": "false", "error": "not signed in"]
    }

    let result = FloatingControlBarManager.shared.showNotification(
      ownerID: ownerID,
      title: "Connect \(entry.displayName) to Omi",
      message: entry.pitch,
      assistantId: IntegrationNudgeCoordinator.assistantID,
      sound: .none,
      action: .connectIntegration(telemetryID: entry.telemetryID)
    )
    return [
      "presented": (result == .presented || result == .queued) ? "true" : "false",
      "result": "\(result)",
      "integration": entry.displayName,
    ]
  }
}
