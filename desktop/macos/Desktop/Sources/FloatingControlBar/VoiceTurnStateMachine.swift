import Foundation

// MARK: - Typed identities

struct VoiceTurnID: Hashable, Equatable, Sendable, CustomStringConvertible {
  let rawValue: UUID

  init(_ rawValue: UUID = UUID()) {
    self.rawValue = rawValue
  }

  var description: String { rawValue.uuidString }
}

struct VoiceCaptureID: Hashable, Equatable, Sendable, CustomStringConvertible {
  let rawValue: UInt64

  init(_ rawValue: UInt64) {
    self.rawValue = rawValue
  }

  var description: String { String(rawValue) }
}

struct VoiceSessionID: Hashable, Equatable, Sendable, CustomStringConvertible {
  let rawValue: UUID

  init(_ rawValue: UUID = UUID()) {
    self.rawValue = rawValue
  }

  var description: String { rawValue.uuidString }
}

struct VoiceResponseID: Hashable, Equatable, Sendable, CustomStringConvertible {
  let rawValue: String

  init(_ rawValue: String) {
    self.rawValue = rawValue
  }

  var description: String { rawValue }
}

struct VoiceToolCallID: Hashable, Equatable, Sendable, CustomStringConvertible {
  let rawValue: String

  init(_ rawValue: String) {
    self.rawValue = rawValue
  }

  var description: String { rawValue }
}

struct VoiceLeaseID: Hashable, Equatable, Sendable, CustomStringConvertible {
  let rawValue: UUID

  init(_ rawValue: UUID = UUID()) {
    self.rawValue = rawValue
  }

  var description: String { rawValue.uuidString }
}

struct VoiceContextSnapshotVersion: Hashable, Equatable, Sendable, CustomStringConvertible {
  let rawValue: String

  init(_ rawValue: String) {
    self.rawValue = rawValue
  }

  var description: String { rawValue }
}

/// Identity for one asynchronous effect within a logical turn. `generation`
/// is the immutable turn generation; `effectID` distinguishes remints,
/// reconnects, tool attempts, playback attempts, and journal writes that happen
/// without changing the logical turn ID.
struct VoiceEffectIdentity: Hashable, Equatable, Sendable {
  let generation: UUID
  let effectID: UInt64

  init(turnID: VoiceTurnID, effectID: UInt64) {
    generation = turnID.rawValue
    self.effectID = effectID
  }
}

// MARK: - State

enum VoiceTurnIntent: String, Equatable, Sendable {
  case hold
  case locked
  case automation
}

enum VoiceTurnRoute: Equatable, Sendable {
  case undecided
  case hubWarmWait
  case hub(sessionID: VoiceSessionID?)
  case omniSTT
  case deepgramBatch
  case deepgramLive
}

enum VoiceContextOutcome: Equatable, Sendable {
  case captured(VoiceContextSnapshotVersion)
  case omitted(reason: String)
}

enum VoiceProviderConnection: Equatable, Sendable {
  case ready
  case reconnecting(identity: VoiceEffectIdentity, previousSessionID: VoiceSessionID?)
  case replacing(identity: VoiceEffectIdentity, previousResponseID: VoiceResponseID?)
}

enum VoiceJournalFinalization: Equatable, Sendable {
  case pending
  case writing(VoiceEffectIdentity)
  case accepted(VoiceEffectIdentity)
}

enum VoiceTranscriptionFinalizationMode: Equatable, Sendable {
  case omni
  case live
}

enum VoiceOutputLane: String, Equatable, Sendable, CaseIterable {
  case nativeRealtime = "native_realtime"
  case selectedVoiceFallback = "selected_voice_fallback"
  case deterministicAgentAck = "deterministic_agent_ack"
  case filler
  case systemVoiceFallback = "system_voice_fallback"
}

struct VoiceOutputLease: Equatable, Sendable {
  let id: VoiceLeaseID
  let turnID: VoiceTurnID
  let lane: VoiceOutputLane
  let identity: VoiceEffectIdentity

