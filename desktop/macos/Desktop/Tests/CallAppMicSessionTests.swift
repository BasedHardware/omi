import XCTest

@testable import Omi_Computer

/// Microphone-session classification, Zoom's per-release identity, adaptive
/// poll cadence, and the daily call-audio summary. Clocks are injected.
final class CallAudioSessionTrackerTests: XCTestCase {
  private let start = Date(timeIntervalSince1970: 10_000)

  private func at(_ seconds: TimeInterval) -> Date { start.addingTimeInterval(seconds) }

  private func snapshot(
    _ bundle: String,
    input: Bool,
    output: Bool,
    device: UInt32 = 1,
    pid: Int32 = 1,
    titles: [String] = []
  ) -> CallAudioSnapshot {
    CallAudioSnapshot(
      processes: [
        CallAudioProcessSnapshot(
          bundleID: bundle, pid: pid, isRunningInput: input, isRunningOutput: output)
      ],
      defaultInputDeviceID: device,
      browserWindowTitles: titles)
  }

  private func counters(
    after steps: [(TimeInterval, CallAudioSnapshot)]
  ) -> CallAudioBundleCounters {
    var tracker = CallAudioSessionTracker()
    for step in steps {
      tracker.ingest(step.1, at: at(step.0))
    }
    let bundle = steps.compactMap { $0.1.processes.first?.bundleID }.last ?? ""
    return tracker.counters[bundle] ?? CallAudioBundleCounters()
  }

  func testCallEndWhenOutputStopsWithInput() {
    let row = counters(after: [
      (0, snapshot("us.zoom.xos", input: true, output: true)),
      (10, snapshot("us.zoom.xos", input: false, output: false)),
      (12, snapshot("us.zoom.xos", input: false, output: false)),
    ])
    XCTAssertEqual(row.releasesCallEnd, 1)
    XCTAssertEqual(row.releasesMuteLike, 0)
    XCTAssertEqual(row.releasesDeviceSwitch, 0)
  }

  func testCallEndWhenOutputWasNotRunning() {
    let row = counters(after: [
      (0, snapshot("us.zoom.xos", input: true, output: false)),
      (10, snapshot("us.zoom.xos", input: false, output: false)),
      (12, snapshot("us.zoom.xos", input: false, output: false)),
    ])
    XCTAssertEqual(row.releasesCallEnd, 1)
    XCTAssertEqual(row.releasesMuteLike, 0)
  }

  func testCallEndWhenOutputStopsWithinOneSecond() {
    let row = counters(after: [
      (0, snapshot("us.zoom.xos", input: true, output: true)),
      (10, snapshot("us.zoom.xos", input: false, output: true)),
      (11, snapshot("us.zoom.xos", input: false, output: false)),
      (12, snapshot("us.zoom.xos", input: false, output: false)),
    ])
    XCTAssertEqual(row.releasesCallEnd, 1)
    XCTAssertEqual(row.releasesMuteLike, 0)
  }

  func testMuteLikeWhenOutputKeepsRunningForTwoSeconds() {
    let row = counters(after: [
      (0, snapshot("com.google.chrome.helper", input: true, output: true)),
      (10, snapshot("com.google.chrome.helper", input: false, output: true)),
      (12, snapshot("com.google.chrome.helper", input: false, output: true)),
    ])
    XCTAssertEqual(row.releasesMuteLike, 1)
    XCTAssertEqual(row.releasesCallEnd, 0)
    XCTAssertEqual(row.releasesDeviceSwitch, 0)
  }

  func testOutputStoppingBetweenOneAndTwoSecondsIsNeitherCallEndNorMute() {
    let row = counters(after: [
      (0, snapshot("com.google.chrome.helper", input: true, output: true)),
      (10, snapshot("com.google.chrome.helper", input: false, output: true)),
      (11.5, snapshot("com.google.chrome.helper", input: false, output: false)),
      (12, snapshot("com.google.chrome.helper", input: false, output: false)),
    ])
    XCTAssertEqual(row.releasesCallEnd, 0)
    XCTAssertEqual(row.releasesMuteLike, 0)
    XCTAssertEqual(row.releasesDeviceSwitch, 0)
  }

