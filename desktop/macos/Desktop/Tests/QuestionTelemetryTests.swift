import XCTest

@testable import Omi_Computer
@testable import VoiceTurnDomain

/// `question_asked` / `question_answered` are one vocabulary across typed chat
/// and push-to-talk. The in-app question counter (rating prompt, remote
/// `question_count` prompts) advances from the same seam, so a voice question
/// counts exactly like a typed one. Before this, the counter was typed-only and
/// the activation dashboard undercounted push-to-talk by half.
@MainActor
final class QuestionTelemetryTests: XCTestCase {
  private var captured: [(String, [String: Any])] = []

  // Async hooks without `super` calls: awaiting the pinned SDK's nonisolated
  // super.setUp()/tearDown() would transfer the non-Sendable test instance
  // across actors (see scripts/check-main-actor-xctest-hooks.py).
  override func setUp() async throws {
    captured = []
    AnalyticsManager.shared.questionTelemetryCaptureForTests = { [weak self] name, props in
      self?.captured.append((name, props))
    }
  }

  override func tearDown() async throws {
    AnalyticsManager.shared.questionTelemetryCaptureForTests = nil
  }

  func testFloatingBarVoiceQueryEmitsQuestionAskedWithTheTurnID() {
    AnalyticsManager.shared.floatingBarQuerySent(
      messageLength: 12, hasScreenshot: false, source: .pttRealtime, attemptID: "turn-1")
    let asked = captured.filter { $0.0 == "question_asked" }
    XCTAssertEqual(asked.count, 1)
    XCTAssertEqual(asked.first?.1["surface"] as? String, "ptt_realtime")
    XCTAssertEqual(asked.first?.1["attempt_id"] as? String, "turn-1")
    XCTAssertEqual(asked.first?.1["source"] as? String, "ptt_realtime")
  }

  func testTypedChatEmitsQuestionAskedOnlyForAcceptedQuestions() {
    AnalyticsManager.shared.chatMessageSent(
      messageLength: 5, source: "home_ask_bar", attemptID: "typed-attempt-1")
    AnalyticsManager.shared.chatMessageSent(messageLength: 5, source: "home_ask_bar", countsAsQuestion: false)
    let asked = captured.filter { $0.0 == "question_asked" }
    XCTAssertEqual(asked.count, 1, "A retry of the same logical question must not count twice")
    XCTAssertEqual(asked.first?.1["surface"] as? String, "chat_window")
    XCTAssertEqual(asked.first?.1["source"] as? String, "home_ask_bar")
    XCTAssertEqual(asked.first?.1["attempt_id"] as? String, "typed-attempt-1")
  }

  @MainActor
  func testAcceptedChatCallbackJoinsTerminalAnswerByTheSameAttemptID() {
    var acceptedAttemptID: String?
    let attempt = ChatQueryTelemetryAttempt(
      attemptId: "accepted-turn-1",
      surface: "main_chat",
      harness: "piMono"
    )

    ChatProvider.notifyAccepted(
      telemetryAttempt: attempt,
      onAccepted: nil,
      onAcceptedWithAttemptID: { attemptID in
        acceptedAttemptID = attemptID
        AnalyticsManager.shared.chatMessageSent(
          messageLength: 12, source: "query_shell", attemptID: attemptID)
      }
    )

    let metrics = ChatQueryCompletionMetrics(
      toolCallCount: 0,
      toolNames: [],
      costUsd: 0,
      responseLength: 8,
      screenToolRequested: false,
      screenToolSucceeded: false,
      screenToolApprovalRequired: false,
      screenToolFailureCodes: []
    )
    XCTAssertTrue(attempt.complete(metrics: metrics))

    let asked = captured.filter { $0.0 == "question_asked" }
    let answered = captured.filter { $0.0 == "question_answered" }
    XCTAssertEqual(acceptedAttemptID, "accepted-turn-1")
    XCTAssertEqual(asked.count, 1)
    XCTAssertEqual(answered.count, 1)
    XCTAssertEqual(asked.first?.1["attempt_id"] as? String, acceptedAttemptID)
    XCTAssertEqual(answered.first?.1["attempt_id"] as? String, acceptedAttemptID)
  }

  func testEveryFloatingBarSourceMapsToASurface() {
    let mapped = Dictionary(
      FloatingBarQuerySource.allCases.map { ($0, AnalyticsManager.QuestionSurface($0)) },
      uniquingKeysWith: { first, _ in first })
    XCTAssertEqual(mapped[.typed], .floatingBarTyped)
    XCTAssertEqual(mapped[.ptt], .ptt)
    XCTAssertEqual(mapped[.pttVoiceOnly], .ptt)
    XCTAssertEqual(mapped[.pttRealtime], .pttRealtime)
  }

