import Foundation

// MARK: - Questions (one vocabulary across typed chat and push-to-talk)
//
// `question_asked` / `question_answered` are the activation metric's events.
// Before this, "questions" meant `Chat Message Sent` ∪ `floating_bar_query_sent`,
// which missed the realtime push-to-talk lane and undercounted PTT by half
// (22.6% vs 48.3% of the 2026-08 true-new cohort reaching three questions).

extension AnalyticsManager {
  /// Where a question entered Omi. Coarser than the per-surface `source`
  /// strings so activation can be measured with one event instead of a
  /// union of `Chat Message Sent` and `floating_bar_query_sent`, which
  /// undercounted push-to-talk by half in the 2026-09 activation analysis.
  enum QuestionSurface: String, Sendable {
    case chatWindow = "chat_window"
    case floatingBarTyped = "floating_bar_typed"
    case ptt
    case pttRealtime = "ptt_realtime"

    init(_ source: FloatingBarQuerySource) {
      switch source {
      case .typed: self = .floatingBarTyped
      case .ptt, .pttVoiceOnly: self = .ptt
      case .pttRealtime: self = .pttRealtime
      }
    }
  }

  /// How a question ended. `grounded` means an answer was delivered; the
  /// name is deliberately not "helpful", which no client signal can know.
  enum QuestionOutcome: String, Sendable {
    case grounded
    case screenFailed = "screen_failed"
    case error
    case cancelled
  }

  /// One accepted question, on any surface. Also the single place the
  /// in-app question counter (rating prompt, remote `question_count`
  /// prompts) is advanced, so a voice question counts exactly like a typed one.
  func questionAsked(surface: QuestionSurface, source: String, messageLength: Int, attemptID: String?) {
    var props: [String: Any] = [
      "surface": surface.rawValue,
      "source": source,
      "message_length": messageLength,
    ]
    if let attemptID { props["attempt_id"] = attemptID }
    // Added, never substituted: `surface` says where the question was asked,
    // `origin` says what prompted it (see AnalyticsManager+QuestionOrigin).
    props["origin"] = consumeQuestionOrigin().rawValue
    questionTelemetryCaptureForTests?("question_asked", props)
    PostHogManager.shared.track("question_asked", properties: props)
    Task { @MainActor in
      RatingPromptManager.shared.recordQuestionAsked()
    }
  }

  /// The terminal outcome of a question, joined to `question_asked` by
  /// `attempt_id` where the surface mints one (voice turns; chat attempts).
  func questionAnswered(surface: QuestionSurface, outcome: QuestionOutcome, attemptID: String?, durationMs: Int?) {
    var props: [String: Any] = [
      "surface": surface.rawValue,
      "outcome": outcome.rawValue,
    ]
    if let attemptID { props["attempt_id"] = attemptID }
    if let durationMs { props["duration_ms"] = max(0, durationMs) }
    questionTelemetryCaptureForTests?("question_answered", props)
    PostHogManager.shared.track("question_answered", properties: props)
  }

  /// Maps a voice turn's terminal record onto the question vocabulary.
  /// Turns that never committed a question (too short, silent) produce no
  /// answer record, so asked and answered stay paired.
  nonisolated static func questionOutcome(forVoiceTerminalReason reason: String, answerDelivered: Bool)
    -> QuestionOutcome?
  {
    if answerDelivered { return .grounded }
    switch reason {
    case "success":
      return .grounded
    // Terminal before any question was committed: no `question_asked` exists
    // for these, so no answer record either (asked and answered stay paired).
    // `capture_not_ready` belongs here for the same reason as `capture_failed`:
    // the microphone never became operational, so the turn ended before any
    // question was committed. Left in `default` it emitted an orphan `.error`
    // answer with no `question_asked` to pair with.
    case "too_short", "silent_rejected", "permission_denied", "capture_failed", "capture_not_ready",
      "transcription_failed", "hub_warm_timeout", "deferred_commit_timeout":
      return nil
    // A cancellation may land before or after the commit; the reason string
    // cannot tell them apart, so a cancelled turn with no delivered answer is
    // dropped rather than risk an orphan `cancelled` row.
    case "cancelled", "owner_changed", "interrupted_by_barge_in", "explicit_interrupt", "cleanup":
      return nil
    default:
      return .error
    }
  }

  /// The realtime hub lanes carry the `hub` / `hub_warm_wait` route labels
  /// (`VoiceTurnCoordinator.routeLabel`); everything else is the STT cascade.
  nonisolated static func questionSurface(forVoiceRoute route: String) -> QuestionSurface {
    route == "hub" || route == "hub_warm_wait" ? .pttRealtime : .ptt
  }

  nonisolated static func questionOutcome(forChatEvent event: ChatQueryTelemetryEvent) -> QuestionOutcome? {
    switch event {
    case .started:
      return nil
    case .completed(_, _, let metrics):
      return metrics.screenToolRequested && !metrics.screenToolSucceeded ? .screenFailed : .grounded
    case .failed:
      return .error
    case .cancelled:
      return .cancelled
    }
  }

  /// Which `ChatProvider` telemetry surfaces are user questions the chat path
  /// answers for. Voice turns that route through `ChatProvider`
  /// (`floating_voice`, `floating_text`) terminalize in `VoiceTurnCoordinator`,
  /// which owns their answer record; onboarding and agent-pill sends are not
  /// questions. Returns `nil` for surfaces the chat path must not answer for.
  nonisolated static func questionSurface(forChatSurface surface: String) -> QuestionSurface? {
    switch surface {
    case "main_chat", "task_chat": return .chatWindow
    default: return nil
    }
  }

  /// Terminal chat lifecycle → one `question_answered`, joined by `attempt_id`.
  func questionAnswered(forChatEvent event: ChatQueryTelemetryEvent) {
    guard let outcome = Self.questionOutcome(forChatEvent: event) else { return }
    // Known small overcount: a query-shell replay sends with countsAsQuestion:
    // false (no `question_asked`) but still terminalizes here.
    let context: ChatQueryTelemetryContext
    let durationMs: Int?
    switch event {
    case .started(let c):
      context = c
      durationMs = nil
    case .completed(let c, let d, _):
      context = c
      durationMs = d
    case .failed(let c, let d, _, _, _, _):
      context = c
      durationMs = d
    case .cancelled(let c, let d, _, _):
      context = c
      durationMs = d
    }
    guard let surface = Self.questionSurface(forChatSurface: context.surface) else { return }
    questionAnswered(surface: surface, outcome: outcome, attemptID: context.attemptId, durationMs: durationMs)
  }
}