  func testDeviceSwitchTakesPrecedenceOverCallEnd() {
    let row = counters(after: [
      (0, snapshot("us.zoom.xos", input: true, output: true, device: 1)),
      (10, snapshot("us.zoom.xos", input: false, output: false, device: 2)),
      (12, snapshot("us.zoom.xos", input: false, output: false, device: 2)),
    ])
    XCTAssertEqual(row.releasesDeviceSwitch, 1)
    XCTAssertEqual(row.releasesCallEnd, 0)
    XCTAssertEqual(row.releasesMuteLike, 0)
  }

  func testDeviceSwitchWithinTwoSecondsBeforeTheStopBeatsMute() {
    let row = counters(after: [
      (0, snapshot("com.google.chrome.helper", input: true, output: true, device: 1)),
      (8, snapshot("com.google.chrome.helper", input: true, output: true, device: 2)),
      (10, snapshot("com.google.chrome.helper", input: false, output: true, device: 2)),
      (12, snapshot("com.google.chrome.helper", input: false, output: true, device: 2)),
    ])
    XCTAssertEqual(row.releasesDeviceSwitch, 1)
    XCTAssertEqual(row.releasesMuteLike, 0)
    XCTAssertEqual(row.releasesCallEnd, 0)
  }

  func testDeviceSwitchWithinTwoSecondsAfterTheStopBeatsCallEnd() {
    let row = counters(after: [
      (0, snapshot("us.zoom.xos", input: true, output: true, device: 1)),
      (10, snapshot("us.zoom.xos", input: false, output: false, device: 1)),
      (11, snapshot("us.zoom.xos", input: false, output: false, device: 2)),
      (13, snapshot("us.zoom.xos", input: false, output: false, device: 2)),
    ])
    XCTAssertEqual(row.releasesDeviceSwitch, 1)
    XCTAssertEqual(row.releasesCallEnd, 0)
  }

  func testReacquireGapBuckets() {
    let cases: [(TimeInterval, KeyPath<CallAudioBundleCounters, Int>)] = [
      (1.9, \.reacquireGapLt2s),
      (2, \.reacquireGap2to10s),
      (9.9, \.reacquireGap2to10s),
      (10, \.reacquireGap10to60s),
      (59.9, \.reacquireGap10to60s),
      (60, \.reacquireGap60to300s),
      (300, \.reacquireGap60to300s),
    ]
    for (gap, keyPath) in cases {
      let row = counters(after: [
        (0, snapshot("us.zoom.xos", input: true, output: true)),
        (1, snapshot("us.zoom.xos", input: false, output: false)),
        (1 + gap, snapshot("us.zoom.xos", input: true, output: true)),
      ])
      XCTAssertEqual(row[keyPath: keyPath], 1, "gap \(gap)")
      let others: [KeyPath<CallAudioBundleCounters, Int>] = [
        \.reacquireGapLt2s, \.reacquireGap2to10s, \.reacquireGap10to60s, \.reacquireGap60to300s,
      ]
      for other in others where other != keyPath {
        XCTAssertEqual(row[keyPath: other], 0, "gap \(gap) should not fill another bucket")
      }
    }
  }

  func testReacquireGapBeyond300SecondsIsNotRecorded() {
    let row = counters(after: [
      (0, snapshot("us.zoom.xos", input: true, output: false)),
      (1, snapshot("us.zoom.xos", input: false, output: false)),
      (301.1, snapshot("us.zoom.xos", input: true, output: false)),
    ])
    XCTAssertEqual(row.reacquireGapLt2s, 0)
    XCTAssertEqual(row.reacquireGap2to10s, 0)
    XCTAssertEqual(row.reacquireGap10to60s, 0)
    XCTAssertEqual(row.reacquireGap60to300s, 0)
  }

  func testCallLikeSessionThresholdAndDurationBuckets() {
    let cases: [(TimeInterval, KeyPath<CallAudioBundleCounters, Int>, Bool)] = [
      (59.9, \.sessionLt1m, false),
      (60, \.session1to10m, true),
      (599.9, \.session1to10m, true),
      (600, \.session10to60m, true),
      (3599.9, \.session10to60m, true),
      (3600, \.sessionGe60m, true),
    ]
    for (duration, keyPath, callLike) in cases {
      let row = counters(after: [
        (0, snapshot("us.zoom.xos", input: true, output: true)),
        (duration, snapshot("us.zoom.xos", input: false, output: false)),
      ])
      XCTAssertEqual(row[keyPath: keyPath], 1, "duration \(duration)")
      XCTAssertEqual(row.callLikeSessions, callLike ? 1 : 0, "duration \(duration)")
    }
  }

