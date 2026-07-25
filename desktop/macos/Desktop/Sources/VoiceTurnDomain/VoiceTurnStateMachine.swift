import Foundation

// MARK: - Typed identities

package struct VoiceTurnID: Hashable, Equatable, Sendable, CustomStringConvertible {
  package let rawValue: UUID

  package init(_ rawValue: UUID = UUID()) {
    self.rawValue = rawValue
  }

  package var description: String { rawValue.uuidString }
}

package struct VoiceCaptureID: Hashable, Equatable, Sendable, CustomStringConvertible {
  package let rawValue: UInt64

  package init(_ rawValue: UInt64) {
    self.rawValue = rawValue
  }

  package var description: String { String(rawValue) }
}

package struct VoiceSessionID: Hashable, Equatable, Sendable, CustomStringConvertible {
  package let rawValue: UUID

  package init(_ rawValue: UUID = UUID()) {
    self.rawValue = rawValue
  }

  package var description: String { rawValue.uuidString }
}

package struct VoiceResponseID: Hashable, Equatable, Sendable, CustomStringConvertible {
  package let rawValue: String

  package init(_ rawValue: String) {
    self.rawValue = rawValue
  }

  package var description: String { rawValue }
}

package struct VoiceToolCallID: Hashable, Equatable, Sendable, CustomStringConvertible {
  package let rawValue: String

  package init(_ rawValue: String) {
    self.rawValue = rawValue
  }

  package var description: String { rawValue }
}

package struct VoiceLeaseID: Hashable, Equatable, Sendable, CustomStringConvertible {
  package let rawValue: UUID

  package init(_ rawValue: UUID = UUID()) {
    self.rawValue = rawValue
  }

  package var description: String { rawValue.uuidString }
}

package struct VoiceContextSnapshotVersion: Hashable, Equatable, Sendable, CustomStringConvertible {
  package let rawValue: String

  package init(_ rawValue: String) {
    self.rawValue = rawValue
  }

  package var description: String { rawValue }
}

/// Identity for one asynchronous effect within a logical turn. `generation`
/// is the immutable turn generation; `effectID` distinguishes remints,
/// reconnects, tool attempts, playback attempts, and journal writes that happen
/// without changing the logical turn ID.
package struct VoiceEffectIdentity: Hashable, Equatable, Sendable {
  package let generation: UUID
  package let effectID: UInt64

  package init(turnID: VoiceTurnID, effectID: UInt64) {
    generation = turnID.rawValue
    self.effectID = effectID
  }
}

/// The screenshot half of a current-screen answer remains an active tool until
/// native code either verifies the paired report or fails the protocol closed.
/// Keeping this token in the reducer prevents a provider callback from using a
/// stale or cross-turn image, while a verified report still requires the
/// provider to answer the user's original request.
package struct VoiceScreenEvidenceProtocolToken: Equatable, Sendable {
  package let turnID: VoiceTurnID
  package let screenshotCallID: VoiceToolCallID
  package let screenshotIdentity: VoiceEffectIdentity

  package init(
    turnID: VoiceTurnID,
    screenshotCallID: VoiceToolCallID,
    screenshotIdentity: VoiceEffectIdentity
  ) {
    self.turnID = turnID
    self.screenshotCallID = screenshotCallID
    self.screenshotIdentity = screenshotIdentity
  }
}

/// A local result may be the canonical user-visible answer for a tool-driven
/// turn. The provider must not hold that answer open for an additional text or
/// audio continuation.
package enum VoiceAuthoritativeLocalResultKind: Equatable, Sendable {
  case spawnReceipt
  case screenEvidenceFailure
}

// MARK: - State

package enum VoiceTurnIntent: String, Equatable, Sendable {
  case hold
  case locked
  case automation
}

package enum VoiceTurnRoute: Equatable, Sendable {
  case undecided
  case hubWarmWait
  case hub(sessionID: VoiceSessionID?)
  case omniSTT
  case deepgramBatch
  case deepgramLive
}

package enum VoiceContextOutcome: Equatable, Sendable {
  case captured(VoiceContextSnapshotVersion)
  case omitted(reason: String)
}

package enum VoiceProviderConnection: Equatable, Sendable {
  case ready
  case reconnecting(identity: VoiceEffectIdentity, previousSessionID: VoiceSessionID?)
  case replacing(identity: VoiceEffectIdentity, previousResponseID: VoiceResponseID?)
}

package enum VoiceJournalFinalization: Equatable, Sendable {
  case pending
  case writing(VoiceEffectIdentity)
  case accepted(VoiceEffectIdentity)
}

package enum VoiceTranscriptionFinalizationMode: Equatable, Sendable {
  case omni
  case live
}

package enum VoiceOutputLane: String, Equatable, Sendable, CaseIterable {
  case nativeRealtime = "native_realtime"
  case selectedVoiceFallback = "selected_voice_fallback"
  case deterministicAgentAck = "deterministic_agent_ack"
  case deterministicScreenEvidence = "deterministic_screen_evidence"
  case filler
  case systemVoiceFallback = "system_voice_fallback"
}

package struct VoiceOutputLease: Equatable, Sendable {
  package let id: VoiceLeaseID
  package let turnID: VoiceTurnID
  package let lane: VoiceOutputLane
  package let identity: VoiceEffectIdentity

  package init(
    id: VoiceLeaseID,
    turnID: VoiceTurnID,
    lane: VoiceOutputLane,
    identity: VoiceEffectIdentity
  ) {
    self.id = id
    self.turnID = turnID
    self.lane = lane
    self.identity = identity
  }
}

package enum VoiceOutputDecision: Equatable, Sendable {
  case acquired(VoiceOutputLease)
  case denied(active: VoiceOutputLease)
  case staleTurn
}

package struct VoiceOutputSnapshot: Equatable, Sendable {
  package let turnID: VoiceTurnID?
  package let activeLease: VoiceOutputLease?
  package let providerOutputSuppressed: Bool

  package init(turnID: VoiceTurnID?, activeLease: VoiceOutputLease?, providerOutputSuppressed: Bool) {
    self.turnID = turnID
    self.activeLease = activeLease
    self.providerOutputSuppressed = providerOutputSuppressed
  }
}

package enum VoiceOutputHandoffPolicy {
  package static func fillerCanYield(
    active: VoiceOutputLease,
    to incomingLane: VoiceOutputLane,
    turnID: VoiceTurnID
  ) -> Bool {
    active.turnID == turnID && active.lane == .filler && incomingLane != .filler
  }
}

package enum VoiceTurnTerminalReason: String, Equatable, Sendable, CaseIterable {
  case success
  case tooShort = "too_short"
  case silentRejected = "silent_rejected"
  case cancelled
  case ownerChanged = "owner_changed"
  case interruptedByBargeIn = "interrupted_by_barge_in"
  case permissionDenied = "permission_denied"
  case captureFailed = "capture_failed"
  case transcriptionFailed = "transcription_failed"
  case providerFailed = "provider_failed"
  case providerNoResponse = "provider_no_response"
  case hubWarmTimeout = "hub_warm_timeout"
  case deferredCommitTimeout = "deferred_commit_timeout"
  case bargeInReplacementTimeout = "barge_in_replacement_timeout"
  case toolTimeout = "tool_timeout"
  case playbackFailed = "playback_failed"
  case journalFailed = "journal_failed"
  case explicitInterrupt = "explicit_interrupt"
  case cleanup
}

package enum VoiceTurnPhase: Equatable, Sendable {
  case idle
  case pendingLockDecision
  case recording
  case lockedRecording
  case finalizing
  case awaitingResponse
  case awaitingTools
  case awaitingJournal
  case playing(VoiceOutputLane)
  case terminal(VoiceTurnTerminalReason)

  package var isRecording: Bool {
    self == .recording || self == .lockedRecording || self == .pendingLockDecision
  }

  package var isTerminal: Bool {
    if case .terminal = self { return true }
    return false
  }
}

package enum VoiceTurnDeadline: String, Equatable, Hashable, Sendable, CaseIterable {
  case lockDecision = "lock_decision"
  case captureStart = "capture_start"
  case hubWarm = "hub_warm"
  case transcription = "transcription"
  case providerResponse = "provider_response"
  case pendingTools = "pending_tools"
  case screenEvidenceProtocol = "screen_evidence_protocol"
  case deferredCommit = "deferred_commit"
  case bargeInReplacement = "barge_in_replacement"
  case playbackDrain = "playback_drain"
  case providerReconnect = "provider_reconnect"
  case journalFinalization = "journal_finalization"
  case transcriptionFinalization = "transcription_finalization"
  case hintVisibility = "hint_visibility"
}

package struct VoiceTurnUIProjection: Equatable, Sendable {
  package var isListening = false
  package var isLocked = false
  package var transcript = ""
  package var hint = ""
  package var isThinking = false
  package var isResponseWaiting = false
  package var isResponseActive = false

  package static let idle = VoiceTurnUIProjection()
}

/// Pure copy / status-banner projections over reducer state and terminal reasons.
/// Every string here is derived from existing `VoiceTurnUIProjection` / `VoiceTurnTerminalReason`
/// — not a second lifecycle enum.
package enum VoiceTurnUICopy {
  package static let transcribingProgress = "Transcribing…"

  /// Banner text is reserved for actionable capture/provider failures. Normal
  /// recording, transcription, fallback, and barge-in state stays visual.
  package static func statusBannerText(for projection: VoiceTurnUIProjection) -> String {
    projection.hint
  }

  /// User-facing terminal hint. Branches on typed reason only.
  package static func terminalHint(for reason: VoiceTurnTerminalReason) -> String? {
    switch reason {
    case .tooShort:
      return "Hold longer to record"
    case .captureFailed:
      return "Microphone unavailable — try again"
    case .transcriptionFailed:
      return "Couldn't transcribe that — try again"
    case .journalFailed:
      return "Couldn't save that reply — try again"
    case .providerFailed, .providerNoResponse, .deferredCommitTimeout:
      return "Couldn't get a voice reply — try again"
    case .bargeInReplacementTimeout:
      return "Previous reply was interrupted — try again"
    case .toolTimeout:
      return "A tool took too long — try again"
    case .playbackFailed:
      return "Audio playback failed"
    case .interruptedByBargeIn:
      // Applied on the replacement turn in `.start` (this turn is replaced immediately).
      return nil
    case .success, .silentRejected, .cancelled, .ownerChanged, .explicitInterrupt,
      .permissionDenied, .hubWarmTimeout, .cleanup:
      return nil
    }
  }
}

