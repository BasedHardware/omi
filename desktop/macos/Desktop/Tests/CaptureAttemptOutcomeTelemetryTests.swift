import XCTest

@testable import Omi_Computer

/// Behavioral contract for the ambient capture-attempt outcome funnel
/// (`Desktop Capture Attempt Outcome`): stable event name, bounded
/// content-free payload, Meetings-idle disposition, and the cancel /
/// completed / error / pending mapping. The privacy boundary (no transcript,
/// audio, device, path, or error-string fields) is asserted as an exact
/// key-set contract on every payload builder.
@MainActor
final class CaptureAttemptOutcomeTelemetryTests: XCTestCase {
  override func tearDown() {
    super.tearDown()
    MainActor.assumeIsolated {
      AnalyticsManager.shared.setCaptureAttemptTelemetryCaptureForTests(nil)
      CaptureAttemptAcceptanceRegistry.resetForTests()
    }
  }

  // MARK: - Event name

  func testEventNameIsStable() {
    XCTAssertEqual(PostHogManager.captureAttemptOutcomeEventName, "Desktop Capture Attempt Outcome")
  }

  // MARK: - Payload contract (privacy boundary)

  func testOutcomePayloadCarriesExactlyTheBoundedDimensionSet() throws {
    var attempt = CaptureAttemptOutcomeState(mode: "always", intent: .userStart)
    attempt.noteCaptureEligible()
    attempt.noteFirstAudioFrame()
    attempt.noteSpeech()

    let properties = PostHogManager.captureAttemptOutcomeProperties(attempt, finalizationReason: .userStop)

    XCTAssertEqual(
      Set(properties.keys),
      [
        "platform", "attempt_id", "mode", "intent", "capture_eligible", "first_audio_frame",
        "speech_observed", "terminal_reason", "conversation_accepted",
      ])
    XCTAssertEqual(properties["platform"] as? String, "macos")
    XCTAssertEqual(properties["mode"] as? String, "always")
    XCTAssertEqual(properties["intent"] as? String, "user_start")
    XCTAssertEqual(properties["capture_eligible"] as? Bool, true)
    XCTAssertEqual(properties["first_audio_frame"] as? Bool, true)
    XCTAssertEqual(properties["speech_observed"] as? Bool, true)
    XCTAssertEqual(properties["terminal_reason"] as? String, "completed")
    XCTAssertEqual(properties["conversation_accepted"] as? Bool, false)
    let attemptId = try XCTUnwrap(properties["attempt_id"] as? String)
    XCTAssertEqual(attemptId.count, 36, "attempt_id is an opaque UUID string")
  }

  func testPendingPayloadCarriesOnlyTheSurvivingJoinKey() {
    let properties = PostHogManager.captureAttemptPendingProperties(attemptId: "fixed-attempt-id")

    XCTAssertEqual(Set(properties.keys), ["platform", "attempt_id", "terminal_reason"])
    XCTAssertEqual(properties["attempt_id"] as? String, "fixed-attempt-id")
    XCTAssertEqual(properties["terminal_reason"] as? String, "pending")
  }

  // MARK: - Disposition mapping

  func testMeetingsIdleWaitMapsToIdleWaitingMeetingNeverError() {
    for reason in [TranscriptionFinalizationReason.userStop, .meetingEnded, .maxDurationRotation] {
      let disposition = CaptureAttemptOutcomeState.terminalReason(
        finalizationReason: reason,
        mode: AssistantSettings.AudioRecordingMode.onlyMeetings.rawValue,
        firstAudioFrame: false,
        errorTerminal: false)
      XCTAssertEqual(disposition, .idleWaitingMeeting, "for \(reason.rawValue)")
    }
  }

  func testMeetingsAttemptWithAudioIsNotIdleWaiting() {
    let disposition = CaptureAttemptOutcomeState.terminalReason(
      finalizationReason: .userStop,
      mode: AssistantSettings.AudioRecordingMode.onlyMeetings.rawValue,
      firstAudioFrame: true,
      errorTerminal: false)
    XCTAssertEqual(disposition, .completed)
  }

  func testArmedWithoutAudioEndsAsCancelled() {
    let disposition = CaptureAttemptOutcomeState.terminalReason(
      finalizationReason: .userStop,
      mode: AssistantSettings.AudioRecordingMode.always.rawValue,
      firstAudioFrame: false,
      errorTerminal: false)
    XCTAssertEqual(disposition, .cancelled)
  }

  func testErrorTerminalReasonsAreErrors() {
    for mode in AssistantSettings.AudioRecordingMode.allCases where mode != .off {
      let disposition = CaptureAttemptOutcomeState.terminalReason(
        finalizationReason: .userStop,
        mode: mode.rawValue,
        firstAudioFrame: false,
        errorTerminal: true)
      XCTAssertEqual(disposition, .error, "for mode \(mode.rawValue)")
    }
  }