  func testZoomIdentityIncrementsOnReacquireAndOtherAppsDoNot() {
    var zoom = CallAudioSessionTracker()
    zoom.ingest(snapshot("us.zoom.xos", input: true, output: true), at: at(0))
    XCTAssertEqual(zoom.nativeCallIdentity(bundleID: "us.zoom.xos"), "app:us.zoom.xos#1")
    zoom.ingest(snapshot("us.zoom.xos", input: false, output: false), at: at(40))
    zoom.ingest(snapshot("us.zoom.xos", input: true, output: true), at: at(48))
    XCTAssertEqual(zoom.nativeCallIdentity(bundleID: "US.ZOOM.XOS"), "app:us.zoom.xos#2")

    var slack = CallAudioSessionTracker()
    slack.ingest(snapshot("com.tinyspeck.slackmacgap", input: true, output: true), at: at(0))
    slack.ingest(snapshot("com.tinyspeck.slackmacgap", input: false, output: false), at: at(40))
    slack.ingest(snapshot("com.tinyspeck.slackmacgap", input: true, output: true), at: at(48))
    XCTAssertEqual(
      slack.nativeCallIdentity(bundleID: "com.tinyspeck.slackmacgap"),
      "app:com.tinyspeck.slackmacgap")

    XCTAssertFalse(CallAppReleasePolicy.releaseEndsCall(bundleID: "com.google.Chrome"))
    XCTAssertTrue(CallAppReleasePolicy.releaseEndsCall(bundleID: "us.zoom.xos"))
  }
}

final class MeetingCallObservationTests: XCTestCase {
  func testDetectionKeepsTodaySemanticsIncludingThePre144Fallback() {
    let zoom = CallAudioSnapshot(
      processes: [
        CallAudioProcessSnapshot(bundleID: "us.zoom.xos", pid: 1, isRunningInput: true, isRunningOutput: true)
      ],
      defaultInputDeviceID: 1,
      browserWindowTitles: [])
    let titleOnly = CallAudioSnapshot(
      processes: [],
      defaultInputDeviceID: 1,
      browserWindowTitles: ["Meet - abc-defg-hij"])
    let browserMic = CallAudioSnapshot(
      processes: [
        CallAudioProcessSnapshot(
          bundleID: "com.google.chrome.helper", pid: 2, isRunningInput: true, isRunningOutput: true)
      ],
      defaultInputDeviceID: 1,
      browserWindowTitles: [])
    let quiet = CallAudioSnapshot(processes: [], defaultInputDeviceID: 1, browserWindowTitles: [])

    XCTAssertTrue(
      MeetingCallObservation.isDetected(snapshot: zoom, mode: .always, processInputAPIAvailable: true))
    XCTAssertFalse(
      MeetingCallObservation.isDetected(snapshot: titleOnly, mode: .always, processInputAPIAvailable: true))
    XCTAssertTrue(
      MeetingCallObservation.isDetected(
        snapshot: titleOnly, mode: .onlyMeetings, processInputAPIAvailable: true))
    XCTAssertTrue(
      MeetingCallObservation.isDetected(snapshot: browserMic, mode: .always, processInputAPIAvailable: true))
    XCTAssertFalse(
      MeetingCallObservation.isDetected(snapshot: quiet, mode: .onlyMeetings, processInputAPIAvailable: true))

    XCTAssertFalse(
      MeetingCallObservation.isDetected(snapshot: zoom, mode: .always, processInputAPIAvailable: false))
    XCTAssertTrue(
      MeetingCallObservation.isDetected(snapshot: titleOnly, mode: .always, processInputAPIAvailable: false))
    XCTAssertTrue(
      MeetingCallObservation.isDetected(
        snapshot: titleOnly, mode: .onlyMeetings, processInputAPIAvailable: false))
    XCTAssertFalse(
      MeetingCallObservation.isDetected(snapshot: titleOnly, mode: .off, processInputAPIAvailable: false))
  }