  func testVoiceTerminalReasonsMapToOutcomesAndUncommittedTurnsProduceNone() {
    // Nothing was committed for these, so no `question_asked` exists to pair with.
    for reason in [
      "too_short", "silent_rejected", "permission_denied", "capture_failed", "capture_not_ready",
      "transcription_failed", "hub_warm_timeout", "deferred_commit_timeout", "cancelled",
      "explicit_interrupt", "owner_changed",
    ] {
      XCTAssertNil(AnalyticsManager.questionOutcome(forVoiceTerminalReason: reason, answerDelivered: false), reason)
    }
    XCTAssertEqual(
      AnalyticsManager.questionOutcome(forVoiceTerminalReason: "success", answerDelivered: true), .grounded)
    XCTAssertEqual(
      AnalyticsManager.questionOutcome(forVoiceTerminalReason: "explicit_interrupt", answerDelivered: true), .grounded)
    XCTAssertEqual(
      AnalyticsManager.questionOutcome(forVoiceTerminalReason: "provider_failed", answerDelivered: false), .error)
    // Spelled by the state machine, not by this test: a rename there must not
    // quietly drop the reason back into `default` and emit an orphan answer.
    XCTAssertNil(
      AnalyticsManager.questionOutcome(
        forVoiceTerminalReason: VoiceTurnTerminalReason.captureNotReady.rawValue,
        answerDelivered: false),
      "a turn whose microphone never came up committed no question")
  }

  func testVoiceRouteLabelsMapToTheSurfaceTheAskUsed() {
    XCTAssertEqual(AnalyticsManager.questionSurface(forVoiceRoute: "hub"), .pttRealtime)
    XCTAssertEqual(AnalyticsManager.questionSurface(forVoiceRoute: "hub_warm_wait"), .pttRealtime)
    XCTAssertEqual(AnalyticsManager.questionSurface(forVoiceRoute: "deepgram_batch"), .ptt)
    XCTAssertEqual(AnalyticsManager.questionSurface(forVoiceRoute: "omni_stt"), .ptt)
  }

  func testChatPathAnswersOnlyForChatQuestionSurfaces() {
    // Voice turns routed through ChatProvider terminalize in VoiceTurnCoordinator,
    // which owns their answer record; a second row here would double count.
    for surface in ["floating_voice", "floating_text", "onboarding", "agent_pill"] {
      let context = ChatQueryTelemetryContext(attemptId: "a-\(surface)", surface: surface, harness: "kernel")
      AnalyticsManager.shared.chatQueryTelemetry(
        .cancelled(context, durationMs: 10, reason: .userStop, partialResponse: false))
    }
    XCTAssertTrue(captured.filter { $0.0 == "question_answered" }.isEmpty)
    XCTAssertNil(AnalyticsManager.questionSurface(forChatSurface: "floating_voice"))
    XCTAssertEqual(AnalyticsManager.questionSurface(forChatSurface: "main_chat"), .chatWindow)
    XCTAssertEqual(AnalyticsManager.questionSurface(forChatSurface: "task_chat"), .chatWindow)
  }

  func testChatTerminalEventsEmitQuestionAnsweredJoinedByAttemptID() {
    let first = ChatQueryTelemetryContext(attemptId: "attempt-9", surface: "main_chat", harness: "kernel")
    let second = ChatQueryTelemetryContext(attemptId: "attempt-10", surface: "main_chat", harness: "kernel")
    let metrics = ChatQueryCompletionMetrics(
      toolCallCount: 1, toolNames: ["capture_screen"], costUsd: 0, responseLength: 10,
      screenToolRequested: true, screenToolSucceeded: false, screenToolApprovalRequired: false,
      screenToolFailureCodes: ["image_unavailable"])
    AnalyticsManager.shared.chatQueryTelemetry(.started(first))
    AnalyticsManager.shared.chatQueryTelemetry(.completed(first, durationMs: 1200, metrics: metrics))
    AnalyticsManager.shared.chatQueryTelemetry(.started(second))
    AnalyticsManager.shared.chatQueryTelemetry(
      .cancelled(second, durationMs: 300, reason: .userStop, partialResponse: false))

    let answered = captured.filter { $0.0 == "question_answered" }
    XCTAssertEqual(answered.count, 2, "started is not a terminal outcome; one answer per attempt")
    XCTAssertEqual(answered[0].1["outcome"] as? String, "screen_failed")
    XCTAssertEqual(answered[0].1["attempt_id"] as? String, "attempt-9")
    XCTAssertEqual(answered[0].1["surface"] as? String, "chat_window")
    XCTAssertEqual(answered[1].1["outcome"] as? String, "cancelled")
    XCTAssertEqual(answered[1].1["attempt_id"] as? String, "attempt-10")
  }

}
