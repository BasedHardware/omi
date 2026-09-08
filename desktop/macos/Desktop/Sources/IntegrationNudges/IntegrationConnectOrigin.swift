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
    /// The catalog telemetry id (`import:chatgpt`, `export:chatgpt`), never the
    /// bare connector id. ChatGPT and Claude exist on both sides of the
    /// catalog, so a bare id lets an accepted *export* nudge take credit for an
    /// unrelated *import* connect of the same-named tool.
    let telemetryID: String
    let claimedAt: Date
  }

  private static var claim: Claim?

  /// Opens a window for `route`, if that route's connect is measured by the
  /// connect funnel at all.
  ///
  /// Only import connectors are: they run through `ConnectorImportRunner`,
  /// which is the single place `IntegrationConnectTelemetry` is emitted. Export
  /// destinations emit no connect funnel, so recording a window for one would
  /// store state nothing can ever consume. Export conversion is measured by
  /// `Integration Nudge Actioned` with `action: connect` instead, which covers
  /// both halves of the catalog.
  @discardableResult
  static func recordNudgeOpened(for route: IntegrationNudgeRoute, now: Date = Date()) -> Bool {
    guard case .importConnector = route else { return false }
    claim = Claim(telemetryID: route.telemetryID, claimedAt: now)
    return true
  }

  /// Returns the surface to attribute a connect to, consuming any matching
  /// nudge window. `route` disambiguates the two halves of the catalog.
  static func consumeSurface(
    for route: IntegrationNudgeRoute,
    now: Date = Date()
  ) -> IntegrationConnectTelemetry.Surface {
    guard let claim,
      claim.telemetryID == route.telemetryID,
      now.timeIntervalSince(claim.claimedAt) < claimLifetime
    else { return .apps }
    self.claim = nil
    return .nudge
  }

  static func reset() {
    claim = nil
  }
}
