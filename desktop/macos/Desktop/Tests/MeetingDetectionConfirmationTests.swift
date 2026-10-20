import XCTest

@testable import Omi_Computer

@MainActor
final class MeetingDetectionConfirmationTests: XCTestCase {
  private var now = Date(timeIntervalSince1970: 1000)
  private let suiteName = "MeetingDetectionConfirmationTests.\(UUID().uuidString)"

  private func shot(
    _ bundle: String = "com.google.chrome.helper", input: Bool = true, output: Bool = false,
    title: String? = nil, windowBundle: String = "com.google.chrome", readable: Bool = true
  ) -> CallAudioSnapshot {
    CallAudioSnapshot(
      processes: [.init(bundleID: bundle, pid: 1, isRunningInput: input, isRunningOutput: output)],
      defaultInputDeviceID: 1,
      browserWindows: title.map { [.init(bundleID: windowBundle, title: $0)] } ?? [],
      browserTitlesReadable: readable)
  }

  private func detected(_ snapshot: CallAudioSnapshot, mode: AssistantSettings.AudioRecordingMode = .onlyMeetings)
    -> Bool
  {
    MeetingCallObservation.isDetected(snapshot: snapshot, mode: mode, processInputAPIAvailable: true)
  }

  func testBrowserSTTMicrophoneDoesNotDetectMeeting() {
    for mode in [AssistantSettings.AudioRecordingMode.always, .onlyMeetings] {
      XCTAssertFalse(detected(shot(title: "Whisper transcription"), mode: mode))
      XCTAssertFalse(detected(shot(title: "Voice chat"), mode: mode))
      XCTAssertFalse(detected(shot(), mode: mode), "readable empty titles must not fail open")
    }
  }

  func testParkedMeetNeedsAudioFromTheSameBrowser() {
    XCTAssertFalse(detected(shot(input: false, title: "Meet - abc-defg-hij")))
    XCTAssertFalse(detected(shot(title: "Meet - abc-defg-hij", windowBundle: "com.apple.safari")))
    XCTAssertTrue(detected(shot(input: false, output: true, title: "Meet - abc-defg-hij")))
    XCTAssertFalse(detected(shot(input: false, output: true, title: "Meet - abc-defg-hij"), mode: .always))
  }

  func testNoScreenRecordingPermissionRetainsBrowserMicrophoneDetection() {
    XCTAssertTrue(detected(shot(readable: false)))
    XCTAssertFalse(detected(shot(input: false, readable: false)))
    XCTAssertTrue(
      detected(shot("com.apple.WebKit.GPU", title: "Meet - abc-defg-hij", windowBundle: "com.apple.Safari")))
  }

  func testTelegramVoiceNoteAndOtherMessagingInputOnlyAreNotMeetings() {
    for bundle in [
      "com.tdesktop.telegram", "ru.keepcoder.telegram", "com.hnc.discord.helper.renderer",
      "com.tinyspeck.slackmacgap", "net.whatsapp.whatsapp",
    ] {
      XCTAssertFalse(detected(shot(bundle)))
      XCTAssertTrue(detected(shot(bundle, output: true)))
    }
  }

  func testMessagingOutputMayBelongToAnotherHelperButNotAnotherApp() {
    var snapshot = shot("com.hnc.discord.helper.renderer")
    snapshot.processes.append(
      .init(bundleID: "com.hnc.discord.helper", pid: 2, isRunningInput: false, isRunningOutput: true))
    XCTAssertTrue(detected(snapshot))
    snapshot.processes[1].bundleID = "com.apple.Music"
    XCTAssertFalse(detected(snapshot))
  }

  private func detector(
    mode: AssistantSettings.AudioRecordingMode = .onlyMeetings,
    onConfirmed: @escaping (Bool) -> Void = { _ in },
    notice: @escaping () -> Void = {},
    evidence: @escaping (MeetingDetectionEvidence) -> Void = { _ in }
  ) throws -> MeetingDetector {
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    return MeetingDetector(
      mode: mode, processInputAPIAvailable: true,
      now: { [unowned self] in now }, audioLedgerDefaults: defaults,
      onChange: { _ in }, onConfirmedChange: onConfirmed,
      onNoteTakingNoticeReady: notice, onConfirmedEvidence: evidence)
  }

