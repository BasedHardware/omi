import XCTest

@testable import Omi_Computer

// MARK: - ConferencingApps

final class ConferencingAppsTests: XCTestCase {

    func testNativeCallAppMatchesOnOwnerNameAlone() {
        XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "zoom.us", title: nil))
        XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "Microsoft Teams", title: "anything"))
        XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "FaceTime", title: nil))
        XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "Webex", title: nil))
    }

    func testBrowserRequiresCallKeywordInTitle() {
        XCTAssertTrue(
            ConferencingApps.isCallWindow(ownerName: "Google Chrome", title: "Google Meet — Standup"))
        XCTAssertTrue(
            ConferencingApps.isCallWindow(ownerName: "Safari", title: "https://meet.google.com/abc-defg"))
        XCTAssertFalse(
            ConferencingApps.isCallWindow(ownerName: "Google Chrome", title: "GitHub - omi"))
        XCTAssertFalse(ConferencingApps.isCallWindow(ownerName: "Google Chrome", title: nil))
    }

    func testNonCallAppAndNilOwnerAreNotCalls() {
        // A non-browser, non-call app is never a call — even if its title mentions a meeting.
        XCTAssertFalse(ConferencingApps.isCallWindow(ownerName: "Finder", title: "Zoom Meeting"))
        XCTAssertFalse(ConferencingApps.isCallWindow(ownerName: nil, title: "Google Meet"))
    }

    func testNativeCallBundleIDMatchingIsCaseInsensitive() {
        XCTAssertTrue(ConferencingApps.isNativeCallApp(bundleID: "us.zoom.xos"))
        XCTAssertTrue(ConferencingApps.isNativeCallApp(bundleID: "US.Zoom.XOS"))
        XCTAssertTrue(ConferencingApps.isNativeCallApp(bundleID: "com.microsoft.teams2"))
        XCTAssertTrue(ConferencingApps.isNativeCallApp(bundleID: "com.apple.facetime"))
        // Omi itself (which is always using the mic while recording) must not count as a meeting.
        XCTAssertFalse(ConferencingApps.isNativeCallApp(bundleID: "com.omi.omi-mtg-sysaudio"))
        XCTAssertFalse(ConferencingApps.isNativeCallApp(bundleID: "com.google.Chrome"))
    }

    func testBrowserBundleIDPrefixMatchingCatchesHelpers() {
        // Browsers route call audio through helper processes — match by prefix.
        XCTAssertTrue(ConferencingApps.isBrowserBundleID("net.imput.helium.helper"))  // Helium (Meet)
        XCTAssertTrue(ConferencingApps.isBrowserBundleID("com.google.Chrome.helper"))
        XCTAssertTrue(ConferencingApps.isBrowserBundleID("company.thebrowser.Browser"))  // Arc
        XCTAssertTrue(ConferencingApps.isBrowserBundleID("com.apple.WebKit.GPU"))
        // Not browsers.
        XCTAssertFalse(ConferencingApps.isBrowserBundleID("com.omi.omi-mtg-sysaudio"))
        XCTAssertFalse(ConferencingApps.isBrowserBundleID("us.zoom.xos"))
    }
}

// MARK: - MeetingDetector hysteresis

@MainActor
final class MeetingDetectorTests: XCTestCase {

    // Test-controlled clock; hysteresis is driven directly via applyDetected(_:) (no timers/probe).
    private var now = Date(timeIntervalSince1970: 1000)

    private func makeDetector(
        offGrace: TimeInterval = 8.0, onChange: @escaping (Bool) -> Void = { _ in }
    ) -> MeetingDetector {
        MeetingDetector(
            pollInterval: 4.0,
            offGracePeriod: offGrace,
            now: { [weak self] in self?.now ?? Date(timeIntervalSince1970: 0) },
            onChange: onChange
        )
    }

    func testTurnsOnImmediatelyWhenMeetingDetected() {
        var changes = [Bool]()
        let detector = makeDetector(onChange: { changes.append($0) })

        detector.applyDetected(true)

        XCTAssertTrue(detector.isMeetingActive)
        XCTAssertEqual(changes, [true])
    }

