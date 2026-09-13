import XCTest

@testable import Omi_Computer

/// A dictation into Wispr Flow used to become an Omi conversation: ambient capture heard it, and
/// anything over the backend's 100-word discard early-exit was never reconsidered. These pin the
/// capture-time rule — a catalogued dictation app holding the microphone mutes the ambient mic
/// contribution, and a call surface holding it outranks that — without CoreAudio or a clock.
final class DictationMicSuppressionPolicyTests: XCTestCase {
  private let superwhisper = "com.superduper.superwhisper"

  func testCataloguedDictationAppAloneSuppresses() {
    XCTAssertEqual(
      DictationMicSuppressionPolicy.verdict(runningInputBundleIDs: [superwhisper], enabled: true),
      .suppress(bundleID: superwhisper))
  }

  func testBundleIDMatchIsCaseInsensitiveAndTokenBased() {
    // Electron vendors rename bundles; the token catches a renamed Wispr Flow.
    XCTAssertEqual(
      DictationMicSuppressionPolicy.verdict(
        runningInputBundleIDs: ["ai.WisprFlow.Desktop"], enabled: true),
      .suppress(bundleID: "ai.wisprflow.desktop"))
    XCTAssertTrue(DictationMicSuppressionPolicy.isDictationApp(bundleID: "COM.Apple.DictationIM"))
  }

  func testNothingRunningInputPasses() {
    XCTAssertEqual(
      DictationMicSuppressionPolicy.verdict(runningInputBundleIDs: [], enabled: true),
      .pass(.noDictationApp))
  }

  func testUnknownNonCallProcessNeverSuppresses() {
    // Deliberately a catalog: Krisp, OBS, Voice Memos and other mic holders are not dictation.
    XCTAssertEqual(
      DictationMicSuppressionPolicy.verdict(
        runningInputBundleIDs: ["ai.krisp.krispmac", "com.apple.voicememos"], enabled: true),
      .pass(.noDictationApp))
  }

  func testCallSurfaceHoldingTheMicOutranksDictation() {
    // Dictating during a Zoom call keeps everything.
    XCTAssertEqual(
      DictationMicSuppressionPolicy.verdict(
        runningInputBundleIDs: [superwhisper, "us.zoom.xos"], enabled: true),
      .pass(.callSurfaceHoldsMic))
    // A browser helper process (Google Meet) counts as a call surface too.
    XCTAssertEqual(
      DictationMicSuppressionPolicy.verdict(
        runningInputBundleIDs: ["com.google.Chrome.helper", superwhisper], enabled: true),
      .pass(.callSurfaceHoldsMic))
  }

  func testOmiItselfHoldingTheMicIsNotADictationApp() {
    XCTAssertEqual(
      DictationMicSuppressionPolicy.verdict(
        runningInputBundleIDs: ["com.omi.computer-macos"], enabled: true),
      .pass(.noDictationApp))
  }

  func testDisabledSettingPassesEvenWithADictationApp() {
    XCTAssertEqual(
      DictationMicSuppressionPolicy.verdict(runningInputBundleIDs: [superwhisper], enabled: false),
      .pass(.disabled))
  }

  func testCallSurfacePredicateCoversNativeAppsAndBrowsers() {
    XCTAssertTrue(ConferencingApps.isCallSurface(bundleID: "us.zoom.xos"))
    XCTAssertTrue(ConferencingApps.isCallSurface(bundleID: "com.google.chrome.helper"))
    XCTAssertFalse(ConferencingApps.isCallSurface(bundleID: superwhisper))
  }

  /// Mute polarity makes a missed call surface worse than the same gap was for meeting
  /// detection: a channel variant or browser missing here silences a real call while dictating.
  func testCallSurfaceCoversChannelVariantsAndOtherChromiumBrowsers() {
    for bundleID in [
      "com.hnc.DiscordPTB", "com.hnc.DiscordCanary",
      "org.chromium.Chromium.helper", "org.mozilla.nightly", "com.openai.atlas.helper",
    ] {
      XCTAssertTrue(ConferencingApps.isCallSurface(bundleID: bundleID), bundleID)
    }
  }
}

