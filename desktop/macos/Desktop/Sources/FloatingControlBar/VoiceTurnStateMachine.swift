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

// MARK: - State

enum VoiceTurnIntent: String, Equatable, Sendable {
  case hold
  case locked
  case agentFollowUp
  case automation
}

enum VoiceTurnRoute: Equatable, Sendable {
  case undecided
  case hubWarmWait
  case hub(sessionID: VoiceSessionID?)
  case omniSTT
  case deepgramBatch
  case deepgramLive
  case agentFollowUp
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
}

enum VoiceTurnTerminalReason: String, Equatable, Sendable, CaseIterable {
  case success
  case tooShort = "too_short"
  case silentRejected = "silent_rejected"
  case cancelled
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
  case hintVisibility = "hint_visibility"
}

struct VoiceTurnUIProjection: Equatable, Sendable {
  var isListening = false
  var isLocked = false
  var isFollowUp = false
  var transcript = ""
  var hint = ""
  var isThinking = false
  var isResponseWaiting = false
  var isResponseActive = false

  static let idle = VoiceTurnUIProjection()
}

struct VoiceTurn: Equatable, Sendable {
  let id: VoiceTurnID
  var intent: VoiceTurnIntent
  var phase: VoiceTurnPhase
  var route: VoiceTurnRoute
  var captureID: VoiceCaptureID?
  var sessionID: VoiceSessionID?
  var responseID: VoiceResponseID?
  var pendingToolCallIDs: Set<VoiceToolCallID>
  var activeLease: VoiceOutputLease?
  var providerFinished: Bool
  var deadlines: Set<VoiceTurnDeadline>
  var projection: VoiceTurnUIProjection
  var terminalReason: VoiceTurnTerminalReason?