  func testRotationOfCapturingAttemptIsCompleted() {
    let disposition = CaptureAttemptOutcomeState.terminalReason(
      finalizationReason: .maxDurationRotation,
      mode: AssistantSettings.AudioRecordingMode.always.rawValue,
      firstAudioFrame: true,
      errorTerminal: false)
    XCTAssertEqual(disposition, .completed)
  }

  func testCrashRecoveryAndRetryArePending() {
    for reason in [TranscriptionFinalizationReason.crashRecovery, .retry] {
      let disposition = CaptureAttemptOutcomeState.terminalReason(
        finalizationReason: reason,
        mode: AssistantSettings.AudioRecordingMode.always.rawValue,
        firstAudioFrame: true,
        errorTerminal: false)
      XCTAssertEqual(disposition, .pending, "for \(reason.rawValue)")
    }
  }

  // MARK: - Acceptance registry

  func testAcceptanceRegistryNotesAndConsumesExactlyOnce() {
    CaptureAttemptAcceptanceRegistry.noteAccepted("attempt-a")

    XCTAssertTrue(CaptureAttemptAcceptanceRegistry.consumeAccepted("attempt-a"))
    XCTAssertFalse(CaptureAttemptAcceptanceRegistry.consumeAccepted("attempt-a"))
    XCTAssertFalse(CaptureAttemptAcceptanceRegistry.consumeAccepted("attempt-b"))
  }

  // MARK: - Emission boundary

  func testOutcomeEmitConsumesAcceptanceAndObservesAtAnalyticsBoundary() {
    var attempt = CaptureAttemptOutcomeState(attemptId: "accepted-attempt", mode: "always", intent: .auto)
    attempt.noteFirstAudioFrame()
    CaptureAttemptAcceptanceRegistry.noteAccepted("accepted-attempt")

    var observed: [(String, [String: Any])] = []
    AnalyticsManager.shared.setCaptureAttemptTelemetryCaptureForTests { event, properties in
      observed.append((event, properties))
    }

    AnalyticsManager.shared.captureAttemptOutcome(&attempt, finalizationReason: .userStop)

    XCTAssertEqual(observed.count, 1)
    XCTAssertEqual(observed.first?.0, "Desktop Capture Attempt Outcome")
    XCTAssertEqual(observed.first?.1["conversation_accepted"] as? Bool, true)
    XCTAssertEqual(observed.first?.1["terminal_reason"] as? String, "completed")
    XCTAssertEqual(observed.first?.1["intent"] as? String, "auto")
  }

  func testPendingOutcomeObservesAtAnalyticsBoundary() {
    var observed: [(String, [String: Any])] = []
    AnalyticsManager.shared.setCaptureAttemptTelemetryCaptureForTests { event, properties in
      observed.append((event, properties))
    }

    AnalyticsManager.shared.captureAttemptPendingOutcome(attemptId: "crashed-attempt")

    XCTAssertEqual(observed.count, 1)
    XCTAssertEqual(observed.first?.0, "Desktop Capture Attempt Outcome")
    XCTAssertEqual(observed.first?.1["terminal_reason"] as? String, "pending")
    XCTAssertEqual(observed.first?.1["attempt_id"] as? String, "crashed-attempt")
  }

  // MARK: - Attempt identity joins

  func testConversationCreatedTelemetryCarriesPersistedAttemptId() {
    let record = TranscriptionSessionRecord(source: "desktop", captureAttemptId: "persisted-attempt")
    let telemetry = ConversationCreatedTelemetry(session: record, conversationId: "conversation-1")
    XCTAssertEqual(telemetry.attemptId, "persisted-attempt")

    let legacy = TranscriptionSessionRecord(source: "desktop")
    XCTAssertNil(ConversationCreatedTelemetry(session: legacy, conversationId: "conversation-2").attemptId)
  }

  func testConversationCreatedPropertiesAttachAttemptIdOnlyWhenPresent() {
    XCTAssertEqual(
      Set(PostHogManager.conversationCreatedProperties(source: "desktop", durationSeconds: 12, attemptId: "a1").keys),
      ["conversation_source", "duration_seconds", "attempt_id"])
    XCTAssertEqual(
      Set(PostHogManager.conversationCreatedProperties(source: "desktop", durationSeconds: nil, attemptId: nil).keys),
      ["conversation_source"])
  }

  func testRecordingStartedAndStoppedPropertiesCarryAttemptIdentity() {
    XCTAssertEqual(
      Set(
        PostHogManager.transcriptionStartedProperties(
          attemptId: "a1", mode: "onlyMeetings", intent: "auto"
        ).keys
      ),
      ["platform", "attempt_id", "recording_mode", "intent"])
    XCTAssertEqual(
      Set(PostHogManager.transcriptionStoppedProperties(wordCount: 7, attemptId: "a1").keys),
      ["platform", "word_count", "attempt_id"])
    XCTAssertEqual(
      Set(PostHogManager.transcriptionStoppedProperties(wordCount: 0, attemptId: nil).keys),
      ["platform", "word_count"])
  }
}