  func testBrowserTitlesAreSkippedUntilACallSurfaceHoldsTheMicInAlwaysMode() {
    XCTAssertEqual(
      CallAudioBrowserTitlePolicy.capture(mode: .always, processInputAPIAvailable: true),
      .whenCallSurfaceHoldsInput)
    XCTAssertEqual(
      CallAudioBrowserTitlePolicy.capture(mode: .onlyMeetings, processInputAPIAvailable: true),
      .always)
    XCTAssertEqual(
      CallAudioBrowserTitlePolicy.capture(mode: .always, processInputAPIAvailable: false),
      .always)
  }

  func testIdentitiesUseTheZoomGenerationAndIgnoreBrowserBundles() {
    let snapshot = CallAudioSnapshot(
      processes: [
        CallAudioProcessSnapshot(bundleID: "us.zoom.xos", pid: 4, isRunningInput: true, isRunningOutput: true),
        CallAudioProcessSnapshot(
          bundleID: "com.google.chrome.helper", pid: 5, isRunningInput: true, isRunningOutput: true),
      ],
      defaultInputDeviceID: 1,
      browserWindowTitles: ["Meet - abc-defg-hij"])
    let identities = MeetingCallObservation.identities(
      snapshot: snapshot,
      processInputAPIAvailable: true,
      nativeIdentity: { "app:\($0)#2" })
    XCTAssertEqual(identities, ["app:us.zoom.xos#2", "meet:abc-defg-hij"])
  }

  /// A Discord call holds the mic in its Electron renderer helper (probe, 2026-09-26).
  func testHelperProcessesResolveToTheirAppIdentity() {
    let snapshot = CallAudioSnapshot(
      processes: [
        CallAudioProcessSnapshot(
          bundleID: "com.hnc.discord.helper.renderer", pid: 6, isRunningInput: true, isRunningOutput: true),
        CallAudioProcessSnapshot(bundleID: "com.hnc.discord", pid: 7, isRunningInput: true, isRunningOutput: false),
      ],
      defaultInputDeviceID: 1,
      browserWindowTitles: [])
    XCTAssertTrue(
      MeetingCallObservation.isDetected(snapshot: snapshot, mode: .onlyMeetings, processInputAPIAvailable: true))
    let identities = MeetingCallObservation.identities(
      snapshot: snapshot, processInputAPIAvailable: true, nativeIdentity: { "app:\($0)" })
    XCTAssertEqual(identities, ["app:com.hnc.discord"])
  }
}

@MainActor
final class MeetingCallCadenceAndRotationTests: XCTestCase {
  private var now = Date(timeIntervalSince1970: 5_000)

  private struct IsolatedDefaults {
    let suiteName: String
    let defaults: UserDefaults
    func remove() { defaults.removePersistentDomain(forName: suiteName) }
  }

  private func makeDetector(
    mode: AssistantSettings.AudioRecordingMode = .always,
    onCallChanged: @escaping () -> Void = {},
    onChange: @escaping (Bool) -> Void = { _ in }
  ) throws -> (MeetingDetector, IsolatedDefaults) {
    let suiteName = "CallAppMic.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defaults.removePersistentDomain(forName: suiteName)
    let detector = MeetingDetector(
      pollInterval: 4,
      activePollInterval: 1,
      offGracePeriod: 8,
      mode: mode,
      processInputAPIAvailable: true,
      now: { [weak self] in self?.now ?? Date(timeIntervalSince1970: 0) },
      audioLedgerDefaults: defaults,
      onCallChanged: onCallChanged,
      onChange: onChange,
      onAudioSummaries: { _ in })
    return (detector, IsolatedDefaults(suiteName: suiteName, defaults: defaults))
  }

  private func audio(
    _ bundle: String, input: Bool, output: Bool, titles: [String] = []
  ) -> CallAudioSnapshot {
    CallAudioSnapshot(
      processes: [
        CallAudioProcessSnapshot(bundleID: bundle, pid: 7, isRunningInput: input, isRunningOutput: output)
      ],
      defaultInputDeviceID: 3,
      browserWindowTitles: titles)
  }

