import XCTest

@testable import Omi_Computer

@MainActor
final class SettingsControlMetricsTests: XCTestCase {
  func testNotificationFrequencyInitialValueComesFromPersistedMirror() throws {
    let suiteName = "SettingsControlMetricsTests.notification-frequency.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    defaults.set(5, forKey: NotificationService.frequencyDefaultsKey)
    XCTAssertEqual(NotificationService.currentFrequencyLevel(defaults: defaults), 5)
  }

  @MainActor
  func testNotificationMasterInitialValueComesFromPersistedMirror() throws {
    let suiteName = "SettingsControlMetricsTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    XCTAssertTrue(NotificationService.areNotificationsEnabled(defaults: defaults))
    defaults.set(false, forKey: NotificationService.masterEnabledDefaultsKey)
    XCTAssertFalse(NotificationService.areNotificationsEnabled(defaults: defaults))
  }

  func testSteppedSliderEndpointsKeepThumbInsideContainer() {
    let containerWidth: CGFloat = 200
    let thumbRadius = SettingsControlMetrics.steppedSliderThumbDiameter / 2

    let firstPosition = SettingsControlMetrics.steppedSliderPosition(
      index: 0, stepCount: 6, containerWidth: containerWidth)
    let lastPosition = SettingsControlMetrics.steppedSliderPosition(
      index: 5, stepCount: 6, containerWidth: containerWidth)

    XCTAssertEqual(firstPosition - thumbRadius, 0)
    XCTAssertEqual(lastPosition + thumbRadius, containerWidth)
  }

  func testSteppedSliderMapsInsetTrackToFirstAndLastSteps() {
    let containerWidth: CGFloat = 200
    let firstPosition = SettingsControlMetrics.steppedSliderPosition(
      index: 0, stepCount: 6, containerWidth: containerWidth)
    let lastPosition = SettingsControlMetrics.steppedSliderPosition(
      index: 5, stepCount: 6, containerWidth: containerWidth)

    XCTAssertEqual(
      SettingsControlMetrics.steppedSliderIndex(
        locationX: firstPosition, stepCount: 6, containerWidth: containerWidth), 0)
    XCTAssertEqual(
      SettingsControlMetrics.steppedSliderIndex(
        locationX: lastPosition, stepCount: 6, containerWidth: containerWidth), 5)
  }

  func testDailySummaryDateAlwaysUsesWholeHour() {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0)!
    let referenceDate = Date(timeIntervalSince1970: 1_784_020_500)

    let summaryDate = SettingsControlMetrics.dailySummaryDate(
      forHour: 20, referenceDate: referenceDate, calendar: calendar)

    XCTAssertEqual(calendar.component(.hour, from: summaryDate), 20)
    XCTAssertEqual(calendar.component(.minute, from: summaryDate), 0)
    XCTAssertEqual(SettingsControlMetrics.dailySummaryHour(from: summaryDate, calendar: calendar), 20)
  }

  func testDailySummaryCanonicalizesMinutesSoPickerCannotRoundTripQuarterHours() throws {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(secondsFromGMT: 0))
    let referenceDate = Date(timeIntervalSince1970: 1_784_020_500)
    let withMinutes = try XCTUnwrap(
      calendar.date(bySettingHour: 20, minute: 45, second: 30, of: referenceDate))

    let canonical = SettingsControlMetrics.canonicalizeDailySummaryTime(
      withMinutes, calendar: calendar)

    XCTAssertEqual(calendar.component(.hour, from: canonical), 20)
    XCTAssertEqual(calendar.component(.minute, from: canonical), 0)
    XCTAssertEqual(calendar.component(.second, from: canonical), 0)
    XCTAssertEqual(SettingsControlMetrics.dailySummaryHour(from: withMinutes, calendar: calendar), 20)
    XCTAssertEqual(
      SettingsControlMetrics.dailySummaryHour(from: canonical, calendar: calendar),
      SettingsControlMetrics.dailySummaryHour(from: withMinutes, calendar: calendar))
  }

  func testGeneralNotificationStatusNeverClaimsProactiveAlertsEnabled() {
    XCTAssertEqual(
      SettingsControlMetrics.generalNotificationPermissionStatusText(
        hasPermission: true, bannersDisabled: false),
      "macOS banners enabled")
    XCTAssertEqual(
      SettingsControlMetrics.generalNotificationPermissionStatusText(
        hasPermission: true, bannersDisabled: true),
      "Permission granted, but macOS banners are off")
    XCTAssertEqual(
      SettingsControlMetrics.generalNotificationPermissionStatusText(
        hasPermission: false, bannersDisabled: false),
      "macOS notification permission is off")

    let enabledCopy = SettingsControlMetrics.generalNotificationPermissionStatusText(
      hasPermission: true, bannersDisabled: false)
    XCTAssertFalse(
      enabledCopy.lowercased().contains("proactive"),
      "General Notifications must not claim product proactive delivery is on")
  }
}
