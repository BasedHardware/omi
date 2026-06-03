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
}

// MARK: - MeetingDetector hysteresis

@MainActor
final class MeetingDetectorTests: XCTestCase {

    // Injected, test-controlled meeting probe + clock (no timers/observers — evaluate() is driven directly).
    private var meetingNow = false
    private var now = Date(timeIntervalSince1970: 1000)

    private func makeDetector(
        offGrace: TimeInterval = 8.0, onChange: @escaping (Bool) -> Void = { _ in }
    ) -> MeetingDetector {
        MeetingDetector(
            pollInterval: 4.0,
            offGracePeriod: offGrace,
            isMeetingNow: { [weak self] in self?.meetingNow ?? false },
            now: { [weak self] in self?.now ?? Date(timeIntervalSince1970: 0) },
            onChange: onChange
        )
    }

    func testTurnsOnImmediatelyWhenMeetingDetected() {
        var changes = [Bool]()
        let detector = makeDetector(onChange: { changes.append($0) })

        meetingNow = true
        detector.evaluate()

        XCTAssertTrue(detector.isMeetingActive)
        XCTAssertEqual(changes, [true])
    }

    func testTurningOffRequiresSustainedGracePeriod() {
        var changes = [Bool]()
        let detector = makeDetector(offGrace: 8.0, onChange: { changes.append($0) })

        meetingNow = true
        detector.evaluate()  // -> on
        XCTAssertTrue(detector.isMeetingActive)

        // Meeting disappears: arms pending-off, does NOT flip immediately.
        meetingNow = false
        detector.evaluate()
        XCTAssertTrue(detector.isMeetingActive, "should stay active during grace period")

        // Still within the grace window.
        now = now.addingTimeInterval(5)
        detector.evaluate()
        XCTAssertTrue(detector.isMeetingActive, "still within grace window")

        // Grace elapsed (5 + 4 = 9s > 8s).
        now = now.addingTimeInterval(4)
        detector.evaluate()
        XCTAssertFalse(detector.isMeetingActive, "flips off after sustained grace period")
        XCTAssertEqual(changes, [true, false])
    }

    func testMeetingReappearingDuringGraceCancelsTurnOff() {
        var changes = [Bool]()
        let detector = makeDetector(offGrace: 8.0, onChange: { changes.append($0) })

        meetingNow = true
        detector.evaluate()  // -> on

        meetingNow = false
        detector.evaluate()  // arm pending-off
        now = now.addingTimeInterval(5)

        meetingNow = true
        detector.evaluate()  // reappears within grace -> cancels pending-off

        now = now.addingTimeInterval(20)
        detector.evaluate()  // long after the original deadline; should still be active
        XCTAssertTrue(detector.isMeetingActive)
        XCTAssertEqual(changes, [true], "no spurious off edge")
    }

    func testNoChangeEmittedWhileStableInactive() {
        var changes = [Bool]()
        let detector = makeDetector(onChange: { changes.append($0) })

        meetingNow = false
        detector.evaluate()
        now = now.addingTimeInterval(100)
        detector.evaluate()

        XCTAssertFalse(detector.isMeetingActive)
        XCTAssertEqual(changes, [], "no edges while never in a meeting")
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