  func testCadenceIsOneSecondOnlyWhileACallSurfaceHoldsTheMic() throws {
    let (detector, suite) = try makeDetector()
    defer { suite.remove() }
    XCTAssertEqual(detector.pollInterval, 4)

    detector.applySnapshot(CallAudioSnapshot(processes: [], defaultInputDeviceID: 3, browserWindowTitles: []))
    XCTAssertEqual(detector.pollInterval, 4)

    detector.applySnapshot(audio("us.zoom.xos", input: true, output: true))
    XCTAssertEqual(detector.pollInterval, 1)

    detector.applySnapshot(audio("com.google.chrome.helper", input: true, output: true))
    XCTAssertEqual(detector.pollInterval, 1)

    detector.applySnapshot(audio("com.apple.Music", input: true, output: true))
    XCTAssertEqual(detector.pollInterval, 4, "a non-call app holding the mic stays on the idle poll")

    detector.applySnapshot(audio("us.zoom.xos", input: false, output: false))
    XCTAssertEqual(detector.pollInterval, 4)
  }

  /// Measured 2026-09-26: Zoom holds input and output for 40s, both stop together,
  /// and the next meeting re-acquires both 8s later — inside the off grace.
  func testMeasuredZoomTraceRotatesTheConversationOnce() throws {
    var callChanges = 0
    var edges = [Bool]()
    let (detector, suite) = try makeDetector(
      onCallChanged: { callChanges += 1 },
      onChange: { edges.append($0) })
    defer { suite.remove() }

    now = Date(timeIntervalSince1970: 5_000)
    detector.applySnapshot(audio("us.zoom.xos", input: true, output: true))
    now = now.addingTimeInterval(40)
    detector.applySnapshot(audio("us.zoom.xos", input: false, output: false))
    now = now.addingTimeInterval(4)
    detector.applySnapshot(audio("us.zoom.xos", input: false, output: false))
    now = now.addingTimeInterval(4)
    detector.applySnapshot(audio("us.zoom.xos", input: true, output: true))
    XCTAssertEqual(callChanges, 0)
    now = now.addingTimeInterval(8)
    detector.applySnapshot(audio("us.zoom.xos", input: true, output: true))

    XCTAssertEqual(edges, [true], "the 8s gap stays inside the off grace")
    XCTAssertEqual(callChanges, 1)
    XCTAssertTrue(detector.hasPendingCallChange)
    XCTAssertTrue(detector.isMeetingActive)
  }

  func testZoomGapLongerThanTheOffGraceDoesNotAlsoReportACallChange() throws {
    var callChanges = 0
    var edges = [Bool]()
    let (detector, suite) = try makeDetector(
      onCallChanged: { callChanges += 1 },
      onChange: { edges.append($0) })
    defer { suite.remove() }

    detector.applySnapshot(audio("us.zoom.xos", input: true, output: true))
    now = now.addingTimeInterval(40)
    detector.applySnapshot(audio("us.zoom.xos", input: false, output: false))
    now = now.addingTimeInterval(9)
    detector.applySnapshot(audio("us.zoom.xos", input: false, output: false))
    now = now.addingTimeInterval(1)
    detector.applySnapshot(audio("us.zoom.xos", input: true, output: true))
    now = now.addingTimeInterval(20)
    detector.applySnapshot(audio("us.zoom.xos", input: true, output: true))

    XCTAssertEqual(edges, [true, false, true])
    XCTAssertEqual(callChanges, 0)
    XCTAssertFalse(detector.hasPendingCallChange)
  }

  func testBrowserMicDropAndReacquireDoesNotRotate() throws {
    var callChanges = 0
    var edges = [Bool]()
    let (detector, suite) = try makeDetector(
      onCallChanged: { callChanges += 1 },
      onChange: { edges.append($0) })
    defer { suite.remove() }
    let title = ["Meet - abc-defg-hij"]

    detector.applySnapshot(audio("com.google.chrome.helper", input: true, output: true, titles: title))
    now = now.addingTimeInterval(4)
    detector.applySnapshot(audio("com.google.chrome.helper", input: false, output: true, titles: title))
    now = now.addingTimeInterval(4)
    detector.applySnapshot(audio("com.google.chrome.helper", input: true, output: true, titles: title))
    now = now.addingTimeInterval(20)
    detector.applySnapshot(audio("com.google.chrome.helper", input: true, output: true, titles: title))

    XCTAssertEqual(edges, [true])
    XCTAssertEqual(callChanges, 0)
    XCTAssertTrue(detector.isMeetingActive)
  }