final class DictationMicSuppressionGateTests: XCTestCase {
  func testGatedChunkIsSameLengthSilenceOnlyWhileSuppressing() {
    let gate = DictationMicSuppressionGate()
    let chunk = Data([1, 2, 3, 4, 5, 6])

    XCTAssertEqual(gate.gated(chunk), chunk)

    gate.set(true)
    let muted = gate.gated(chunk)
    XCTAssertEqual(muted.count, chunk.count, "length is preserved so mixer liveness and cadence hold")
    XCTAssertTrue(muted.allSatisfy { $0 == 0 })

    gate.set(false)
    XCTAssertEqual(gate.gated(chunk), chunk)
  }
}

@MainActor
final class DictationMicSuppressionMonitorTests: XCTestCase {
  private let superwhisper = "com.superduper.superwhisper"

  private func makeMonitor(
    enabled: @escaping () -> Bool = { true },
    clock: @escaping () -> Date,
    closed: @escaping (DictationMicSuppressionMonitor.ClosedWindow) -> Void
  ) -> DictationMicSuppressionMonitor {
    DictationMicSuppressionMonitor(
      probe: { [] }, isEnabled: enabled, now: clock, onWindowClosed: closed)
  }

  func testWindowOpensOnDictationAndClosesWithItsDuration() {
    var now = Date(timeIntervalSince1970: 1_000)
    var closed: [DictationMicSuppressionMonitor.ClosedWindow] = []
    let monitor = makeMonitor(clock: { now }, closed: { closed.append($0) })

    monitor.apply(runningInputBundleIDs: [superwhisper])
    XCTAssertTrue(monitor.isSuppressing)
    XCTAssertTrue(closed.isEmpty)

    now = now.addingTimeInterval(3.5)
    monitor.apply(runningInputBundleIDs: [superwhisper])
    XCTAssertTrue(monitor.isSuppressing, "a continuing hold stays one window")
    XCTAssertTrue(closed.isEmpty)

    now = now.addingTimeInterval(0.5)
    monitor.apply(runningInputBundleIDs: [])
    XCTAssertFalse(monitor.isSuppressing)
    XCTAssertEqual(closed, [.init(bundleID: superwhisper, duration: 4.0)])
  }

  func testCallStartingMidDictationReleasesTheGate() {
    var now = Date(timeIntervalSince1970: 1_000)
    var closed: [DictationMicSuppressionMonitor.ClosedWindow] = []
    let monitor = makeMonitor(clock: { now }, closed: { closed.append($0) })

    monitor.apply(runningInputBundleIDs: [superwhisper])
    now = now.addingTimeInterval(1)
    monitor.apply(runningInputBundleIDs: [superwhisper, "us.zoom.xos"])

    XCTAssertFalse(monitor.isSuppressing, "nothing said on a call is ever muted")
    XCTAssertEqual(closed.map(\.duration), [1])
  }

  func testTogglingTheSettingOffMidWindowReleasesTheGate() {
    var enabled = true
    var closed: [DictationMicSuppressionMonitor.ClosedWindow] = []
    let monitor = makeMonitor(
      enabled: { enabled }, clock: { Date(timeIntervalSince1970: 1_000) }, closed: { closed.append($0) })

    monitor.apply(runningInputBundleIDs: [superwhisper])
    XCTAssertTrue(monitor.isSuppressing)
    enabled = false
    monitor.apply(runningInputBundleIDs: [superwhisper])
    XCTAssertFalse(monitor.isSuppressing)
    XCTAssertEqual(closed.count, 1)
  }

  func testStopClosesAnOpenWindowAndReleasesTheGate() {
    var now = Date(timeIntervalSince1970: 1_000)
    var closed: [DictationMicSuppressionMonitor.ClosedWindow] = []
    let monitor = makeMonitor(clock: { now }, closed: { closed.append($0) })

    monitor.start()
    monitor.apply(runningInputBundleIDs: [superwhisper])
    now = now.addingTimeInterval(2)
    monitor.stop()

    XCTAssertFalse(monitor.isSuppressing, "a capture that outlives the monitor must never stay muted")
    XCTAssertEqual(closed, [.init(bundleID: superwhisper, duration: 2)])
  }
}

@MainActor
final class AmbientIgnoresDictationAppsPersistenceTests: XCTestCase {
  func testAbsentKeyReadsOnAndStoredFalseReadsOff() throws {
    let suite = "DictationMicSuppressionTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }

    XCTAssertTrue(ShortcutSettings.persistedAmbientIgnoresDictationApps(from: defaults))
    defaults.set(false, forKey: DefaultsKey.transcriptionIgnoreDictationApps.rawValue)
    XCTAssertFalse(ShortcutSettings.persistedAmbientIgnoresDictationApps(from: defaults))
  }
}
