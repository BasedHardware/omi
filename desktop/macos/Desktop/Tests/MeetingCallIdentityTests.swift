import XCTest

@testable import Omi_Computer

/// Back-to-back calls with no off edge between them (2026-09-25: leaving one Meet and joining the
/// next within the off grace merged both into one conversation).
final class MeetingCallIdentityTrackerTests: XCTestCase {
  private let start = Date(timeIntervalSince1970: 1000)

  private func at(_ seconds: TimeInterval) -> Date { start.addingTimeInterval(seconds) }

  func testFirstIdentitiesNameTheCallInProgress() {
    var tracker = MeetingCallIdentityTracker(confirmationPeriod: 8)
    XCTAssertFalse(tracker.observe(["meet:aaa-bbbb-ccc"], at: at(0)))
    XCTAssertFalse(tracker.observe(["meet:aaa-bbbb-ccc"], at: at(20)))
  }

  func testIdentitiesAppearingLateAreAdoptedNotTreatedAsANewCall() {
    var tracker = MeetingCallIdentityTracker(confirmationPeriod: 8)
    XCTAssertFalse(tracker.observe([], at: at(0)))
    XCTAssertFalse(tracker.observe(["meet:aaa-bbbb-ccc"], at: at(4)))
    XCTAssertFalse(tracker.observe(["meet:aaa-bbbb-ccc"], at: at(40)))
  }

  func testNewMeetReplacingTheOldOneConfirmsAfterThePeriod() {
    var tracker = MeetingCallIdentityTracker(confirmationPeriod: 8)
    _ = tracker.observe(["meet:aaa-bbbb-ccc"], at: at(0))
    XCTAssertFalse(tracker.observe(["meet:ddd-eeee-fff"], at: at(4)))
    XCTAssertFalse(tracker.observe(["meet:ddd-eeee-fff"], at: at(8)))
    XCTAssertTrue(tracker.observe(["meet:ddd-eeee-fff"], at: at(12)))
    XCTAssertFalse(tracker.observe(["meet:ddd-eeee-fff"], at: at(16)), "confirmed once, not every probe")
  }

  /// Left A with its tab still open: A's title stays, but the mic dropped as B appeared.
  func testNewCallCountsWhileTheOldWindowStaysOnScreenIfTheMicDropped() {
    var tracker = MeetingCallIdentityTracker(confirmationPeriod: 8)
    _ = tracker.observe(["meet:aaa-bbbb-ccc"], at: at(0))
    tracker.noteMicrophoneGap(at: at(100))
    _ = tracker.observe(["meet:aaa-bbbb-ccc", "meet:ddd-eeee-fff"], at: at(104))
    XCTAssertTrue(tracker.observe(["meet:aaa-bbbb-ccc", "meet:ddd-eeee-fff"], at: at(112)))
  }

  /// The next meeting's green room opened early while A continues: not a replacement.
  func testNewCallAlongsideTheCurrentOneDoesNotRotateUntilTheCurrentOneEnds() {
    var tracker = MeetingCallIdentityTracker(confirmationPeriod: 8)
    _ = tracker.observe(["meet:aaa-bbbb-ccc"], at: at(0))
    tracker.noteMicrophoneGap(at: at(10))  // a brief mute long before B appears
    _ = tracker.observe(["meet:aaa-bbbb-ccc", "meet:ddd-eeee-fff"], at: at(100))
    XCTAssertFalse(tracker.observe(["meet:aaa-bbbb-ccc", "meet:ddd-eeee-fff"], at: at(112)))
    XCTAssertFalse(tracker.observe(["meet:aaa-bbbb-ccc", "meet:ddd-eeee-fff"], at: at(400)))
    // A's window closes: B now replaces it.
    XCTAssertTrue(tracker.observe(["meet:ddd-eeee-fff"], at: at(404)))
  }

  func testAHuddleStartedDuringAMeetDoesNotRotate() {
    var tracker = MeetingCallIdentityTracker(confirmationPeriod: 8)
    _ = tracker.observe(["meet:aaa-bbbb-ccc"], at: at(0))
    _ = tracker.observe(["meet:aaa-bbbb-ccc", "app:com.tinyspeck.slackmacgap"], at: at(60))
    XCTAssertFalse(tracker.observe(["meet:aaa-bbbb-ccc", "app:com.tinyspeck.slackmacgap"], at: at(120)))
  }

