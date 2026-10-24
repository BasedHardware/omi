import XCTest

@testable import Omi_Computer

@MainActor
final class MeetingSessionResumeTests: XCTestCase {
  private var now = Date(timeIntervalSince1970: 1000)
  private var role = TranscriptionConversationRole.ambient
  private var transitions: [MeetingConversationBoundaryPolicy.Transition] = []
  private var captureEdges: [Bool] = []

  private func shot(_ bundle: String = "com.hnc.discord.helper.renderer", input: Bool = true, output: Bool = true)
    -> CallAudioSnapshot
  {
    CallAudioSnapshot(
      processes: [.init(bundleID: bundle, pid: 1, isRunningInput: input, isRunningOutput: output)],
      defaultInputDeviceID: 1, browserWindows: [])
  }

  private func detector(notice: @escaping () -> Void = {}) -> MeetingDetector {
    let name = "MeetingSessionResumeTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: name) else {
      preconditionFailure("Could not create isolated meeting test defaults")
    }
    addTeardownBlock { UserDefaults(suiteName: name)?.removePersistentDomain(forName: name) }
    return MeetingDetector(
      processInputAPIAvailable: true, now: { [unowned self] in now }, audioLedgerDefaults: defaults,
      onChange: { [unowned self] in captureEdges.append($0) },
      onConfirmedChange: { [unowned self] active in
        if let transition = MeetingConversationBoundaryPolicy.transition(previousRole: role, meetingActive: active) {
          transitions.append(transition)
          role = transition.nextRole
        }
      }, onNoteTakingNoticeReady: notice, onConfirmedEvidence: { _ in }, onAudioSummaries: { _ in })
  }

  private func confirm(_ detector: MeetingDetector, events: Set<String> = []) {
    detector.applySnapshot(shot(), calendarEventIDs: events)
    now += 10
    detector.applySnapshot(shot(), calendarEventIDs: events)
    XCTAssertEqual(role, .meeting)
  }

  private func loseEvidence(_ detector: MeetingDetector) -> Date {
    detector.applySnapshot(shot(input: false, output: false))
    now += 8
    detector.applySnapshot(shot(input: false, output: false))
    XCTAssertFalse(detector.isMeetingActive, "Only Meetings must close capture during the hold")
    XCTAssertTrue(detector.isMeetingConfirmed)
    XCTAssertEqual(role, .meeting)
    return now
  }

  func testConfirmedDiscordResumesAfter150SecondsWithoutAnAmbientSessionOrNewMeetingStart() {
    let detector = detector()
    confirm(detector)
    _ = loseEvidence(detector)
    now += 150
    detector.applySnapshot(shot())
    now += 10
    detector.applySnapshot(shot())
    XCTAssertTrue(detector.isMeetingActive)
    XCTAssertTrue(detector.isMeetingConfirmed)
    XCTAssertNil(detector.resumeOffAt)
    XCTAssertFalse(detector.hasPendingCallChange)
    XCTAssertEqual(role, .meeting)
    XCTAssertEqual(transitions.map(\.nextRole), [.meeting], "one meeting session and no ambient fragment")
    XCTAssertEqual(captureEdges, [true, false, true])
  }

  func testResumePresentsAnUndeliveredCommittedNoticeOnce() {
    var notices = 0
    let detector = detector(notice: { notices += 1 })
    confirm(detector)
    detector.requestNoteTakingNotice()
    now += 20
    _ = loseEvidence(detector)
    XCTAssertEqual(notices, 0)
    now += 150
    detector.applySnapshot(shot())
    XCTAssertEqual(notices, 1)
    now += 35
    detector.applySnapshot(shot())
    XCTAssertEqual(notices, 1)
    XCTAssertEqual(transitions.map(\.nextRole), [.meeting])
  }

  func testResumeDoesNotDuplicateAnAlreadyPresentedNotice() {
    var notices = 0
    let detector = detector(notice: { notices += 1 })
    confirm(detector)
    detector.requestNoteTakingNotice()
    now += 35
    detector.applySnapshot(shot())
    XCTAssertEqual(notices, 1)
    _ = loseEvidence(detector)
    detector.requestNoteTakingNotice()  // duplicate late boundary completion during the hold
    now += 150
    detector.applySnapshot(shot())
    detector.requestNoteTakingNotice()
    XCTAssertEqual(notices, 1)
  }

  func testBoundaryCommitDuringHoldQueuesTheNoticeUntilCaptureResumes() {
    var notices = 0
    let detector = detector(notice: { notices += 1 })
    confirm(detector)
    _ = loseEvidence(detector)
    now += 150
    detector.requestNoteTakingNotice()
    XCTAssertEqual(notices, 0, "closed capture must not claim it is taking notes")
    detector.applySnapshot(shot())
    XCTAssertEqual(notices, 1)
  }

  func testExpiredUndeliveredNoticeDoesNotLeakIntoANewCall() {
    var notices = 0
    let detector = detector(notice: { notices += 1 })
    confirm(detector)
    detector.requestNoteTakingNotice()
    _ = loseEvidence(detector)
    now += MeetingDetectionTiming.resumeWindow
    detector.applyDetected(false)
    confirm(detector)
    now += 35
    detector.applySnapshot(shot())
    XCTAssertEqual(notices, 0, "a new session still needs its own committed notice request")
    detector.requestNoteTakingNotice()
    XCTAssertEqual(notices, 1)
  }

  func testExpiryEndsExactlyOnceAtOriginalOffEdgeAndNextCallConfirmsNormally() {
    let detector = detector()
    confirm(detector)
    let offEdge = loseEvidence(detector)
    now += 239
    detector.applyDetected(false)
    XCTAssertEqual(transitions.count, 1)
    now += 1
    detector.applyDetected(false)
    XCTAssertFalse(detector.isMeetingConfirmed)
    XCTAssertEqual(detector.lastMeetingEndedAt, offEdge)
    XCTAssertEqual(role, .ambient)
    detector.applyDetected(false)
    XCTAssertEqual(transitions.map(\.finalizationReason), [.meetingStarted, .meetingEnded])
    detector.applySnapshot(shot(output: false))
    XCTAssertFalse(detector.isMeetingActive, "expired confirmation must not admit a voice note")
    detector.applySnapshot(shot())
    now += 10
    detector.applySnapshot(shot())
    XCTAssertEqual(transitions.map(\.nextRole), [.meeting, .ambient, .meeting])
  }

  func testInputOnlySustainsOnlyTheConfirmedMessagingApp() {
    let detector = detector()
    detector.applySnapshot(shot(output: false))
    XCTAssertFalse(detector.isMeetingActive)
    confirm(detector)
    now += 150
    detector.applySnapshot(shot(output: false))
    XCTAssertTrue(detector.isMeetingActive)
    XCTAssertNil(detector.resumeOffAt)
    XCTAssertTrue(detector.lastPositiveEvidenceDescription.contains("input=true,output=false"))
    detector.applySnapshot(shot("net.whatsapp.whatsapp", output: false))
    now += 8
    detector.applySnapshot(shot("net.whatsapp.whatsapp", output: false))
    XCTAssertFalse(detector.isMeetingActive, "Discord confirmation must not admit WhatsApp voice notes")
  }

  func testAFKMessagingCallClosesCaptureAfterFiveMinutesAndThenFinalizes() {
    let detector = detector()
    confirm(detector)
    now += MeetingDetectionTiming.inputOnlySustainPeriod - 1
    detector.applySnapshot(shot(output: false))
    XCTAssertTrue(detector.isMeetingActive)
    now += 1
    detector.applySnapshot(shot(output: false))
    now += 8
    detector.applySnapshot(shot(output: false))
    let offEdge = now
    XCTAssertFalse(detector.isMeetingActive, "an AFK mic cannot sustain capture indefinitely")
    XCTAssertEqual(detector.resumeOffAt, offEdge)
    now += MeetingDetectionTiming.resumeWindow
    detector.applySnapshot(shot(output: false))
    XCTAssertFalse(detector.isMeetingConfirmed)
    XCTAssertEqual(detector.lastMeetingEndedAt, offEdge)
    XCTAssertEqual(transitions.map(\.finalizationReason), [.meetingStarted, .meetingEnded])
    now += 4 * 60 * 60
    detector.applySnapshot(shot(output: false))
    XCTAssertFalse(detector.isMeetingActive, "continuing input alone must not start a new meeting")
    XCTAssertEqual(transitions.count, 2)
  }

  func testIntermittentOutputRefreshesTheCapForALongRealCall() {
    let detector = detector()
    confirm(detector)
    for _ in 0..<12 {
      now += MeetingDetectionTiming.inputOnlySustainPeriod - 1
      detector.applySnapshot(shot(output: false))
      XCTAssertTrue(detector.isMeetingActive)
      XCTAssertNil(detector.resumeOffAt)
      // Output from a different helper of this same app refreshes the cap.
      var snapshot = shot(output: false)
      snapshot.processes.append(
        .init(bundleID: "com.hnc.discord.helper", pid: 2, isRunningInput: false, isRunningOutput: true))
      detector.applySnapshot(snapshot)
    }
    XCTAssertEqual(transitions.map(\.nextRole), [.meeting])
    XCTAssertEqual(captureEdges, [true])
  }

  func testOutputReturningAfterTheCapResumesInsideTheWindow() {
    let detector = detector()
    confirm(detector)
    now += MeetingDetectionTiming.inputOnlySustainPeriod
    detector.applySnapshot(shot(output: false))
    now += 8
    detector.applySnapshot(shot(output: false))
    XCTAssertFalse(detector.isMeetingActive)
    now += 150
    detector.applySnapshot(shot(output: false))
    XCTAssertFalse(detector.isMeetingActive, "the resume hold cannot extend input-only sustain")
    detector.applySnapshot(shot())
    XCTAssertTrue(detector.isMeetingActive)
    XCTAssertTrue(detector.isMeetingConfirmed)
    XCTAssertNil(detector.resumeOffAt)
    XCTAssertEqual(transitions.map(\.nextRole), [.meeting])
    XCTAssertEqual(captureEdges, [true, false, true])
  }

  func testOtherAppsOutputCannotRefreshConfirmedMessagingSustain() {
    let detector = detector()
    confirm(detector)
    now += MeetingDetectionTiming.inputOnlySustainPeriod
    var snapshot = shot(output: false)
    snapshot.processes.append(
      .init(bundleID: "net.whatsapp.whatsapp", pid: 2, isRunningInput: false, isRunningOutput: true))
    detector.applySnapshot(snapshot)
    now += 8
    detector.applySnapshot(snapshot)
    XCTAssertFalse(detector.isMeetingActive)
    XCTAssertNotNil(detector.resumeOffAt)
  }

  func testProvisionalMessagingAudioStillNeedsOutputUntilConfirmed() {
    let detector = detector()
    detector.applySnapshot(shot())
    now += 9
    detector.applySnapshot(shot(output: false))
    now += 10
    detector.applySnapshot(shot(output: false))
    XCTAssertFalse(detector.isMeetingConfirmed)
    XCTAssertFalse(detector.isMeetingActive)
    XCTAssertTrue(transitions.isEmpty)
  }

  func testInputOnlyFirstSampleAfterExpiryCannotUseStaleConfirmation() {
    let detector = detector()
    confirm(detector)
    _ = loseEvidence(detector)
    now += MeetingDetectionTiming.resumeWindow
    detector.applySnapshot(shot(output: false))
    XCTAssertFalse(detector.isMeetingActive)
    XCTAssertFalse(detector.isMeetingConfirmed)
    XCTAssertEqual(role, .ambient)
  }

  func testSameCalendarEventResumesAcrossAppsButADifferentCallDoesNot() {
    let detector = detector()
    confirm(detector, events: ["event-A"])
    _ = loseEvidence(detector)
    now += 150
    detector.applySnapshot(shot("com.microsoft.teams2"), calendarEventIDs: ["event-A"])
    XCTAssertEqual(transitions.map(\.nextRole), [.meeting])
    _ = loseEvidence(detector)
    detector.applySnapshot(shot("net.whatsapp.whatsapp"), calendarEventIDs: ["event-B"])
    XCTAssertFalse(detector.isMeetingConfirmed)
    XCTAssertEqual(role, .ambient)
    now += 10
    detector.applySnapshot(shot("net.whatsapp.whatsapp"), calendarEventIDs: ["event-B"])
    XCTAssertEqual(transitions.map(\.nextRole), [.meeting, .ambient, .meeting])
  }

  func testAppStateCaptureOwnerDoesNotScheduleFinalizationDuringResumeHold() {
    let detector = detector()
    confirm(detector)
    _ = loseEvidence(detector)
    let state = AppState()
    state.isTranscribing = true
    state.currentSessionId = 42
    state.currentConversationRole = .meeting
    state.totalSegmentCount = 4
    state.meetingDetector = detector
    defer {
      state.isTranscribing = false
      state.meetingDetector = nil
    }
    state.finalizeEndedMeetingIfNeeded(mode: .onlyMeetings, meetingStateReady: true, shouldCapture: false)
    XCTAssertFalse(state.meetingEndFinalizationInProgress)
    XCTAssertEqual(state.currentSessionId, 42)
    XCTAssertEqual(state.currentConversationRole, .meeting)
  }

  func testBusyBoundaryRetainsOffEdgeForSessionCreationReplay() async {
    let state = AppState()
    state.isTranscribing = true
    state.currentSessionId = 42
    state.currentConversationRole = .meeting
    state.conversationRotationInFlight = true
    defer {
      state.isTranscribing = false
      state.conversationRotationInFlight = false
    }
    await state.handleMeetingObservation(active: false, endedAt: now)
    XCTAssertEqual(state.pendingMeetingState, false)
    XCTAssertEqual(state.pendingMeetingEndedAt, now)
    XCTAssertEqual(state.currentConversationRole, .meeting)
    XCTAssertFalse(state.meetingBoundaryInProgress)
  }

  func testResumeHoldPreventsTheCaptureOwnersFallbackFinalizer() {
    XCTAssertFalse(
      MeetingConversationBoundaryPolicy.shouldFinishConversation(
        mode: .onlyMeetings, meetingStateReady: true, shouldCapture: false,
        segmentCount: 4, conversationRole: .meeting, hasSpeakerSegments: true,
        meetingResumePending: true))
    XCTAssertTrue(
      MeetingConversationBoundaryPolicy.shouldFinishConversation(
        mode: .onlyMeetings, meetingStateReady: true, shouldCapture: false,
        segmentCount: 4, conversationRole: .meeting, hasSpeakerSegments: true,
        meetingResumePending: false))
  }

  func testFinalizationUsesOffEdgeOnlyWhenCaptureWasGated() {
    XCTAssertEqual(MeetingSessionResumePolicy.finalizationTime(mode: .onlyMeetings, offAt: now), now)
    XCTAssertNil(
      MeetingSessionResumePolicy.finalizationTime(mode: .always, offAt: now),
      "continuous Always audio must not extend past the stored interval")
  }

  func testZoomReleaseGenerationStillSeparatesBackToBackCallsWithoutCalendarMatch() {
    let detector = detector()
    detector.applySnapshot(shot("us.zoom.xos"))
    now += 10
    detector.applySnapshot(shot("us.zoom.xos"))
    detector.applySnapshot(shot("us.zoom.xos", input: false, output: false))
    now += 8
    detector.applySnapshot(shot("us.zoom.xos", input: false, output: false))
    detector.applySnapshot(shot("us.zoom.xos"))
    XCTAssertFalse(detector.isMeetingConfirmed, "release-ends-call catalog remains authoritative")
    XCTAssertEqual(role, .ambient)
  }
}

