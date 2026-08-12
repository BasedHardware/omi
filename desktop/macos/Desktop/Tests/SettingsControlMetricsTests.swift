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

  func testNotificationPeriodLabelUsesClamped24HourTime() {
    XCTAssertEqual(SettingsControlMetrics.notificationPeriodLabel(forMinute: 0), "00:00")
    XCTAssertEqual(SettingsControlMetrics.notificationPeriodLabel(forMinute: 20 * 60 + 45), "20:45")
    XCTAssertEqual(SettingsControlMetrics.notificationPeriodLabel(forMinute: 1_500), "23:59")
  }
}
