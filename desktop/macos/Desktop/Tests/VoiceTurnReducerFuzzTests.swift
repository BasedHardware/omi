import XCTest

@testable import Omi_Computer

// Test-only convenience. Production leases have no initializer that can mint
// an identity outside VoiceTurnCoordinator.
extension VoiceOutputLease {
  fileprivate init(
    fuzzLeaseID: VoiceLeaseID, turnID: VoiceTurnID, lane: VoiceOutputLane,
    identity: VoiceEffectIdentity
  ) {
    self.init(id: fuzzLeaseID, turnID: turnID, lane: lane, identity: identity)
  }
}

// MARK: - Seeded PRNG

private struct FuzzRNG: RandomNumberGenerator {
  private var state: UInt64

  init(seed: UInt64) {
    state = seed == 0 ? 0x9E37_79B9_7F4A_7C15 : seed
  }

  mutating func next() -> UInt64 {
    state &+= 0x9E37_79B9_7F4A_7C15
    var z = state
    z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
    z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
    return z ^ (z >> 31)
  }

  mutating func nextUInt64() -> UInt64 { next() }

  mutating func nextInt(bound: Int) -> Int {
    guard bound > 0 else { return 0 }
    return Int(next() % UInt64(bound))
  }

  mutating func nextBool() -> Bool { next() & 1 == 0 }

  mutating func pick<T>(_ values: [T]) -> T {
    values[nextInt(bound: values.count)]
  }
}

// MARK: - Deterministic identities

private enum FuzzIDs {
  static func uuid(_ rng: inout FuzzRNG) -> UUID {
    var bytes = [UInt8](repeating: 0, count: 16)
    for index in 0..<2 {
      let value = rng.nextUInt64()
      for offset in 0..<8 {
        bytes[index * 8 + offset] = UInt8((value >> (offset * 8)) & 0xFF)
      }
    }
    bytes[6] = (bytes[6] & 0x0F) | 0x40
    bytes[8] = (bytes[8] & 0x3F) | 0x80
    return UUID(
      uuid: (
        bytes[0], bytes[1], bytes[2], bytes[3],
        bytes[4], bytes[5], bytes[6], bytes[7],
        bytes[8], bytes[9], bytes[10], bytes[11],
        bytes[12], bytes[13], bytes[14], bytes[15]
      ))
  }

  static func turnID(_ rng: inout FuzzRNG) -> VoiceTurnID { VoiceTurnID(uuid(&rng)) }
  static func sessionID(_ rng: inout FuzzRNG) -> VoiceSessionID { VoiceSessionID(uuid(&rng)) }
  static func leaseID(_ rng: inout FuzzRNG) -> VoiceLeaseID { VoiceLeaseID(uuid(&rng)) }
  static func captureID(_ rng: inout FuzzRNG) -> VoiceCaptureID { VoiceCaptureID(rng.nextUInt64()) }
  static func responseID(_ rng: inout FuzzRNG, salt: UInt64) -> VoiceResponseID {
    VoiceResponseID("resp-\(salt)-\(rng.nextUInt64())")
  }

  static func toolCallID(_ rng: inout FuzzRNG, salt: UInt64) -> VoiceToolCallID {
    VoiceToolCallID("tool-\(salt)-\(rng.nextUInt64())")
  }

  static func contextVersion(_ rng: inout FuzzRNG) -> VoiceContextSnapshotVersion {
    VoiceContextSnapshotVersion("ctx-\(rng.nextUInt64())")
  }
}

// MARK: - Effect classification

private enum FuzzEffectKind {
  case diagnostic
  case terminalTransitionAllowed
  case nonTerminalWork
}

private func fuzzEffectKind(_ effect: VoiceTurnEffect) -> FuzzEffectKind {
  switch effect {
  case .staleEventDropped, .invalidTransition:
    return .diagnostic
  case .stopCapture, .cancelHub, .stopPlayback, .cancelDeadline, .cancelAllDeadlines, .terminal:
    return .terminalTransitionAllowed
  case .scheduleDeadline(_, let deadline, _):
    return deadline == .hintVisibility ? .terminalTransitionAllowed : .nonTerminalWork
  case .finalizeCapturedInput, .commitClaimedHubInput, .prepareHubInput,
    .transcriptionFinalizationTimedOut, .finalizeJournal, .fallbackToTranscription:
    return .nonTerminalWork
  }
}

private func fuzzEffectTurnID(_ effect: VoiceTurnEffect) -> VoiceTurnID? {
  switch effect {
  case .scheduleDeadline(let turnID, _, _), .cancelDeadline(let turnID, _),
    .cancelAllDeadlines(let turnID), .stopCapture(let turnID, _),
    .finalizeCapturedInput(let turnID), .commitClaimedHubInput(let turnID),
    .prepareHubInput(let turnID, _), .transcriptionFinalizationTimedOut(let turnID, _),
    .finalizeJournal(let turnID, _), .cancelHub(let turnID, _),
    .fallbackToTranscription(let turnID, _):
    return turnID
  case .stopPlayback(let lease):
    return lease.turnID
  case .terminal(let record):
    return record.turnID
  case .staleEventDropped(let turnID, _), .invalidTransition(let turnID, _, _):
    return turnID
  }
}