package enum VoiceTurnDebugPresentationState: String, Equatable, Sendable {
  case idle
  case listening
  case thinking
  case answering

  package var projection: VoiceTurnUIProjection {
    switch self {
    case .idle:
      return .idle
    case .listening:
      return VoiceTurnUIProjection(isListening: true)
    case .thinking:
      return VoiceTurnUIProjection(isThinking: true)
    case .answering:
      return VoiceTurnUIProjection(isResponseActive: true)
    }
  }
}

package struct VoiceTurn: Equatable, Sendable {
  package let id: VoiceTurnID
  /// Immutable authenticated owner captured when the physical voice turn starts.
  /// Every provider, tool, and journal driver must fence against this identity;
  /// reading the ambient account after an `await` can otherwise route owner A's
  /// speech or response into owner B's session.
  package let ownerID: String?
  package var supersededTurnID: VoiceTurnID?
  package var intent: VoiceTurnIntent
  package var phase: VoiceTurnPhase
  package var route: VoiceTurnRoute
  package var captureID: VoiceCaptureID?
  package var sessionID: VoiceSessionID?
  package var responseID: VoiceResponseID?
  package var pendingToolCallIDs: Set<VoiceToolCallID>
  package var toolEffectIdentities: [VoiceToolCallID: VoiceEffectIdentity]
  package var screenEvidenceProtocol: VoiceScreenEvidenceProtocolToken?
  package var activeLease: VoiceOutputLease?
  package var providerFinished: Bool
  package var postToolContinuationRequired: Bool
  package var hubCommitPending: Bool
  package var providerEffectIdentity: VoiceEffectIdentity?
  package var transcriptionEffectIdentity: VoiceEffectIdentity?
  package var transcriptionCompletionClaimed: Bool
  package var providerConnection: VoiceProviderConnection
  package var contextOutcome: VoiceContextOutcome?
  package var journalFinalization: VoiceJournalFinalization
  package var transcriptionFinalizationMode: VoiceTranscriptionFinalizationMode?
  package var providerOutputSuppressed: Bool
  package var nextEffectID: UInt64
  package var reservedEffectIdentities: Set<VoiceEffectIdentity>
  package var deadlines: Set<VoiceTurnDeadline>
  package var projection: VoiceTurnUIProjection
  package var terminalReason: VoiceTurnTerminalReason?

  package init(
    id: VoiceTurnID,
    ownerID: String? = nil,
    intent: VoiceTurnIntent,
    supersededTurnID: VoiceTurnID? = nil
  ) {
    self.id = id
    self.ownerID = ownerID
    self.supersededTurnID = supersededTurnID
    self.intent = intent
    phase = intent == .locked ? .lockedRecording : .recording
    route = .undecided
    pendingToolCallIDs = []
    toolEffectIdentities = [:]
    screenEvidenceProtocol = nil
    providerFinished = false
    postToolContinuationRequired = false
    hubCommitPending = false
    providerEffectIdentity = nil
    transcriptionEffectIdentity = nil
    transcriptionCompletionClaimed = false
    providerConnection = .ready
    contextOutcome = nil
    journalFinalization = .pending
    transcriptionFinalizationMode = nil
    providerOutputSuppressed = false
    nextEffectID = 1
    reservedEffectIdentities = []
    deadlines = []
    projection = VoiceTurnUIProjection(
      isListening: true,
      isLocked: intent == .locked,
      transcript: "",
      hint: "",
      isThinking: false,
      isResponseWaiting: false,
      isResponseActive: false)
  }
}

package struct VoiceTurnTerminalRecord: Equatable, Sendable {
  package let turnID: VoiceTurnID
  package let reason: VoiceTurnTerminalReason
  package let route: VoiceTurnRoute

  package init(
    turnID: VoiceTurnID,
    reason: VoiceTurnTerminalReason,
    route: VoiceTurnRoute = .undecided
  ) {
    self.turnID = turnID
    self.reason = reason
    self.route = route
  }
}

package struct VoiceTurnModel: Equatable, Sendable {
  package var turn: VoiceTurn?
  package var lastTerminal: VoiceTurnTerminalRecord?
  package var staleEventCount = 0
  package var invalidTransitionCount = 0
  package var duplicateTerminalCount = 0

  package init(
    turn: VoiceTurn? = nil,
    lastTerminal: VoiceTurnTerminalRecord? = nil,
    staleEventCount: Int = 0,
    invalidTransitionCount: Int = 0,
    duplicateTerminalCount: Int = 0
  ) {
    self.turn = turn
    self.lastTerminal = lastTerminal
    self.staleEventCount = staleEventCount
    self.invalidTransitionCount = invalidTransitionCount
    self.duplicateTerminalCount = duplicateTerminalCount
  }

  package static let idle = VoiceTurnModel()
}

// MARK: - Events and effects

