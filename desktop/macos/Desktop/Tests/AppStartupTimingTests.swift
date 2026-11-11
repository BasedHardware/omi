import XCTest

@testable import Omi_Computer

/// `App Startup Timing` reported `time_to_interactive_ms` of 11–131ms, which is
/// not a cold start of this app. It was the duration of
/// `ViewModelContainer.loadAllData()`, which begins long after `main()`. These
/// tests pin the replacement measurement.
final class AppStartupTimingTests: XCTestCase {
  func testProcessStartIsReadFromTheKernelAndPrecedesNow() throws {
    let start = try XCTUnwrap(
      AppStartupTiming.processStartDate(),
      "the kernel process table is the only source for a real process start")
    XCTAssertLessThanOrEqual(start, Date(), "a process cannot start in the future")

    let elapsed = try XCTUnwrap(AppStartupTiming.millisecondsSinceProcessStart())
    XCTAssertGreaterThan(
      elapsed, 0,
      "time from process start to now must be positive; a zero here means the stamp was not read")
  }

  /// The old measurement started inside `loadAllData()`. The new one starts at
  /// exec, so it must include everything before the data load — otherwise the
  /// rename bought nothing.
  func testProcessStartPrecedesAnyTimestampTakenByOurOwnCode() throws {
    let start = try XCTUnwrap(AppStartupTiming.processStartDate())
    let takenNow = Date()
    XCTAssertLessThan(
      start, takenNow,
      "any Date() our code can take is necessarily after the kernel's exec stamp")
    XCTAssertGreaterThan(
      AppStartupTiming.elapsedMilliseconds(from: start, to: takenNow),
      0)
  }

  func testElapsedMillisecondsConvertsAndNeverGoesNegative() {
    let base = Date(timeIntervalSince1970: 1_000)
    XCTAssertEqual(
      AppStartupTiming.elapsedMilliseconds(from: base, to: base.addingTimeInterval(1.5)),
      1_500,
      accuracy: 0.001)

    // Both instants come from the wall clock, so an adjustment between them can
    // invert them. A startup metric must never report a negative duration.
    XCTAssertEqual(
      AppStartupTiming.elapsedMilliseconds(from: base, to: base.addingTimeInterval(-30)),
      0,
      accuracy: 0.001)
  }

  /// When the kernel lookup fails the property is omitted rather than replaced
  /// with a plausible-looking number, which is how the implausible 11–131ms
  /// values became indistinguishable from real ones.
  func testMissingProcessStartYieldsNoMeasurementRatherThanAFabricatedOne() {
    XCTAssertNil(
      AppStartupTiming.millisecondsSinceProcessStart(now: Date(), processStart: nil))
  }
}