// MARK: - Oracle

private struct FuzzTurnOracle {
  var terminalReason: VoiceTurnTerminalReason?
  var emittedTerminal = false
  var effects: [VoiceTurnEffect] = []
}

private struct FuzzOracle {
  private var turns: [VoiceTurnID: FuzzTurnOracle] = [:]

  mutating func record(effects: [VoiceTurnEffect], model: VoiceTurnModel, event: VoiceTurnEvent? = nil) {
    var restartedTurnID: VoiceTurnID?
    if case .start(let turnID, _, _) = event {
      restartedTurnID = turnID
      turns[turnID] = FuzzTurnOracle()
    }
    for effect in effects {
      guard let turnID = fuzzEffectTurnID(effect) else { continue }
      if turnID == restartedTurnID, case .terminal = effect {
        // Barge-in teardown terminates the superseded lifecycle in the same
        // `.start` reduce; the harness tracks the new lifecycle separately.
        continue
      }
      var record = turns[turnID] ?? FuzzTurnOracle()
      record.effects.append(effect)
      if case .terminal(let terminal) = effect {
        record.emittedTerminal = true
        if record.terminalReason == nil {
          record.terminalReason = terminal.reason
        }
      }
      turns[turnID] = record
    }
    if let turn = model.turn, turn.phase.isTerminal, let reason = turn.terminalReason {
      var record = turns[turn.id] ?? FuzzTurnOracle()
      if record.terminalReason == nil {
        record.terminalReason = reason
      }
      turns[turn.id] = record
    }
    if let last = model.lastTerminal {
      let relifecycleActive =
        model.turn?.id == last.turnID && model.turn?.phase.isTerminal == false
      if !relifecycleActive, last.turnID != restartedTurnID {
        var record = turns[last.turnID] ?? FuzzTurnOracle()
        if record.terminalReason == nil {
          record.terminalReason = last.reason
        }
        turns[last.turnID] = record
      }
    }
  }

  mutating func resetLifecycle(for turnID: VoiceTurnID) {
    turns[turnID] = FuzzTurnOracle()
  }

  func terminalReason(for turnID: VoiceTurnID) -> VoiceTurnTerminalReason? {
    turns[turnID]?.terminalReason
  }

  func emittedTerminal(for turnID: VoiceTurnID) -> Bool {
    turns[turnID]?.emittedTerminal == true
  }

  func effectCount(for turnID: VoiceTurnID) -> Int {
    turns[turnID]?.effects.count ?? 0
  }
}

// MARK: - Harness context

private struct FuzzTurnContext {
  var sessionID: VoiceSessionID?
  var captureID: VoiceCaptureID?
  var responseID: VoiceResponseID?
  var providerIdentity: VoiceEffectIdentity?
  var transcriptionIdentity: VoiceEffectIdentity?
  var reconnectIdentity: VoiceEffectIdentity?
  var replacementIdentity: VoiceEffectIdentity?
  var toolCallID: VoiceToolCallID?
  var toolIdentity: VoiceEffectIdentity?
  var journalIdentity: VoiceEffectIdentity?
  var activeLease: VoiceOutputLease?
  var reservedIdentity: VoiceEffectIdentity?
}

private struct FuzzSequenceHarness {
  let reducer = VoiceTurnReducer()
  let poolTurnIDs: [VoiceTurnID]
  var model = VoiceTurnModel.idle
  var oracle = FuzzOracle()
  var contexts: [VoiceTurnID: FuzzTurnContext] = [:]
  var stringSalt: UInt64 = 0

  init(poolTurnIDs: [VoiceTurnID]) {
    self.poolTurnIDs = poolTurnIDs
    for turnID in poolTurnIDs {
      contexts[turnID] = FuzzTurnContext()
    }
  }

  mutating func context(for turnID: VoiceTurnID) -> FuzzTurnContext {
    contexts[turnID] ?? FuzzTurnContext()
  }

  mutating func setContext(_ context: FuzzTurnContext, for turnID: VoiceTurnID) {
    contexts[turnID] = context
  }

  mutating func pickTurnID(_ rng: inout FuzzRNG, preferCurrent: Bool) -> VoiceTurnID {
    if preferCurrent, let current = model.turn?.id, rng.nextBool() {
      return current
    }
    return poolTurnIDs[rng.nextInt(bound: poolTurnIDs.count)]
  }

