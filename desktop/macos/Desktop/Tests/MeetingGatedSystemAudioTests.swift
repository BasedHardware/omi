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

        XCTAssertFalse(detector.hasObservedState)
        detector.applyDetected(true)

        XCTAssertTrue(detector.hasObservedState)
        XCTAssertTrue(detector.isMeetingActive)
        XCTAssertEqual(changes, [true])
    }

    func testInitialInactiveProbeMarksStateObservedWithoutMeetingChange() {
        var initialObservedCount = 0
        var changes = [Bool]()
        let detector = MeetingDetector(
            pollInterval: 4.0,
            offGracePeriod: 8.0,
            now: { [weak self] in self?.now ?? Date(timeIntervalSince1970: 0) },
            onInitialStateObserved: { initialObservedCount += 1 },
            onChange: { changes.append($0) }
        )

        detector.applyDetected(false)
        detector.applyDetected(false)

        XCTAssertTrue(detector.hasObservedState)
        XCTAssertFalse(detector.isMeetingActive)
        XCTAssertEqual(initialObservedCount, 1)
        XCTAssertEqual(changes, [], "initial inactive readiness is not a meeting state change")
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

    func testStopDiscardsInFlightProbeResult() async {
        let probeStarted = DispatchSemaphore(value: 0)
        let releaseProbe = DispatchSemaphore(value: 0)
        let unexpectedInitialObservation = DispatchSemaphore(value: 0)
        let unexpectedChange = DispatchSemaphore(value: 0)
        var changes = [Bool]()
        var initialObservedCount = 0
        let detector = MeetingDetector(
            pollInterval: 60.0,
            offGracePeriod: 8.0,
            isMeetingNow: {
                probeStarted.signal()
                _ = releaseProbe.wait(timeout: .now() + 2)
                return true
            },
            now: { [weak self] in self?.now ?? Date(timeIntervalSince1970: 0) },
            onInitialStateObserved: {
                initialObservedCount += 1
                unexpectedInitialObservation.signal()
            },
            onChange: {
                changes.append($0)
                unexpectedChange.signal()
            }
        )

        detector.start()
        XCTAssertEqual(probeStarted.wait(timeout: .now() + 2), .success)
        detector.stop()
        releaseProbe.signal()
        await Task.yield()

        XCTAssertFalse(detector.hasObservedState)
        XCTAssertFalse(detector.isMeetingActive)
        XCTAssertEqual(initialObservedCount, 0)
        XCTAssertEqual(changes, [])
        XCTAssertEqual(unexpectedInitialObservation.wait(timeout: .now()), .timedOut)
        XCTAssertEqual(unexpectedChange.wait(timeout: .now()), .timedOut)
    }

    func testNewerProbeWinsWhenCanceledProbeFinishesLater() async {
        let firstProbeStarted = DispatchSemaphore(value: 0)
        let secondProbeStarted = DispatchSemaphore(value: 0)
        let releaseFirstProbe = DispatchSemaphore(value: 0)
        let releaseSecondProbe = DispatchSemaphore(value: 0)
        let unexpectedChange = DispatchSemaphore(value: 0)
        let probeLock = NSLock()
        var probeCount = 0
        var changes = [Bool]()
        var initialObservedCount = 0
        let detector = MeetingDetector(
            pollInterval: 60.0,
            offGracePeriod: 8.0,
            isMeetingNow: {
                probeLock.lock()
                probeCount += 1
                let probeIndex = probeCount
                probeLock.unlock()

                if probeIndex == 1 {
                    firstProbeStarted.signal()
                    _ = releaseFirstProbe.wait(timeout: .now() + 2)
                    return true
                }

                secondProbeStarted.signal()
                _ = releaseSecondProbe.wait(timeout: .now() + 2)
                return false
            },
            now: { [weak self] in self?.now ?? Date(timeIntervalSince1970: 0) },
            onInitialStateObserved: { initialObservedCount += 1 },
            onChange: {
                changes.append($0)
                unexpectedChange.signal()
            }
        )

        detector.start()
        defer { detector.stop() }
        XCTAssertEqual(firstProbeStarted.wait(timeout: .now() + 2), .success)
        guard let firstProbeTask = detector.currentProbeTaskForTesting else {
            return XCTFail("initial probe task was not installed")
        }

        guard let secondProbeTask = detector.triggerProbeForTesting() else {
            return XCTFail("replacement probe task was not installed")
        }
        XCTAssertEqual(secondProbeStarted.wait(timeout: .now() + 2), .success)

        releaseSecondProbe.signal()
        await secondProbeTask.value
        XCTAssertTrue(detector.hasObservedState)
        XCTAssertFalse(detector.isMeetingActive)
        XCTAssertEqual(initialObservedCount, 1)

        releaseFirstProbe.signal()
        await firstProbeTask.value
        XCTAssertFalse(detector.isMeetingActive, "the canceled older probe must not overwrite the newer result")
        XCTAssertEqual(changes, [])
        XCTAssertEqual(unexpectedChange.wait(timeout: .now()), .timedOut)
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

    func testDefaultsToOnlyDuringMeetings() {
        XCTAssertEqual(AssistantSettings.shared.systemAudioCaptureMode, .onlyDuringMeetings)
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
        XCTAssertEqual(AssistantSettings.shared.systemAudioCaptureMode, .onlyDuringMeetings)
    }
}

// MARK: - Meeting conversation boundary

final class MeetingConversationBoundaryPolicyTests: XCTestCase {

    func testMeetingGateClosingWithSegmentsFinishesConversation() {
        XCTAssertTrue(
            MeetingConversationBoundaryPolicy.shouldFinishConversation(
                mode: .onlyDuringMeetings,
                meetingStateReady: true,
                shouldCapture: false,
                segmentCount: 12,
                hasSpeakerSegments: false
            )
        )
    }

    func testMeetingGateClosingWithOnlyInMemorySegmentsFinishesConversation() {
        XCTAssertTrue(
            MeetingConversationBoundaryPolicy.shouldFinishConversation(
                mode: .onlyDuringMeetings,
                meetingStateReady: true,
                shouldCapture: false,
                segmentCount: 0,
                hasSpeakerSegments: true
            )
        )
    }

    func testWaitingForFirstMeetingDoesNotFinishEmptySession() {
        XCTAssertFalse(
            MeetingConversationBoundaryPolicy.shouldFinishConversation(
                mode: .onlyDuringMeetings,
                meetingStateReady: true,
                shouldCapture: false,
                segmentCount: 0,
                hasSpeakerSegments: false
            )
        )
    }

    func testNonMeetingModesDoNotUseMeetingEndBoundary() {
        XCTAssertFalse(
            MeetingConversationBoundaryPolicy.shouldFinishConversation(
                mode: .always,
                meetingStateReady: true,
                shouldCapture: false,
                segmentCount: 12,
                hasSpeakerSegments: true
            )
        )
        XCTAssertFalse(
            MeetingConversationBoundaryPolicy.shouldFinishConversation(
                mode: .never,
                meetingStateReady: true,
                shouldCapture: false,
                segmentCount: 12,
                hasSpeakerSegments: true
            )
        )
    }

    func testActiveMeetingDoesNotFinishConversation() {
        XCTAssertFalse(
            MeetingConversationBoundaryPolicy.shouldFinishConversation(
                mode: .onlyDuringMeetings,
                meetingStateReady: true,
                shouldCapture: true,
                segmentCount: 12,
                hasSpeakerSegments: true
            )
        )
    }

    func testUnreadyMeetingStateDoesNotFinishExistingConversation() {
        XCTAssertFalse(
            MeetingConversationBoundaryPolicy.shouldFinishConversation(
                mode: .onlyDuringMeetings,
                meetingStateReady: false,
                shouldCapture: false,
                segmentCount: 12,
                hasSpeakerSegments: true
            )
        )
    }
}
