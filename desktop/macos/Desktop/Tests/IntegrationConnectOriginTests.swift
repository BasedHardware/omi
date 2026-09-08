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
    XCTAssertEqual(IntegrationConnectOrigin.consumeSurface(for: .importConnector("email"), now: now), .apps)
  }

  func testANudgeClaimsTheConnectThatFollows() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(for: .importConnector("email"), now: now)
    XCTAssertEqual(IntegrationConnectOrigin.consumeSurface(for: .importConnector("email"), now: now), .nudge)
  }

  /// Single-use: a second connect of the same integration is the user acting on
  /// their own, not the nudge converting twice.
  func testTheClaimIsConsumedOnce() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(for: .importConnector("email"), now: now)
    _ = IntegrationConnectOrigin.consumeSurface(for: .importConnector("email"), now: now)
    XCTAssertEqual(IntegrationConnectOrigin.consumeSurface(for: .importConnector("email"), now: now), .apps)
  }

  /// A Gmail nudge must not take credit for the user connecting Notion.
  func testAClaimOnlyCoversItsOwnIntegration() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(for: .importConnector("email"), now: now)
    XCTAssertEqual(
      IntegrationConnectOrigin.consumeSurface(for: .importConnector("calendar"), now: now),
      .apps
    )
  }

  /// Detouring through an unrelated connector does not close the window. The
  /// user who accepted a Gmail nudge and then connected Calendar first was still
  /// moved by the Gmail nudge when they come back to Gmail a minute later —
  /// and the window can only ever credit the exact integration it names, so
  /// Calendar itself is never miscredited.
  func testAnUnrelatedConnectDoesNotCloseTheWindow() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(for: .importConnector("email"), now: now)

    XCTAssertEqual(
      IntegrationConnectOrigin.consumeSurface(for: .importConnector("calendar"), now: now),
      .apps
    )
    XCTAssertEqual(
      IntegrationConnectOrigin.consumeSurface(
        for: .importConnector("email"),
        now: now.addingTimeInterval(60)
      ),
      .nudge
    )
  }

  /// Accepting a newer nudge replaces the window rather than stacking, so the
  /// older integration cannot be credited by a later unrelated connect.
  func testANewerNudgeReplacesTheWindow() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(for: .importConnector("email"), now: now)
    IntegrationConnectOrigin.recordNudgeOpened(for: .importConnector("calendar"), now: now)

    XCTAssertEqual(IntegrationConnectOrigin.consumeSurface(for: .importConnector("email"), now: now), .apps)
  }

  /// Coming back through the Apps tab an hour later is an Apps-tab connect.
  func testTheClaimExpires() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(for: .importConnector("email"), now: now)
    let later = now.addingTimeInterval(IntegrationConnectOrigin.claimLifetime)
    XCTAssertEqual(IntegrationConnectOrigin.consumeSurface(for: .importConnector("email"), now: later), .apps)
  }

  /// Export destinations emit no connect funnel, so opening a window for one
  /// would store state nothing can consume — and, with a bare id, an accepted
  /// ChatGPT *export* nudge would have credited a ChatGPT *import* connect.
  func testAnExportNudgeOpensNoWindowAndCannotCreditTheSameNamedImport() {
    IntegrationConnectOrigin.reset()

    XCTAssertFalse(
      IntegrationConnectOrigin.recordNudgeOpened(for: .exportDestination("chatgpt"), now: now))
    XCTAssertEqual(
      IntegrationConnectOrigin.consumeSurface(for: .importConnector("chatgpt"), now: now),
      .apps
    )
  }

  func testAnImportNudgeOpensAWindow() {
    IntegrationConnectOrigin.reset()
    XCTAssertTrue(
      IntegrationConnectOrigin.recordNudgeOpened(for: .importConnector("email"), now: now))
  }

  func testTheClaimHoldsRightUpToItsDeadline() {
    IntegrationConnectOrigin.reset()
    IntegrationConnectOrigin.recordNudgeOpened(for: .importConnector("email"), now: now)
    let justInside = now.addingTimeInterval(IntegrationConnectOrigin.claimLifetime - 1)
    XCTAssertEqual(
      IntegrationConnectOrigin.consumeSurface(for: .importConnector("email"), now: justInside),
      .nudge
    )
  }
}