  mutating func reserveIdentity(for turnID: VoiceTurnID) -> VoiceEffectIdentity {
    var context = self.context(for: turnID)
    if let reserved = context.reservedIdentity {
      return reserved
    }
    let effectID = model.turn?.id == turnID ? (model.turn?.nextEffectID ?? 1) : UInt64(context.toolIdentity?.effectID ?? 1)
    let identity = VoiceEffectIdentity(turnID: turnID, effectID: effectID)
    context.reservedIdentity = identity
    setContext(context, for: turnID)
    let reserved = reducer.reduce(model, .effectIdentityReserved(turnID: turnID))
    model = reserved.model
    oracle.record(effects: reserved.effects, model: model, event: .effectIdentityReserved(turnID: turnID))
    return identity
  }

  @discardableResult
  mutating func reduce(
    _ event: VoiceTurnEvent,
    step: Int,
    baseSeed: UInt64,
    sequenceSeed: UInt64
  ) throws -> [VoiceTurnEffect] {
    if case .start(let turnID, _, _) = event {
      oracle.resetLifecycle(for: turnID)
    }
    let preModel = model
    let preTurn = preModel.turn
    let reduction = reducer.reduce(model, event)
    try assertInvariants(
      event: event,
      preModel: preModel,
      preTurn: preTurn,
      reduction: reduction,
      step: step,
      baseSeed: baseSeed,
      sequenceSeed: sequenceSeed)
    model = reduction.model
    oracle.record(effects: reduction.effects, model: model, event: event)
    absorb(reduction.effects, event: event)
    return reduction.effects
  }

  private mutating func absorb(_ effects: [VoiceTurnEffect], event: VoiceTurnEvent) {
    guard let turnID = event.turnID else { return }
    var context = self.context(for: turnID)
    switch event {
    case .captureStarted(_, let captureID):
      context.captureID = captureID
    case .selectRoute(_, let route):
      if case .hub(let sessionID) = route {
        context.sessionID = sessionID
      }
    case .hubReady(_, let sessionID):
      context.sessionID = sessionID
    case .hubCommitAccepted(_, let sessionID, let responseID):
      context.sessionID = sessionID
      context.responseID = responseID
      context.providerIdentity = model.turn?.providerEffectIdentity
    case .transcriptionProviderStartedScoped(_, let identity):
      context.transcriptionIdentity = identity
      context.reservedIdentity = nil
    case .providerReconnectStarted(_, let identity, _):
      context.reconnectIdentity = identity
      context.reservedIdentity = nil
    case .providerReplacementStarted(_, let identity, _, let nextResponseID):
      context.replacementIdentity = identity
      context.responseID = nextResponseID
      context.reservedIdentity = nil
    case .toolStartedScoped(_, let identity, let callID):
      context.toolCallID = callID
      context.toolIdentity = identity
      context.reservedIdentity = nil
    case .playbackStartedScoped(_, let lease):
      context.activeLease = lease
      context.reservedIdentity = nil
    case .providerResponseStartedScoped(_, let identity, let sessionID, let responseID):
      context.providerIdentity = identity
      if let sessionID { context.sessionID = sessionID }
      if let responseID { context.responseID = responseID }
    default:
      break
    }
    if case .writing(let identity) = model.turn?.journalFinalization, model.turn?.id == turnID {
      context.journalIdentity = identity
    }
    setContext(context, for: turnID)
  }

