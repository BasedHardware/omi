import Foundation

/// Privacy-bounded terminal record for one armed ambient-capture attempt.
///
/// The retention investigation (Sep 2026) could not tell no-opportunity,
/// idle Meetings wait, explicit cancel, silent capture failure, and pending
/// finalization apart, because `Desktop Recording Started` only observes the
/// armed state and `Memory Created` only observes the accepted output. This
/// model carries the bounded, content-free dimensions of ONE attempt — from
/// `startTranscription` arming to the session's terminalization in
/// `clearTranscriptionState` — so those dispositions can be counted.
///
/// It is the ambient-capture sibling of `PTTAttemptLifecycleRecorder` (which
/// owns PTT turns and must not be overloaded for ambient capture).
///
/// Privacy boundary: every field is a low-cardinality bucket, boolean, or
/// opaque per-attempt UUID. No transcript text, audio, sample counts, device
/// names, file paths, or error strings — detail stays in the local log,
/// `Desktop Recording Error`, and Sentry.
struct CaptureAttemptOutcomeState {
  /// How the attempt was armed. Only intents already distinguished by the
  /// arming code are modeled; there is no third "armed" producer today.
  enum Intent: String {
    case userStart = "user_start"
    case auto
  }

  /// Coarse disposition of the attempt at terminalization. `idle_waiting_meeting`
  /// is an expected Meetings-mode wait and must never be classified as `error`;
  /// `pending` is only emitted by the next-run crash-recovery hook for attempts
  /// whose process died mid-flight (their dimensions died with the process, so
  /// the recovery record carries only the join key).
  enum TerminalReason: String {
    case completed
    case cancelled
    case idleWaitingMeeting = "idle_waiting_meeting"
    case error
    case pending
    case unknown
  }

  /// Opaque, stable id for the whole attempt (one arming → one terminalization).
  /// Shared with `Desktop Recording Started`/`Stopped`, persisted on every
  /// `TranscriptionSessionRecord` created during the attempt, and attached to
  /// `Memory Created` so the accepted-conversation outcome can join the attempt
  /// even when finalization completes minutes later or after a crash.
  let attemptId: String

  /// The user-owned recording policy at arming (`AssistantSettings.AudioRecordingMode`
  /// rawValue: "always" / "onlyMeetings"). A mid-attempt mode switch is not
  /// rewritten into the attempt's identity.
  let mode: String

  /// How this attempt was armed.
  let intent: Intent

  /// Mic permission was granted AND the meeting gate allowed capture to run at
  /// least once during the attempt.
  private(set) var captureEligible = false

  /// At least one audio chunk was delivered by mic or system capture.
  private(set) var firstAudioFrame = false

  /// At least one transcript segment was appended during the attempt.
  private(set) var speechObserved = false

  /// A backend conversation from this attempt was accepted (`Memory Created`
  /// path) before the outcome was emitted.
  private(set) var conversationAccepted = false

  /// An error path initiated this terminalization (mic-start failure, silent
  /// capture exhausted, STT fallback stop, BLE loss).
  private(set) var errorTerminal = false

  /// The attempt spent time in Only-during-meetings mode with the capture gate
  /// closed (no meeting detected yet).
  private(set) var idleMeetingWait = false

  init(mode: String, intent: Intent) {
    attemptId = UUID().uuidString.lowercased()
    self.mode = mode
    self.intent = intent
  }

  init(attemptId: String, mode: String, intent: Intent) {
    self.attemptId = attemptId
    self.mode = mode
    self.intent = intent
  }

  mutating func noteCaptureEligible() { captureEligible = true }
  mutating func noteFirstAudioFrame() { firstAudioFrame = true }
  mutating func noteSpeech() { speechObserved = true }
  mutating func noteConversationAccepted() { conversationAccepted = true }
  mutating func noteErrorTerminal() { errorTerminal = true }
  mutating func noteIdleMeetingWait() { idleMeetingWait = true }

  /// Pure disposition mapping, testable without AppState.
  ///
  /// Order: a marked error path is an error regardless of what followed.
  /// A Meetings-mode attempt that never delivered an audio frame terminated
  /// while waiting for a meeting — `idle_waiting_meeting`, never `error`.
  /// Otherwise normal terminal reasons with observed audio are `completed`,
  /// and an armed-but-silent attempt ended by its owner is `cancelled`.
  static func terminalReason(
    finalizationReason: TranscriptionFinalizationReason,
    mode: String,
    firstAudioFrame: Bool,
    errorTerminal: Bool
  ) -> TerminalReason {
    if errorTerminal {
      return .error
    }
    if mode == AssistantSettings.AudioRecordingMode.onlyMeetings.rawValue, !firstAudioFrame {
      return .idleWaitingMeeting
    }
    switch finalizationReason {
    case .userStop, .finishAndContinue, .meetingStarted, .meetingEnded, .maxDurationRotation:
      return firstAudioFrame ? .completed : .cancelled
    case .crashRecovery, .retry:
      return .pending
    }
  }

  /// Disposition of this attempt for the terminal event.
  func terminalReason(for finalizationReason: TranscriptionFinalizationReason) -> TerminalReason {
    Self.terminalReason(
      finalizationReason: finalizationReason,
      mode: mode,
      firstAudioFrame: firstAudioFrame,
      errorTerminal: errorTerminal)
  }
}

/// Records which attempts already had a conversation accepted, at the one
/// funnel every desktop `Memory Created` emission passes through
/// (`AnalyticsManager.conversationCreated`). The live attempt consumes its
/// entry when the outcome event is emitted; entries for attempts that never
/// terminalize are bounded by accepted-conversation volume.
@MainActor
enum CaptureAttemptAcceptanceRegistry {
  private static var acceptedAttemptIds: Set<String> = []

  static func noteAccepted(_ attemptId: String) {
    acceptedAttemptIds.insert(attemptId)
  }

  /// Returns whether an acceptance was recorded, and clears it.
  static func consumeAccepted(_ attemptId: String) -> Bool {
    acceptedAttemptIds.remove(attemptId) != nil
  }

  static func resetForTests() {
    acceptedAttemptIds.removeAll()
  }
}

/// Audio chunks arrive on capture-queue threads; this latch coalesces
/// "first chunk observed" into at most one main-actor note per capture start.
/// Idempotent against the attempt state it feeds, so a paused/resumed or
/// rebuilt capture re-arming a fresh latch cannot double-count.
final class CaptureAttemptFirstAudioFrameLatch: @unchecked Sendable {
  private let lock = NSLock()
  private var noted = false

  func noteFirstAudioFrame(_ note: @escaping @MainActor () -> Void) {
    let shouldNote = lock.withLock {
      if noted {
        return false
      }
      noted = true
      return true
    }
    if shouldNote {
      Task { @MainActor in note() }
    }
  }
}
