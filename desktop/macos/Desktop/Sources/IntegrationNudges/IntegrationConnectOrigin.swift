import Foundation

/// Remembers that the connector sheet currently on screen was opened by a
/// proactive nudge, so the connect that follows is attributed to
/// ``IntegrationConnectTelemetry/Surface/nudge`` rather than to the Apps tab.
///
/// Without this the nudge is unmeasurable: it opens the same sheet the Apps tab
/// does, so every nudge-sourced connect would be indistinguishable from a user
/// who browsed to the tab — which is exactly the comparison the feature exists
/// to make.
///
/// The claim is single-use and time-boxed. A user who opens the sheet from a
/// nudge, closes it, and comes back through the Apps tab an hour later is an
/// Apps-tab connect, and reporting it as a nudge conversion would flatter the
/// feature.
@MainActor
enum IntegrationConnectOrigin {
  /// How long a nudge's claim on the next connect survives.
  static let claimLifetime: TimeInterval = 5 * 60

  private struct Claim {
    let connectorID: String
    let claimedAt: Date
  }

  private static var claim: Claim?

  static func recordNudgeOpened(connectorID: String, now: Date = Date()) {
    claim = Claim(connectorID: connectorID, claimedAt: now)
  }

  /// Returns the surface to attribute a connect of `connectorID` to, consuming
  /// any matching nudge claim.
  static func consumeSurface(
    forConnectorID connectorID: String,
    now: Date = Date()
  ) -> IntegrationConnectTelemetry.Surface {
    guard let claim,
      claim.connectorID == connectorID,
      now.timeIntervalSince(claim.claimedAt) < claimLifetime
    else { return .apps }
    self.claim = nil
    return .nudge
  }

  static func reset() {
    claim = nil
  }
}