  private func assertInvariants(
    event: VoiceTurnEvent,
    preModel: VoiceTurnModel,
    preTurn: VoiceTurn?,
    reduction: VoiceTurnReduction,
    step: Int,
    baseSeed: UInt64,
    sequenceSeed: UInt64
  ) throws {
    let postModel = reduction.model
    let currentID = postModel.turn?.id

    if let eventTurnID = event.turnID {
      // I1 + I2 via oracle
      if let priorReason = oracle.terminalReason(for: eventTurnID) {
        if postModel.turn?.id == eventTurnID, postModel.turn?.phase.isTerminal == true,
          let observed = postModel.turn?.terminalReason,
          observed != priorReason
        {
          throw FuzzFailure(
            baseSeed: baseSeed,
            sequenceSeed: sequenceSeed,
            step: step,
            event: event,
            message: "I1 terminal reason changed for \(eventTurnID): \(priorReason) -> \(observed)")
        }
        if oracle.emittedTerminal(for: eventTurnID),
          let terminalEffect = reduction.effects.first(where: { effect in
            guard case .terminal(let record) = effect else { return false }
            if case .start(let startedTurnID, _, _) = event, record.turnID == startedTurnID {
              return false
            }
            return record.turnID == eventTurnID
          }),
          case .terminal(let record) = terminalEffect,
          record.reason != priorReason
        {
          throw FuzzFailure(
            baseSeed: baseSeed,
            sequenceSeed: sequenceSeed,
            step: step,
            event: event,
            message: "I2 duplicate terminal reason for \(eventTurnID)")
        }
      }

      let oracleAlreadyTerminal = oracle.terminalReason(for: eventTurnID) != nil
      let isCurrent = currentID == eventTurnID
      let transitionedToTerminal =
        preTurn?.id == eventTurnID
        && preTurn?.phase.isTerminal == false
        && postModel.turn?.id == eventTurnID
        && postModel.turn?.phase.isTerminal == true

      for effect in reduction.effects {
        guard let effectTurnID = fuzzEffectTurnID(effect) else { continue }
        let targetsObservedTurn = effectTurnID == eventTurnID
        guard targetsObservedTurn else { continue }

        let kind = fuzzEffectKind(effect)
        switch kind {
        case .diagnostic:
          continue
        case .terminalTransitionAllowed:
          if transitionedToTerminal || !oracleAlreadyTerminal {
            continue
          }
          if case .scheduleDeadline(_, let deadline, _) = effect, deadline == .hintVisibility {
            continue
          }
          if case .cancelDeadline = effect { continue }
          if case .cancelAllDeadlines = effect { continue }
          if !isCurrent || oracleAlreadyTerminal {
            throw FuzzFailure(
              baseSeed: baseSeed,
              sequenceSeed: sequenceSeed,
              step: step,
              event: event,
              message: "I3 terminal-transition effect \(effect) for terminal/stale turn \(effectTurnID)")
          }
        case .nonTerminalWork:
          if oracleAlreadyTerminal && (!isCurrent || postModel.turn?.phase.isTerminal == true) {
            throw FuzzFailure(
              baseSeed: baseSeed,
              sequenceSeed: sequenceSeed,
              step: step,
              event: event,
              message: "I3 non-terminal work \(effect) for terminal/stale turn \(effectTurnID)")
          }
          if !isCurrent {
            throw FuzzFailure(
              baseSeed: baseSeed,
              sequenceSeed: sequenceSeed,
              step: step,
              event: event,
              message: "I3 non-terminal work \(effect) for stale turn \(effectTurnID)")
          }
        }
      }

      if transitionedToTerminal {
        for effect in reduction.effects {
          let kind = fuzzEffectKind(effect)
          if kind == .nonTerminalWork {
            throw FuzzFailure(
              baseSeed: baseSeed,
              sequenceSeed: sequenceSeed,
              step: step,
              event: event,
              message: "I3 unexpected non-terminal work during terminal transition: \(effect)")
          }
        }
        let terminalEffects = reduction.effects.filter {
          if case .terminal = $0 { return true }
          return false
        }
        if terminalEffects.count > 1 {
          throw FuzzFailure(
            baseSeed: baseSeed,
            sequenceSeed: sequenceSeed,
            step: step,
            event: event,
            message: "I2 multiple terminal effects in one step: \(terminalEffects.count)")
        }
      }
    }

    // I4 — stale phase deadlines must not terminate the live phase/turn
    if case .deadlineFired(let turnID, let deadline) = event,
      let active = preTurn,
      active.id == turnID,
      !active.deadlines.contains(deadline)
    {
      if reduction.effects.contains(where: {
        if case .terminal = $0 { return true }
        return false
      }) {
        throw FuzzFailure(
          baseSeed: baseSeed,
          sequenceSeed: sequenceSeed,
          step: step,
          event: event,
          message: "I4 absent deadline \(deadline) still terminated")
      }
    }

    if case .deadlineFired(let turnID, let deadline) = event,
      let active = preTurn,
      active.id == turnID,
      active.deadlines.contains(deadline),
      !deadlineMatchesPhase(deadline, turn: active)
    {
      if reduction.effects.contains(where: {
        if case .terminal = $0 { return true }
        return false
      }) {
        throw FuzzFailure(
          baseSeed: baseSeed,
          sequenceSeed: sequenceSeed,
          step: step,
          event: event,
          message: "I4 deadline \(deadline) fired in wrong phase \(active.phase)")
      }
    }
  }

  private func deadlineMatchesPhase(_ deadline: VoiceTurnDeadline, turn: VoiceTurn) -> Bool {
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
    case .pendingTools:
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
      return turn.deadlines.contains(.hintVisibility)
    }
  }
}

private struct FuzzFailure: Error, CustomStringConvertible {
  let baseSeed: UInt64
  let sequenceSeed: UInt64
  let step: Int
  let event: VoiceTurnEvent
  let message: String

  var description: String {
    "FuzzFailure baseSeed=0x\(String(baseSeed, radix: 16)) "
      + "sequenceSeed=0x\(String(sequenceSeed, radix: 16)) step=\(step) "
      + "event=\(event.diagnosticLabel): \(message)"
  }
}

// MARK: - Event alphabet

