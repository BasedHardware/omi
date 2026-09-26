import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class DesktopUsageDailyReporterTests: XCTestCase {
  func testUsageReporterAccumulatesAndRollsOverWithoutDroppingPriorDay() throws {
    let suite = "DesktopUsageDailyReporterTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    let dayOne = Date(timeIntervalSince1970: 1_788_230_400)
    let dayTwo = try XCTUnwrap(calendar.date(byAdding: .day, value: 1, to: dayOne))
    let reporter = DesktopUsageDailyReporter(
      defaults: defaults,
      now: { dayOne },
      calendar: calendar,
      timezone: { calendar.timeZone },
      deviceID: { "device-1" })

    reporter.sampleForTesting(watching: true, listening: false, at: dayOne)
    reporter.recordProactiveCardShown()
    reporter.recordProactiveCardActed()
    reporter.recordCompletedPTTTurn(repliedToCard: true)
    reporter.sampleForTesting(watching: true, listening: true, at: dayTwo)

    let snapshot = reporter.snapshotForTesting()
    let keys = snapshot.records.keys.sorted()
    XCTAssertEqual(keys.count, 2)
    XCTAssertEqual(snapshot.records[keys[0]]?.watchingSeconds, 60)
    XCTAssertEqual(snapshot.records[keys[1]]?.watchingSeconds, 60)
    XCTAssertEqual(snapshot.records[keys[1]]?.listeningSeconds, 60)
    XCTAssertEqual(snapshot.records[keys[0]]?.proactiveCardsShown, 1)
    XCTAssertEqual(snapshot.records[keys[0]]?.proactiveCardsActed, 2)
    XCTAssertEqual(snapshot.records[keys[0]]?.pttTurns, 1)
  }

  func testUsagePersistenceIsNamespacedByOwner() throws {
    let suite = "DesktopUsageDailyReporterTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    let ownerA = DesktopUsageDailyReporter(defaults: defaults, ownerID: { "owner-a" })
    ownerA.recordProactiveCardShown()
    let ownerB = DesktopUsageDailyReporter(defaults: defaults, ownerID: { "owner-b" })

    XCTAssertEqual(ownerA.snapshotForTesting().dirtyDates.count, 1)
    XCTAssertTrue(ownerB.snapshotForTesting().dirtyDates.isEmpty)
  }

  func testFailedUploadKeepsDirtyCountersAndSchedulesRetry() async throws {
    let harness = try makeUploadHarness(shouldFail: true)
    defer { harness.defaults.removePersistentDomain(forName: harness.suite) }

    harness.reporter.sampleForTesting(watching: true, listening: false, at: harness.clock.now)
    await harness.reporter.uploadDirtyRecordsForTesting()

    let snapshot = harness.reporter.snapshotForTesting()
    let dateKey = try XCTUnwrap(snapshot.dirtyDates.first)
    XCTAssertEqual(harness.probe.calls.count, 1)
    XCTAssertEqual(snapshot.records[dateKey]?.watchingSeconds, 60)
    XCTAssertEqual(harness.reporter.retryAttemptsForTesting(dateKey), 1)
    XCTAssertEqual(
      harness.reporter.retryAfterForTesting(dateKey),
      harness.clock.now.addingTimeInterval(30))
  }

  func testRepeatedUploadFailuresBackOffInsteadOfRetryingImmediately() async throws {
    let harness = try makeUploadHarness(shouldFail: true)
    defer { harness.defaults.removePersistentDomain(forName: harness.suite) }

    harness.reporter.sampleForTesting(watching: true, listening: false, at: harness.clock.now)
    await harness.reporter.uploadDirtyRecordsForTesting()
    await harness.reporter.uploadDirtyRecordsForTesting()
    XCTAssertEqual(harness.probe.calls.count, 1)

    let dateKey = try XCTUnwrap(harness.reporter.snapshotForTesting().dirtyDates.first)
    let firstRetryAfter = try XCTUnwrap(harness.reporter.retryAfterForTesting(dateKey))
    harness.clock.now = firstRetryAfter
    await harness.reporter.uploadDirtyRecordsForTesting()
    XCTAssertEqual(harness.probe.calls.count, 2)
    XCTAssertEqual(harness.reporter.retryAttemptsForTesting(dateKey), 2)

    let secondRetryAfter = try XCTUnwrap(harness.reporter.retryAfterForTesting(dateKey))
    XCTAssertEqual(secondRetryAfter.timeIntervalSince(harness.clock.now), 60)
    await harness.reporter.uploadDirtyRecordsForTesting()
    XCTAssertEqual(harness.probe.calls.count, 2)
  }

  func testUploadedDayIsNotReuploaded() async throws {
    let harness = try makeUploadHarness(shouldFail: false)
    defer { harness.defaults.removePersistentDomain(forName: harness.suite) }

    harness.reporter.sampleForTesting(watching: true, listening: false, at: harness.clock.now)
    await harness.reporter.uploadDirtyRecordsForTesting()
    XCTAssertEqual(harness.probe.calls.count, 1)
    XCTAssertTrue(harness.reporter.snapshotForTesting().dirtyDates.isEmpty)

    await harness.reporter.uploadDirtyRecordsForTesting()
    XCTAssertEqual(harness.probe.calls.count, 1)
    XCTAssertEqual(
      harness.reporter.retryAttemptsForTesting(try XCTUnwrap(harness.probe.calls.first?.date)),
      0)
  }

  func testCountersAccumulatedDuringFailedUploadSurviveNextAttempt() async throws {
    let harness = try makeUploadHarness(shouldFail: true)
    defer { harness.defaults.removePersistentDomain(forName: harness.suite) }

    harness.reporter.sampleForTesting(watching: true, listening: false, at: harness.clock.now)
    await harness.reporter.uploadDirtyRecordsForTesting()
    harness.reporter.sampleForTesting(watching: true, listening: true, at: harness.clock.now)
    harness.reporter.recordProactiveCardShown()

    let dateKey = try XCTUnwrap(harness.reporter.snapshotForTesting().dirtyDates.first)
    harness.clock.now = try XCTUnwrap(harness.reporter.retryAfterForTesting(dateKey))
    harness.probe.shouldFail = false
    await harness.reporter.uploadDirtyRecordsForTesting()

    XCTAssertEqual(harness.probe.calls.count, 2)
    XCTAssertEqual(harness.probe.calls.last?.watchingSeconds, 120)
    XCTAssertEqual(harness.probe.calls.last?.listeningSeconds, 60)
    XCTAssertEqual(harness.probe.calls.last?.proactiveCardsShown, 1)
    XCTAssertTrue(harness.reporter.snapshotForTesting().dirtyDates.isEmpty)
  }

  func testRelaunchRetriesDirtyDayImmediatelyBecauseBackoffIsInMemoryOnly() async throws {
    let harness = try makeUploadHarness(shouldFail: true)
    defer { harness.defaults.removePersistentDomain(forName: harness.suite) }

    harness.reporter.sampleForTesting(watching: true, listening: false, at: harness.clock.now)
    await harness.reporter.uploadDirtyRecordsForTesting()
    XCTAssertEqual(harness.probe.calls.count, 1)

    let relaunchProbe = UploadProbe(shouldFail: false)
    let relaunched = DesktopUsageDailyReporter(
      defaults: harness.defaults,
      now: { harness.clock.now },
      calendar: harness.calendar,
      timezone: { harness.calendar.timeZone },
      deviceID: { "device-1" },
      ownerID: { "owner-a" },
      uploadPayload: { try await relaunchProbe.upload($0) })
    relaunched.assumeAuthorizedForTesting()

    let snapshot = relaunched.snapshotForTesting()
    let dateKey = try XCTUnwrap(snapshot.dirtyDates.first)
    XCTAssertNil(relaunched.retryAfterForTesting(dateKey))
    XCTAssertEqual(relaunched.retryAttemptsForTesting(dateKey), 0)
    XCTAssertEqual(snapshot.records[dateKey]?.watchingSeconds, 60)

    await relaunched.uploadDirtyRecordsForTesting()
    XCTAssertEqual(relaunchProbe.calls.count, 1)
    XCTAssertTrue(relaunched.snapshotForTesting().dirtyDates.isEmpty)
  }

  private struct UploadHarness {
    let suite: String
    let defaults: UserDefaults
    let calendar: Calendar
    let clock: TestClock
    let probe: UploadProbe
    let reporter: DesktopUsageDailyReporter
  }

  private func makeUploadHarness(shouldFail: Bool) throws -> UploadHarness {
    let suite = "DesktopUsageDailyReporterTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    let clock = TestClock(Date(timeIntervalSince1970: 1_788_230_400))
    let probe = UploadProbe(shouldFail: shouldFail)
    let reporter = DesktopUsageDailyReporter(
      defaults: defaults,
      now: { clock.now },
      calendar: calendar,
      timezone: { calendar.timeZone },
      deviceID: { "device-1" },
      ownerID: { "owner-a" },
      uploadPayload: { try await probe.upload($0) })
    reporter.assumeAuthorizedForTesting()
    return UploadHarness(
      suite: suite,
      defaults: defaults,
      calendar: calendar,
      clock: clock,
      probe: probe,
      reporter: reporter)
  }
}

private enum TestUploadError: Error {
  case rejected
}

private final class TestClock: @unchecked Sendable {
  var now: Date
  init(_ now: Date) { self.now = now }
}

private final class UploadProbe: @unchecked Sendable {
  private let lock = NSLock()
  var shouldFail: Bool
  private var _calls: [DesktopUsageDailyPayload] = []

  init(shouldFail: Bool) {
    self.shouldFail = shouldFail
  }

  var calls: [DesktopUsageDailyPayload] {
    lock.withLock { _calls }
  }

  func upload(_ payload: DesktopUsageDailyPayload) async throws {
    lock.withLock { _calls.append(payload) }
    if shouldFail { throw TestUploadError.rejected }
  }
}
