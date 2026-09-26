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
      isConnected: isConnected
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

  /// Offer one catalog entry through the coordinator's real delivery path, so
  /// the card can be inspected without waiting for the user to open the matching
  /// app — and so its budget is spent exactly as a real nudge's would be.
  ///
  /// Deliberately not a direct `showNotification` call: a QA path that presents
  /// without recording would diverge from production, and an e2e flow asserting
  /// the cooldown afterwards would be asserting something that never happened.
  static func present(telemetryID: String) -> [String: String] {
    guard let entry = IntegrationNudgeCatalog.entry(telemetryID: telemetryID) else {
      return [
        "presented": "false",
        "error": "unknown telemetry_id",
        "known": IntegrationNudgeCatalog.allTelemetryIDs.joined(separator: ","),
      ]
    }
    guard RuntimeOwnerIdentity.currentOwnerId() != nil else {
      return ["presented": "false", "error": "not signed in"]
    }

    let trigger =
      entry.triggers.first
      ?? IntegrationNudgeTrigger(id: "automation", match: .application(bundleIdentifiers: []))
    let outcome = IntegrationNudgeCoordinator.shared.offer(
      match: IntegrationNudgeMatcher.Match(entry: entry, trigger: trigger),
      isConnected: false
    )
    // `.delivered` means the bar took the card, which for a queued one is not
    // the same as drawing it — and only drawing spends the budget. Report the
    // budget, so an e2e step that asserts a cooldown afterwards is asserting
    // something that actually happened.
    let spentBudget = IntegrationNudgeStore.shared.state(for: entry.telemetryID).shownCount > 0
    return [
      "presented": outcome == .delivered ? "true" : "false",
      "spent_budget": spentBudget ? "true" : "false",
      "outcome": "\(outcome)",
      "integration": entry.displayName,
    ]
  }
}