private struct FuzzEventGenerator {
  struct Entry {
    let label: String
    let isDriver: Bool
    let generate: (inout FuzzRNG, inout FuzzSequenceHarness) -> VoiceTurnEvent
  }

  static let entries: [Entry] = [
    Entry(label: "start", isDriver: true) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: false)
      let intent = rng.pick([VoiceTurnIntent.hold, .locked, .automation])
      return .start(turnID: turnID, ownerID: rng.nextBool() ? "owner-\(rng.nextUInt64())" : nil, intent: intent)
    },
    Entry(label: "effect_identity_reserved", isDriver: true) { _, harness in
      let turnID = harness.model.turn?.id ?? harness.poolTurnIDs[0]
      return .effectIdentityReserved(turnID: turnID)
    },
    Entry(label: "transcription_provider_started_scoped", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let identity = harness.reserveIdentity(for: turnID)
      return .transcriptionProviderStartedScoped(turnID: turnID, identity: identity)
    },
    Entry(label: "transcription_completion_claimed_scoped", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      var context = harness.context(for: turnID)
      let identity = context.transcriptionIdentity ?? harness.reserveIdentity(for: turnID)
      return .transcriptionCompletionClaimedScoped(turnID: turnID, identity: identity)
    },
    Entry(label: "open_lock_window", isDriver: true) { rng, harness in
      .openLockWindow(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "lock", isDriver: true) { rng, harness in
      .lock(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "finalize", isDriver: true) { rng, harness in
      .finalize(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "capture_started", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      return .captureStarted(turnID: turnID, captureID: FuzzIDs.captureID(&rng))
    },
    Entry(label: "capture_failed", isDriver: true) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let context = harness.context(for: turnID)
      return .captureFailed(
        turnID: turnID,
        captureID: rng.nextBool() ? context.captureID : FuzzIDs.captureID(&rng),
        message: "fuzz-capture-\(rng.nextUInt64())")
    },
    Entry(label: "select_route", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let route: VoiceTurnRoute = rng.pick([
        .undecided, .hubWarmWait, .hub(sessionID: FuzzIDs.sessionID(&rng)),
        .omniSTT, .deepgramBatch, .deepgramLive,
      ])
      return .selectRoute(turnID: turnID, route: route)
    },
    Entry(label: "hub_ready", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      return .hubReady(turnID: turnID, sessionID: FuzzIDs.sessionID(&rng))
    },
    Entry(label: "hub_admission_rejected", isDriver: true) { rng, harness in
      .hubAdmissionRejected(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "hub_commit_accepted", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      var context = harness.context(for: turnID)
      let sessionID = context.sessionID ?? FuzzIDs.sessionID(&rng)
      harness.stringSalt &+= 1
      return .hubCommitAccepted(
        turnID: turnID,
        sessionID: sessionID,
        responseID: FuzzIDs.responseID(&rng, salt: harness.stringSalt))
    },
    Entry(label: "hub_commit_claimed", isDriver: false) { rng, harness in
      .hubCommitClaimed(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "hub_commit_deferred", isDriver: false) { rng, harness in
      .hubCommitDeferred(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "hub_commit_deferred_for_replacement", isDriver: false) { rng, harness in
      .hubCommitDeferredForReplacement(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "provider_reconnect_started", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let identity = harness.reserveIdentity(for: turnID)
      let context = harness.context(for: turnID)
      return .providerReconnectStarted(
        turnID: turnID,
        identity: identity,
        previousSessionID: context.sessionID)
    },
    Entry(label: "provider_reconnected", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let context = harness.context(for: turnID)
      let identity = context.reconnectIdentity ?? harness.reserveIdentity(for: turnID)
      return .providerReconnected(
        turnID: turnID,
        identity: identity,
        sessionID: context.sessionID ?? FuzzIDs.sessionID(&rng))
    },
    Entry(label: "provider_reconnect_failed", isDriver: true) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let context = harness.context(for: turnID)
      let identity = context.reconnectIdentity ?? harness.reserveIdentity(for: turnID)
      return .providerReconnectFailed(
        turnID: turnID,
        identity: identity,
        message: "fuzz-reconnect-\(rng.nextUInt64())")
    },
    Entry(label: "provider_replacement_started", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let identity = harness.reserveIdentity(for: turnID)
      var context = harness.context(for: turnID)
      harness.stringSalt &+= 1
      let next = FuzzIDs.responseID(&rng, salt: harness.stringSalt)
      return .providerReplacementStarted(
        turnID: turnID,
        identity: identity,
        previousResponseID: context.responseID,
        nextResponseID: next)
    },
    Entry(label: "provider_replacement_ready", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let context = harness.context(for: turnID)
      let identity = context.replacementIdentity ?? harness.reserveIdentity(for: turnID)
      let responseID = context.responseID ?? FuzzIDs.responseID(&rng, salt: harness.stringSalt)
      return .providerReplacementReady(
        turnID: turnID,
        identity: identity,
        sessionID: context.sessionID ?? FuzzIDs.sessionID(&rng),
        responseID: responseID)
    },
    Entry(label: "provider_replacement_failed", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let context = harness.context(for: turnID)
      let identity = context.replacementIdentity ?? harness.reserveIdentity(for: turnID)
      return .providerReplacementFailed(
        turnID: turnID,
        identity: identity,
        message: "fuzz-replacement-\(rng.nextUInt64())")
    },
    Entry(label: "context_resolved", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let outcome: VoiceContextOutcome = rng.nextBool()
        ? .captured(FuzzIDs.contextVersion(&rng))
        : .omitted(reason: "fuzz-omit-\(rng.nextUInt64())")
      return .contextResolved(turnID: turnID, outcome: outcome)
    },
    Entry(label: "transcription_started", isDriver: false) { rng, harness in
      .transcriptionStarted(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "transcription_final", isDriver: false) { rng, harness in
      .transcriptionFinal(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        text: "fuzz-transcript-\(rng.nextUInt64())")
    },
    Entry(label: "transcription_failed", isDriver: true) { rng, harness in
      .transcriptionFailed(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        message: "fuzz-transcription-\(rng.nextUInt64())")
    },
    Entry(label: "provider_response_started_scoped", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      var context = harness.context(for: turnID)
      let identity = context.providerIdentity ?? harness.model.turn?.providerEffectIdentity
        ?? harness.reserveIdentity(for: turnID)
      return .providerResponseStartedScoped(
        turnID: turnID,
        identity: identity,
        sessionID: context.sessionID,
        responseID: context.responseID)
    },
    Entry(label: "provider_turn_finished_scoped", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      var context = harness.context(for: turnID)
      let identity = context.providerIdentity ?? harness.model.turn?.providerEffectIdentity
        ?? harness.reserveIdentity(for: turnID)
      return .providerTurnFinishedScoped(
        turnID: turnID,
        identity: identity,
        sessionID: context.sessionID,
        responseID: context.responseID)
    },
    Entry(label: "tool_started_scoped", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let identity = harness.reserveIdentity(for: turnID)
      harness.stringSalt &+= 1
      return .toolStartedScoped(
        turnID: turnID,
        identity: identity,
        callID: FuzzIDs.toolCallID(&rng, salt: harness.stringSalt))
    },
    Entry(label: "tool_finished_scoped", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let context = harness.context(for: turnID)
      let identity = context.toolIdentity ?? harness.reserveIdentity(for: turnID)
      harness.stringSalt &+= 1
      let callID = context.toolCallID ?? FuzzIDs.toolCallID(&rng, salt: harness.stringSalt)
      return .toolFinishedScoped(turnID: turnID, identity: identity, callID: callID)
    },
    Entry(label: "playback_started_scoped", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let identity = harness.reserveIdentity(for: turnID)
      let lane = rng.pick(VoiceOutputLane.allCases)
      let lease = VoiceOutputLease(
        fuzzLeaseID: FuzzIDs.leaseID(&rng),
        turnID: turnID,
        lane: lane,
        identity: identity)
      return .playbackStartedScoped(turnID: turnID, lease: lease)
    },
    Entry(label: "playback_drained_scoped", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let context = harness.context(for: turnID)
      let identity = context.activeLease?.identity ?? harness.reserveIdentity(for: turnID)
      let leaseID = context.activeLease?.id ?? FuzzIDs.leaseID(&rng)
      return .playbackDrainedScoped(turnID: turnID, identity: identity, leaseID: leaseID)
    },
    Entry(label: "playback_failed_scoped", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let context = harness.context(for: turnID)
      let identity = context.activeLease?.identity ?? harness.reserveIdentity(for: turnID)
      return .playbackFailedScoped(
        turnID: turnID,
        identity: identity,
        leaseID: rng.nextBool() ? context.activeLease?.id : FuzzIDs.leaseID(&rng),
        message: "fuzz-playback-\(rng.nextUInt64())")
    },
    Entry(label: "transcription_finalization_started", isDriver: false) { rng, harness in
      .transcriptionFinalizationStarted(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        mode: rng.pick([VoiceTranscriptionFinalizationMode.omni, .live]))
    },
    Entry(label: "transcription_finalization_completed", isDriver: false) { rng, harness in
      .transcriptionFinalizationCompleted(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "journal_accepted", isDriver: false) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let context = harness.context(for: turnID)
      let identity = context.journalIdentity ?? harness.reserveIdentity(for: turnID)
      return .journalAccepted(turnID: turnID, identity: identity)
    },
    Entry(label: "journal_failed", isDriver: true) { rng, harness in
      let turnID = harness.pickTurnID(&rng, preferCurrent: true)
      let context = harness.context(for: turnID)
      let identity = context.journalIdentity ?? harness.reserveIdentity(for: turnID)
      return .journalFailed(
        turnID: turnID,
        identity: identity,
        message: "fuzz-journal-\(rng.nextUInt64())")
    },
    Entry(label: "transcript_changed", isDriver: false) { rng, harness in
      .transcriptChanged(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        text: "fuzz-live-\(rng.nextUInt64())")
    },
    Entry(label: "hint_changed", isDriver: false) { rng, harness in
      .hintChanged(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        text: rng.nextBool() ? "" : "fuzz-hint-\(rng.nextUInt64())")
    },
    Entry(label: "response_waiting_changed", isDriver: false) { rng, harness in
      .responseWaitingChanged(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        active: rng.nextBool())
    },
    Entry(label: "response_active_changed", isDriver: false) { rng, harness in
      .responseActiveChanged(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        active: rng.nextBool())
    },
    Entry(label: "debug_presentation_changed", isDriver: false) { rng, harness in
      .debugPresentationChanged(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        state: rng.pick([
          VoiceTurnDebugPresentationState.idle,
          .listening, .thinking, .answering,
        ]))
    },
    Entry(label: "clear_presentation", isDriver: false) { rng, harness in
      .clearPresentation(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "deadline_fired", isDriver: true) { rng, harness in
      .deadlineFired(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        deadline: rng.pick(Array(VoiceTurnDeadline.allCases)))
    },
    Entry(label: "finish", isDriver: true) { rng, harness in
      .finish(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        reason: rng.pick(Array(VoiceTurnTerminalReason.allCases)))
    },
    Entry(label: "cancel", isDriver: true) { rng, harness in
      .cancel(
        turnID: harness.pickTurnID(&rng, preferCurrent: true),
        reason: rng.pick(Array(VoiceTurnTerminalReason.allCases)))
    },
    Entry(label: "interrupt", isDriver: true) { rng, harness in
      .interrupt(turnID: harness.pickTurnID(&rng, preferCurrent: true))
    },
    Entry(label: "cleanup", isDriver: true) { _, _ in .cleanup },
    Entry(label: "reset", isDriver: true) { _, _ in .reset },
  ]

  static let expectedLabels: Set<String> = [
    "start", "effect_identity_reserved", "transcription_provider_started_scoped",
    "transcription_completion_claimed_scoped", "open_lock_window", "lock", "finalize",
    "capture_started", "capture_failed", "select_route", "hub_ready", "hub_admission_rejected",
    "hub_commit_accepted", "hub_commit_claimed", "hub_commit_deferred",
    "hub_commit_deferred_for_replacement", "provider_reconnect_started", "provider_reconnected",
    "provider_reconnect_failed", "provider_replacement_started", "provider_replacement_ready",
    "provider_replacement_failed", "context_resolved", "transcription_started",
    "transcription_final", "transcription_failed", "provider_response_started_scoped",
    "provider_turn_finished_scoped", "tool_started_scoped", "tool_finished_scoped",
    "playback_started_scoped", "playback_drained_scoped", "playback_failed_scoped",
    "transcription_finalization_started", "transcription_finalization_completed",
    "journal_accepted", "journal_failed", "transcript_changed", "hint_changed",
    "response_waiting_changed", "response_active_changed", "debug_presentation_changed",
    "clear_presentation", "deadline_fired", "finish", "cancel", "interrupt", "cleanup", "reset",
  ]
}

// MARK: - Runner

private struct FuzzRunSnapshot: Equatable {
  var models: [VoiceTurnModel]
  var effectBatches: [[VoiceTurnEffect]]
}

private enum FuzzRunner {
  static let baseSeedCorpus: [UInt64] = [
    0x5054_5453_545AB_01,
    0x5054_5453_545AB_02,
    0x5054_5453_545AB_03,
    0x5054_5453_545AB_04,
    0xDEAD_BEEF_CAFE_0001,
  ]

  static let sequencesPerBaseSeed = 400
  static let maxEventsPerSequence = 60
  static let turnIDsPerSequence = 3

  static func resolvedBaseSeeds() -> [UInt64] {
    guard let override = ProcessInfo.processInfo.environment["OMI_FUZZ_SEED"] else {
      return baseSeedCorpus
    }
    let trimmed = override.trimmingCharacters(in: .whitespacesAndNewlines)
    if let seed = UInt64(trimmed, radix: 0) {
      return [seed]
    }
    return baseSeedCorpus
  }

  static func deriveSequenceSeed(base: UInt64, sequenceIndex: Int) -> UInt64 {
    var hash = base ^ (UInt64(sequenceIndex &+ 1) &* 0x9E37_79B9_7F4A_7C15)
    hash ^= hash >> 33
    hash &*= 0xFF51_AFD7_ED55_8CCD
    hash ^= hash >> 33
    hash &*= 0xC4CE_B9FE_1A85_EC53
    hash ^= hash >> 33
    return hash
  }

  static func runSequence(
    baseSeed: UInt64,
    sequenceSeed: UInt64,
    captureSnapshots: Bool
  ) throws -> FuzzRunSnapshot {
    var rng = FuzzRNG(seed: sequenceSeed)
    var pool: [VoiceTurnID] = []
    while pool.count < turnIDsPerSequence {
      pool.append(FuzzIDs.turnID(&rng))
    }
    var harness = FuzzSequenceHarness(poolTurnIDs: pool)
    var models: [VoiceTurnModel] = []
    var effectBatches: [[VoiceTurnEffect]] = []

    for step in 0..<maxEventsPerSequence {
      let entry: FuzzEventGenerator.Entry
      if rng.nextInt(bound: 100) < 35 {
        let drivers = FuzzEventGenerator.entries.filter(\.isDriver)
        entry = drivers[rng.nextInt(bound: drivers.count)]
      } else {
        entry = FuzzEventGenerator.entries[rng.nextInt(bound: FuzzEventGenerator.entries.count)]
      }
      let event = entry.generate(&rng, &harness)
      let effects = try harness.reduce(
        event,
        step: step,
        baseSeed: baseSeed,
        sequenceSeed: sequenceSeed)
      if captureSnapshots {
        models.append(harness.model)
        effectBatches.append(effects)
      }
    }
    return FuzzRunSnapshot(models: models, effectBatches: effectBatches)
  }
}

// MARK: - Tests

final class VoiceTurnReducerFuzzTests: XCTestCase {
  func testEventAlphabetCoversAllDiagnosticLabels() {
    let generatorLabels = Set(FuzzEventGenerator.entries.map(\.label))
    XCTAssertEqual(generatorLabels, FuzzEventGenerator.expectedLabels)
    XCTAssertEqual(generatorLabels.count, FuzzEventGenerator.expectedLabels.count)
  }

  func testDeterminismReplayMatchesSnapshotsAndEffects() throws {
    let baseSeed = FuzzRunner.baseSeedCorpus[0]
    let sequenceSeed = FuzzRunner.deriveSequenceSeed(base: baseSeed, sequenceIndex: 0)
    let first = try runSequenceWithEffects(baseSeed: baseSeed, sequenceSeed: sequenceSeed)
    let second = try runSequenceWithEffects(baseSeed: baseSeed, sequenceSeed: sequenceSeed)
    XCTAssertEqual(first.models, second.models)
    XCTAssertEqual(first.effectBatches, second.effectBatches)
  }

  func testFuzzReducerInvariantsAcrossCorpus() throws {
    for baseSeed in FuzzRunner.resolvedBaseSeeds() {
      for sequenceIndex in 0..<FuzzRunner.sequencesPerBaseSeed {
        let sequenceSeed = FuzzRunner.deriveSequenceSeed(base: baseSeed, sequenceIndex: sequenceIndex)
        do {
          _ = try FuzzRunner.runSequence(
            baseSeed: baseSeed,
            sequenceSeed: sequenceSeed,
            captureSnapshots: false)
        } catch let failure as FuzzFailure {
          XCTFail(
            "\(failure)\n"
              + "Replay with: OMI_FUZZ_SEED=0x\(String(baseSeed, radix: 16)) "
              + "and sequenceSeed=0x\(String(sequenceSeed, radix: 16))")
          return
        }
      }
    }
  }

  private func runSequenceWithEffects(
    baseSeed: UInt64,
    sequenceSeed: UInt64
  ) throws -> (models: [VoiceTurnModel], effectBatches: [[VoiceTurnEffect]]) {
    var rng = FuzzRNG(seed: sequenceSeed)
    var pool: [VoiceTurnID] = []
    while pool.count < FuzzRunner.turnIDsPerSequence {
      pool.append(FuzzIDs.turnID(&rng))
    }
    var harness = FuzzSequenceHarness(poolTurnIDs: pool)
    var models: [VoiceTurnModel] = []
    var effectBatches: [[VoiceTurnEffect]] = []

    for step in 0..<FuzzRunner.maxEventsPerSequence {
      let entry: FuzzEventGenerator.Entry
      if rng.nextInt(bound: 100) < 35 {
        let drivers = FuzzEventGenerator.entries.filter(\.isDriver)
        entry = drivers[rng.nextInt(bound: drivers.count)]
      } else {
        entry = FuzzEventGenerator.entries[rng.nextInt(bound: FuzzEventGenerator.entries.count)]
      }
      let event = entry.generate(&rng, &harness)
      let effects = try harness.reduce(
        event,
        step: step,
        baseSeed: baseSeed,
        sequenceSeed: sequenceSeed)
      models.append(harness.model)
      effectBatches.append(effects)
    }
    return (models, effectBatches)
  }
}