enum VoiceTurnEvent: Equatable, Sendable {
  case start(turnID: VoiceTurnID, ownerID: String?, intent: VoiceTurnIntent)
  case effectIdentityReserved(turnID: VoiceTurnID)
  case transcriptionProviderStartedScoped(turnID: VoiceTurnID, identity: VoiceEffectIdentity)
  case transcriptionCompletionClaimedScoped(turnID: VoiceTurnID, identity: VoiceEffectIdentity)
  case openLockWindow(turnID: VoiceTurnID)
  case lock(turnID: VoiceTurnID)
  case finalize(turnID: VoiceTurnID)
  case captureStarted(turnID: VoiceTurnID, captureID: VoiceCaptureID)
  case captureFailed(turnID: VoiceTurnID, captureID: VoiceCaptureID?, message: String)
  case selectRoute(turnID: VoiceTurnID, route: VoiceTurnRoute)
  case hubReady(turnID: VoiceTurnID, sessionID: VoiceSessionID)
  /// The physical realtime socket is ready, but the context-bound input admission
  /// rejected this turn. This is distinct from transport readiness: the warm deadline
  /// was already cancelled by `hubReady`, so the reducer must explicitly restore the
  /// bounded transcription fallback instead of leaving a finalizing turn parked.
  case hubAdmissionRejected(turnID: VoiceTurnID)
  case hubCommitAccepted(
    turnID: VoiceTurnID, sessionID: VoiceSessionID, responseID: VoiceResponseID?)
  case hubCommitClaimed(turnID: VoiceTurnID)
  case hubCommitDeferred(turnID: VoiceTurnID)
  case hubCommitDeferredForReplacement(turnID: VoiceTurnID)
  case providerReconnectStarted(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity, previousSessionID: VoiceSessionID?)
  case providerReconnected(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity, sessionID: VoiceSessionID)
  case providerReconnectFailed(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity, message: String)
  case providerReplacementStarted(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity,
    previousResponseID: VoiceResponseID?, nextResponseID: VoiceResponseID)
  case providerReplacementReady(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity,
    sessionID: VoiceSessionID, responseID: VoiceResponseID)
  case providerReplacementFailed(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity, message: String)
  case contextResolved(turnID: VoiceTurnID, outcome: VoiceContextOutcome)
  case transcriptionStarted(turnID: VoiceTurnID)
  case transcriptionFinal(turnID: VoiceTurnID, text: String)
  case transcriptionFailed(turnID: VoiceTurnID, message: String)
  case providerResponseStartedScoped(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity,
    sessionID: VoiceSessionID?, responseID: VoiceResponseID?)
  case providerTurnFinishedScoped(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity,
    sessionID: VoiceSessionID?, responseID: VoiceResponseID?)
  case toolStartedScoped(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity, callID: VoiceToolCallID)
  /// A native result is already the complete user-visible answer for a tool.
  /// It replaces, rather than races, an optional provider continuation.
  case authoritativeLocalResultAcceptedScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    callID: VoiceToolCallID,
    kind: VoiceAuthoritativeLocalResultKind)
  /// A screenshot/report pair has been verified for the active provider turn.
  /// This closes the local provenance protocol only; the provider must still
  /// continue and answer the original user request from that image.
  case screenEvidenceReportVerifiedScoped(
    turnID: VoiceTurnID,
    screenshotIdentity: VoiceEffectIdentity,
    screenshotCallID: VoiceToolCallID,
    reportIdentity: VoiceEffectIdentity,
    reportCallID: VoiceToolCallID)
  /// A screenshot tool returned a recoverable unavailable result (such as
  /// missing Screen Recording permission). Clear only the local provenance
  /// protocol so the provider can continue in its normal voice lane.
  case screenEvidenceUnavailableScoped(
    turnID: VoiceTurnID,
    screenshotIdentity: VoiceEffectIdentity,
    screenshotCallID: VoiceToolCallID)
  case screenEvidenceProtocolStartedScoped(
    turnID: VoiceTurnID,
    token: VoiceScreenEvidenceProtocolToken,
    expiresAfter: TimeInterval)
  case toolFinishedScoped(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity, callID: VoiceToolCallID)
  case playbackStartedScoped(turnID: VoiceTurnID, lease: VoiceOutputLease)
  /// Native provider output is still arriving for this exact lease. This is a
  /// liveness heartbeat, not a second playback start: long valid replies must
  /// not hit the drain watchdog solely because their first PCM chunk was over
  /// thirty seconds ago.
  case playbackProgressScoped(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity, leaseID: VoiceLeaseID)
  case playbackDrainedScoped(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity, leaseID: VoiceLeaseID)
  case playbackFailedScoped(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity,
    leaseID: VoiceLeaseID?, message: String)
  case transcriptionFinalizationStarted(
    turnID: VoiceTurnID, mode: VoiceTranscriptionFinalizationMode)
  case transcriptionFinalizationCompleted(turnID: VoiceTurnID)
  case journalAccepted(turnID: VoiceTurnID, identity: VoiceEffectIdentity)
  case journalFailed(turnID: VoiceTurnID, identity: VoiceEffectIdentity, message: String)
  case transcriptChanged(turnID: VoiceTurnID, text: String)
  case hintChanged(turnID: VoiceTurnID, text: String)
  case responseWaitingChanged(turnID: VoiceTurnID, active: Bool)
  case responseActiveChanged(turnID: VoiceTurnID, active: Bool)
  case debugPresentationChanged(
    turnID: VoiceTurnID, state: VoiceTurnDebugPresentationState)
  case clearPresentation(turnID: VoiceTurnID)
  case deadlineFired(turnID: VoiceTurnID, deadline: VoiceTurnDeadline)
  case finish(turnID: VoiceTurnID, reason: VoiceTurnTerminalReason)
  case cancel(turnID: VoiceTurnID, reason: VoiceTurnTerminalReason)
  case interrupt(turnID: VoiceTurnID)
  case cleanup
  case reset

  var turnID: VoiceTurnID? {
    switch self {
    case .start(let turnID, _, _), .effectIdentityReserved(let turnID),
      .transcriptionProviderStartedScoped(let turnID, _),
      .transcriptionCompletionClaimedScoped(let turnID, _),
      .openLockWindow(let turnID), .lock(let turnID),
      .finalize(let turnID), .captureStarted(let turnID, _), .captureFailed(let turnID, _, _),
      .selectRoute(let turnID, _), .hubReady(let turnID, _),
      .hubAdmissionRejected(let turnID),
      .hubCommitAccepted(let turnID, _, _), .hubCommitClaimed(let turnID),
      .hubCommitDeferred(let turnID),
      .hubCommitDeferredForReplacement(let turnID),
      .providerReconnectStarted(let turnID, _, _), .providerReconnected(let turnID, _, _),
      .providerReconnectFailed(let turnID, _, _),
      .providerReplacementStarted(let turnID, _, _, _),
      .providerReplacementReady(let turnID, _, _, _), .contextResolved(let turnID, _),
      .providerReplacementFailed(let turnID, _, _),
      .transcriptionStarted(let turnID), .transcriptionFinal(let turnID, _),
      .transcriptionFailed(let turnID, _),
      .providerResponseStartedScoped(let turnID, _, _, _),
      .providerTurnFinishedScoped(let turnID, _, _, _),
      .toolStartedScoped(let turnID, _, _),
      .authoritativeLocalResultAcceptedScoped(let turnID, _, _, _),
      .screenEvidenceReportVerifiedScoped(let turnID, _, _, _, _),
      .screenEvidenceUnavailableScoped(let turnID, _, _),
      .screenEvidenceProtocolStartedScoped(let turnID, _, _),
      .toolFinishedScoped(let turnID, _, _),
      .playbackStartedScoped(let turnID, _), .transcriptChanged(let turnID, _),
      .playbackProgressScoped(let turnID, _, _),
      .playbackDrainedScoped(let turnID, _, _),
      .playbackFailedScoped(let turnID, _, _, _),
      .transcriptionFinalizationStarted(let turnID, _),
      .transcriptionFinalizationCompleted(let turnID),
      .journalAccepted(let turnID, _),
      .journalFailed(let turnID, _, _),
      .hintChanged(let turnID, _), .responseWaitingChanged(let turnID, _),
      .responseActiveChanged(let turnID, _), .debugPresentationChanged(let turnID, _),
      .clearPresentation(let turnID),
      .deadlineFired(let turnID, _),
      .finish(let turnID, _), .cancel(let turnID, _), .interrupt(let turnID):
      return turnID
    case .cleanup, .reset:
      return nil
    }
  }

  /// A bounded diagnostics label that never includes transcript, hint, or error payloads.
  var diagnosticLabel: String {
    switch self {
    case .start: return "start"
    case .effectIdentityReserved: return "effect_identity_reserved"
    case .transcriptionProviderStartedScoped: return "transcription_provider_started_scoped"
    case .transcriptionCompletionClaimedScoped: return "transcription_completion_claimed_scoped"
    case .openLockWindow: return "open_lock_window"
    case .lock: return "lock"
    case .finalize: return "finalize"
    case .captureStarted: return "capture_started"
    case .captureFailed: return "capture_failed"
    case .selectRoute: return "select_route"
    case .hubReady: return "hub_ready"
    case .hubAdmissionRejected: return "hub_admission_rejected"
    case .hubCommitAccepted: return "hub_commit_accepted"
    case .hubCommitClaimed: return "hub_commit_claimed"
    case .hubCommitDeferred: return "hub_commit_deferred"
    case .hubCommitDeferredForReplacement: return "hub_commit_deferred_for_replacement"
    case .providerReconnectStarted: return "provider_reconnect_started"
    case .providerReconnected: return "provider_reconnected"
    case .providerReconnectFailed: return "provider_reconnect_failed"
    case .providerReplacementStarted: return "provider_replacement_started"
    case .providerReplacementReady: return "provider_replacement_ready"
    case .providerReplacementFailed: return "provider_replacement_failed"
    case .contextResolved: return "context_resolved"
    case .transcriptionStarted: return "transcription_started"
    case .transcriptionFinal: return "transcription_final"
    case .transcriptionFailed: return "transcription_failed"
    case .providerResponseStartedScoped: return "provider_response_started_scoped"
    case .providerTurnFinishedScoped: return "provider_turn_finished_scoped"
    case .toolStartedScoped: return "tool_started_scoped"
    case .authoritativeLocalResultAcceptedScoped: return "authoritative_local_result_accepted_scoped"
    case .screenEvidenceReportVerifiedScoped: return "screen_evidence_report_verified_scoped"
    case .screenEvidenceUnavailableScoped: return "screen_evidence_unavailable_scoped"
    case .screenEvidenceProtocolStartedScoped: return "screen_evidence_protocol_started_scoped"
    case .toolFinishedScoped: return "tool_finished_scoped"
    case .playbackStartedScoped: return "playback_started_scoped"
    case .playbackProgressScoped: return "playback_progress_scoped"
    case .playbackDrainedScoped: return "playback_drained_scoped"
    case .playbackFailedScoped: return "playback_failed_scoped"
    case .transcriptionFinalizationStarted: return "transcription_finalization_started"
    case .transcriptionFinalizationCompleted: return "transcription_finalization_completed"
    case .journalAccepted: return "journal_accepted"
    case .journalFailed: return "journal_failed"
    case .transcriptChanged: return "transcript_changed"
    case .hintChanged: return "hint_changed"
    case .responseWaitingChanged: return "response_waiting_changed"
    case .responseActiveChanged: return "response_active_changed"
    case .debugPresentationChanged: return "debug_presentation_changed"
    case .clearPresentation: return "clear_presentation"
    case .deadlineFired: return "deadline_fired"
    case .finish: return "finish"
    case .cancel: return "cancel"
    case .interrupt: return "interrupt"
    case .cleanup: return "cleanup"
    case .reset: return "reset"
    }
  }
}

