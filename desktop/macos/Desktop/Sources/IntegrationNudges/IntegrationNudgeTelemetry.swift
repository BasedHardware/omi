import Foundation

/// Closed, privacy-safe telemetry contract for proactive integration nudges.
///
/// The funnel this measures is: an uncovered integration was detected → a nudge
/// was delivered → the user acted on it. It deliberately does **not** re-measure
/// the connect itself; once the user taps Connect, the existing
/// ``IntegrationConnectTelemetry`` funnel takes over from
/// `ConnectorImportRunner`, tagged with the ``IntegrationConnectTelemetry/Surface/nudge``
/// surface so nudge-sourced connects are attributable without a parallel schema.
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
  static let suppressedEventName = "Integration Nudge Suppressed"
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
    "trigger_id",
    "trigger_kind",
    "suppression_reason",
    "action",
    "shown_count",
  ]

  static func shownPayload(
    integrationName: String,
    connectorID: String,
    triggerID: String,
    triggerKind: TriggerKind,
    shownCount: Int
  ) -> [String: Any] {
    allowListOnly([
      "integration_name": integrationName,
      "connector_id": connectorID,
      "trigger_id": triggerID,
      "trigger_kind": triggerKind.rawValue,
      "shown_count": shownCount,
    ])
  }

  /// Emitted when a recognized trigger did *not* produce a nudge. This is the
  /// denominator: without it, a feature that silently suppresses everything
  /// looks identical to one nobody triggers.
  static func suppressedPayload(
    integrationName: String,
    connectorID: String,
    triggerID: String,
    triggerKind: TriggerKind,
    reason: IntegrationNudgePolicy.Suppression
  ) -> [String: Any] {
    allowListOnly([
      "integration_name": integrationName,
      "connector_id": connectorID,
      "trigger_id": triggerID,
      "trigger_kind": triggerKind.rawValue,
      "suppression_reason": reason.rawValue,
    ])
  }

  /// `triggerID` is what makes conversion measurable per trigger. Without it a
  /// Notion nudge from the desktop app and one from a browser tab are the same
  /// row, and the experiment cannot tell which recognition path is worth
  /// keeping.
  static func actionedPayload(
    integrationName: String,
    connectorID: String,
    action: Action,
    triggerID: String
  ) -> [String: Any] {
    allowListOnly([
      "integration_name": integrationName,
      "connector_id": connectorID,
      "action": action.rawValue,
      "trigger_id": triggerID,
    ])
  }

  private static func allowListOnly(_ properties: [String: Any]) -> [String: Any] {
    properties.filter { allowedKeys.contains($0.key) }
  }
}