  func testShortBlipOpensCaptureWithoutRotatingOrAnnouncing() throws {
    defer { UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName) }
    var edges = [Bool]()
    var notices = 0
    let detector = try detector(onConfirmed: { edges.append($0) }, notice: { notices += 1 })
    detector.applySnapshot(shot("us.zoom.xos"))
    XCTAssertTrue(detector.isMeetingActive, "Only Meetings capture starts on provisional evidence")
    XCTAssertFalse(detector.isMeetingConfirmed)
    now += 9
    detector.applySnapshot(shot("us.zoom.xos", input: false))
    now += 9
    detector.applySnapshot(shot("us.zoom.xos", input: false))
    XCTAssertFalse(detector.isMeetingActive)
    XCTAssertEqual(edges, [])
    XCTAssertEqual(notices, 0)
    XCTAssertNil(
      MeetingConversationBoundaryPolicy.transition(previousRole: .ambient, meetingActive: detector.isMeetingConfirmed))
  }

  func testNegativeSampleRestartsSustainedConfirmationDespiteCaptureGrace() throws {
    defer { UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName) }
    let detector = try detector()
    detector.applyDetected(true)
    now += 9
    detector.applyDetected(false)
    now += 1
    detector.applyDetected(true)
    now += 9
    detector.applyDetected(true)
    XCTAssertFalse(detector.isMeetingConfirmed)
    now += 1
    detector.applyDetected(true)
    XCTAssertTrue(detector.isMeetingConfirmed)
  }

  func testRealZoomMeetTeamsFaceTimeCaptureRotationAndNoticeInBothModes() throws {
    defer { UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName) }
    for mode in [AssistantSettings.AudioRecordingMode.always, .onlyMeetings] {
      for snapshot in [
        shot("us.zoom.xos"), shot("com.microsoft.teams2"), shot("com.apple.facetime"),
        shot(title: "Meet - abc-defg-hij"),
      ] {
        var role = TranscriptionConversationRole.ambient
        var transitions = [MeetingConversationBoundaryPolicy.Transition]()
        var notices = 0
        var telemetry = [MeetingDetectionEvidence]()
        let detector = try detector(
          mode: mode,
          onConfirmed: { active in
            if let transition = MeetingConversationBoundaryPolicy.transition(previousRole: role, meetingActive: active)
            {
              transitions.append(transition)
              role = MeetingConversationBoundaryPolicy.committedRole(
                previousRole: role, transition: transition, rotationSucceeded: true)
            }
          }, notice: { notices += 1 }, evidence: { telemetry.append($0) })
        detector.applySnapshot(snapshot)
        XCTAssertTrue(detector.isMeetingActive)
        XCTAssertEqual(role, .ambient)
        now += 10
        detector.applySnapshot(snapshot)
        XCTAssertEqual(role, .meeting)
        XCTAssertEqual(transitions.map(\.finalizationReason), [.meetingStarted])
        XCTAssertEqual(telemetry.count, 1)
        detector.requestNoteTakingNotice()  // successful committed rotation
        XCTAssertEqual(notices, 0)
        now += 35
        detector.applySnapshot(snapshot)
        detector.applySnapshot(snapshot)
        XCTAssertEqual(notices, 1)
        detector.applyDetected(false)
        now += 8
        detector.applyDetected(false)
        XCTAssertFalse(detector.isMeetingActive)
        XCTAssertFalse(detector.isMeetingConfirmed)
        XCTAssertEqual(role, .ambient)
        XCTAssertEqual(transitions.map(\.finalizationReason), [.meetingStarted, .meetingEnded])
      }
    }
  }

  func testShortConfirmedMeetingNeverPostsNoticeEvenDuringOffGrace() throws {
    defer { UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName) }
    var notices = 0
    let detector = try detector(notice: { notices += 1 })
    detector.applyDetected(true)
    now += 10
    detector.applyDetected(true)
    detector.requestNoteTakingNotice()
    now += 34
    detector.applyDetected(false)
    now += 2
    detector.applyDetected(false)  // notice deadline elapsed inside the off grace
    XCTAssertEqual(notices, 0)
    now += 6
    detector.applyDetected(false)
    detector.requestNoteTakingNotice()  // late rotation completion cannot resurrect a notice
    XCTAssertEqual(notices, 0)
  }

  func testUncommittedRotationNeverPostsNotice() throws {
    defer { UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName) }
    var notices = 0
    let detector = try detector(notice: { notices += 1 })
    detector.applyDetected(true)
    now += 10
    detector.applyDetected(true)
    now += 50
    detector.applyDetected(true)
    XCTAssertEqual(notices, 0)
  }

  func testCallReplacementRestartsNoticeDelayAndStillRotates() throws {
    defer { UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName) }
    var notices = 0
    var changes = 0
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    let detector = MeetingDetector(
      now: { [unowned self] in now }, audioLedgerDefaults: defaults,
      onCallChanged: { changes += 1 }, onChange: { _ in },
      onNoteTakingNoticeReady: { notices += 1 })
    detector.applyDetected(true, callIDs: ["meet:aaa-bbbb-ccc"])
    now += 10
    detector.applyDetected(true, callIDs: ["meet:aaa-bbbb-ccc"])
    detector.requestNoteTakingNotice()
    now += 20
    detector.applyDetected(true, callIDs: ["meet:ddd-eeee-fff"])
    now += 8
    detector.applyDetected(true, callIDs: ["meet:ddd-eeee-fff"])
    XCTAssertEqual(changes, 1)
    detector.requestNoteTakingNotice()
    now += 7  // original call's notice deadline; replacement call is still short
    detector.applyDetected(true, callIDs: ["meet:ddd-eeee-fff"])
    XCTAssertEqual(notices, 0)
    now += 28
    detector.applyDetected(true, callIDs: ["meet:ddd-eeee-fff"])
    XCTAssertEqual(notices, 1)
  }

  func testGapBeforeConfirmationDoesNotMakeAnOverlappingCallAReplacement() throws {
    defer { UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName) }
    var changes = 0
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    let detector = MeetingDetector(
      now: { [unowned self] in now }, audioLedgerDefaults: defaults,
      onCallChanged: { changes += 1 }, onChange: { _ in })
    detector.applyDetected(true, callIDs: ["meet:aaa-bbbb-ccc"])
    now += 9
    detector.applyDetected(false)
    now += 1
    detector.applyDetected(true, callIDs: ["meet:aaa-bbbb-ccc"])
    now += 10
    detector.applyDetected(true, callIDs: ["meet:aaa-bbbb-ccc"])
    now += 1
    detector.applyDetected(true, callIDs: ["meet:aaa-bbbb-ccc", "meet:ddd-eeee-fff"])
    now += 8
    detector.applyDetected(true, callIDs: ["meet:aaa-bbbb-ccc", "meet:ddd-eeee-fff"])
    XCTAssertEqual(changes, 0)
  }

  func testInitialProvisionalProbeDoesNotRotateAnExistingMeetingDuringModeChange() throws {
    defer { UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName) }
    let detector = try detector()
    detector.applyDetected(true)
    XCTAssertNil(
      MeetingConversationBoundaryPolicy.initialObservation(
        captureActive: detector.isMeetingActive, meetingConfirmed: detector.isMeetingConfirmed))
    now += 10
    detector.applyDetected(true)
    let confirmed = MeetingConversationBoundaryPolicy.initialObservation(
      captureActive: detector.isMeetingActive, meetingConfirmed: detector.isMeetingConfirmed)
    XCTAssertEqual(confirmed, true)
    if let confirmed {
      XCTAssertNil(MeetingConversationBoundaryPolicy.transition(previousRole: .meeting, meetingActive: confirmed))
    }
    XCTAssertEqual(
      MeetingConversationBoundaryPolicy.initialObservation(captureActive: false, meetingConfirmed: false), false)
  }

  func testUnconfirmedCapturedSpeechDoesNotRotateWhenGateCloses() {
    for (count, speakers) in [(1, false), (0, true)] {
      XCTAssertFalse(
        MeetingConversationBoundaryPolicy.shouldFinishConversation(
          mode: .onlyMeetings, meetingStateReady: true, shouldCapture: false,
          segmentCount: count, conversationRole: .ambient, hasSpeakerSegments: speakers))
      XCTAssertTrue(
        MeetingConversationBoundaryPolicy.shouldFinishConversation(
          mode: .onlyMeetings, meetingStateReady: true, shouldCapture: false,
          segmentCount: count, conversationRole: .meeting, hasSpeakerSegments: speakers))
    }
  }

  func testConfirmationTelemetryHasOnlyBoundedEvidence() {
    let evidence = MeetingDetectionEvidence(
      snapshot: shot(title: "Meet - abc-defg-hij private title"), mode: .onlyMeetings, processInputAPIAvailable: true)
    XCTAssertEqual(evidence.bundleIDs, ["com.google.chrome"])
    XCTAssertTrue(evidence.titleMatched)
    XCTAssertEqual(
      Set(evidence.properties.keys),
      [
        "platform", "bundle_ids", "browser_title_matched", "browser_titles_readable", "process_input_api_available",
        "recording_mode", "confirmation_seconds",
      ])
    XCTAssertFalse(String(describing: evidence.properties).contains("abc-defg-hij"))
  }
}
