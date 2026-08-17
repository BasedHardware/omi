import Foundation

/// A short attribution window: connecting integration X within
/// ``claimLifetime`` of accepting a nudge for X counts as
/// ``IntegrationConnectTelemetry/Surface/nudge`` rather than an Apps-tab
/// connect.
///
/// Without this the nudge is unmeasurable: it opens the same sheet the Apps tab
/// does, so every nudge-sourced connect would be indistinguishable from a user
/// who browsed to the tab — which is exactly the comparison the feature exists
/// to make.
///
/// It is a *window*, not a claim on one specific sheet, and the distinction is
/// deliberate. A user who accepts the Gmail nudge, wanders off, and finishes the
/// Gmail connect from the Apps tab two minutes later was still moved by the
/// nudge; requiring an unbroken sheet session would undercount it. Detouring
/// through an unrelated connector in between does not change that, so an
/// unrelated connect leaves the window intact.
///
/// Two properties keep the window from flattering the feature: it only ever
/// credits the exact integration that was nudged, and it is single-use and
/// time-boxed, so a connect an hour later is an Apps-tab connect.
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
