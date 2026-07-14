import XCTest

@testable import Omi_Computer

final class ProofFirstDashboardPolicyTests: XCTestCase {
  func testPrimaryPagesStayFlatOrderedAndAutomationAddressable() {
    XCTAssertEqual(ProofFirstDashboardPage.allCases.map(\.title), ["Home", "Connect data", "Features"])
    XCTAssertEqual(
      ProofFirstDashboardPage.allCases.map(\.automationLabel),
      ["home", "connectData", "features"]
    )
    XCTAssertEqual(ProofFirstDashboardPage(automationLabel: "connectData"), .connectData)
    XCTAssertNil(ProofFirstDashboardPage(automationLabel: "settings"))
  }

  func testLoadingGuardWinsBeforeAnyFallbackTier() {
    XCTAssertEqual(
      DashboardHeroCascadePolicy.resolve(
        hasSettled: false,
        hasRecommendation: false,
        mostRecentConversationAt: nil,
        mostRecentTaskAt: nil
      ),
      .loading
    )
  }

  func testRecommendationWinsEvenWhenRecentActivityExists() {
    XCTAssertEqual(
      DashboardHeroCascadePolicy.resolve(
        hasSettled: true,
        hasRecommendation: true,
        mostRecentConversationAt: Date(timeIntervalSince1970: 100),
        mostRecentTaskAt: Date(timeIntervalSince1970: 200)
      ),
      .recommendation
    )
  }

  func testLaterRecentActivityWinsWithoutARecommendation() {
    XCTAssertEqual(
      DashboardHeroCascadePolicy.resolve(
        hasSettled: true,
        hasRecommendation: false,
        mostRecentConversationAt: Date(timeIntervalSince1970: 300),
        mostRecentTaskAt: Date(timeIntervalSince1970: 200)
      ),
      .recentConversation
    )
    XCTAssertEqual(
      DashboardHeroCascadePolicy.resolve(
        hasSettled: true,
        hasRecommendation: false,
        mostRecentConversationAt: Date(timeIntervalSince1970: 100),
        mostRecentTaskAt: Date(timeIntervalSince1970: 200)
      ),
      .recentTask
    )
  }

  func testEmptySettledDataFallsThroughToDayZero() {
    XCTAssertEqual(
      DashboardHeroCascadePolicy.resolve(
        hasSettled: true,
        hasRecommendation: false,
        mostRecentConversationAt: nil,
        mostRecentTaskAt: nil
      ),
      .dayZero
    )
  }

  func testDayZeroSourceCountControlsSetupStaticAndRotation() {
    XCTAssertEqual(DashboardDayZeroSourcePolicy.presentation(sourceCount: 0), .setup)
    XCTAssertEqual(DashboardDayZeroSourcePolicy.presentation(sourceCount: 1), .staticCard)
    XCTAssertEqual(DashboardDayZeroSourcePolicy.presentation(sourceCount: 2), .rotating)
    XCTAssertEqual(
      DashboardDayZeroSourcePolicy.automationLabel(for: .rotating),
      "rotating"
    )
  }

  func testPostOnboardingPromptIsStrictlyLegacyOnly() {
    XCTAssertTrue(
      DashboardPostOnboardingPromptPolicy.shouldPresent(
        useLegacyHomeDesign: true,
        postOnboardingShouldShowPopup: true,
        hasSuggestions: true
      )
    )
    XCTAssertFalse(
      DashboardPostOnboardingPromptPolicy.shouldPresent(
        useLegacyHomeDesign: false,
        postOnboardingShouldShowPopup: true,
        hasSuggestions: true
      )
    )
    XCTAssertFalse(
      DashboardPostOnboardingPromptPolicy.shouldPresent(
        useLegacyHomeDesign: true,
        postOnboardingShouldShowPopup: false,
        hasSuggestions: true
      )
    )
  }
}

@MainActor
final class DashboardDayZeroSourceStoreTests: XCTestCase {
  func testPermissionOrMetadataFailureDoesNotFabricateAScreenCard() {
    XCTAssertNil(DashboardDayZeroSourceStore.screenCard(from: [
      "failure_code": "permission_denied",
      "screen_now": ["available": false],
    ]))
    XCTAssertNil(DashboardDayZeroSourceStore.screenCard(from: [
      "screen_now": ["available": true],
    ]))
  }

  func testScreenCardUsesOnlyGroundedAppAndWindowValues() throws {
    let card = try XCTUnwrap(DashboardDayZeroSourceStore.screenCard(from: [
      "screen_now": [
        "available": true,
        "app_name": "Linear",
        "window_title": "Bug: Auth token refresh loop",
      ],
    ]))

    XCTAssertEqual(card.kind, .screen)
    XCTAssertTrue(card.text.contains("Linear"))
    XCTAssertTrue(card.text.contains("Bug: Auth token refresh loop"))
  }

  func testCalendarCardSelectsTheNearestRealUpcomingEvent() throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let formatter = ISO8601DateFormatter()
    let later = CalendarEvent(
      id: "later",
      summary: "Product review",
      startTime: formatter.string(from: now.addingTimeInterval(7_200)),
      endTime: "",
      attendees: [],
      location: "",
      description: "",
      isAllDay: false
    )
    let sooner = CalendarEvent(
      id: "sooner",
      summary: "Design sync",
      startTime: formatter.string(from: now.addingTimeInterval(3_600)),
      endTime: "",
      attendees: [],
      location: "",
      description: "",
      isAllDay: false
    )

    let card = try XCTUnwrap(
      DashboardDayZeroSourceStore.calendarCard(from: [later, sooner], now: now)
    )
    XCTAssertEqual(card.id, "calendar:sooner")
    XCTAssertTrue(card.text.contains("Design sync"))
  }

  func testFailedSourceLoadersSettleToHonestEmptySetupState() async {
    let store = DashboardDayZeroSourceStore(
      screenLoader: { nil },
      calendarLoader: { _ in nil },
      emailLoader: { nil }
    )

    await store.load(connectedConnectorIDs: ["calendar", "email"])

    XCTAssertTrue(store.hasSettled)
    XCTAssertTrue(store.cards.isEmpty)
    XCTAssertEqual(
      DashboardDayZeroSourcePolicy.presentation(sourceCount: store.cards.count),
      .setup
    )
  }
}