  func testBrieflyVisibleNewIdentityDoesNotCount() {
    var tracker = MeetingCallIdentityTracker(confirmationPeriod: 8)
    _ = tracker.observe(["meet:aaa-bbbb-ccc"], at: at(0))
    XCTAssertFalse(tracker.observe(["meet:ddd-eeee-fff"], at: at(4)))
    XCTAssertFalse(tracker.observe(["meet:aaa-bbbb-ccc"], at: at(8)), "gone again: candidate dropped")
    XCTAssertFalse(tracker.observe(["meet:ddd-eeee-fff"], at: at(12)), "reappearing restarts the period")
    XCTAssertTrue(tracker.observe(["meet:ddd-eeee-fff"], at: at(20)))
  }

  func testTabSwitchingAwayAndBackDoesNotRotate() {
    var tracker = MeetingCallIdentityTracker(confirmationPeriod: 8)
    _ = tracker.observe(["meet:aaa-bbbb-ccc"], at: at(0))
    XCTAssertFalse(tracker.observe([], at: at(4)), "another tab is frontmost")
    XCTAssertFalse(tracker.observe([], at: at(30)))
    XCTAssertFalse(tracker.observe(["meet:aaa-bbbb-ccc"], at: at(60)))
  }

  func testSwitchingFromAMeetToANativeCallCounts() {
    var tracker = MeetingCallIdentityTracker(confirmationPeriod: 8)
    _ = tracker.observe(["meet:aaa-bbbb-ccc"], at: at(0))
    _ = tracker.observe(["app:com.tdesktop.telegram"], at: at(4))
    XCTAssertTrue(tracker.observe(["app:com.tdesktop.telegram"], at: at(12)))
  }

  func testResetStartsAFreshMeeting() {
    var tracker = MeetingCallIdentityTracker(confirmationPeriod: 8)
    _ = tracker.observe(["meet:aaa-bbbb-ccc"], at: at(0))
    tracker.reset()
    XCTAssertFalse(tracker.observe(["meet:ddd-eeee-fff"], at: at(4)))
    XCTAssertFalse(tracker.observe(["meet:ddd-eeee-fff"], at: at(20)))
  }
}

@MainActor
final class MeetingDetectorCallChangeTests: XCTestCase {
  private var now = Date(timeIntervalSince1970: 1000)

  private func makeDetector(
    onCallChanged: @escaping () -> Void, onChange: @escaping (Bool) -> Void = { _ in }
  ) -> MeetingDetector {
    MeetingDetector(
      pollInterval: 4.0,
      offGracePeriod: 8.0,
      callConfirmationPeriod: 8.0,
      now: { [weak self] in self?.now ?? Date(timeIntervalSince1970: 0) },
      onCallChanged: onCallChanged,
      onChange: onChange)
  }

  /// The 2026-09-25 shape: Meet A's mic drops, Meet B's green room takes it within the grace.
  func testBackToBackMeetsReportACallChangeWithoutAnOffEdge() {
    var callChanges = 0
    var edges = [Bool]()
    let detector = makeDetector(onCallChanged: { callChanges += 1 }, onChange: { edges.append($0) })

    detector.applyDetected(true, callIDs: ["meet:aaa-bbbb-ccc"])
    now += 4
    detector.applyDetected(false)  // A left: pending off
    now += 4
    detector.applyDetected(true, callIDs: ["meet:ddd-eeee-fff"])  // B green room, within grace
    now += 4
    detector.applyDetected(true, callIDs: ["meet:ddd-eeee-fff"])
    XCTAssertEqual(callChanges, 0)
    now += 4
    detector.applyDetected(true, callIDs: ["meet:ddd-eeee-fff"])

    XCTAssertEqual(edges, [true], "no off edge between the two calls")
    XCTAssertEqual(callChanges, 1)
    XCTAssertTrue(detector.hasPendingCallChange)
  }

