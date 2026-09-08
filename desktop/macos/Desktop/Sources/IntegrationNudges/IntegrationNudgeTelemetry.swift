import Foundation

/// Closed, privacy-safe telemetry contract for proactive integration nudges.
///
/// The funnel this measures is: a nudge was delivered → the user acted on it.
///
/// There is deliberately no "suppressed" event. Every reason a recognized window
/// does not produce a card is a deterministic function of the budgets in
/// ``IntegrationNudgePolicy`` and the Shown events already recorded, and the
/// states that dominate — already connected, opted out, cooling down — hold for
/// days while apps like Finder are activated dozens of times an hour. An event
/// for them is unbounded volume that tells the analysis nothing it cannot
/// derive. It deliberately does **not** re-measure
/// the connect itself; once the user taps Connect, the existing
/// ``IntegrationConnectTelemetry`` funnel takes over from
/// `ConnectorImportRunner`, tagged with the ``IntegrationConnectTelemetry/Surface/nudge``
/// surface so nudge-sourced connects are attributable without a parallel schema.
///
/// `connector_id` is the *bare* connector id (`email`, `notion`) so these events
/// join to `IntegrationConnectTelemetry` on the same property with the same
/// shape; `route` (`import` / `export`) is what disambiguates ChatGPT and Claude,
/// which exist on both sides of the catalog.
///
/// Payloads carry bounded dimensions only. The triggering app is reported as its
/// **catalog trigger id** — a value from a closed set this repo defines — never
/// the raw `NSRunningApplication.localizedName`, bundle identifier, window
/// title, or URL. Window titles in particular are content: "Re: layoffs — Gmail"
/// must never leave the machine, so title matching happens locally and only the
/// matched trigger id is emitted.
enum IntegrationNudgeTelemetry {
  /// PostHog event names. Stable identifiers — do not rename.
  static let shownEventName = "Integration Nudge Shown"
  static let actionedEventName = "Integration Nudge Actioned"

  /// What the user did with a delivered nudge. Closed set.
  enum Action: String, CaseIterable {
    /// Tapped the card / "Connect" — routed to the connector sheet.
    case connect
    /// Chose "Not now" — snoozed this integration.
    case notNow = "not_now"
    /// Chose "Don't show again" — opted this integration out permanently.
    case dismissForever = "dismiss_forever"
  }

  /// How the trigger was recognized. Distinguishes a native app activation from
  /// a browser window whose title matched a site, because their false-positive
  /// rates are different and should be separable in analysis.
  enum TriggerKind: String, CaseIterable {
    case nativeApp = "native_app"
    case browserSite = "browser_site"
  }

  /// Keys permitted in any emitted payload. Anything else is dropped by the
  /// allow-list filter, mirroring ``IntegrationConnectTelemetry``.
  static let allowedKeys: Set<String> = [
    "integration_name",
    "connector_id",
    "route",
    "trigger_id",
    "trigger_kind",
    "action",
    "shown_count",
  ]

  static func shownPayload(
    integrationName: String,
    route: IntegrationNudgeRoute,
    triggerID: String,
    triggerKind: TriggerKind,
    shownCount: Int
  ) -> [String: Any] {
    allowListOnly([
      "integration_name": integrationName,
      "connector_id": route.identifier,
      "route": route.telemetryPrefix,
      "trigger_id": triggerID,
      "trigger_kind": triggerKind.rawValue,
      "shown_count": shownCount,
    ])
  }

  static func actionedPayload(
    integrationName: String,
    route: IntegrationNudgeRoute,
    action: Action,
    triggerID: String
  ) -> [String: Any] {
    allowListOnly([
      "integration_name": integrationName,
      "connector_id": route.identifier,
      "route": route.telemetryPrefix,
      "action": action.rawValue,
      "trigger_id": triggerID,
    ])
  }

  private static func allowListOnly(_ properties: [String: Any]) -> [String: Any] {
    properties.filter { allowedKeys.contains($0.key) }
  }
}