  func testSlackReacquireKeepsTheSameIdentityAndDoesNotRotate() throws {
    var callChanges = 0
    var edges = [Bool]()
    let (detector, suite) = try makeDetector(
      onCallChanged: { callChanges += 1 },
      onChange: { edges.append($0) })
    defer { suite.remove() }

    detector.applySnapshot(audio("com.tinyspeck.slackmacgap", input: true, output: true))
    now = now.addingTimeInterval(10)
    detector.applySnapshot(audio("com.tinyspeck.slackmacgap", input: false, output: false))
    now = now.addingTimeInterval(4)
    detector.applySnapshot(audio("com.tinyspeck.slackmacgap", input: true, output: true))
    now = now.addingTimeInterval(20)
    detector.applySnapshot(audio("com.tinyspeck.slackmacgap", input: true, output: true))

    XCTAssertEqual(edges, [true])
    XCTAssertEqual(callChanges, 0)
  }
}

final class CallAppAudioDailyLedgerTests: XCTestCase {
  private var suiteName = ""
  private var defaults: UserDefaults?
  private let calendar: Calendar = {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = .gmt
    return calendar
  }()

  override func setUp() {
    super.setUp()
    suiteName = "CallAppMicLedger.\(UUID().uuidString)"
    defaults = UserDefaults(suiteName: suiteName)
    defaults?.removePersistentDomain(forName: suiteName)
  }

  override func tearDown() {
    defaults?.removePersistentDomain(forName: suiteName)
    defaults = nil
    super.tearDown()
  }

  private func day(_ day: Int, hour: Int = 12) -> Date {
    calendar.date(from: DateComponents(year: 2026, month: 9, day: day, hour: hour))
      ?? Date(timeIntervalSince1970: 0)
  }

  private func zoom(input: Bool, output: Bool) -> CallAudioSnapshot {
    CallAudioSnapshot(
      processes: [
        CallAudioProcessSnapshot(
          bundleID: "us.zoom.xos", pid: 9, isRunningInput: input, isRunningOutput: output)
      ],
      defaultInputDeviceID: 1,
      browserWindowTitles: [])
  }

  private func ledger() -> CallAppAudioDailyLedger {
    CallAppAudioDailyLedger(defaults: defaults ?? UserDefaults(), calendar: calendar)
  }

  func testRelaunchMidDayKeepsCountersAndTheNextDayFlushesTheSum() {
    var first = ledger()
    _ = first.ingest(zoom(input: true, output: true), at: day(26))
    _ = first.ingest(zoom(input: false, output: false), at: day(26).addingTimeInterval(60))

    var resumed = ledger()
    XCTAssertEqual(resumed.begin(at: day(26, hour: 18)), [])
    _ = resumed.ingest(zoom(input: true, output: true), at: day(26, hour: 18))
    _ = resumed.ingest(zoom(input: false, output: false), at: day(26, hour: 18).addingTimeInterval(60))
    let flushed = resumed.ingest(zoom(input: false, output: false), at: day(27))

    XCTAssertEqual(flushed.count, 1)
    XCTAssertEqual(flushed.first?.bundleID, "us.zoom.xos")
    XCTAssertEqual(flushed.first?.localDay, "2026-09-26")
    XCTAssertEqual(flushed.first?.counters.callLikeSessions, 2)
    XCTAssertEqual(flushed.first?.catalogReleaseEndsCall, true)
    XCTAssertEqual(flushed.first?.counters.session1to10m, 2)
  }

  func testLaunchOnANewDayFlushesTheStoredDay() {
    var yesterday = ledger()
    _ = yesterday.ingest(zoom(input: true, output: true), at: day(26))
    _ = yesterday.ingest(zoom(input: false, output: false), at: day(26).addingTimeInterval(90))

    var today = ledger()
    let flushed = today.begin(at: day(27))
    XCTAssertEqual(flushed.map(\.localDay), ["2026-09-26"])
    XCTAssertEqual(flushed.first?.counters.callLikeSessions, 1)

    let again = today.begin(at: day(27, hour: 13))
    XCTAssertEqual(again, [], "the stored day was cleared when it was flushed")
  }