#if DEBUG
  // omi-release-compile: calendar timeout tests inspect DEBUG-only probe receipts.
  private actor HangingMeetingCalendarProbe {
    let requested: XCTestExpectation
    private var continuation: CheckedContinuation<Set<String>, Never>?
    private var calls = 0

    init(requested: XCTestExpectation) { self.requested = requested }

    func events() async -> Set<String> {
      calls += 1
      guard calls == 1 else { return ["fresh-event"] }
      return await withCheckedContinuation {
        continuation = $0
        requested.fulfill()
      }
    }

    func release() {
      continuation?.resume(returning: ["stale-event"])
      continuation = nil
    }
  }

  extension MeetingSessionResumeTests {
    func testHungCalendarProbeTimesOutRetriesAndIgnoresItsLateResult() async throws {
      let requested = expectation(description: "first calendar request is suspended")
      let probe = HangingMeetingCalendarProbe(requested: requested)
      let name = "MeetingCalendarTimeoutTests.\(UUID().uuidString)"
      let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
      defer { defaults.removePersistentDomain(forName: name) }
      let detector = MeetingDetector(
        processInputAPIAvailable: true,
        snapshot: { CallAudioSnapshot(processes: [], defaultInputDeviceID: 0, browserWindows: []) },
        calendarEventIDs: { await probe.events() },
        now: { [unowned self] in now }, audioLedgerDefaults: defaults,
        onChange: { _ in }, onConfirmedEvidence: { _ in }, onAudioSummaries: { _ in })
      detector.start()
      defer { detector.stop() }
      await fulfillment(of: [requested], timeout: 2)
      let hungTask = try XCTUnwrap(detector.currentCalendarTaskForTesting)
      now += MeetingDetectionTiming.calendarProbeTimeout - 1
      await detector.triggerProbeForTesting()?.value
      XCTAssertFalse(hungTask.isCancelled, "a pending lookup is not replaced before its deadline")
      now += 1
      await detector.triggerProbeForTesting()?.value
      await detector.currentCalendarTaskForTesting?.value
      XCTAssertTrue(hungTask.isCancelled)
      XCTAssertEqual(detector.calendarEventIDsForTesting, ["fresh-event"])
      await probe.release()
      await hungTask.value
      XCTAssertEqual(
        detector.calendarEventIDsForTesting, ["fresh-event"], "a late result cannot replace fresh evidence")
    }
  }
#endif
