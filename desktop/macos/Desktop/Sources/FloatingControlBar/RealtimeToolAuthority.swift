import CryptoKit
import Foundation
import VoiceTurnDomain

struct RealtimeAuthorizedToolInvocation {
  let invocationID: String
  let binding: ExternalSurfaceRunBinding
  let turnID: VoiceTurnID
  let callID: VoiceToolCallID
  let effectIdentity: VoiceEffectIdentity
  let canonicalToolName: String
  let inputHash: String
  let sourceObjectID: ObjectIdentifier
  let turnEpoch: Int
}

enum RealtimeAuthorizedToolOwnership {
  static func accepts(
    command: AuthorizedToolExecution,
    invocation: RealtimeAuthorizedToolInvocation,
    activeTurnID: VoiceTurnID?,
    activeToolIdentity: VoiceEffectIdentity?,
    activeSourceObjectID: ObjectIdentifier?,
    currentTurnEpoch: Int
  ) -> Bool {
    command.executor == .realtimeHub
      && command.surfaceKind == "realtime_voice"
      && command.invocationID == invocation.invocationID
      && command.ownerID == invocation.binding.ownerID
      && command.sessionID == invocation.binding.sessionID
      && command.runID == invocation.binding.runID
      && command.attemptID == invocation.binding.attemptID
      && command.canonicalToolName == invocation.canonicalToolName
      && command.inputHash == invocation.inputHash
      && activeTurnID == invocation.turnID
      && activeToolIdentity == invocation.effectIdentity
      && activeSourceObjectID == invocation.sourceObjectID
      && currentTurnEpoch == invocation.turnEpoch
  }
}

enum RealtimeExternalRunTerminalPolicy {
  static func status(for reason: VoiceTurnTerminalReason) -> ExternalSurfaceRunTerminalStatus {
    switch reason {
    case .success:
      return .completed
    case .tooShort, .silentRejected, .cancelled, .ownerChanged, .interruptedByBargeIn,
      .explicitInterrupt, .cleanup:
      return .cancelled
    case .permissionDenied, .captureFailed, .captureNotReady, .transcriptionFailed,
      .providerFailed, .noNetwork, .providerNoResponse, .hubWarmTimeout, .deferredCommitTimeout,
      .bargeInReplacementTimeout, .toolTimeout, .playbackFailed, .journalFailed:
      return .failed
    }
  }
}

/// Journal status as a total function of the reducer's terminal reason and the
/// turn's full-answer delivery state.
///
/// The journal is the model's only memory across push-to-talk presses, and the
/// kernel prompt calls it canonical. A turn that was cut off — barge-in, provider
/// error, timeout — must therefore not be recorded as a completed answer: the
/// model reads its own half-sentence back as finished work and re-asks or moves on.
///
/// The inverse lie is just as corrosive: a reply whose audio fully drained before
/// the user spoke again was heard in full, and journaling it `.failed` teaches the
/// model its own delivered answer was cut off — so it re-delivers or "corrects"
/// that answer turns later, out of context (measured on 2026-09-04: three fully
/// spoken replies in one session journaled `interrupted_by_barge_in` failures,
/// followed by exactly that recurrence). A barge-in after playback drained is an
/// interruption of the *silence*, not of the answer, and journals `.completed`.
///
/// Delivery also gates `.success` itself: a turn the reducer terminalized without
/// any full-answer playback draining never delivered its answer, and journals
/// `.failed` (#12743: the 12:45 potion answer was sealed `.completed` while only
/// "Let me verify." was ever spoken). The turn-done funnel writes while playback
/// is still pending — that optimistic `.completed` is corrected by the reducer's
/// terminal through `VoiceJournalSealedRowRevisionPolicy`, never by reading
/// "still draining" as "never played".
///
/// `KernelJournalTurnStatus` has no `cancelled` case, so every non-delivered
/// non-success reason maps to `.failed` and the precise reason travels in
/// `metadata.terminalReason`. That distinction matters for measurement (a barge-in
/// is not a defect), never for whether the turn may claim completion.
enum VoiceTurnJournalStatusPolicy {
  /// What the writer knows about full-answer playback delivery when it computes
  /// the assistant row's status.
  enum AnswerDelivery {
    /// Playback had not resolved yet. The turn-done funnel journals at
    /// provider-response-finish, while local playback is usually still
    /// draining — "not yet drained" must never be read as "never played", so a
    /// `.success` row stays optimistically `.completed` here and the reducer's
    /// terminal revises it if the answer never reaches the user.
    case pending
    case delivered
    case notDelivered
  }

  static func status(for reason: VoiceTurnTerminalReason) -> KernelJournalTurnStatus {
    status(for: reason, delivery: .pending)
  }