  func testBundlesWithoutACallLikeSessionAreNotFlushed() {
    var tracker = CallAudioSessionTracker()
    let mute = CallAudioSnapshot(
      processes: [
        CallAudioProcessSnapshot(
          bundleID: "com.google.chrome.helper", pid: 3, isRunningInput: false, isRunningOutput: true)
      ],
      defaultInputDeviceID: 1,
      browserWindowTitles: [])
    tracker.ingest(
      CallAudioSnapshot(
        processes: [
          CallAudioProcessSnapshot(
            bundleID: "com.google.chrome.helper", pid: 3, isRunningInput: true, isRunningOutput: true)
        ],
        defaultInputDeviceID: 1,
        browserWindowTitles: []),
      at: day(26))
    tracker.ingest(mute, at: day(26).addingTimeInterval(1))
    tracker.ingest(mute, at: day(26).addingTimeInterval(4))

    let summaries = CallAppAudioSummaryRanking.select(counters: tracker.counters, localDay: "2026-09-26")
    XCTAssertEqual(summaries, [])
  }

  func testDailyFlushKeepsTheTwentyBundlesWithTheMostCallLikeSessions() {
    var counters: [String: CallAudioBundleCounters] = [:]
    for index in 1...21 {
      var row = CallAudioBundleCounters()
      row.callLikeSessions = index
      counters[String(format: "com.example.app%02d", index)] = row
    }
    var quiet = CallAudioBundleCounters()
    quiet.releasesMuteLike = 50
    counters["com.example.quiet"] = quiet

    let summaries = CallAppAudioSummaryRanking.select(counters: counters, localDay: "2026-09-26")
    XCTAssertEqual(summaries.count, 20)
    XCTAssertEqual(summaries.first?.bundleID, "com.example.app21")
    XCTAssertEqual(summaries.first?.counters.callLikeSessions, 21)
    XCTAssertFalse(summaries.contains { $0.bundleID == "com.example.app01" })
    XCTAssertFalse(summaries.contains { $0.bundleID == "com.example.quiet" })
  }

  func testOmisOwnCaptureIsNeverReportedAsACallApp() {
    var own = CallAudioBundleCounters()
    own.callLikeSessions = 9
    var zoom = CallAudioBundleCounters()
    zoom.callLikeSessions = 1
    let summaries = CallAppAudioSummaryRanking.select(
      counters: ["com.omi.computer-macos.beta": own, "com.omi.computer-macos": own, "us.zoom.xos": zoom],
      localDay: "2026-09-26")
    XCTAssertEqual(summaries.map(\.bundleID), ["us.zoom.xos"])
  }

  func testTiedBundlesFlushInBundleIdOrderUpToTheCap() {
    var counters: [String: CallAudioBundleCounters] = [:]
    for index in 1...21 {
      var row = CallAudioBundleCounters()
      row.callLikeSessions = 1
      counters[String(format: "com.example.app%02d", index)] = row
    }
    let summaries = CallAppAudioSummaryRanking.select(counters: counters, localDay: "2026-09-26")
    XCTAssertEqual(summaries.map(\.bundleID), (1...20).map { String(format: "com.example.app%02d", $0) })
  }
}

final class CallAppAudioSummaryTelemetryTests: XCTestCase {
  func testEventNameIsStable() {
    XCTAssertEqual(CallAppAudioSummaryTelemetry.eventName, "Desktop Call App Audio Summary")
  }