/// Facts observed by physical voice drivers. Lifecycle events remain internal
/// to `VoiceTurnDomain`; callers can publish only this typed input surface.
package struct VoiceTurnFact: Sendable {
  fileprivate let event: VoiceTurnEvent

  private init(_ event: VoiceTurnEvent) {
    self.event = event
  }

  package var diagnosticLabel: String { event.diagnosticLabel }
  package var turnID: VoiceTurnID? { event.turnID }

  package static func start(turnID: VoiceTurnID, ownerID: String?, intent: VoiceTurnIntent) -> Self {
    Self(.start(turnID: turnID, ownerID: ownerID, intent: intent))
  }

  package static func effectIdentityReserved(turnID: VoiceTurnID) -> Self {
    Self(.effectIdentityReserved(turnID: turnID))
  }

  package static func transcriptionProviderStartedScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity
  ) -> Self {
    Self(.transcriptionProviderStartedScoped(turnID: turnID, identity: identity))
  }

  package static func transcriptionCompletionClaimedScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity
  ) -> Self {
    Self(.transcriptionCompletionClaimedScoped(turnID: turnID, identity: identity))
  }

  package static func openLockWindow(turnID: VoiceTurnID) -> Self { Self(.openLockWindow(turnID: turnID)) }
  package static func lock(turnID: VoiceTurnID) -> Self { Self(.lock(turnID: turnID)) }
  package static func finalize(turnID: VoiceTurnID) -> Self { Self(.finalize(turnID: turnID)) }

  package static func captureStarted(turnID: VoiceTurnID, captureID: VoiceCaptureID) -> Self {
    Self(.captureStarted(turnID: turnID, captureID: captureID))
  }

  package static func captureFailed(
    turnID: VoiceTurnID,
    captureID: VoiceCaptureID?,
    message: String
  ) -> Self {
    Self(.captureFailed(turnID: turnID, captureID: captureID, message: message))
  }

  package static func selectRoute(turnID: VoiceTurnID, route: VoiceTurnRoute) -> Self {
    Self(.selectRoute(turnID: turnID, route: route))
  }

  package static func hubReady(turnID: VoiceTurnID, sessionID: VoiceSessionID) -> Self {
    Self(.hubReady(turnID: turnID, sessionID: sessionID))
  }

  package static func hubAdmissionRejected(turnID: VoiceTurnID) -> Self {
    Self(.hubAdmissionRejected(turnID: turnID))
  }

  package static func hubCommitAccepted(
    turnID: VoiceTurnID,
    sessionID: VoiceSessionID,
    responseID: VoiceResponseID?
  ) -> Self {
    Self(.hubCommitAccepted(turnID: turnID, sessionID: sessionID, responseID: responseID))
  }

  package static func hubCommitClaimed(turnID: VoiceTurnID) -> Self { Self(.hubCommitClaimed(turnID: turnID)) }
  package static func hubCommitDeferred(turnID: VoiceTurnID) -> Self { Self(.hubCommitDeferred(turnID: turnID)) }

  package static func hubCommitDeferredForReplacement(turnID: VoiceTurnID) -> Self {
    Self(.hubCommitDeferredForReplacement(turnID: turnID))
  }

  package static func providerReconnectStarted(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    previousSessionID: VoiceSessionID?
  ) -> Self {
    Self(.providerReconnectStarted(turnID: turnID, identity: identity, previousSessionID: previousSessionID))
  }

  package static func providerReconnected(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    sessionID: VoiceSessionID
  ) -> Self {
    Self(.providerReconnected(turnID: turnID, identity: identity, sessionID: sessionID))
  }

  package static func providerReconnectFailed(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    message: String
  ) -> Self {
    Self(.providerReconnectFailed(turnID: turnID, identity: identity, message: message))
  }

  package static func providerReplacementStarted(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    previousResponseID: VoiceResponseID?,
    nextResponseID: VoiceResponseID
  ) -> Self {
    Self(
      .providerReplacementStarted(
        turnID: turnID,
        identity: identity,
        previousResponseID: previousResponseID,
        nextResponseID: nextResponseID))
  }

  package static func providerReplacementReady(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    sessionID: VoiceSessionID,
    responseID: VoiceResponseID
  ) -> Self {
    Self(
      .providerReplacementReady(
        turnID: turnID,
        identity: identity,
        sessionID: sessionID,
        responseID: responseID))
  }

  package static func providerReplacementFailed(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    message: String
  ) -> Self {
    Self(.providerReplacementFailed(turnID: turnID, identity: identity, message: message))
  }

  package static func contextResolved(turnID: VoiceTurnID, outcome: VoiceContextOutcome) -> Self {
    Self(.contextResolved(turnID: turnID, outcome: outcome))
  }

  package static func transcriptionStarted(turnID: VoiceTurnID) -> Self {
    Self(.transcriptionStarted(turnID: turnID))
  }

  package static func transcriptionFinal(turnID: VoiceTurnID, text: String) -> Self {
    Self(.transcriptionFinal(turnID: turnID, text: text))
  }

  package static func transcriptionFailed(turnID: VoiceTurnID, message: String) -> Self {
    Self(.transcriptionFailed(turnID: turnID, message: message))
  }

  package static func providerResponseStartedScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    sessionID: VoiceSessionID?,
    responseID: VoiceResponseID?
  ) -> Self {
    Self(
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: identity,
        sessionID: sessionID,
        responseID: responseID))
  }

  package static func providerTurnFinishedScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    sessionID: VoiceSessionID?,
    responseID: VoiceResponseID?
  ) -> Self {
    Self(
      .providerTurnFinishedScoped(
        turnID: turnID,
        identity: identity,
        sessionID: sessionID,
        responseID: responseID))
  }

  package static func toolStartedScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    callID: VoiceToolCallID
  ) -> Self {
    Self(.toolStartedScoped(turnID: turnID, identity: identity, callID: callID))
  }

  package static func authoritativeLocalResultAcceptedScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    callID: VoiceToolCallID,
    kind: VoiceAuthoritativeLocalResultKind
  ) -> Self {
    Self(
      .authoritativeLocalResultAcceptedScoped(
        turnID: turnID,
        identity: identity,
        callID: callID,
        kind: kind))
  }

  package static func screenEvidenceReportVerifiedScoped(
    turnID: VoiceTurnID,
    screenshotIdentity: VoiceEffectIdentity,
    screenshotCallID: VoiceToolCallID,
    reportIdentity: VoiceEffectIdentity,
    reportCallID: VoiceToolCallID
  ) -> Self {
    Self(
      .screenEvidenceReportVerifiedScoped(
        turnID: turnID,
        screenshotIdentity: screenshotIdentity,
        screenshotCallID: screenshotCallID,
        reportIdentity: reportIdentity,
        reportCallID: reportCallID))
  }

  package static func screenEvidenceUnavailableScoped(
    turnID: VoiceTurnID,
    screenshotIdentity: VoiceEffectIdentity,
    screenshotCallID: VoiceToolCallID
  ) -> Self {
    Self(
      .screenEvidenceUnavailableScoped(
        turnID: turnID,
        screenshotIdentity: screenshotIdentity,
        screenshotCallID: screenshotCallID))
  }

  package static func screenEvidenceProtocolStartedScoped(
    turnID: VoiceTurnID,
    token: VoiceScreenEvidenceProtocolToken,
    expiresAfter: TimeInterval
  ) -> Self {
    Self(.screenEvidenceProtocolStartedScoped(turnID: turnID, token: token, expiresAfter: expiresAfter))
  }

  package static func toolFinishedScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    callID: VoiceToolCallID
  ) -> Self {
    Self(.toolFinishedScoped(turnID: turnID, identity: identity, callID: callID))
  }

  package static func playbackStartedScoped(turnID: VoiceTurnID, lease: VoiceOutputLease) -> Self {
    Self(.playbackStartedScoped(turnID: turnID, lease: lease))
  }

  package static func playbackProgressScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    leaseID: VoiceLeaseID
  ) -> Self {
    Self(.playbackProgressScoped(turnID: turnID, identity: identity, leaseID: leaseID))
  }

  package static func playbackDrainedScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    leaseID: VoiceLeaseID
  ) -> Self {
    Self(.playbackDrainedScoped(turnID: turnID, identity: identity, leaseID: leaseID))
  }

  package static func playbackFailedScoped(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    leaseID: VoiceLeaseID?,
    message: String
  ) -> Self {
    Self(.playbackFailedScoped(turnID: turnID, identity: identity, leaseID: leaseID, message: message))
  }

  package static func transcriptionFinalizationStarted(
    turnID: VoiceTurnID,
    mode: VoiceTranscriptionFinalizationMode
  ) -> Self {
    Self(.transcriptionFinalizationStarted(turnID: turnID, mode: mode))
  }

  package static func transcriptionFinalizationCompleted(turnID: VoiceTurnID) -> Self {
    Self(.transcriptionFinalizationCompleted(turnID: turnID))
  }

  package static func journalAccepted(turnID: VoiceTurnID, identity: VoiceEffectIdentity) -> Self {
    Self(.journalAccepted(turnID: turnID, identity: identity))
  }

  package static func journalFailed(
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    message: String
  ) -> Self {
    Self(.journalFailed(turnID: turnID, identity: identity, message: message))
  }

  package static func transcriptChanged(turnID: VoiceTurnID, text: String) -> Self {
    Self(.transcriptChanged(turnID: turnID, text: text))
  }

  package static func hintChanged(turnID: VoiceTurnID, text: String) -> Self {
    Self(.hintChanged(turnID: turnID, text: text))
  }

  package static func responseWaitingChanged(turnID: VoiceTurnID, active: Bool) -> Self {
    Self(.responseWaitingChanged(turnID: turnID, active: active))
  }

  package static func responseActiveChanged(turnID: VoiceTurnID, active: Bool) -> Self {
    Self(.responseActiveChanged(turnID: turnID, active: active))
  }

  package static func debugPresentationChanged(
    turnID: VoiceTurnID,
    state: VoiceTurnDebugPresentationState
  ) -> Self {
    Self(.debugPresentationChanged(turnID: turnID, state: state))
  }

  package static func clearPresentation(turnID: VoiceTurnID) -> Self {
    Self(.clearPresentation(turnID: turnID))
  }

  package static func deadlineFired(turnID: VoiceTurnID, deadline: VoiceTurnDeadline) -> Self {
    Self(.deadlineFired(turnID: turnID, deadline: deadline))
  }

  package static func finish(turnID: VoiceTurnID, reason: VoiceTurnTerminalReason) -> Self {
    Self(.finish(turnID: turnID, reason: reason))
  }

  package static func cancel(turnID: VoiceTurnID, reason: VoiceTurnTerminalReason) -> Self {
    Self(.cancel(turnID: turnID, reason: reason))
  }

  package static func interrupt(turnID: VoiceTurnID) -> Self { Self(.interrupt(turnID: turnID)) }
  package static let cleanup = Self(.cleanup)
  package static let reset = Self(.reset)
}

/// The only mutable lifecycle owner. Its event representation and reducer stay
/// internal to this target; drivers publish facts and consume immutable results.
@MainActor package final class VoiceTurnDomain {
  private let reducer: VoiceTurnReducer
  package private(set) var model: VoiceTurnModel

  package init(model: VoiceTurnModel = .idle) {
    reducer = VoiceTurnReducer()
    self.model = model
  }

  package func publish(_ fact: VoiceTurnFact) -> VoiceTurnReduction {
    let reduction = reducer.reduce(model, fact.event)
    model = reduction.model
    return reduction
  }
}

package enum VoiceTurnEffect: Equatable, Sendable {
  case scheduleDeadline(turnID: VoiceTurnID, deadline: VoiceTurnDeadline, after: TimeInterval)
  case cancelDeadline(turnID: VoiceTurnID, deadline: VoiceTurnDeadline)
  case cancelAllDeadlines(turnID: VoiceTurnID)
  case stopCapture(turnID: VoiceTurnID, captureID: VoiceCaptureID?)
  case finalizeCapturedInput(turnID: VoiceTurnID)
  /// The reducer has recorded the hub commit claim. The provider-facing driver
  /// must run only after this effect, never inline with the request that
  /// enqueued `hubCommitClaimed`, because `VoiceTurnCoordinator` drains nested
  /// events FIFO.
  case commitClaimedHubInput(turnID: VoiceTurnID)
  /// The physical socket is authenticated, but provider input is still closed.
  /// The driver must bind the current canonical context before replaying audio.
  case prepareHubInput(turnID: VoiceTurnID, sessionID: VoiceSessionID)
  case transcriptionFinalizationTimedOut(
    turnID: VoiceTurnID, mode: VoiceTranscriptionFinalizationMode)
  case screenEvidenceProtocolExpired(turnID: VoiceTurnID, token: VoiceScreenEvidenceProtocolToken)
  case finalizeJournal(turnID: VoiceTurnID, identity: VoiceEffectIdentity)
  case cancelHub(turnID: VoiceTurnID, route: VoiceTurnRoute)
  case fallbackToTranscription(turnID: VoiceTurnID, reason: VoiceTurnTerminalReason)
  case stopPlayback(VoiceOutputLease)
  case terminal(VoiceTurnTerminalRecord)
  case staleEventDropped(turnID: VoiceTurnID?, event: String)
  case invalidTransition(turnID: VoiceTurnID?, event: String, phase: VoiceTurnPhase?)
}

package struct VoiceTurnReduction: Equatable, Sendable {
  package var model: VoiceTurnModel
  package var effects: [VoiceTurnEffect]
}

// MARK: - Pure reducer

struct VoiceTurnReducer {
  struct Deadlines: Equatable, Sendable {
    var lockDecision: TimeInterval = 0.4
    var captureStart: TimeInterval = 3
    var hubWarm: TimeInterval = 1
    var transcription: TimeInterval = 12
    var providerResponse: TimeInterval = 20
    var pendingTools: TimeInterval = 30
    var deferredCommit: TimeInterval = 8
    var bargeInReplacement: TimeInterval = 3
    var playbackDrain: TimeInterval = 30
    /// One controller-owned physical rebind is permitted for captured input.
    /// If it cannot reconnect promptly, the same turn moves to the existing
    /// transcript fallback rather than leaving PTT in an ambiguous spinner.
    var providerReconnect: TimeInterval = 3
    var journalFinalization: TimeInterval = 15
    var transcriptionFinalization: TimeInterval = 8
    var hintVisibility: TimeInterval = 2
  }