  static func status(
    for reason: VoiceTurnTerminalReason,
    answerDelivered: Bool
  ) -> KernelJournalTurnStatus {
    status(for: reason, delivery: answerDelivered ? .delivered : .notDelivered)
  }

  static func status(
    for reason: VoiceTurnTerminalReason,
    delivery: AnswerDelivery
  ) -> KernelJournalTurnStatus {
    switch reason {
    case .success:
      // A turn the reducer terminalized `.success` without any full-answer
      // playback draining never delivered its answer; the journal must not
      // teach the model the user heard an answer they never did (#12743).
      return delivery == .notDelivered ? .failed : .completed
    case .interruptedByBargeIn, .explicitInterrupt:
      return delivery == .delivered ? .completed : .failed
    case .tooShort, .silentRejected, .cancelled, .ownerChanged,
      .cleanup, .permissionDenied, .captureFailed, .captureNotReady,
      .transcriptionFailed, .providerFailed, .noNetwork, .providerNoResponse, .hubWarmTimeout,
      .deferredCommitTimeout, .bargeInReplacementTimeout, .toolTimeout, .playbackFailed,
      .journalFailed:
      return .failed
    }
  }
}

/// Whether the reducer's terminal may revise an assistant row the turn-done
/// funnel already sealed `.completed`.
///
/// The funnel journals at provider-response-finish — before the reducer's
/// playback fence resolves — so a `.success` row is optimistic by design. When
/// the reducer later terminalizes without having delivered the answer (playback
/// failed, a barge-in cut the reply before it drained, or `.success` with no
/// full-answer playback at all), the sealed row must stop claiming a completed
/// answer: the journal is the model's only memory, and a completed row for an
/// unheard answer is how later turns believe the user was answered (#12743).
///
/// Delivered outcomes never revise: a barge-in after playback drained
/// interrupts the silence, not the answer (#12730 semantics), and a later
/// journal failure must not rewrite a delivered response as missing. Reasons
/// outside the delivery set either never reach a sealed row (capture-time
/// journaling already carries their outcome) or must not be reinterpreted
/// after the fact.
enum VoiceJournalSealedRowRevisionPolicy {
  struct Revision: Equatable {
    let status: KernelJournalTurnStatus
    let terminalReason: String
  }

  static func revision(
    forTerminalReason reason: VoiceTurnTerminalReason,
    answerDelivered: Bool,
    sealedCompletedRowExists: Bool
  ) -> Revision? {
    guard sealedCompletedRowExists, revisableReasons.contains(reason) else { return nil }
    guard
      VoiceTurnJournalStatusPolicy.status(for: reason, answerDelivered: answerDelivered)
        == .failed
    else { return nil }
    // The reducer terminal said `.success` while the answer never drained;
    // "success" would be a false truncation cause on a failed row.
    let terminalReason = reason == .success ? "answer_not_delivered" : reason.rawValue
    return Revision(status: .failed, terminalReason: terminalReason)
  }

  private static let revisableReasons: Set<VoiceTurnTerminalReason> = [
    .success, .interruptedByBargeIn, .explicitInterrupt, .playbackFailed,
  ]
}

enum RealtimeExternalRunPromptPolicy {
  enum Source: Equatable {
    case finalizedTranscript
    case partialTranscript
    case authorizedToolFallback
  }

  struct Selection: Equatable {
    let prompt: String
    let source: Source
  }

  /// A realtime tool call has already passed the current-session, current-turn,
  /// and reducer-owned capability checks before this policy is reached. Gemini
  /// can send that call before (or instead of) a final input transcript and wait
  /// for the result, so waiting for a final transcript here creates a circular
  /// wait. A partial transcript is still the user's actual request and retains
  /// target-sensitive policy context (for example, rejecting a request about
  /// another app). Permission tools fail closed if no transcript exists at all:
  /// their type alone must not fabricate user authority or discard an external
  /// app target.
  static func promptForAuthorizedTool(
    transcript: String,
    isFinal: Bool,
    toolName: String = "",
    arguments: [String: Any] = [:]
  ) -> Selection? {
    let prompt = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    if !prompt.isEmpty {
      return Selection(
        prompt: prompt,
        source: isFinal ? .finalizedTranscript : .partialTranscript)
    }
    guard !isPermissionTool(toolName, arguments: arguments) else { return nil }
    return Selection(
      prompt:
        "A realtime voice provider has already authorized one tool invocation for this active turn. Execute only that separately authorized invocation. Do not infer, expand, or perform any additional user request.",
      source: .authorizedToolFallback)
  }

  private static func isPermissionTool(_ toolName: String, arguments: [String: Any]) -> Bool {
    RealtimePermissionToolIdentityPolicy.contains(toolName)
  }
}