  init(id: VoiceTurnID, intent: VoiceTurnIntent) {
    self.id = id
    self.intent = intent
    phase = intent == .locked ? .lockedRecording : .recording
    route = intent == .agentFollowUp ? .agentFollowUp : .undecided
    pendingToolCallIDs = []
    providerFinished = false
    deadlines = []
    projection = VoiceTurnUIProjection(
      isListening: true,
      isLocked: intent == .locked,
      isFollowUp: intent == .agentFollowUp,
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
  case start(turnID: VoiceTurnID, intent: VoiceTurnIntent)
  case openLockWindow(turnID: VoiceTurnID)
  case lock(turnID: VoiceTurnID)
  case finalize(turnID: VoiceTurnID)
  case captureStarted(turnID: VoiceTurnID, captureID: VoiceCaptureID)
  case captureFailed(turnID: VoiceTurnID, captureID: VoiceCaptureID?, message: String)
  case selectRoute(turnID: VoiceTurnID, route: VoiceTurnRoute)
  case hubReady(turnID: VoiceTurnID, sessionID: VoiceSessionID)
  case hubCommitAccepted(
    turnID: VoiceTurnID, sessionID: VoiceSessionID, responseID: VoiceResponseID?)
  case hubCommitDeferred(turnID: VoiceTurnID)
  case hubCommitDeferredForReplacement(turnID: VoiceTurnID)
  case transcriptionStarted(turnID: VoiceTurnID)
  case transcriptionFinal(turnID: VoiceTurnID, text: String)
  case transcriptionFailed(turnID: VoiceTurnID, message: String)
  case providerResponseStarted(
    turnID: VoiceTurnID, sessionID: VoiceSessionID?, responseID: VoiceResponseID?)
  case providerTurnFinished(
    turnID: VoiceTurnID, sessionID: VoiceSessionID?, responseID: VoiceResponseID?)
  case toolStarted(turnID: VoiceTurnID, callID: VoiceToolCallID)
  case toolFinished(turnID: VoiceTurnID, callID: VoiceToolCallID)
  case playbackStarted(turnID: VoiceTurnID, lease: VoiceOutputLease)
  case playbackDrained(turnID: VoiceTurnID, leaseID: VoiceLeaseID)
  case playbackFailed(turnID: VoiceTurnID, leaseID: VoiceLeaseID?, message: String)
  case transcriptChanged(turnID: VoiceTurnID, text: String)
  case hintChanged(turnID: VoiceTurnID, text: String)
  case responseWaitingChanged(turnID: VoiceTurnID, active: Bool)
  case responseActiveChanged(turnID: VoiceTurnID, active: Bool)
  case clearPresentation(turnID: VoiceTurnID)
  case deadlineFired(turnID: VoiceTurnID, deadline: VoiceTurnDeadline)
  case finish(turnID: VoiceTurnID, reason: VoiceTurnTerminalReason)
  case cancel(turnID: VoiceTurnID, reason: VoiceTurnTerminalReason)
  case cleanup
  case reset

  var turnID: VoiceTurnID? {
    switch self {
    case .start(let turnID, _), .openLockWindow(let turnID), .lock(let turnID),
      .finalize(let turnID), .captureStarted(let turnID, _), .captureFailed(let turnID, _, _),
      .selectRoute(let turnID, _), .hubReady(let turnID, _),
      .hubCommitAccepted(let turnID, _, _), .hubCommitDeferred(let turnID),
      .hubCommitDeferredForReplacement(let turnID),
      .transcriptionStarted(let turnID), .transcriptionFinal(let turnID, _),
      .transcriptionFailed(let turnID, _), .providerResponseStarted(let turnID, _, _),
      .providerTurnFinished(let turnID, _, _),
      .toolStarted(let turnID, _), .toolFinished(let turnID, _),
      .playbackStarted(let turnID, _), .playbackDrained(let turnID, _),
      .playbackFailed(let turnID, _, _), .transcriptChanged(let turnID, _),
      .hintChanged(let turnID, _), .responseWaitingChanged(let turnID, _),
      .responseActiveChanged(let turnID, _), .clearPresentation(let turnID),
      .deadlineFired(let turnID, _),
      .finish(let turnID, _), .cancel(let turnID, _):
      return turnID
    case .cleanup, .reset:
      return nil
    }
  }

  /// A bounded diagnostics label that never includes transcript, hint, or error payloads.
  var diagnosticLabel: String {
    switch self {
    case .start: return "start"
    case .openLockWindow: return "open_lock_window"
    case .lock: return "lock"
    case .finalize: return "finalize"
    case .captureStarted: return "capture_started"
    case .captureFailed: return "capture_failed"
    case .selectRoute: return "select_route"
    case .hubReady: return "hub_ready"
    case .hubCommitAccepted: return "hub_commit_accepted"
    case .hubCommitDeferred: return "hub_commit_deferred"
    case .hubCommitDeferredForReplacement: return "hub_commit_deferred_for_replacement"
    case .transcriptionStarted: return "transcription_started"
    case .transcriptionFinal: return "transcription_final"
    case .transcriptionFailed: return "transcription_failed"
    case .providerResponseStarted: return "provider_response_started"
    case .providerTurnFinished: return "provider_turn_finished"
    case .toolStarted: return "tool_started"
    case .toolFinished: return "tool_finished"
    case .playbackStarted: return "playback_started"
    case .playbackDrained: return "playback_drained"
    case .playbackFailed: return "playback_failed"
    case .transcriptChanged: return "transcript_changed"
    case .hintChanged: return "hint_changed"
    case .responseWaitingChanged: return "response_waiting_changed"
    case .responseActiveChanged: return "response_active_changed"
    case .clearPresentation: return "clear_presentation"
    case .deadlineFired: return "deadline_fired"
    case .finish: return "finish"
    case .cancel: return "cancel"
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
  case cancelHub(turnID: VoiceTurnID, route: VoiceTurnRoute)
  case fallbackToTranscription(turnID: VoiceTurnID, reason: VoiceTurnTerminalReason)
  case stopPlayback(turnID: VoiceTurnID, leaseID: VoiceLeaseID?)
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
    var hintVisibility: TimeInterval = 2
  }

  var deadlines = Deadlines()

  func reduce(_ current: VoiceTurnModel, _ event: VoiceTurnEvent) -> VoiceTurnReduction {
    var model = current
    var effects: [VoiceTurnEffect] = []

    if case .start(let turnID, let intent) = event {
      if let active = model.turn, !active.phase.isTerminal {
        terminate(&model, reason: .interruptedByBargeIn, effects: &effects)
      } else if let terminal = model.turn, !terminal.deadlines.isEmpty {
        effects.append(.cancelAllDeadlines(turnID: terminal.id))
      }
      model.turn = VoiceTurn(id: turnID, intent: intent)
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
      model.turn?.route = .hub(sessionID: sessionID)
      model.turn?.sessionID = sessionID

    case .hubCommitAccepted(_, let sessionID, let responseID):
      let isDeferredCommit =
        turn.phase == .awaitingResponse
        && (turn.deadlines.contains(.deferredCommit)
          || turn.deadlines.contains(.bargeInReplacement))
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
      model.turn?.phase = .awaitingResponse
      model.turn?.projection.isThinking = true
      model.turn?.projection.isResponseWaiting = true
      cancel(.deferredCommit, in: &model, effects: &effects)
      cancel(.bargeInReplacement, in: &model, effects: &effects)
      schedule(.providerResponse, after: deadlines.providerResponse, in: &model, effects: &effects)

    case .hubCommitDeferred:
      guard turn.phase == .finalizing, routeMatchesHub(turn.route) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.phase = .awaitingResponse
      model.turn?.projection.isThinking = true
      model.turn?.projection.isResponseWaiting = true
      schedule(.deferredCommit, after: deadlines.deferredCommit, in: &model, effects: &effects)

    case .hubCommitDeferredForReplacement:
      guard turn.phase == .finalizing, routeMatchesHub(turn.route) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.phase = .awaitingResponse
      model.turn?.projection.isThinking = true
      model.turn?.projection.isResponseWaiting = true
      schedule(
        .bargeInReplacement,
        after: deadlines.bargeInReplacement,
        in: &model,
        effects: &effects)

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
      schedule(.providerResponse, after: deadlines.providerResponse, in: &model, effects: &effects)

    case .transcriptionFailed:
      terminate(&model, reason: .transcriptionFailed, effects: &effects)

    case .providerResponseStarted(_, let sessionID, let responseID):
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

    case .providerTurnFinished(_, let sessionID, let responseID):
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
      model.turn?.providerFinished = true
      cancel(.providerResponse, in: &model, effects: &effects)
      cancel(.deferredCommit, in: &model, effects: &effects)
      cancel(.bargeInReplacement, in: &model, effects: &effects)
      if turn.activeLease == nil, turn.pendingToolCallIDs.isEmpty {
        terminate(&model, reason: .success, effects: &effects)
      }

    case .toolStarted(_, let callID):
      guard acceptsProviderOutput(turn.phase) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.pendingToolCallIDs.insert(callID)
      model.turn?.phase = .awaitingTools
      schedule(.pendingTools, after: deadlines.pendingTools, in: &model, effects: &effects)

    case .toolFinished(_, let callID):
      guard turn.pendingToolCallIDs.contains(callID) else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      model.turn?.pendingToolCallIDs.remove(callID)
      if model.turn?.pendingToolCallIDs.isEmpty == true {
        cancel(.pendingTools, in: &model, effects: &effects)
        if turn.providerFinished, turn.activeLease == nil {
          terminate(&model, reason: .success, effects: &effects)
        } else if let lease = turn.activeLease {
          model.turn?.phase = .playing(lease.lane)
        } else {
          model.turn?.phase = .awaitingResponse
          schedule(
            .providerResponse, after: deadlines.providerResponse, in: &model, effects: &effects)
        }
      }

    case .playbackStarted(_, let lease):
      guard acceptsProviderOutput(turn.phase) else {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      guard lease.turnID == turn.id else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      if let activeLease = turn.activeLease, activeLease != lease {
        invalid(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.providerResponse, in: &model, effects: &effects)
      model.turn?.activeLease = lease
      model.turn?.phase = .playing(lease.lane)
      model.turn?.projection.isThinking = false
      model.turn?.projection.isResponseWaiting = false
      model.turn?.projection.isResponseActive = true
      schedule(.playbackDrain, after: deadlines.playbackDrain, in: &model, effects: &effects)

    case .playbackDrained(_, let leaseID):
      guard turn.activeLease?.id == leaseID else {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      cancel(.playbackDrain, in: &model, effects: &effects)
      model.turn?.activeLease = nil
      if turn.providerFinished, turn.pendingToolCallIDs.isEmpty {
        terminate(&model, reason: .success, effects: &effects)
      } else if !turn.pendingToolCallIDs.isEmpty {
        model.turn?.phase = .awaitingTools
        model.turn?.projection.isResponseActive = false
        model.turn?.projection.isResponseWaiting = false
      } else {
        model.turn?.phase = .awaitingResponse
        model.turn?.projection.isResponseActive = false
        model.turn?.projection.isResponseWaiting = true
        schedule(
          .providerResponse, after: deadlines.providerResponse, in: &model, effects: &effects)
      }

    case .playbackFailed(_, let leaseID, _):
      if let leaseID, turn.activeLease?.id != leaseID {
        stale(&model, event: event, effects: &effects)
        return VoiceTurnReduction(model: model, effects: effects)
      }
      terminate(&model, reason: .playbackFailed, effects: &effects)

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

    case .clearPresentation:
      model.turn?.projection.isListening = false
      model.turn?.projection.isLocked = false
      model.turn?.projection.isFollowUp = false
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
      case .hintVisibility:
        model.turn?.projection.hint = ""
      }

    case .finish(_, let reason), .cancel(_, let reason):
      terminate(&model, reason: reason, effects: &effects)

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
    case .idle, .pendingLockDecision, .recording, .lockedRecording, .finalizing, .terminal:
      return false
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
      effects.append(.stopPlayback(turnID: turn.id, leaseID: lease.id))
    }
    effects.append(.cancelAllDeadlines(turnID: turn.id))
    effects.append(.terminal(record))
    turn.deadlines.removeAll()
    turn.pendingToolCallIDs.removeAll()
    turn.activeLease = nil
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
      .bargeInReplacementTimeout, .toolTimeout:
      terminalHint = "Voice response failed — try again"
    case .playbackFailed:
      terminalHint = "Audio playback failed"
    case .success, .silentRejected, .cancelled, .interruptedByBargeIn,
      .permissionDenied, .hubWarmTimeout, .cleanup:
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