  var deadlines = Deadlines()

  func reduce(_ current: VoiceTurnModel, _ event: VoiceTurnEvent) -> VoiceTurnReduction {
    var model = current
    var effects: [VoiceTurnEffect] = []

    if case .start(let turnID, let ownerID, let intent) = event {
      let supersededTurnID: VoiceTurnID?
      if let active = model.turn, !active.phase.isTerminal {
        supersededTurnID = active.id
        terminate(&model, reason: .interruptedByBargeIn, effects: &effects)
      } else if let terminal = model.turn, !terminal.deadlines.isEmpty {
        supersededTurnID = nil
        effects.append(.cancelAllDeadlines(turnID: terminal.id))
      } else {
        supersededTurnID = nil
      }
      model.turn = VoiceTurn(
        id: turnID,
        ownerID: ownerID,
        intent: intent,
        supersededTurnID: supersededTurnID)
      model.staleEventCount = 0
      model.invalidTransitionCount = 0
      model.duplicateTerminalCount = 0
      schedule(.captureStart, after: deadlines.captureStart, in: &model, effects: &effects)
      return VoiceTurnReduction(model: model, effects: effects)
    }

    if case .cleanup = event {
      if model.turn != nil {
        terminate(&model, reason: .cleanup, effects: &effects)
      }
      return VoiceTurnReduction(model: model, effects: effects)
    }

    if case .reset = event {
      if model.turn?.phase.isTerminal == true || model.turn == nil {
        if let turn = model.turn, !turn.deadlines.isEmpty {
          effects.append(.cancelAllDeadlines(turnID: turn.id))
        }
        model.turn = nil
      } else {
        invalid(&model, event: event, effects: &effects)
      }
      return VoiceTurnReduction(model: model, effects: effects)
    }

    guard var turn = model.turn else {
      stale(&model, event: event, effects: &effects)
      return VoiceTurnReduction(model: model, effects: effects)
    }
    guard event.turnID == turn.id else {
      stale(&model, event: event, effects: &effects)
      return VoiceTurnReduction(model: model, effects: effects)
    }

    if turn.phase.isTerminal {
      if case .deadlineFired(_, .hintVisibility) = event,
        turn.deadlines.contains(.hintVisibility)
      {
        turn.deadlines.remove(.hintVisibility)
        turn.projection.hint = ""
        model.turn = turn
        return VoiceTurnReduction(model: model, effects: effects)
      }
      switch event {
      case .finish, .cancel:
        model.duplicateTerminalCount += 1
      default:
        stale(&model, event: event, effects: &effects)
      }
      return VoiceTurnReduction(model: model, effects: effects)
    }

    switch event {
    case .effectIdentityReserved:
      let identity = VoiceEffectIdentity(turnID: turn.id, effectID: turn.nextEffectID)
      model.turn?.reservedEffectIdentities.insert(identity)
      model.turn?.nextEffectID &+= 1

    case .transcriptionProviderStartedScoped(_, let identity):
      guard turn.reservedEffectIdentities.contains(identity),
        turn.transcriptionEffectIdentity == nil,
        turn.phase.isRecording || turn.phase == .finalizing
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.reservedEffectIdentities.remove(identity)
      model.turn?.transcriptionEffectIdentity = identity
      model.turn?.transcriptionCompletionClaimed = false

    case .transcriptionCompletionClaimedScoped(_, let identity):
      guard turn.transcriptionEffectIdentity == identity,
        !turn.transcriptionCompletionClaimed
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.transcriptionCompletionClaimed = true

    case .openLockWindow:
      guard turn.phase == .recording else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      turn.phase = .pendingLockDecision
      turn.projection.isListening = true
      turn.projection.isLocked = false
      model.turn = turn
      schedule(.lockDecision, after: deadlines.lockDecision, in: &model, effects: &effects)

    case .lock:
      guard turn.phase == .recording || turn.phase == .pendingLockDecision else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.lockDecision, in: &model, effects: &effects)
      model.turn?.phase = .lockedRecording
      model.turn?.intent = .locked
      model.turn?.projection.isListening = true
      model.turn?.projection.isLocked = true

    case .finalize:
      guard turn.phase.isRecording else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.lockDecision, in: &model, effects: &effects)
      cancel(.captureStart, in: &model, effects: &effects)
      model.turn?.phase = .finalizing
      model.turn?.projection.isListening = false
      model.turn?.projection.isLocked = false
      model.turn?.projection.isThinking = true
      effects.append(.stopCapture(turnID: turn.id, captureID: turn.captureID))
      effects.append(.finalizeCapturedInput(turnID: turn.id))

    case .captureStarted(_, let captureID):
      guard turn.phase.isRecording else {
        stale(&model, event: event, effects: &effects)
        effects.append(.stopCapture(turnID: turn.id, captureID: captureID))
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.captureStart, in: &model, effects: &effects)
      model.turn?.captureID = captureID

    case .captureFailed(_, let captureID, _):
      if let expected = turn.captureID, let captureID, expected != captureID {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      terminate(&model, reason: .captureFailed, effects: &effects)

    case .selectRoute(_, let route):
      guard turn.phase.isRecording || turn.phase == .finalizing else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.route = route
      if route == .hubWarmWait {
        schedule(.hubWarm, after: deadlines.hubWarm, in: &model, effects: &effects)
      }

    case .hubReady(_, let sessionID):
      guard turn.route == .hubWarmWait else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.hubWarm, in: &model, effects: &effects)
      // The route is the driver's audio/commit routing signal, not an admission
      // grant: the PTT driver owns a hub turn only while the route reads `.hub`.
      // Input admission stays fenced by `providerConnection` and
      // `RealtimeInputAdmissionPolicy`, so binding here cannot leak audio to the
      // provider before the canonical context is bound.
      model.turn?.route = .hub(sessionID: sessionID)
      model.turn?.sessionID = sessionID
      effects.append(.prepareHubInput(turnID: turn.id, sessionID: sessionID))

    case .hubAdmissionRejected:
      guard routeMatchesHub(turn.route) else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      // `hubReady` cancelled the warm deadline before asking the provider to bind
      // the canonical context. If that admission fails, restore the same bounded
      // transcription fallback explicitly; otherwise a released turn remains in
      // finalizing + hubWarmWait until the idle socket teardown (observed as a
      // multi-minute PTT spinner).
      cancel(.hubWarm, in: &model, effects: &effects)
      effects.append(.fallbackToTranscription(turnID: turn.id, reason: .hubWarmTimeout))
      model.turn?.route = .deepgramBatch
      if turn.phase == .finalizing {
        schedule(.transcription, after: deadlines.transcription, in: &model, effects: &effects)
      }

    case .hubCommitAccepted(_, let sessionID, let responseID):
      let isDeferredCommit = turn.phase == .awaitingResponse && turn.hubCommitPending
      guard turn.phase == .finalizing || isDeferredCommit, routeMatchesHub(turn.route) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      guard turn.sessionID == nil || turn.sessionID == sessionID else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.route = .hub(sessionID: sessionID)
      model.turn?.sessionID = sessionID
      model.turn?.responseID = responseID
      model.turn?.hubCommitPending = false
      allocateProviderEffectIdentityIfNeeded(in: &model)
      model.turn?.phase = .awaitingResponse
      model.turn?.projection.isThinking = true
      model.turn?.projection.isResponseWaiting = true
      cancel(.deferredCommit, in: &model, effects: &effects)
      cancel(.bargeInReplacement, in: &model, effects: &effects)
      schedule(.providerResponse, after: deadlines.providerResponse, in: &model, effects: &effects)

    case .hubCommitClaimed:
      guard turn.phase == .finalizing, routeMatchesHub(turn.route) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.phase = .awaitingResponse
      model.turn?.projection.isThinking = true
      model.turn?.projection.isResponseWaiting = true
      model.turn?.hubCommitPending = true
      effects.append(.commitClaimedHubInput(turnID: turn.id))

    case .hubCommitDeferred:
      guard turn.phase == .finalizing, routeMatchesHub(turn.route) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.phase = .awaitingResponse
      model.turn?.projection.isThinking = true
      model.turn?.projection.isResponseWaiting = true
      model.turn?.hubCommitPending = true
      schedule(.deferredCommit, after: deadlines.deferredCommit, in: &model, effects: &effects)

    case .hubCommitDeferredForReplacement:
      guard turn.phase == .finalizing, routeMatchesHub(turn.route) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.phase = .awaitingResponse
      model.turn?.projection.isThinking = true
      model.turn?.projection.isResponseWaiting = true
      model.turn?.hubCommitPending = true
      schedule(
        .bargeInReplacement,
        after: deadlines.bargeInReplacement,
        in: &model,
        effects: &effects)

    case .providerReconnectStarted(_, let identity, let previousSessionID):
      guard turn.reservedEffectIdentities.contains(identity),
        routeMatchesHub(turn.route),
        acceptsProviderOutput(turn.phase) || turn.phase == .finalizing || turn.phase.isRecording
      else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.reservedEffectIdentities.remove(identity)
      model.turn?.providerConnection = .reconnecting(
        identity: identity, previousSessionID: previousSessionID)
      model.turn?.sessionID = nil
      model.turn?.providerFinished = false
      // Once the controller owns a captured input boundary, its typed rebind
      // deadline—not the generic one-second warm hint—governs this turn.
      // Otherwise a healthy reconnect can race into batch STT before it has a
      // chance to replay the user's already-captured audio.
      cancel(.hubWarm, in: &model, effects: &effects)
      if shouldProjectProviderConnectionAsAwaitingResponse(turn) {
        model.turn?.phase = .awaitingResponse
        model.turn?.projection.isThinking = true
        model.turn?.projection.isResponseWaiting = true
      }
      schedule(
        .providerReconnect, after: deadlines.providerReconnect, in: &model, effects: &effects)

    case .providerReconnected(_, let identity, let sessionID):
      guard case .reconnecting(let expectedIdentity, _) = turn.providerConnection,
        expectedIdentity == identity
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      // A successful rebind is always admissible for the reconnect identity.
      // Whether a failed reconnect may use transcription fallback is decided
      // separately below; rejecting this success after the provider accepted a
      // commit incorrectly terminalized healthy turns while their response was
      // still draining.
      cancel(.providerReconnect, in: &model, effects: &effects)
      model.turn?.providerConnection = .ready
      model.turn?.sessionID = sessionID
      // A manager-owned warm capture still has PCM in PushToTalkManager's
      // bounded buffer. Keep its route at `.hubWarmWait` until `hubReady`
      // emits `prepareHubInput`; that effect is the one place which flushes
      // that PCM into the now-admitted provider input window. Rewriting the
      // route here would make the controller replay its own buffer while
      // silently orphaning the manager buffer.
      if turn.route != .hubWarmWait {
        model.turn?.route = .hub(sessionID: sessionID)
      }
      if shouldProjectProviderConnectionAsAwaitingResponse(turn) {
        model.turn?.phase = .awaitingResponse
      }