    func testTurningOffRequiresSustainedGracePeriod() {
        var changes = [Bool]()
        let detector = makeDetector(offGrace: 8.0, onChange: { changes.append($0) })

        detector.applyDetected(true)  // -> on
        XCTAssertTrue(detector.isMeetingActive)

        // Meeting disappears: arms pending-off, does NOT flip immediately.
        detector.applyDetected(false)
        XCTAssertTrue(detector.isMeetingActive, "should stay active during grace period")

        // Still within the grace window.
        now = now.addingTimeInterval(5)
        detector.applyDetected(false)
        XCTAssertTrue(detector.isMeetingActive, "still within grace window")

        // Grace elapsed (5 + 4 = 9s > 8s).
        now = now.addingTimeInterval(4)
        detector.applyDetected(false)
        XCTAssertFalse(detector.isMeetingActive, "flips off after sustained grace period")
        XCTAssertEqual(changes, [true, false])
    }

    func testMeetingReappearingDuringGraceCancelsTurnOff() {
        var changes = [Bool]()
        let detector = makeDetector(offGrace: 8.0, onChange: { changes.append($0) })

        detector.applyDetected(true)  // -> on
        detector.applyDetected(false)  // arm pending-off
        now = now.addingTimeInterval(5)
        detector.applyDetected(true)  // reappears within grace -> cancels pending-off
        now = now.addingTimeInterval(20)
        detector.applyDetected(true)  // long after the original deadline; should still be active

        XCTAssertTrue(detector.isMeetingActive)
        XCTAssertEqual(changes, [true], "no spurious off edge")
    }

    func testNoChangeEmittedWhileStableInactive() {
        var changes = [Bool]()
        let detector = makeDetector(onChange: { changes.append($0) })

        detector.applyDetected(false)
        now = now.addingTimeInterval(100)
        detector.applyDetected(false)

        XCTAssertFalse(detector.isMeetingActive)
        XCTAssertEqual(changes, [], "no edges while never in a meeting")
    }

    func testStickyBrowserCallStaysActiveWhileMutedThenEndsWhenAudioStops() {
        var changes = [Bool]()
        let detector = makeDetector(offGrace: 8.0, onChange: { changes.append($0) })

        // In a browser call (browser is using the mic).
        detector.applySignal(.init(inCall: true, browserInvolved: true, browserAudioOutput: true))
        XCTAssertTrue(detector.isMeetingActive)

        // User mutes: mic input drops (inCall=false) but the browser still plays the call's audio.
        detector.applySignal(.init(inCall: false, browserInvolved: false, browserAudioOutput: true))
        now = now.addingTimeInterval(30)
        detector.applySignal(.init(inCall: false, browserInvolved: false, browserAudioOutput: true))
        XCTAssertTrue(detector.isMeetingActive, "muted browser call stays active while audio plays")

        // Call ends: browser stops playing audio → flips off after the grace period.
        detector.applySignal(.none)
        now = now.addingTimeInterval(9)
        detector.applySignal(.none)
        XCTAssertFalse(detector.isMeetingActive)
        XCTAssertEqual(changes, [true, false])
    }
}

// MARK: - AssistantSettings.systemAudioCaptureMode

@MainActor
final class SystemAudioCaptureModeSettingsTests: XCTestCase {
    private let key = "systemAudioCaptureMode"

    override func setUp() {
        super.setUp()
        UserDefaults.standard.removeObject(forKey: key)
    }

    override func tearDown() {
        UserDefaults.standard.removeObject(forKey: key)
        super.tearDown()
    }

    func testDefaultsToAlways() {
        XCTAssertEqual(AssistantSettings.shared.systemAudioCaptureMode, .always)
    }

    func testPersistsAndReadsBack() {
        AssistantSettings.shared.systemAudioCaptureMode = .onlyDuringMeetings
        XCTAssertEqual(UserDefaults.standard.string(forKey: key), "onlyDuringMeetings")
        XCTAssertEqual(AssistantSettings.shared.systemAudioCaptureMode, .onlyDuringMeetings)

        AssistantSettings.shared.systemAudioCaptureMode = .never
        XCTAssertEqual(AssistantSettings.shared.systemAudioCaptureMode, .never)
    }

    func testUnknownRawValueFallsBackToDefault() {
        UserDefaults.standard.set("garbage", forKey: key)
        XCTAssertEqual(AssistantSettings.shared.systemAudioCaptureMode, .always)
    }
}
