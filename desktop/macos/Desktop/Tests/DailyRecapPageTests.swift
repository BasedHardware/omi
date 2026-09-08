import Foundation
import XCTest

@testable import Omi_Computer

/// The recap route's identity contract and the dedicated page's date rules.
final class DailyRecapPageTests: XCTestCase {
  // MARK: - Route

  /// The route persists across launches, so the ref must survive the exact
  /// Codable round trip the navigation owner performs, and the route must stay
  /// out of the primary destinations a sidebar chip or an automation name can
  /// reach: only a recap row opens it.
  func testRecapRouteCarriesIdentityAndIsNotPrimary() throws {
    let ref = DailyRecapRouteRef(recordID: "ds_1", date: "2026-09-03")
    let route = ChatFirstRoute.dailyRecap(ref)

    let data = try JSONEncoder().encode(route)
    let decoded = try JSONDecoder().decode(ChatFirstRoute.self, from: data)
    XCTAssertEqual(decoded, route)
    guard case .dailyRecap(let decodedRef) = decoded else {
      return XCTFail("expected .dailyRecap, got \(decoded)")
    }
    XCTAssertEqual(decodedRef.recordID, "ds_1")
    XCTAssertEqual(decodedRef.date, "2026-09-03")

    XCTAssertFalse(route.isPrimaryDestination)
    XCTAssertEqual(route.stableName, "daily-recap")
    XCTAssertEqual(route.title, "Daily recap")
    XCTAssertEqual(
      ChatFirstModernNavigationPolicy.topBarIndex(for: route),
      SidebarNavItem.dashboard.rawValue,
      "the recap opened from a surface keeps that surface's top-bar selection")
    XCTAssertTrue(
      ChatFirstPageGlassLanePolicy.shouldWrap(route),
      "the page sits on the glass lane like the other full pages")
    XCTAssertNil(
      ChatFirstRoute.primaryAutomationDestination(named: "daily-recap"),
      "no automation name may navigate to the recap page")
  }

  /// The opening pill captures `navigation.route` as the origin, and the page's
  /// back chevron returns there — not always to Chat. An explicit tab select
  /// supersedes the origin, and a relaunch must not restore it.
  @MainActor
  func testOpenDailyRecapCapturesOriginAndCloseReturnsThere() throws {
    let suiteName = "DailyRecapPageTests.origin.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(
      defaults: defaults, analytics: { _ in })
    let ref = DailyRecapRouteRef(recordID: "ds_1", date: "2026-09-03")

    navigation.openDailyRecap(ref)
    guard case .dailyRecap = navigation.route else {
      return XCTFail("expected the recap route, got \(navigation.route)")
    }
    XCTAssertEqual(navigation.dailyRecapOrigin, .chat)
    navigation.closeDailyRecap()
    XCTAssertEqual(navigation.route, .chat)
    XCTAssertNil(navigation.dailyRecapOrigin)

    navigation.selectPrimary(.goals)
    navigation.openDailyRecap(ref)
    XCTAssertEqual(navigation.dailyRecapOrigin, .goals)
    navigation.closeDailyRecap()
    XCTAssertEqual(navigation.route, .goals)

    // Esc on the page is the back chevron.
    navigation.selectPrimary(.memories)
    navigation.openDailyRecap(ref)
    XCTAssertTrue(navigation.handleEscapeNavigation())
    XCTAssertEqual(navigation.route, .memories)

    // The origin is transient, like a focus: a fresh owner must not inherit it.
    navigation.selectPrimary(.goals)
    navigation.openDailyRecap(ref)
    let relaunched = ChatFirstShellNavigation(
      defaults: defaults, analytics: { _ in })
    guard case .dailyRecap = relaunched.route else {
      return XCTFail("the route itself persists, got \(relaunched.route)")
    }
    XCTAssertNil(relaunched.dailyRecapOrigin)
  }

  // MARK: - Page date

  /// The page's eyebrow names the day in full ("Wednesday, September 3") where
  /// the pill's eyebrow abbreviates ("Wed, Sep 3") — the page is the full
  /// record, so its date reads like prose.
  func testPageDateLabelNamesOlderDaysInFull() throws {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "UTC"))
    let now = try XCTUnwrap(
      calendar.date(from: DateComponents(year: 2_026, month: 9, day: 4)))
    let locale = Locale(identifier: "en_US")

    XCTAssertEqual(
      ChatDailySummaryPresentation.pageDateLabel(
        for: "2026-09-04", now: now, calendar: calendar, locale: locale),
      "Today")
    XCTAssertEqual(
      ChatDailySummaryPresentation.pageDateLabel(
        for: "2026-09-03", now: now, calendar: calendar, locale: locale),
      "Yesterday")
    XCTAssertEqual(
      ChatDailySummaryPresentation.pageDateLabel(
        for: "2026-09-02", now: now, calendar: calendar, locale: locale),
      "Wednesday, September 2")
    XCTAssertEqual(
      ChatDailySummaryPresentation.dateLabel(
        for: "2026-09-02", now: now, calendar: calendar, locale: locale),
      "Wed, Sep 2",
      "the pill keeps its compact format; only the page widened")
    XCTAssertNil(
      ChatDailySummaryPresentation.pageDateLabel(
        for: "not-a-date", now: now, calendar: calendar))
  }
}