enum RealtimePermissionToolIdentityPolicy {
  private static let names: Set<String> = [
    GeneratedSwiftTool.requestPermission.rawValue,
    GeneratedSwiftTool.checkPermissionStatus.rawValue,
  ]

  static func contains(_ toolName: String) -> Bool {
    names.contains(toolName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
  }
}

/// `ptt_test_turn` injects text as the authoritative user request while still
/// exercising the real provider, reducer, kernel, and native-tool path. Live
/// providers may emit a bogus input transcription for the synthetic silence
/// used to keep their activity window valid. That transport artifact must not
/// replace the exact harness request used for authorization or persistence.
enum RealtimeAutomationTranscriptOverridePolicy {
  struct Selection: Equatable {
    let text: String
    let isFinal: Bool
    let usedOverride: Bool
  }

  static func select(
    providerText: String,
    providerIsFinal: Bool,
    forcedText: String?
  ) -> Selection {
    let forced = forcedText?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !forced.isEmpty {
      return Selection(text: forced, isFinal: true, usedOverride: true)
    }
    return Selection(text: providerText, isFinal: providerIsFinal, usedOverride: false)
  }
}

@MainActor
enum RealtimeAutomationTurnHarness {
  /// Synthetic PTT owns a real reducer capture boundary even though it does not
  /// start CoreAudio. Without this event, spoken fixtures longer than the
  /// capture-start deadline terminalize before their provider commit.
  static func begin(on coordinator: VoiceTurnCoordinator) -> VoiceTurnID {
    let turnID = coordinator.begin(intent: .automation)
    coordinator.publish(.captureStarted(turnID: turnID, captureID: VoiceCaptureID(1)))
    return turnID
  }
}

/// Voice providers do not have a uniform "input transcript final" event. OpenAI
/// eventually emits a final, while Gemini Live may only send non-final updates
/// before it proposes a native permission tool. A permission proposal therefore
/// collects the bounded live-transcription window, then requires the stream to
/// be quiet rather than deriving authority from the provider's type-only tool
/// arguments. Waiting through the complete window matters: an early quiet gap
/// must not authorize before a later suffix can name a non-Omi app. The bounded
/// wait keeps the provider's tool turn moving and never converts missing context
/// into an Omi permission request.
enum RealtimePermissionTranscriptSettlementPolicy {
  static let quietPeriod: TimeInterval = 0.2
  static let maximumWait: TimeInterval = 1.0

  enum Decision: Equatable {
    case execute
    case wait(TimeInterval)
    case reject
  }

  static func decision(
    toolName: String,
    transcriptIsFinal: Bool,
    hasTranscript: Bool,
    lastTranscriptUpdate: Date?,
    requestStartedAt: Date,
    now: Date
  ) -> Decision {
    guard isPermissionTool(toolName) else { return .execute }
    guard !transcriptIsFinal else { return hasTranscript ? .execute : .reject }

    let deadline = requestStartedAt.addingTimeInterval(maximumWait)
    guard now >= deadline else {
      return .wait(deadline.timeIntervalSince(now))
    }
    guard
      hasTranscript,
      let lastTranscriptUpdate,
      now >= lastTranscriptUpdate.addingTimeInterval(quietPeriod)
    else { return .reject }
    return .execute
  }

  static func isPermissionTool(_ toolName: String) -> Bool {
    RealtimePermissionToolIdentityPolicy.contains(toolName)
  }
}

enum RealtimeToolTurnOwnership {
  static func accepts(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    sourceObjectID: ObjectIdentifier,
    turnEpoch: Int,
    activeTurnID: VoiceTurnID?,
    activeToolIdentity: VoiceEffectIdentity?,
    activeSourceObjectID: ObjectIdentifier?,
    currentTurnEpoch: Int
  ) -> Bool {
    activeTurnID == turnID
      && activeToolIdentity == identity
      && activeSourceObjectID == sourceObjectID
      && currentTurnEpoch == turnEpoch
      && identity.generation == turnID.rawValue
  }
}

enum RealtimeExternalToolInvocationIdentity {
  static func make(turnID: VoiceTurnID, providerCallID: String, toolName: String) -> String {
    let canonical = [
      turnID.rawValue.uuidString.lowercased(),
      "\(providerCallID.utf8.count):\(providerCallID)",
      "\(toolName.utf8.count):\(toolName)",
    ].joined(separator: "|")
    let digest = SHA256.hash(data: Data(canonical.utf8))
      .map { String(format: "%02x", $0) }
      .joined()
    return "voice-tool:\(digest)"
  }
}

enum RealtimeAuthorizedInvocationReplayGate {
  static func shouldExecute(
    invocationID: String,
    completedInvocationIDs: Set<String>
  ) -> Bool {
    !completedInvocationIDs.contains(invocationID)
  }
}