    case .providerReconnectFailed(_, let identity, _):
      guard case .reconnecting(let expectedIdentity, _) = turn.providerConnection,
        expectedIdentity == identity
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.providerReconnect, in: &model, effects: &effects)
      model.turn?.providerConnection = .ready
      if turn.phase == .awaitingResponse, turn.hubCommitPending {
        // The physical release already happened, but its buffered input never
        // reached a provider. Return it to the finalizing boundary so the
        // existing transcription fallback can own the same turn exactly once.
        model.turn?.phase = .finalizing
        model.turn?.hubCommitPending = false
        model.turn?.projection.isResponseWaiting = false
        model.turn?.projection.isThinking = true
      }
      model.turn?.route = .deepgramBatch
      effects.append(.fallbackToTranscription(turnID: turn.id, reason: .providerFailed))
      if model.turn?.phase == .finalizing {
        schedule(.transcription, after: deadlines.transcription, in: &model, effects: &effects)
      }

    case .providerReplacementStarted(
      _, let identity, let previousResponseID, let nextResponseID):
      guard turn.reservedEffectIdentities.contains(identity),
        routeMatchesHub(turn.route),
        acceptsProviderOutput(turn.phase) || turn.phase == .finalizing || turn.phase.isRecording
      else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.reservedEffectIdentities.remove(identity)
      if let previousResponseID, let expected = turn.responseID, previousResponseID != expected {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      if let lease = turn.activeLease {
        effects.append(.stopPlayback(lease))
        cancel(.playbackDrain, in: &model, effects: &effects)
      }
      model.turn?.activeLease = nil
      model.turn?.providerOutputSuppressed = false
      model.turn?.providerConnection = .replacing(
        identity: identity, previousResponseID: previousResponseID)
      model.turn?.responseID = nextResponseID
      model.turn?.providerEffectIdentity = identity
      model.turn?.sessionID = nil
      model.turn?.providerFinished = false
      if shouldProjectProviderConnectionAsAwaitingResponse(turn) {
        model.turn?.phase = .awaitingResponse
        model.turn?.projection.isResponseActive = false
        model.turn?.projection.isResponseWaiting = true
        model.turn?.projection.isThinking = true
      }
      schedule(
        .bargeInReplacement,
        after: deadlines.bargeInReplacement,
        in: &model,
        effects: &effects)

    case .providerReplacementReady(_, let identity, let sessionID, let responseID):
      guard case .replacing(let expectedIdentity, _) = turn.providerConnection,
        expectedIdentity == identity,
        turn.responseID == responseID
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.bargeInReplacement, in: &model, effects: &effects)
      model.turn?.providerConnection = .ready
      model.turn?.sessionID = sessionID
      model.turn?.route = .hub(sessionID: sessionID)
      if shouldProjectProviderConnectionAsAwaitingResponse(turn) {
        model.turn?.phase = .awaitingResponse
      }

    case .providerReplacementFailed(_, let identity, _):
      guard case .replacing(let expectedIdentity, _) = turn.providerConnection,
        expectedIdentity == identity
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      guard turn.phase.isRecording || turn.phase == .finalizing || turn.hubCommitPending else {
        terminate(&model, reason: .providerFailed, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      fallbackFromProviderReplacement(
        reason: .providerFailed,
        in: &model,
        effects: &effects)

    case .contextResolved(_, let outcome):
      if let existing = turn.contextOutcome, existing != outcome {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.contextOutcome = outcome

    case .transcriptionStarted:
      guard turn.phase == .finalizing else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.projection.isThinking = true
      model.turn?.projection.transcript = VoiceTurnUICopy.transcribingProgress
      schedule(.transcription, after: deadlines.transcription, in: &model, effects: &effects)

    case .transcriptionFinal(_, let text):
      guard turn.phase == .finalizing else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.transcription, in: &model, effects: &effects)
      model.turn?.phase = .awaitingResponse
      model.turn?.projection.transcript = text
      model.turn?.projection.isThinking = true
      model.turn?.projection.isResponseWaiting = true
      allocateProviderEffectIdentityIfNeeded(in: &model)
      schedule(.providerResponse, after: deadlines.providerResponse, in: &model, effects: &effects)

    case .transcriptionFailed:
      terminate(&model, reason: .transcriptionFailed, effects: &effects)

    case .providerResponseStartedScoped(_, let identity, let sessionID, let responseID):
      guard turn.providerEffectIdentity == identity else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      guard acceptsProviderOutput(turn.phase) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      if let expected = turn.sessionID, sessionID != expected {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      if let expected = turn.responseID, responseID != expected {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.providerResponse, in: &model, effects: &effects)
      cancel(.deferredCommit, in: &model, effects: &effects)
      cancel(.bargeInReplacement, in: &model, effects: &effects)
      model.turn?.sessionID = sessionID ?? turn.sessionID
      model.turn?.responseID = responseID ?? turn.responseID
      model.turn?.projection.isThinking = false
      model.turn?.projection.isResponseWaiting = false
      model.turn?.projection.isResponseActive = true
      if turn.pendingToolCallIDs.isEmpty, turn.postToolContinuationRequired {
        model.turn?.postToolContinuationRequired = false
      }

    case .providerTurnFinishedScoped(_, let identity, let sessionID, let responseID):
      guard turn.providerEffectIdentity == identity else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      guard acceptsProviderOutput(turn.phase) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      if let expected = turn.sessionID, sessionID != expected {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      if let expected = turn.responseID, responseID != expected {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.providerResponse, in: &model, effects: &effects)
      cancel(.deferredCommit, in: &model, effects: &effects)
      cancel(.bargeInReplacement, in: &model, effects: &effects)
      if turn.screenEvidenceProtocol != nil {
        // A screen answer owns a paired screenshot/report protocol. Its native
        // freshness deadline, not an optional provider continuation, closes it.
        model.turn?.phase = .awaitingTools
        model.turn?.projection.isThinking = true
        model.turn?.projection.isResponseActive = false
        model.turn?.projection.isResponseWaiting = false
        return VoiceTurnReduction(model: model, effects: effects)
      }
      if turn.pendingToolCallIDs.isEmpty, !turn.postToolContinuationRequired {
        model.turn?.providerFinished = true
        startJournalFinalizationIfNeeded(in: &model, effects: &effects)
        if completionFencesSatisfied(model.turn) {
          terminate(&model, reason: .success, effects: &effects)
        }
      } else {
        // A provider cycle that ends on tool calls is not the logical turn end.
        // Tool results reopen the response cycle; journal only the post-tool answer.
        model.turn?.providerFinished = false
        model.turn?.phase = turn.pendingToolCallIDs.isEmpty ? .awaitingResponse : .awaitingTools
        model.turn?.projection.isThinking = true
        model.turn?.projection.isResponseActive = false
        model.turn?.projection.isResponseWaiting = turn.pendingToolCallIDs.isEmpty
        if turn.pendingToolCallIDs.isEmpty {
          schedule(
            .providerResponse, after: deadlines.providerResponse, in: &model, effects: &effects)
        }
      }

    case .toolStartedScoped(_, let identity, let callID):
      guard turn.reservedEffectIdentities.contains(identity),
        turn.toolEffectIdentities[callID] == nil,
        !turn.providerFinished,
        acceptsProviderOutput(turn.phase)
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.reservedEffectIdentities.remove(identity)
      model.turn?.toolEffectIdentities[callID] = identity
      model.turn?.pendingToolCallIDs.insert(callID)
      model.turn?.postToolContinuationRequired = true
      model.turn?.phase = .awaitingTools
      cancel(.providerResponse, in: &model, effects: &effects)
      schedule(.pendingTools, after: deadlines.pendingTools, in: &model, effects: &effects)

    case .authoritativeLocalResultAcceptedScoped(_, let identity, let callID, let kind):
      guard turn.toolEffectIdentities[callID] == identity,
        acceptsProviderOutput(turn.phase)
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      switch kind {
      case .spawnReceipt:
        break
      case .screenEvidenceFailure:
        guard let token = turn.screenEvidenceProtocol,
          token.screenshotCallID == callID,
          token.screenshotIdentity == identity
        else {
          stale(&model, event: event, effects: &effects)
          return VoiceTurnReduction(model: model, effects: effects)
        }
        model.turn?.screenEvidenceProtocol = nil
        cancel(.screenEvidenceProtocol, in: &model, effects: &effects)
      }
      acceptAuthoritativeLocalResult(in: &model, effects: &effects)

    case .screenEvidenceReportVerifiedScoped(
      _, let screenshotIdentity, let screenshotCallID, let reportIdentity, let reportCallID):
      guard let token = turn.screenEvidenceProtocol,
        token.screenshotCallID == screenshotCallID,
        token.screenshotIdentity == screenshotIdentity,
        turn.toolEffectIdentities[reportCallID] == reportIdentity,
        acceptsProviderOutput(turn.phase)
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      // Verification proves the attached JPEG was current for this tool pair;
      // it is not the answer. Keep the normal post-tool continuation fence so
      // native realtime audio answers the user's original question.
      model.turn?.screenEvidenceProtocol = nil
      cancel(.screenEvidenceProtocol, in: &model, effects: &effects)

    case .screenEvidenceUnavailableScoped(_, let screenshotIdentity, let screenshotCallID):
      guard let token = turn.screenEvidenceProtocol,
        token.screenshotCallID == screenshotCallID,
        token.screenshotIdentity == screenshotIdentity,
        acceptsProviderOutput(turn.phase)
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      // A recoverable screenshot-tool error is not a user-visible local
      // answer. The provider receives the error payload and keeps its normal
      // post-tool continuation and native voice lane.
      model.turn?.screenEvidenceProtocol = nil
      cancel(.screenEvidenceProtocol, in: &model, effects: &effects)

    case .screenEvidenceProtocolStartedScoped(_, let token, let expiresAfter):
      guard token.turnID == turn.id,
        turn.toolEffectIdentities[token.screenshotCallID] == token.screenshotIdentity,
        turn.screenEvidenceProtocol == nil,
        acceptsProviderOutput(turn.phase)
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.screenEvidenceProtocol = token
      schedule(
        .screenEvidenceProtocol,
        after: max(0, expiresAfter),
        in: &model,
        effects: &effects)

    case .toolFinishedScoped(_, let identity, let callID):
      guard turn.toolEffectIdentities[callID] == identity else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.pendingToolCallIDs.remove(callID)
      model.turn?.toolEffectIdentities.removeValue(forKey: callID)
      if model.turn?.pendingToolCallIDs.isEmpty == true {
        cancel(.pendingTools, in: &model, effects: &effects)
        if model.turn?.screenEvidenceProtocol != nil {
          // The controller has a reducer-owned screen protocol deadline. Do not
          // turn a missing report into the generic provider-response wait.
          model.turn?.phase = .awaitingTools
          model.turn?.projection.isThinking = true
          model.turn?.projection.isResponseActive = false
          model.turn?.projection.isResponseWaiting = false
        } else if completionFencesSatisfied(model.turn) {
          terminate(&model, reason: .success, effects: &effects)
        } else if let lease = turn.activeLease {
          model.turn?.phase = .playing(lease.lane)
        } else if model.turn?.providerFinished == true {
          model.turn?.phase = .awaitingJournal
          model.turn?.projection.isThinking = true
          model.turn?.projection.isResponseActive = false
          model.turn?.projection.isResponseWaiting = false
        } else {
          model.turn?.phase = .awaitingResponse
          model.turn?.projection.isThinking = true
          model.turn?.projection.isResponseWaiting = true
          schedule(
            .providerResponse, after: deadlines.providerResponse, in: &model, effects: &effects)
        }
      }

    case .playbackStartedScoped(_, let lease):
      guard turn.reservedEffectIdentities.contains(lease.identity) else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.reservedEffectIdentities.remove(lease.identity)
      guard acceptsProviderOutput(turn.phase) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      guard lease.turnID == turn.id, lease.identity.generation == turn.id.rawValue else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      if let activeLease = turn.activeLease, activeLease != lease {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.providerResponse, in: &model, effects: &effects)
      model.turn?.activeLease = lease
      model.turn?.providerOutputSuppressed = lease.lane == .deterministicAgentAck
      model.turn?.phase = .playing(lease.lane)
      model.turn?.projection.isThinking = false
      model.turn?.projection.isResponseWaiting = false
      model.turn?.projection.isResponseActive = true
      schedule(.playbackDrain, after: deadlines.playbackDrain, in: &model, effects: &effects)

    case .playbackProgressScoped(_, let identity, let leaseID):
      guard turn.activeLease?.identity == identity,
        turn.activeLease?.id == leaseID,
        turn.phase == .playing(turn.activeLease?.lane ?? .nativeRealtime)
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      // `VoiceTurnCoordinator.schedule` atomically replaces the existing task
      // for this key. The deadline therefore remains an inactivity watchdog,
      // not a maximum duration for a healthy streaming answer.
      schedule(.playbackDrain, after: deadlines.playbackDrain, in: &model, effects: &effects)

    case .playbackDrainedScoped(_, let identity, let leaseID):
      guard turn.activeLease?.identity == identity,
        turn.activeLease?.id == leaseID
      else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.playbackDrain, in: &model, effects: &effects)
      model.turn?.activeLease = nil
      model.turn?.providerOutputSuppressed = false
      if completionFencesSatisfied(model.turn) {
        terminate(&model, reason: .success, effects: &effects)
      } else if !turn.pendingToolCallIDs.isEmpty {
        model.turn?.phase = .awaitingTools
        model.turn?.projection.isResponseActive = false
        model.turn?.projection.isResponseWaiting = false
      } else if model.turn?.providerFinished == true {
        model.turn?.phase = .awaitingJournal
        model.turn?.projection.isThinking = true
        model.turn?.projection.isResponseActive = false
        model.turn?.projection.isResponseWaiting = false
      } else {
        model.turn?.phase = .awaitingResponse
        model.turn?.projection.isResponseActive = false
        model.turn?.projection.isResponseWaiting = true
        schedule(
          .providerResponse, after: deadlines.providerResponse, in: &model, effects: &effects)
      }

    case .playbackFailedScoped(_, let identity, let leaseID, _):
      guard turn.activeLease?.identity == identity else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      if let leaseID, turn.activeLease?.id != leaseID {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      terminate(&model, reason: .playbackFailed, effects: &effects)

    case .transcriptionFinalizationStarted(_, let mode):
      guard turn.phase == .finalizing else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.transcriptionFinalizationMode = mode
      schedule(
        .transcriptionFinalization,
        after: mode == .live ? 3 : deadlines.transcriptionFinalization,
        in: &model,
        effects: &effects)

    case .transcriptionFinalizationCompleted:
      guard turn.transcriptionFinalizationMode != nil else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.transcriptionFinalization, in: &model, effects: &effects)
      model.turn?.transcriptionFinalizationMode = nil

    case .journalAccepted(_, let identity):
      guard turn.journalFinalization == .writing(identity) else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.journalFinalization, in: &model, effects: &effects)
      model.turn?.journalFinalization = .accepted(identity)
      if completionFencesSatisfied(model.turn) {
        terminate(&model, reason: .success, effects: &effects)
      }

    case .journalFailed(_, let identity, _):
      guard turn.journalFinalization == .writing(identity) else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      terminate(&model, reason: .journalFailed, effects: &effects)

    case .transcriptChanged(_, let text):
      model.turn?.projection.transcript = text

    case .hintChanged(_, let text):
      model.turn?.projection.hint = text
      if text.isEmpty {
        cancel(.hintVisibility, in: &model, effects: &effects)
      } else {
        schedule(.hintVisibility, after: deadlines.hintVisibility, in: &model, effects: &effects)
      }

    case .responseWaitingChanged(_, let active):
      model.turn?.projection.isResponseWaiting = active
      model.turn?.projection.isThinking = active

    case .responseActiveChanged(_, let active):
      model.turn?.projection.isResponseActive = active
      if active {
        model.turn?.projection.isThinking = false
        model.turn?.projection.isResponseWaiting = false
      }

    case .debugPresentationChanged(_, let state):
      guard turn.intent == .automation else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.captureStart, in: &model, effects: &effects)
      if state == .idle {
        terminate(&model, reason: .cleanup, effects: &effects)
      } else {
        model.turn?.projection = state.projection
      }

    case .clearPresentation:
      model.turn?.projection.isListening = false
      model.turn?.projection.isLocked = false
      model.turn?.projection.transcript = ""
      model.turn?.projection.hint = ""
      model.turn?.projection.isThinking = false
      model.turn?.projection.isResponseWaiting = false
      model.turn?.projection.isResponseActive = false
      cancel(.hintVisibility, in: &model, effects: &effects)

    case .deadlineFired(_, let deadline):
      guard turn.deadlines.contains(deadline) else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      guard deadlineMatchesCurrentState(deadline, turn: turn) else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.deadlines.remove(deadline)
      switch deadline {
      case .lockDecision:
        guard turn.phase == .pendingLockDecision else {
          stale(&model, event: event, effects: &effects)
          return VoiceTurnReduction(model: model, effects: effects)
        }
        model.turn?.phase = .finalizing
        model.turn?.projection.isListening = false
        model.turn?.projection.isThinking = true
        effects.append(.stopCapture(turnID: turn.id, captureID: turn.captureID))
        effects.append(.finalizeCapturedInput(turnID: turn.id))
      case .captureStart:
        terminate(&model, reason: .captureFailed, effects: &effects)
      case .hubWarm:
        // A replacement may still be connecting when the bounded warm window
        // expires. Once batch STT owns the turn, a late provider-ready callback
        // must not restore the hub route or replay the same capture there.
        cancel(.bargeInReplacement, in: &model, effects: &effects)
        cancel(.deferredCommit, in: &model, effects: &effects)
        cancel(.providerResponse, in: &model, effects: &effects)
        model.turn?.providerConnection = .ready
        model.turn?.sessionID = nil
        model.turn?.providerEffectIdentity = nil
        model.turn?.responseID = nil
        if turn.phase == .awaitingResponse, turn.hubCommitPending {
          model.turn?.phase = .finalizing
          model.turn?.hubCommitPending = false
          model.turn?.projection.isResponseWaiting = false
          model.turn?.projection.isThinking = true
        }
        effects.append(.fallbackToTranscription(turnID: turn.id, reason: .hubWarmTimeout))
        model.turn?.route = .deepgramBatch
        if model.turn?.phase == .finalizing {
          schedule(.transcription, after: deadlines.transcription, in: &model, effects: &effects)
        }
      case .transcription:
        terminate(&model, reason: .transcriptionFailed, effects: &effects)
      case .providerResponse:
        terminate(&model, reason: .providerNoResponse, effects: &effects)
      case .pendingTools:
        terminate(&model, reason: .toolTimeout, effects: &effects)
      case .screenEvidenceProtocol:
        guard let token = turn.screenEvidenceProtocol else {
          stale(&model, event: event, effects: &effects)
          return VoiceTurnReduction(model: model, effects: effects)
        }
        effects.append(.screenEvidenceProtocolExpired(turnID: turn.id, token: token))
      case .deferredCommit:
        terminate(&model, reason: .deferredCommitTimeout, effects: &effects)
      case .bargeInReplacement:
        // Replacement owns the physical hub only until its bounded rebind
        // window expires. Releasing that ownership to batch STT keeps the
        // captured audio recoverable and fences a late ready callback from
        // reclaiming the turn for a duplicate hub commit.
        fallbackFromProviderReplacement(
          reason: .bargeInReplacementTimeout,
          in: &model,
          effects: &effects)
      case .playbackDrain:
        terminate(&model, reason: .playbackFailed, effects: &effects)
      case .providerReconnect:
        guard turn.phase.isRecording || turn.phase == .finalizing || turn.hubCommitPending else {
          terminate(&model, reason: .providerFailed, effects: &effects)
          return VoiceTurnReduction(model: model, effects: effects)
        }
        model.turn?.providerConnection = .ready
        if turn.phase == .awaitingResponse, turn.hubCommitPending {
          model.turn?.phase = .finalizing
          model.turn?.hubCommitPending = false
          model.turn?.projection.isResponseWaiting = false
          model.turn?.projection.isThinking = true
        }
        model.turn?.route = .deepgramBatch
        effects.append(.fallbackToTranscription(turnID: turn.id, reason: .providerFailed))
        if model.turn?.phase == .finalizing {
          schedule(.transcription, after: deadlines.transcription, in: &model, effects: &effects)
        }
      case .journalFinalization:
        terminate(&model, reason: .journalFailed, effects: &effects)
      case .transcriptionFinalization:
        guard let mode = turn.transcriptionFinalizationMode else {
          stale(&model, event: event, effects: &effects)
          return VoiceTurnReduction(model: model, effects: effects)
        }
        model.turn?.transcriptionFinalizationMode = nil
        effects.append(.transcriptionFinalizationTimedOut(turnID: turn.id, mode: mode))
      case .hintVisibility:
        model.turn?.projection.hint = ""
      }

    case .finish(_, let reason):
      if reason == .success, !completionFencesSatisfied(model.turn) {
        invalid(&model, event: event, effects: &effects)
      } else {
        terminate(&model, reason: reason, effects: &effects)
      }

    case .cancel(_, let reason):
      terminate(&model, reason: reason, effects: &effects)

    case .interrupt:
      terminate(&model, reason: .explicitInterrupt, effects: &effects)

    case .start, .cleanup, .reset:
      break
    }

    return VoiceTurnReduction(model: model, effects: effects)
  }

  private func routeMatchesHub(_ route: VoiceTurnRoute) -> Bool {
    if case .hub = route { return true }
    return route == .hubWarmWait
  }

  private func acceptsProviderOutput(_ phase: VoiceTurnPhase) -> Bool {
    switch phase {
    case .awaitingResponse, .awaitingTools, .playing:
      return true
    case .idle, .pendingLockDecision, .recording, .lockedRecording, .finalizing,
      .awaitingJournal, .terminal:
      return false
    }
  }

  /// Deadline cancellation is best effort because a scheduled callback may have
  /// already crossed its scheduler boundary. The reducer is the final admission
  /// fence: a callback is valid only for the state that originally scheduled it.
  private func deadlineMatchesCurrentState(_ deadline: VoiceTurnDeadline, turn: VoiceTurn) -> Bool {
    switch deadline {
    case .lockDecision:
      return turn.phase == .pendingLockDecision
    case .captureStart:
      return turn.phase.isRecording
    case .hubWarm:
      return turn.route == .hubWarmWait
    case .transcription:
      return turn.phase == .finalizing
    case .providerResponse:
      return turn.phase == .awaitingResponse
    case .pendingTools, .screenEvidenceProtocol:
      return turn.phase == .awaitingTools
    case .deferredCommit, .bargeInReplacement:
      return turn.phase == .awaitingResponse && turn.hubCommitPending
    case .playbackDrain:
      if case .playing = turn.phase { return true }
      return false
    case .providerReconnect:
      if case .reconnecting = turn.providerConnection { return true }
      return false
    case .journalFinalization:
      return turn.phase == .awaitingJournal
    case .transcriptionFinalization:
      return turn.transcriptionFinalizationMode != nil
    case .hintVisibility:
      return true
    }
  }

  /// A physical PTT release remains `.finalizing` until the reducer has
  /// explicitly claimed its hub commit. Reconnect/replacement setup may run in
  /// that phase to buffer or refresh input context, but it cannot turn a
  /// not-yet-committed capture into a response: `commitTurn()` and the
  /// transcript fallback both require the finalizing boundary. Once a commit is
  /// pending, or while handling existing provider output, keep the established
  /// response projection during connection churn.
  private func shouldProjectProviderConnectionAsAwaitingResponse(_ turn: VoiceTurn) -> Bool {
    acceptsProviderOutput(turn.phase) || turn.hubCommitPending
  }

  private func completionFencesSatisfied(_ turn: VoiceTurn?) -> Bool {
    guard let turn else { return false }
    let journalReady: Bool
    if case .accepted = turn.journalFinalization {
      journalReady = true
    } else {
      journalReady = false
    }
    return turn.providerFinished
      && turn.pendingToolCallIDs.isEmpty
      && turn.activeLease == nil
      && journalReady
  }

  private func allocateProviderEffectIdentityIfNeeded(in model: inout VoiceTurnModel) {
    guard var turn = model.turn, turn.providerEffectIdentity == nil else { return }
    turn.providerEffectIdentity = VoiceEffectIdentity(
      turnID: turn.id,
      effectID: turn.nextEffectID)
    turn.nextEffectID &+= 1
    model.turn = turn
  }

  private func startJournalFinalizationIfNeeded(
    in model: inout VoiceTurnModel,
    effects: inout [VoiceTurnEffect]
  ) {
    guard var turn = model.turn, turn.journalFinalization == .pending else { return }
    let identity = VoiceEffectIdentity(turnID: turn.id, effectID: turn.nextEffectID)
    turn.nextEffectID &+= 1
    turn.journalFinalization = .writing(identity)
    model.turn = turn
    if turn.providerFinished && turn.pendingToolCallIDs.isEmpty && turn.activeLease == nil {
      model.turn?.phase = .awaitingJournal
      model.turn?.projection.isThinking = true
      model.turn?.projection.isResponseActive = false
      model.turn?.projection.isResponseWaiting = false
    }
    schedule(
      .journalFinalization,
      after: deadlines.journalFinalization,
      in: &model,
      effects: &effects)
    effects.append(.finalizeJournal(turnID: turn.id, identity: identity))
  }

  /// A native result that has already become the turn's canonical user-visible
  /// answer must not wait for another provider cycle. Tool and playback fences
  /// remain intact, and the journal receipt still gates terminal success.
  private func acceptAuthoritativeLocalResult(
    in model: inout VoiceTurnModel,
    effects: inout [VoiceTurnEffect]
  ) {
    model.turn?.postToolContinuationRequired = false
    model.turn?.providerFinished = true
    cancel(.providerResponse, in: &model, effects: &effects)
    startJournalFinalizationIfNeeded(in: &model, effects: &effects)
    if completionFencesSatisfied(model.turn) {
      terminate(&model, reason: .success, effects: &effects)
    }
  }

  private func schedule(
    _ deadline: VoiceTurnDeadline,
    after interval: TimeInterval,
    in model: inout VoiceTurnModel,
    effects: inout [VoiceTurnEffect]
  ) {
    guard let turnID = model.turn?.id else { return }
    model.turn?.deadlines.insert(deadline)
    effects.append(.scheduleDeadline(turnID: turnID, deadline: deadline, after: interval))
  }

  private func cancel(
    _ deadline: VoiceTurnDeadline,
    in model: inout VoiceTurnModel,
    effects: inout [VoiceTurnEffect]
  ) {
    guard let turnID = model.turn?.id, model.turn?.deadlines.remove(deadline) != nil else { return }
    effects.append(.cancelDeadline(turnID: turnID, deadline: deadline))
  }

  private func fallbackFromProviderReplacement(
    reason: VoiceTurnTerminalReason,
    in model: inout VoiceTurnModel,
    effects: inout [VoiceTurnEffect]
  ) {
    guard let turn = model.turn else { return }
    let turnID = turn.id
    let wasRecording = turn.phase.isRecording
    cancel(.bargeInReplacement, in: &model, effects: &effects)
    cancel(.providerResponse, in: &model, effects: &effects)
    cancel(.deferredCommit, in: &model, effects: &effects)
    model.turn?.providerConnection = .ready
    model.turn?.sessionID = nil
    model.turn?.providerEffectIdentity = nil
    model.turn?.responseID = nil
    if !wasRecording {
      model.turn?.phase = .finalizing
    }
    model.turn?.hubCommitPending = false
    model.turn?.projection.isResponseWaiting = false
    model.turn?.projection.isThinking = !wasRecording
    model.turn?.route = .deepgramBatch
    effects.append(.fallbackToTranscription(turnID: turnID, reason: reason))
    if model.turn?.phase == .finalizing {
      schedule(.transcription, after: deadlines.transcription, in: &model, effects: &effects)
    }
  }

  private func terminate(
    _ model: inout VoiceTurnModel,
    reason: VoiceTurnTerminalReason,
    effects: inout [VoiceTurnEffect]
  ) {
    guard var turn = model.turn else { return }
    guard !turn.phase.isTerminal else {
      model.duplicateTerminalCount += 1
      return
    }
    let record = VoiceTurnTerminalRecord(turnID: turn.id, reason: reason, route: turn.route)
    if turn.captureID != nil || turn.phase.isRecording || turn.phase == .finalizing {
      effects.append(.stopCapture(turnID: turn.id, captureID: turn.captureID))
    }
    let preservesHubForBargeInHandoff: Bool = {
      guard reason == .interruptedByBargeIn else { return false }
      if case .hub = turn.route { return true }
      return false
    }()
    if !preservesHubForBargeInHandoff {
      effects.append(.cancelHub(turnID: turn.id, route: turn.route))
    }
    if let lease = turn.activeLease, !preservesHubForBargeInHandoff {
      effects.append(.stopPlayback(lease))
    }
    effects.append(.cancelAllDeadlines(turnID: turn.id))
    effects.append(.terminal(record))
    turn.deadlines.removeAll()
    turn.pendingToolCallIDs.removeAll()
    turn.screenEvidenceProtocol = nil
    turn.activeLease = nil
    turn.providerOutputSuppressed = false
    turn.terminalReason = reason
    turn.phase = .terminal(reason)
    turn.projection = .idle
    if let terminalHint = VoiceTurnUICopy.terminalHint(for: reason) {
      turn.projection.hint = terminalHint
      turn.deadlines.insert(.hintVisibility)
      effects.append(
        .scheduleDeadline(
          turnID: turn.id,
          deadline: .hintVisibility,
          after: deadlines.hintVisibility))
    }
    model.turn = turn
    model.lastTerminal = record
  }

  private func stale(
    _ model: inout VoiceTurnModel,
    event: VoiceTurnEvent,
    effects: inout [VoiceTurnEffect]
  ) {
    model.staleEventCount += 1
    effects.append(.staleEventDropped(turnID: event.turnID, event: event.diagnosticLabel))
  }

  private func invalid(
    _ model: inout VoiceTurnModel,
    event: VoiceTurnEvent,
    effects: inout [VoiceTurnEffect]
  ) {
    model.invalidTransitionCount += 1
    effects.append(
      .invalidTransition(
        turnID: event.turnID,
        event: event.diagnosticLabel,
        phase: model.turn?.phase))
  }
}
