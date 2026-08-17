import XCTest

@testable import Omi_Computer

@MainActor
final class IntegrationConnectOriginTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_700_000_000)

  override func tearDown() {
    MainActor.assumeIsolated { IntegrationConnectOrigin.reset() }
    super.tearDown()
  }

  func testUnclaimedConnectsAreAppsTabConnects() {
    IntegrationConnectOrigin.reset()
    XCTAssertEqual(IntegrationConnectOrigin.consumeSurface(forConnectorID: "email", now: now), .apps)
  }

  func testANudgeClaimsTheConnectThatFollows() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(connectorID: "email", now: now)
    XCTAssertEqual(IntegrationConnectOrigin.consumeSurface(forConnectorID: "email", now: now), .nudge)
  }

  /// Single-use: a second connect of the same integration is the user acting on
  /// their own, not the nudge converting twice.
  func testTheClaimIsConsumedOnce() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(connectorID: "email", now: now)
    _ = IntegrationConnectOrigin.consumeSurface(forConnectorID: "email", now: now)
    XCTAssertEqual(IntegrationConnectOrigin.consumeSurface(forConnectorID: "email", now: now), .apps)
  }

  /// A Gmail nudge must not take credit for the user connecting Notion.
  func testAClaimOnlyCoversItsOwnIntegration() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(connectorID: "email", now: now)
    XCTAssertEqual(
      IntegrationConnectOrigin.consumeSurface(forConnectorID: "calendar", now: now),
      .apps
    )
  }

  /// Coming back through the Apps tab an hour later is an Apps-tab connect.
  func testTheClaimExpires() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(connectorID: "email", now: now)
    let later = now.addingTimeInterval(IntegrationConnectOrigin.claimLifetime)
    XCTAssertEqual(IntegrationConnectOrigin.consumeSurface(forConnectorID: "email", now: later), .apps)
  }

  func testTheClaimHoldsRightUpToItsDeadline() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(connectorID: "email", now: now)
    let justInside = now.addingTimeInterval(IntegrationConnectOrigin.claimLifetime - 1)
    XCTAssertEqual(
      IntegrationConnectOrigin.consumeSurface(forConnectorID: "email", now: justInside),
      .nudge
    )
  }
}