  init(
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

enum VoiceOutputDecision: Equatable, Sendable {
  case acquired(VoiceOutputLease)
  case denied(active: VoiceOutputLease)
  case staleTurn
}

struct VoiceOutputSnapshot: Equatable, Sendable {
  let turnID: VoiceTurnID?
  let activeLease: VoiceOutputLease?
  let providerOutputSuppressed: Bool
}

enum VoiceOutputHandoffPolicy {
  static func fillerCanYield(
    active: VoiceOutputLease,
    to incomingLane: VoiceOutputLane,
    turnID: VoiceTurnID
  ) -> Bool {
    active.turnID == turnID && active.lane == .filler && incomingLane != .filler
  }
}

enum VoiceTurnTerminalReason: String, Equatable, Sendable, CaseIterable {
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

enum VoiceTurnPhase: Equatable, Sendable {
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

  var isRecording: Bool {
    self == .recording || self == .lockedRecording || self == .pendingLockDecision
  }

  var isTerminal: Bool {
    if case .terminal = self { return true }
    return false
  }
}

enum VoiceTurnDeadline: String, Equatable, Hashable, Sendable, CaseIterable {
  case lockDecision = "lock_decision"
  case captureStart = "capture_start"
  case hubWarm = "hub_warm"
  case transcription = "transcription"
  case providerResponse = "provider_response"
  case pendingTools = "pending_tools"
  case deferredCommit = "deferred_commit"
  case bargeInReplacement = "barge_in_replacement"
  case playbackDrain = "playback_drain"
  case providerReconnect = "provider_reconnect"
  case journalFinalization = "journal_finalization"
  case transcriptionFinalization = "transcription_finalization"
  case hintVisibility = "hint_visibility"
}

struct VoiceTurnUIProjection: Equatable, Sendable {
  var isListening = false
  var isLocked = false
  var transcript = ""
  var hint = ""
  var isThinking = false
  var isResponseWaiting = false
  var isResponseActive = false

  static let idle = VoiceTurnUIProjection()
}

enum VoiceTurnDebugPresentationState: String, Equatable, Sendable {
  case idle
  case listening
  case thinking
  case answering

  var projection: VoiceTurnUIProjection {
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

struct VoiceTurn: Equatable, Sendable {
  let id: VoiceTurnID
  /// Immutable authenticated owner captured when the physical voice turn starts.
  /// Every provider, tool, and journal driver must fence against this identity;
  /// reading the ambient account after an `await` can otherwise route owner A's
  /// speech or response into owner B's session.
  let ownerID: String?
  var supersededTurnID: VoiceTurnID?
  var intent: VoiceTurnIntent
  var phase: VoiceTurnPhase
  var route: VoiceTurnRoute
  var captureID: VoiceCaptureID?
  var sessionID: VoiceSessionID?
  var responseID: VoiceResponseID?
  var pendingToolCallIDs: Set<VoiceToolCallID>
  var toolEffectIdentities: [VoiceToolCallID: VoiceEffectIdentity]
  var activeLease: VoiceOutputLease?
  var providerFinished: Bool
  var postToolContinuationRequired: Bool
  var hubCommitPending: Bool
  var providerEffectIdentity: VoiceEffectIdentity?
  var transcriptionEffectIdentity: VoiceEffectIdentity?
  var transcriptionCompletionClaimed: Bool
  var providerConnection: VoiceProviderConnection
  var contextOutcome: VoiceContextOutcome?
  var journalFinalization: VoiceJournalFinalization
  var transcriptionFinalizationMode: VoiceTranscriptionFinalizationMode?
  var providerOutputSuppressed: Bool
  var nextEffectID: UInt64
  var reservedEffectIdentities: Set<VoiceEffectIdentity>
  var deadlines: Set<VoiceTurnDeadline>
  var projection: VoiceTurnUIProjection
  var terminalReason: VoiceTurnTerminalReason?

  init(
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

struct VoiceTurnTerminalRecord: Equatable, Sendable {
  let turnID: VoiceTurnID
  let reason: VoiceTurnTerminalReason
  let route: VoiceTurnRoute

  init(
    turnID: VoiceTurnID,
    reason: VoiceTurnTerminalReason,
    route: VoiceTurnRoute = .undecided
  ) {
    self.turnID = turnID
    self.reason = reason
    self.route = route
  }
}

struct VoiceTurnModel: Equatable, Sendable {
  var turn: VoiceTurn?
  var lastTerminal: VoiceTurnTerminalRecord?
  var staleEventCount = 0
  var invalidTransitionCount = 0
  var duplicateTerminalCount = 0

  init(
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

  static let idle = VoiceTurnModel()
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
  case toolFinishedScoped(
    turnID: VoiceTurnID, identity: VoiceEffectIdentity, callID: VoiceToolCallID)
  case playbackStartedScoped(turnID: VoiceTurnID, lease: VoiceOutputLease)
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
      .toolStartedScoped(let turnID, _, _), .toolFinishedScoped(let turnID, _, _),
      .playbackStartedScoped(let turnID, _), .transcriptChanged(let turnID, _),
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
    case .toolFinishedScoped: return "tool_finished_scoped"
    case .playbackStartedScoped: return "playback_started_scoped"
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

enum VoiceTurnEffect: Equatable, Sendable {
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
  case finalizeJournal(turnID: VoiceTurnID, identity: VoiceEffectIdentity)
  case cancelHub(turnID: VoiceTurnID, route: VoiceTurnRoute)
  case fallbackToTranscription(turnID: VoiceTurnID, reason: VoiceTurnTerminalReason)
  case stopPlayback(VoiceOutputLease)
  case terminal(VoiceTurnTerminalRecord)
  case staleEventDropped(turnID: VoiceTurnID?, event: String)
  case invalidTransition(turnID: VoiceTurnID?, event: String, phase: VoiceTurnPhase?)
}

struct VoiceTurnReduction: Equatable, Sendable {
  var model: VoiceTurnModel
  var effects: [VoiceTurnEffect]
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
    var bargeInReplacement: TimeInterval = 8
    var playbackDrain: TimeInterval = 30
    var providerReconnect: TimeInterval = 15
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
      // Transport readiness is not context admission. Keep the logical route in
      // warm-wait until providerReconnected proves an admitted physical binding.
      effects.append(.prepareHubInput(turnID: turn.id, sessionID: sessionID))

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
      cancel(.providerReconnect, in: &model, effects: &effects)
      model.turn?.providerConnection = .ready
      model.turn?.sessionID = sessionID
      model.turn?.route = .hub(sessionID: sessionID)
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
      terminate(&model, reason: .providerFailed, effects: &effects)

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
      terminate(&model, reason: .providerFailed, effects: &effects)

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
      model.turn?.projection.transcript = "Transcribing…"
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
      schedule(.pendingTools, after: deadlines.pendingTools, in: &model, effects: &effects)

    case .toolFinishedScoped(_, let identity, let callID):
      guard turn.toolEffectIdentities[callID] == identity else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.pendingToolCallIDs.remove(callID)
      model.turn?.toolEffectIdentities.removeValue(forKey: callID)
      if model.turn?.pendingToolCallIDs.isEmpty == true {
        cancel(.pendingTools, in: &model, effects: &effects)
        if completionFencesSatisfied(model.turn) {
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
        effects.append(.fallbackToTranscription(turnID: turn.id, reason: .hubWarmTimeout))
        model.turn?.route = .deepgramBatch
        if turn.phase == .finalizing {
          schedule(.transcription, after: deadlines.transcription, in: &model, effects: &effects)
        }
      case .transcription:
        terminate(&model, reason: .transcriptionFailed, effects: &effects)
      case .providerResponse:
        terminate(&model, reason: .providerNoResponse, effects: &effects)
      case .pendingTools:
        terminate(&model, reason: .toolTimeout, effects: &effects)
      case .deferredCommit:
        terminate(&model, reason: .deferredCommitTimeout, effects: &effects)
      case .bargeInReplacement:
        terminate(&model, reason: .bargeInReplacementTimeout, effects: &effects)
      case .playbackDrain:
        terminate(&model, reason: .playbackFailed, effects: &effects)
      case .providerReconnect:
        terminate(&model, reason: .providerFailed, effects: &effects)
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
    turn.activeLease = nil
    turn.providerOutputSuppressed = false
    turn.terminalReason = reason
    turn.phase = .terminal(reason)
    turn.projection = .idle
    let terminalHint: String?
    switch reason {
    case .tooShort:
      terminalHint = "Hold longer to record"
    case .captureFailed:
      terminalHint = "Microphone unavailable — try again"
    case .transcriptionFailed:
      terminalHint = "Couldn't transcribe that — try again"
    case .providerFailed, .providerNoResponse, .deferredCommitTimeout,
      .bargeInReplacementTimeout, .toolTimeout, .journalFailed:
      terminalHint = "Voice response failed — try again"
    case .playbackFailed:
      terminalHint = "Audio playback failed"
    case .success, .silentRejected, .cancelled, .ownerChanged, .interruptedByBargeIn,
      .explicitInterrupt, .permissionDenied, .hubWarmTimeout, .cleanup:
      terminalHint = nil
    }
    if let terminalHint {
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