  func testMeetingEndingClearsPendingCallChangeAndIdentities() {
    var callChanges = 0
    let detector = makeDetector(onCallChanged: { callChanges += 1 })

    detector.applyDetected(true, callIDs: ["meet:aaa-bbbb-ccc"])
    now += 4
    detector.applyDetected(true, callIDs: ["meet:ddd-eeee-fff"])
    now += 8
    detector.applyDetected(true, callIDs: ["meet:ddd-eeee-fff"])
    XCTAssertTrue(detector.hasPendingCallChange)

    detector.applyDetected(false)
    now += 9
    detector.applyDetected(false)
    XCTAssertFalse(detector.isMeetingActive)
    XCTAssertFalse(detector.hasPendingCallChange)

    // The next meeting's first call is a start, not a change.
    detector.applyDetected(true, callIDs: ["meet:ggg-hhhh-iii"])
    now += 20
    detector.applyDetected(true, callIDs: ["meet:ggg-hhhh-iii"])
    XCTAssertEqual(callChanges, 1)
  }
}

final class MeetingCallIdentityPolicyTests: XCTestCase {
  func testMeetCodeIsReadFromAJoinedMeetTitle() {
    XCTAssertEqual(ConferencingApps.meetingCode(fromTitle: "Meet - amc-iajq-asx"), "amc-iajq-asx")
    XCTAssertEqual(ConferencingApps.meetingCode(fromTitle: "Meet – AMC-IAJQ-ASX"), "amc-iajq-asx")
    XCTAssertNil(ConferencingApps.meetingCode(fromTitle: "Meet - notacode"))
    XCTAssertNil(ConferencingApps.meetingCode(fromTitle: "Google Meet"))
  }

  func testCallChangeDuringAMeetingEndsItAndStartsAnother() {
    XCTAssertEqual(
      MeetingConversationBoundaryPolicy.transition(previousRole: .meeting, meetingActive: true, callChanged: true),
      .init(nextRole: .meeting, finalizationReason: .meetingEnded))
  }

  func testCallChangeOutsideAMeetingIsAnOrdinaryStart() {
    XCTAssertEqual(
      MeetingConversationBoundaryPolicy.transition(previousRole: .ambient, meetingActive: true, callChanged: true),
      .init(nextRole: .meeting, finalizationReason: .meetingStarted))
  }
}

/// The pending call change is consumed by the real boundary entry point, and survives a
/// rotation that could not run.
@MainActor
final class MeetingCallChangeBoundaryTests: XCTestCase {
  private func detectorWithPendingCallChange() -> MeetingDetector {
    let detector = MeetingDetector(onChange: { _ in })
    detector.restorePendingCallChange()
    return detector
  }

  func testBusyRotationKeepsTheCallChangeForReplay() async {
    let state = AppState()
    state.isTranscribing = true
    state.currentSessionId = 1
    state.currentConversationRole = .meeting
    state.meetingDetector = detectorWithPendingCallChange()
    state.conversationRotationInFlight = true  // another rotation holds the serializer
    defer {
      state.conversationRotationInFlight = false
      state.meetingDetector = nil
      state.isTranscribing = false
    }

    await state.handleMeetingObservation(active: true)

    XCTAssertEqual(state.meetingDetector?.hasPendingCallChange, true)
    XCTAssertEqual(state.pendingMeetingState, true, "replayed when the in-flight rotation installs its session")
    XCTAssertEqual(state.currentConversationRole, .meeting)
    XCTAssertFalse(state.meetingBoundaryInProgress)
  }

  func testEdgeDeferredUntilASessionExistsKeepsTheCallChange() async {
    let state = AppState()
    state.isTranscribing = true
    state.currentSessionId = nil
    state.currentConversationRole = .meeting
    state.meetingDetector = detectorWithPendingCallChange()
    defer {
      state.meetingDetector = nil
      state.isTranscribing = false
    }

    await state.handleMeetingObservation(active: true)

    XCTAssertEqual(state.meetingDetector?.hasPendingCallChange, true)
    XCTAssertEqual(state.pendingMeetingState, true)
  }
}
