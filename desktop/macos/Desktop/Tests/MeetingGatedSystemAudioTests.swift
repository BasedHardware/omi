import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only test seams; the release-mode
  // notification regression step must compile the bundle without them.

  private final class Box<T>: @unchecked Sendable {
    var value: T
    init(_ v: T) { self.value = v }
  }

  // MARK: - ConferencingApps

  final class ConferencingAppsTests: XCTestCase {

    func testNativeCallAppMatchesOnOwnerNameAlone() {
      XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "zoom.us", title: nil))
      XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "Microsoft Teams", title: "anything"))
      XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "FaceTime", title: nil))
      XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "Webex", title: nil))
    }

    func testChatAppCallMatchesOnOwnerName() {
      // Discord voice, Slack huddles, and WhatsApp calls are meetings, same as Teams:
      // the owner name alone marks the app's windows as call windows (no title /
      // Screen Recording permission needed). Meeting gating stays mic-in-use based
      // (`callAppIsUsingMicrophone`), so this does not make idle chat a meeting.
      XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "Discord", title: nil))
      XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "Slack", title: "#general | Acme"))
      XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "WhatsApp", title: nil))
      XCTAssertTrue(ConferencingApps.isCallWindow(ownerName: "Telegram", title: nil))
      XCTAssertTrue(ConferencingApps.isMessagingCallApp(appName: "Telegram"))
      XCTAssertTrue(ConferencingApps.isMessagingCallApp(appName: "discord"))
      XCTAssertFalse(ConferencingApps.isMessagingCallApp(appName: "Google Chrome"))
    }

    /// A *joined* Google Meet tab is titled with the bare meeting code and contains none of
    /// `browserCallKeywords`. `browserCallWindowPresent()` used to run the keyword loop inline
    /// instead of calling `isBrowserCallTitle`, so the one title shape a live call actually
    /// carries was the one it missed — on macOS 14.0-14.3 that is the only detection path, and
    /// on 14.4+ it is the path a muted browser call falls back to.
    func testJoinedMeetCodeTitleCountsAsABrowserCall() {
      XCTAssertTrue(ConferencingApps.isBrowserCallTitle("Meet - amc-iajq-asx"))
      XCTAssertTrue(ConferencingApps.isBrowserCallTitle("Meet – amc-iajq-asx"))  // en dash
      XCTAssertFalse(ConferencingApps.isBrowserCallTitle("Meet - notacode"))
      XCTAssertFalse(ConferencingApps.isBrowserCallTitle("Meeting notes - Acme"))

      // The keyword shapes must keep matching: this replaced an inline keyword loop.
      XCTAssertTrue(ConferencingApps.isBrowserCallTitle("Google Meet — Standup"))
      XCTAssertTrue(ConferencingApps.isBrowserCallTitle("https://meet.google.com/abc-defg"))
      XCTAssertTrue(ConferencingApps.isBrowserCallTitle("Teams - Microsoft Teams"))
      XCTAssertFalse(ConferencingApps.isBrowserCallTitle("GitHub - omi"))
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
      XCTAssertTrue(ConferencingApps.isNativeCallApp(bundleID: "com.tdesktop.Telegram"))
      XCTAssertTrue(ConferencingApps.isNativeCallApp(bundleID: "ru.keepcoder.telegram"))
      // Omi itself (which is always using the mic while recording) must not count as a meeting.
      XCTAssertFalse(ConferencingApps.isNativeCallApp(bundleID: "com.omi.omi-mtg-sysaudio"))
      XCTAssertFalse(ConferencingApps.isNativeCallApp(bundleID: "com.google.Chrome"))
    }

    func testChatAppBundleIDsAreNativeCallApps() {
      // Verified macOS bundle IDs (Homebrew cask quit targets for the current apps):
      // Discord com.hnc.Discord, Slack com.tinyspeck.slackmacgap, WhatsApp
      // net.whatsapp.WhatsApp. Their calls hold the mic, so mic-in-use detection
      // fires while in a Discord voice channel, Slack huddle, or WhatsApp call.
      XCTAssertTrue(ConferencingApps.isNativeCallApp(bundleID: "com.hnc.Discord"))
      XCTAssertTrue(ConferencingApps.isNativeCallApp(bundleID: "com.hnc.discord"))  // case-insensitive
      XCTAssertTrue(ConferencingApps.isNativeCallApp(bundleID: "com.tinyspeck.slackmacgap"))
      XCTAssertTrue(ConferencingApps.isNativeCallApp(bundleID: "net.whatsapp.WhatsApp"))
      // Omi itself and browsers are not native call apps (browser calls are matched
      // separately by browserBundleIDPrefixes inside callAppIsUsingMicrophone).
      XCTAssertFalse(ConferencingApps.isNativeCallApp(bundleID: "com.omi.omi-mtg-sysaudio"))
      XCTAssertFalse(ConferencingApps.isNativeCallApp(bundleID: "com.google.Chrome"))
    }

    // Regression: issue #10143 — Omi's periodic capture stopped an active screen share.
    // These signatures gate the capture pause; a match means "user is presenting now".
    func testShareIndicatorMatchesKnownPresentingWindows() {
      // Zoom floating share controls (internal window names, present only while sharing).
      XCTAssertTrue(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "zoom.us", title: "zoom share statusbar window"))
      XCTAssertTrue(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "zoom.us", title: "zoom share toolbar window"))
      // Teams presenting toolbar.
      XCTAssertTrue(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "Microsoft Teams", title: "Screen sharing toolbar"))
      XCTAssertTrue(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "MSTeams", title: "Screen sharing toolbar"))
      // Browser (Meet / Teams web) stop-sharing bubble.
      XCTAssertTrue(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "Google Chrome", title: "meet.google.com is sharing your screen."))
      XCTAssertTrue(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "Arc", title: "teams.microsoft.com is sharing a window."))
    }

    func testShareIndicatorIgnoresOrdinaryCallAndAppWindows() {
      // In a Zoom call but NOT sharing: main meeting window must not pause capture.
      XCTAssertFalse(
        ConferencingApps.isShareIndicatorWindow(ownerName: "zoom.us", title: "Zoom Meeting"))
      XCTAssertFalse(
        ConferencingApps.isShareIndicatorWindow(ownerName: "Microsoft Teams", title: "Standup | Microsoft Teams"))
      // A Teams chat about screen sharing is not the presenting toolbar.
      XCTAssertFalse(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "Microsoft Teams", title: "Screen sharing issues | Microsoft Teams"))
      // Ordinary browser tab, even one talking about screen sharing.
      XCTAssertFalse(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "Google Chrome", title: "How to stop sharing your screen - Google Meet Help"))
      // Non-conferencing app can never be a share indicator, whatever the title says.
      XCTAssertFalse(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "Finder", title: "zoom share statusbar window"))
      XCTAssertFalse(ConferencingApps.isShareIndicatorWindow(ownerName: "zoom.us", title: nil))
      XCTAssertFalse(ConferencingApps.isShareIndicatorWindow(ownerName: nil, title: "zoom share"))
      XCTAssertFalse(ConferencingApps.isShareIndicatorWindow(ownerName: "zoom.us", title: ""))
    }

    func testChatAppOrdinaryWindowsAreNotShareIndicators() {
      // Ordinary Slack/Discord/WhatsApp chat windows are not presenting-toolbars;
      // only the Zoom/Teams/browser share signatures may pause capture (#10143).
      XCTAssertFalse(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "Slack", title: "#general | Acme Workspace"))
      XCTAssertFalse(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "Discord", title: "#general | Discord"))
      XCTAssertFalse(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "WhatsApp", title: "Chats"))
      // Even a chat about sharing in one of these apps is not the toolbar itself.
      XCTAssertFalse(
        ConferencingApps.isShareIndicatorWindow(
          ownerName: "Slack", title: "Screen sharing toolbar"))
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
      let probeCount = Box(0)
      var changes = [Bool]()
      var initialObservedCount = 0
      let detector = MeetingDetector(
        pollInterval: 60.0,
        offGracePeriod: 8.0,
        isMeetingNow: {
          probeLock.lock()
          probeCount.value += 1
          let probeIndex = probeCount.value
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

  // MARK: - AssistantSettings.audioRecordingMode

  @MainActor
  final class AudioRecordingModeSettingsTests: XCTestCase {
    private let key = AssistantSettings.audioRecordingModeDefaultsKey

    override func setUp() {
      super.setUp()
      UserDefaults.standard.removeObject(forKey: key)
    }

    override func tearDown() {
      UserDefaults.standard.removeObject(forKey: key)
      super.tearDown()
    }

    func testDefaultsToOnlyDuringMeetings() {
      XCTAssertEqual(AssistantSettings.shared.audioRecordingMode, .onlyMeetings)
    }

    func testPersistsAndReadsBack() {
      AssistantSettings.shared.audioRecordingMode = .onlyMeetings
      XCTAssertEqual(UserDefaults.standard.string(forKey: key), "onlyMeetings")
      XCTAssertEqual(AssistantSettings.shared.audioRecordingMode, .onlyMeetings)

      AssistantSettings.shared.audioRecordingMode = .off
      XCTAssertEqual(AssistantSettings.shared.audioRecordingMode, .off)
    }

    func testUnknownRawValueFallsBackToDefault() {
      UserDefaults.standard.set("garbage", forKey: key)
      XCTAssertEqual(AssistantSettings.shared.audioRecordingMode, .onlyMeetings)
    }

    func testLegacySettingsCollapseIntoOneMode() {
      XCTAssertEqual(
        AssistantSettings.migratedAudioRecordingMode(
          legacyTranscriptionEnabled: false,
          legacySystemAudioModeRaw: "always"),
        .off)
      XCTAssertEqual(
        AssistantSettings.migratedAudioRecordingMode(
          legacyTranscriptionEnabled: true,
          legacySystemAudioModeRaw: "onlyDuringMeetings"),
        .onlyMeetings)
      XCTAssertEqual(
        AssistantSettings.migratedAudioRecordingMode(
          legacyTranscriptionEnabled: true,
          legacySystemAudioModeRaw: "always"),
        .always)
      XCTAssertEqual(
        AssistantSettings.migratedAudioRecordingMode(
          legacyTranscriptionEnabled: true,
          legacySystemAudioModeRaw: "never"),
        .always,
        "Legacy mic-only users should remain recording rather than become Off")
    }
  }

  // MARK: - Meeting conversation boundary

  final class MeetingConversationBoundaryPolicyTests: XCTestCase {

    func testAmbientToMeetingClosesAmbientConversation() {
      XCTAssertEqual(
        MeetingConversationBoundaryPolicy.transition(previousRole: .ambient, meetingActive: true),
        .init(nextRole: .meeting, finalizationReason: .meetingStarted)
      )
    }

    func testMeetingToAmbientClosesMeetingConversation() {
      XCTAssertEqual(
        MeetingConversationBoundaryPolicy.transition(previousRole: .meeting, meetingActive: false),
        .init(nextRole: .ambient, finalizationReason: .meetingEnded)
      )
    }

    func testStableAmbientDoesNotRotate() {
      XCTAssertNil(
        MeetingConversationBoundaryPolicy.transition(previousRole: .ambient, meetingActive: false)
      )
    }

    func testStableMeetingDoesNotRotate() {
      XCTAssertNil(
        MeetingConversationBoundaryPolicy.transition(previousRole: .meeting, meetingActive: true)
      )
    }

    func testFailedRotationDoesNotCommitTheDetectedRole() throws {
      let transition = try XCTUnwrap(
        MeetingConversationBoundaryPolicy.transition(previousRole: .ambient, meetingActive: true)
      )
      XCTAssertEqual(
        MeetingConversationBoundaryPolicy.committedRole(
          previousRole: .ambient, transition: transition, rotationSucceeded: false),
        .ambient
      )
      XCTAssertEqual(
        MeetingConversationBoundaryPolicy.committedRole(
          previousRole: .ambient, transition: transition, rotationSucceeded: true),
        .meeting
      )
    }

    func testMeetingGateClosingWithSegmentsFinishesConversation() {
      XCTAssertTrue(
        MeetingConversationBoundaryPolicy.shouldFinishConversation(
          mode: .onlyMeetings,
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
          mode: .onlyMeetings,
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
          mode: .onlyMeetings,
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
          mode: .off,
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
          mode: .onlyMeetings,
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
          mode: .onlyMeetings,
          meetingStateReady: false,
          shouldCapture: false,
          segmentCount: 12,
          hasSpeakerSegments: true
        )
      )
    }
  }
#endif