  func testPayloadCarriesExactlyTheBoundedKeySet() {
    var counters = CallAudioBundleCounters()
    counters.callLikeSessions = 2
    counters.releasesCallEnd = 3
    counters.releasesMuteLike = 4
    counters.releasesDeviceSwitch = 5
    counters.reacquireGapLt2s = 6
    counters.reacquireGap2to10s = 7
    counters.reacquireGap10to60s = 8
    counters.reacquireGap60to300s = 9
    counters.sessionLt1m = 10
    counters.session1to10m = 11
    counters.session10to60m = 12
    counters.sessionGe60m = 13
    let summary = CallAppAudioSummary(bundleID: "us.zoom.xos", localDay: "2026-09-26", counters: counters)

    let properties = CallAppAudioSummaryTelemetry.properties(summary)

    XCTAssertEqual(
      Set(properties.keys),
      [
        "platform", "bundle_id", "call_like_sessions", "releases_call_end", "releases_mute_like",
        "releases_device_switch", "reacquire_gap_lt2s", "reacquire_gap_2_10s", "reacquire_gap_10_60s",
        "reacquire_gap_60_300s", "session_lt1m", "session_1_10m", "session_10_60m", "session_ge60m",
        "catalog_release_ends_call", "local_day",
      ])
    XCTAssertEqual(properties["platform"] as? String, "macos")
    XCTAssertEqual(properties["bundle_id"] as? String, "us.zoom.xos")
    XCTAssertEqual(properties["call_like_sessions"] as? Int, 2)
    XCTAssertEqual(properties["releases_call_end"] as? Int, 3)
    XCTAssertEqual(properties["releases_mute_like"] as? Int, 4)
    XCTAssertEqual(properties["releases_device_switch"] as? Int, 5)
    XCTAssertEqual(properties["reacquire_gap_lt2s"] as? Int, 6)
    XCTAssertEqual(properties["reacquire_gap_2_10s"] as? Int, 7)
    XCTAssertEqual(properties["reacquire_gap_10_60s"] as? Int, 8)
    XCTAssertEqual(properties["reacquire_gap_60_300s"] as? Int, 9)
    XCTAssertEqual(properties["session_lt1m"] as? Int, 10)
    XCTAssertEqual(properties["session_1_10m"] as? Int, 11)
    XCTAssertEqual(properties["session_10_60m"] as? Int, 12)
    XCTAssertEqual(properties["session_ge60m"] as? Int, 13)
    XCTAssertEqual(properties["catalog_release_ends_call"] as? Bool, true)
    XCTAssertEqual(properties["local_day"] as? String, "2026-09-26")
  }
}

@MainActor
final class MeetingDetectorAudioSummaryFlushTests: XCTestCase {
  func testDetectorStartFlushesThePreviousLocalDay() {
    let suiteName = "CallAppMicFlush.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      return XCTFail("could not open an isolated defaults suite")
    }
    defaults.removePersistentDomain(forName: suiteName)
    defer { defaults.removePersistentDomain(forName: suiteName) }

    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = .gmt
    let yesterday =
      calendar.date(from: DateComponents(year: 2026, month: 9, day: 26, hour: 15))
      ?? Date(timeIntervalSince1970: 0)
    let today =
      calendar.date(from: DateComponents(year: 2026, month: 9, day: 27, hour: 9))
      ?? Date(timeIntervalSince1970: 0)

    var ledger = CallAppAudioDailyLedger(defaults: defaults, calendar: calendar)
    _ = ledger.ingest(
      CallAudioSnapshot(
        processes: [
          CallAudioProcessSnapshot(
            bundleID: "us.zoom.xos", pid: 1, isRunningInput: true, isRunningOutput: true)
        ],
        defaultInputDeviceID: 1,
        browserWindowTitles: []),
      at: yesterday)
    _ = ledger.ingest(
      CallAudioSnapshot(
        processes: [
          CallAudioProcessSnapshot(
            bundleID: "us.zoom.xos", pid: 1, isRunningInput: false, isRunningOutput: false)
        ],
        defaultInputDeviceID: 1,
        browserWindowTitles: []),
      at: yesterday.addingTimeInterval(120))

    var emitted: [CallAppAudioSummary] = []
    let detector = MeetingDetector(
      pollInterval: 60,
      mode: .always,
      processInputAPIAvailable: true,
      snapshot: {
        CallAudioSnapshot(processes: [], defaultInputDeviceID: 1, browserWindowTitles: [])
      },
      now: { today },
      audioLedgerDefaults: defaults,
      calendar: calendar,
      onChange: { _ in },
      onAudioSummaries: { emitted.append(contentsOf: $0) })

    detector.start()
    detector.stop()

    XCTAssertEqual(emitted.count, 1)
    XCTAssertEqual(emitted.first?.bundleID, "us.zoom.xos")
    XCTAssertEqual(emitted.first?.localDay, "2026-09-26")
    XCTAssertEqual(emitted.first?.counters.callLikeSessions, 1)
    let properties = CallAppAudioSummaryTelemetry.properties(emitted[0])
    XCTAssertEqual(properties["platform"] as? String, "macos")
    XCTAssertEqual(Set(properties.keys).count, 16)
  }
}
