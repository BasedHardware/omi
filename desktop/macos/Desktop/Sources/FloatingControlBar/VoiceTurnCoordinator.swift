import Foundation

typealias VoiceTurnDeadlineCancellation = DelayedActionCancellation

@MainActor
final class VoiceTurnSnapshotObservation {
  private var cancelAction: (() -> Void)?

  init(cancel: @escaping () -> Void) {
    cancelAction = cancel
  }

  func cancel() {
    cancelAction?()
    cancelAction = nil
  }

}

@MainActor
protocol VoiceTurnDeadlineScheduling {
  func schedule(
    deadline: VoiceTurnDeadline,
    after interval: TimeInterval,
    action: @escaping @MainActor () -> Void
  )
    -> VoiceTurnDeadlineCancellation
}

@MainActor
final class TaskVoiceTurnDeadlineScheduler: VoiceTurnDeadlineScheduling {
  private let scheduler: DelayedActionScheduling

  init(scheduler: DelayedActionScheduling? = nil) {
    self.scheduler = scheduler ?? TaskDelayedActionScheduler()
  }

  func schedule(
    deadline: VoiceTurnDeadline,
    after interval: TimeInterval,
    action: @escaping @MainActor () -> Void
  )
    -> VoiceTurnDeadlineCancellation
  {
    _ = deadline
    return scheduler.schedule(after: interval, action: action)
  }
}

struct VoiceTurnTimelineEntry: Equatable, Sendable {
  let sequence: UInt64
  let turnID: VoiceTurnID?
  let event: String
  let phaseBefore: VoiceTurnPhase?
  let phaseAfter: VoiceTurnPhase?
  let route: VoiceTurnRoute?
  let terminalReason: VoiceTurnTerminalReason?
  let staleEventCount: Int
  let invalidTransitionCount: Int
}

struct VoiceNonHubCompletionToken: Equatable, Sendable {
  let turnID: VoiceTurnID
  let providerIdentity: VoiceEffectIdentity
}

enum VoiceNonHubCompletionOutcome: Equatable, Sendable {
  case journalAccepted
  case journalFailed
  case providerFailed
}

@MainActor
final class VoiceTurnCoordinator {
  static let shared = VoiceTurnCoordinator(
    requiresAuthenticatedOwner: true,
    ownerIDProvider: { RuntimeOwnerIdentity.currentOwnerId() })

  typealias EffectHandler = @MainActor (VoiceTurnEffect) -> Void
  typealias SnapshotHandler = @MainActor (VoiceTurnModel) -> Void

  private struct DeadlineKey: Hashable {
    let turnID: VoiceTurnID
    let deadline: VoiceTurnDeadline
  }

  private let reducer: VoiceTurnReducer
  private let scheduler: VoiceTurnDeadlineScheduling
  private let ownerIDProvider: @MainActor () -> String?
  private let ownerIsCurrent: @MainActor (String) -> Bool
  private let requiresAuthenticatedOwner: Bool
  private var deadlineCancellations: [DeadlineKey: VoiceTurnDeadlineCancellation] = [:]
  private var presenter: FloatingControlBarState.PTTBarPresenter?
  private var effectHandler: EffectHandler?
  private var snapshotHandler: SnapshotHandler?
  private var snapshotObservers: [UUID: SnapshotHandler] = [:]
  private var timeline: [VoiceTurnTimelineEntry] = []
  private let timelineLimit: Int
  private var timelineSequence: UInt64 = 0
  private var pendingEvents: [VoiceTurnEvent] = []
  private var isDrainingEvents = false

  private(set) var model: VoiceTurnModel

  init(
    model: VoiceTurnModel = .idle,
    reducer: VoiceTurnReducer = VoiceTurnReducer(),
    scheduler: VoiceTurnDeadlineScheduling? = nil,
    timelineLimit: Int = 256,
    requiresAuthenticatedOwner: Bool = false,
    ownerIDProvider: @escaping @MainActor () -> String? = { nil },
    ownerIsCurrent: @escaping @MainActor (String) -> Bool = {
      AuthorizedToolExecution.isOwnerCurrent($0)
    }
  ) {
    self.model = model
    self.reducer = reducer
    self.scheduler = scheduler ?? TaskVoiceTurnDeadlineScheduler()
    self.timelineLimit = max(1, timelineLimit)
    self.requiresAuthenticatedOwner = requiresAuthenticatedOwner
    self.ownerIDProvider = ownerIDProvider
    self.ownerIsCurrent = ownerIsCurrent
  }

  var activeTurnID: VoiceTurnID? { model.turn?.phase.isTerminal == false ? model.turn?.id : nil }
  var activeTurn: VoiceTurn? { model.turn?.phase.isTerminal == false ? model.turn : nil }
  var projection: VoiceTurnUIProjection { model.turn?.projection ?? .idle }
  var outputSnapshot: VoiceOutputSnapshot {
    VoiceOutputSnapshot(
      turnID: activeTurnID,
      activeLease: activeTurn?.activeLease,
      providerOutputSuppressed: activeTurn?.providerOutputSuppressed ?? false)
  }

  /// Reserves an identity from the authoritative turn generation for an async
  /// physical-driver operation. A callback must return this exact identity.
  ///
  /// Effects are deliberately drained FIFO. An effect handler can therefore
  /// reserve an identity while the coordinator is still draining the effect
  /// that invoked it (for example, `prepareHubInput` after `hubReady`). In
  /// that case the reservation is already queued ahead of every subsequent
  /// scoped event from that handler; it is safe to return the identity without
  /// waiting for the reducer to apply it synchronously.
  func reserveEffectIdentity() -> VoiceEffectIdentity? {
    guard let turn = activeTurn else { return nil }
    let identity = VoiceEffectIdentity(turnID: turn.id, effectID: turn.nextEffectID)
    let reservationIsQueuedBehindCurrentEffect = isDrainingEvents
    send(.effectIdentityReserved(turnID: turn.id))
    if reservationIsQueuedBehindCurrentEffect {
      return identity
    }
    guard activeTurn?.nextEffectID == (turn.nextEffectID &+ 1) else { return nil }
    return identity
  }

  /// Captures the exact non-hub provider generation before an asynchronous chat
  /// request starts. Completion must return this token; reading the current turn
  /// only when a callback arrives can otherwise attribute A's callback to B.
  func nonHubCompletionToken(for turnID: VoiceTurnID? = nil) -> VoiceNonHubCompletionToken? {
    guard let turn = activeTurn,
      turnID == nil || turn.id == turnID,
      !Self.isHubRoute(turn.route),
      let providerIdentity = turn.providerEffectIdentity
    else { return nil }
    return VoiceNonHubCompletionToken(turnID: turn.id, providerIdentity: providerIdentity)
  }

  /// Closes a non-hub provider only after its canonical kernel journal operation
  /// has returned. Playback is an independent fence and may drain before or after
  /// this call without claiming provider completion.
  @discardableResult
  func completeNonHubProvider(
    _ token: VoiceNonHubCompletionToken,
    outcome: VoiceNonHubCompletionOutcome
  ) -> Bool {
    guard requireCurrentOwner(for: token.turnID) != nil else { return false }
    guard activeTurn?.id == token.turnID,
      activeTurn?.providerEffectIdentity == token.providerIdentity,
      activeTurn.map({ !Self.isHubRoute($0.route) }) == true
    else { return false }

    if outcome == .providerFailed {
      send(.finish(turnID: token.turnID, reason: .providerFailed))
      return model.lastTerminal?.turnID == token.turnID
        && model.lastTerminal?.reason == .providerFailed
    }

    send(
      .providerTurnFinishedScoped(
        turnID: token.turnID,
        identity: token.providerIdentity,
        sessionID: nil,
        responseID: nil))
    guard activeTurn?.id == token.turnID,
      let journalFinalization = activeTurn?.journalFinalization,
      case .writing(let journalIdentity) = journalFinalization
    else { return false }
    switch outcome {
    case .journalAccepted:
      send(.journalAccepted(turnID: token.turnID, identity: journalIdentity))
    case .journalFailed:
      send(
        .journalFailed(
          turnID: token.turnID,
          identity: journalIdentity,
          message: "kernel journal did not acknowledge the non-hub voice turn"))
    case .providerFailed:
      break
    }
    return true
  }

  func isToolEffectActive(
    turnID: VoiceTurnID,
    callID: VoiceToolCallID,
    identity: VoiceEffectIdentity
  ) -> Bool {
    activeTurn?.id == turnID && activeTurn?.toolEffectIdentities[callID] == identity
  }

  func isProviderConnectionReady(
    turnID: VoiceTurnID,
    sessionID: VoiceSessionID,
    responseID: VoiceResponseID? = nil
  ) -> Bool {
    guard let turn = activeTurn, turn.id == turnID,
      turn.providerConnection == .ready,
      turn.sessionID == sessionID
    else { return false }
    return responseID == nil || turn.responseID == responseID
  }

  func canCommitHubTurn(_ turnID: VoiceTurnID) -> Bool {
    guard let turn = activeTurn, turn.id == turnID,
      Self.isHubRoute(turn.route)
    else { return false }
    return turn.phase == .finalizing && !turn.hubCommitPending
  }

  func acquireOutput(
    _ lane: VoiceOutputLane,
    turnID: VoiceTurnID,
    leaseID: VoiceLeaseID = VoiceLeaseID()
  ) -> VoiceOutputDecision {
    guard activeTurnID == turnID else { return .staleTurn }
    if let activeLease = activeTurn?.activeLease {
      if activeLease.turnID == turnID, activeLease.lane == lane {
        return .acquired(activeLease)
      }
      return .denied(active: activeLease)
    }
    guard let identity = reserveEffectIdentity() else { return .staleTurn }
    let lease = VoiceOutputLease(
      id: leaseID,
      turnID: turnID,
      lane: lane,
      identity: identity)
    send(.playbackStartedScoped(turnID: turnID, lease: lease))
    return activeTurn?.activeLease == lease ? .acquired(lease) : .staleTurn
  }

  @discardableResult
  func releaseOutput(_ lease: VoiceOutputLease) -> Bool {
    guard activeTurn?.activeLease == lease else { return false }
    send(
      .playbackDrainedScoped(
        turnID: lease.turnID,
        identity: lease.identity,
        leaseID: lease.id))
    return true
  }

  /// Refresh the native-output inactivity watchdog after a successfully
  /// scheduled PCM chunk. A matching lease is required so delayed audio from a
  /// replaced turn cannot prolong the current response.
  @discardableResult
  func noteOutputProgress(_ lease: VoiceOutputLease) -> Bool {
    guard activeTurn?.activeLease == lease else { return false }
    send(
      .playbackProgressScoped(
        turnID: lease.turnID,
        identity: lease.identity,
        leaseID: lease.id))
    return activeTurn?.activeLease == lease
  }

  func configure(barState: FloatingControlBarState) {
    presenter = FloatingControlBarState.PTTBarPresenter(barState: barState)
    presenter?.apply(projection)
  }

  func setEffectHandler(_ handler: EffectHandler?) {
    effectHandler = handler
  }

  func setSnapshotHandler(_ handler: SnapshotHandler?) {
    snapshotHandler = handler
    handler?(model)
  }

  func observeSnapshots(_ handler: @escaping SnapshotHandler) -> VoiceTurnSnapshotObservation {
    let id = UUID()
    snapshotObservers[id] = handler
    handler(model)
    return VoiceTurnSnapshotObservation { [weak self] in
      self?.snapshotObservers.removeValue(forKey: id)
    }
  }

  @discardableResult
  func begin(
    intent: VoiceTurnIntent,
    id: VoiceTurnID = VoiceTurnID(),
    ownerID: String? = nil
  ) -> VoiceTurnID {
    if model.turn?.phase.isTerminal == true {
      send(.reset)
    }
    send(.start(turnID: id, ownerID: ownerID ?? ownerIDProvider(), intent: intent))
    return id
  }

  /// Returns the immutable owner captured at turn start only while that owner
  /// remains the authenticated runtime owner. A mismatch terminalizes the turn
  /// before any new provider, tool, or journal effect can be dispatched.
  @discardableResult
  func requireCurrentOwner(for turnID: VoiceTurnID) -> String? {
    guard let turn = activeTurn, turn.id == turnID else { return nil }
    if turn.ownerID == nil, !requiresAuthenticatedOwner {
      return "unowned-test-turn"
    }
    guard let ownerID = turn.ownerID, ownerIsCurrent(ownerID) else {
      if activeTurnID == turnID {
        log("VoiceTurnCoordinator: cancelling turn after authenticated owner changed")
        send(.cancel(turnID: turnID, reason: .cancelled))
      }
      return nil
    }
    return ownerID
  }

  /// Revokes the complete logical voice capability before an effective owner
  /// mutation becomes visible. This enters through the reducer so capture,
  /// provider, playback, deadline, and terminal cleanup effects keep one owner.
  @discardableResult
  func terminateForEffectiveOwnerTransition(previousOwnerID: String?) -> Bool {
    guard let turn = activeTurn else { return false }
    if let previousOwnerID, turn.ownerID != previousOwnerID {
      log(
        "VoiceTurnCoordinator: active turn owner did not match the owner being replaced; "
          + "revoking the turn fail-closed")
    }
    send(.cancel(turnID: turn.id, reason: .ownerChanged))
    return model.lastTerminal?.turnID == turn.id
      && model.lastTerminal?.reason == .ownerChanged
  }

  func send(_ event: VoiceTurnEvent) {
    pendingEvents.append(event)
    guard !isDrainingEvents else { return }

    isDrainingEvents = true
    defer {
      pendingEvents.removeAll(keepingCapacity: true)
      isDrainingEvents = false
    }

    var nextEventIndex = 0
    while nextEventIndex < pendingEvents.count {
      let nextEvent = pendingEvents[nextEventIndex]
      nextEventIndex += 1
      apply(nextEvent)
    }
  }

  /// Applies one event atomically before any callback can advance the machine.
  ///
  /// Effect and snapshot handlers are allowed to synchronously call `send`.
  /// Those nested events join `pendingEvents` and are drained FIFO after this
  /// event has finished publishing, instead of recursively reducing against a
  /// half-published transition.
  private func apply(_ event: VoiceTurnEvent) {
    let before = model
    let reduction = reducer.reduce(model, event)
    model = reduction.model
    appendTimeline(event: event, before: before, after: model)
    process(reduction.effects)
    presenter?.apply(projection)
    snapshotHandler?(model)
    for observer in snapshotObservers.values {
      observer(model)
    }
  }

  func timelineSnapshot() -> [VoiceTurnTimelineEntry] {
    timeline
  }

  func refreshPresentation() {
    presenter?.apply(projection)
  }

  /// Non-production visual harness. Debug presentation still enters through a
  /// turn-scoped reducer event, so it cannot overwrite a real voice turn or
  /// mutate floating-bar state independently.
  @discardableResult
  func applyDebugPresentationState(_ state: VoiceTurnDebugPresentationState) -> Bool {
    guard AppBuild.isNonProduction else { return false }
    if let activeTurn, activeTurn.intent != .automation { return false }
    let turnID = activeTurnID ?? begin(intent: .automation)
    send(.debugPresentationChanged(turnID: turnID, state: state))
    if state == .idle {
      return activeTurnID == nil && projection == .idle
    }
    return activeTurn?.intent == .automation && projection == state.projection
  }

  /// Non-PTT chat playback shares the floating pill, but it must not bypass the
  /// presentation owner. Active PTT turns always use turn-scoped projection
  /// events instead, so a late chat callback cannot clear their glow.
  func setUnscopedResponseActive(_ active: Bool) {
    guard activeTurnID == nil else { return }
    var unscopedProjection = projection
    unscopedProjection.isResponseWaiting = false
    unscopedProjection.isResponseActive = active
    presenter?.apply(unscopedProjection)
  }

  func reset() {
    if model.turn != nil {
      send(.cleanup)
      send(.reset)
    }
    for cancellation in deadlineCancellations.values {
      cancellation.cancel()
    }
    deadlineCancellations.removeAll()
    presenter?.apply(.idle)
  }

  private func process(_ effects: [VoiceTurnEffect]) {
    for effect in effects {
      if let turnID = Self.ownerFencedTurnID(for: effect),
        requireCurrentOwner(for: turnID) == nil
      {
        continue
      }
      switch effect {
      case .scheduleDeadline(let turnID, let deadline, let interval):
        schedule(turnID: turnID, deadline: deadline, interval: interval)
      case .cancelDeadline(let turnID, let deadline):
        cancel(turnID: turnID, deadline: deadline)
      case .cancelAllDeadlines(let turnID):
        cancelAll(turnID: turnID)
      case .terminal(let terminal):
        DesktopDiagnosticsManager.shared.recordVoiceTurnTerminal(
          reason: terminal.reason.rawValue,
          route: Self.routeLabel(terminal.route),
          staleEventCount: model.staleEventCount,
          invalidTransitionCount: model.invalidTransitionCount)
        log(
          "VoiceTurnCoordinator: terminal turn=\(terminal.turnID.description) "
            + "reason=\(terminal.reason.rawValue) route=\(Self.routeLabel(terminal.route))")
        effectHandler?(effect)
      case .staleEventDropped(let turnID, let event):
        DesktopDiagnosticsManager.shared.recordVoiceTurnAnomaly(
          kind: "stale_event",
          phase: model.turn.map { Self.phaseLabel($0.phase) } ?? "idle",
          route: model.turn.map { Self.routeLabel($0.route) } ?? "none")
        log(
          "VoiceTurnCoordinator: dropped stale event turn=\(turnID?.description ?? "none") event=\(event.prefix(160))"
        )
        effectHandler?(effect)
      case .invalidTransition(let turnID, let event, let phase):
        DesktopDiagnosticsManager.shared.recordVoiceTurnAnomaly(
          kind: "invalid_transition",
          phase: phase.map(Self.phaseLabel) ?? "idle",
          route: model.turn.map { Self.routeLabel($0.route) } ?? "none")
        log(
          "VoiceTurnCoordinator: invalid transition turn=\(turnID?.description ?? "none") "
            + "phase=\(phase.map(Self.phaseLabel) ?? "idle") event=\(event.prefix(160))")
        effectHandler?(effect)
      default:
        effectHandler?(effect)
      }
    }
  }

  /// Effects that may start a new provider/query/tool/journal operation require
  /// the turn's pinned owner. Cleanup effects still run after an account change
  /// so capture/playback cannot be left active.
  private static func ownerFencedTurnID(for effect: VoiceTurnEffect) -> VoiceTurnID? {
    switch effect {
    case .finalizeCapturedInput(let turnID), .commitClaimedHubInput(let turnID), .prepareHubInput(let turnID, _),
      .screenEvidenceProtocolExpired(let turnID, _), .finalizeJournal(let turnID, _),
      .fallbackToTranscription(let turnID, _):
      return turnID
    case .scheduleDeadline, .cancelDeadline, .cancelAllDeadlines, .stopCapture,
      .transcriptionFinalizationTimedOut, .cancelHub, .stopPlayback, .terminal,
      .staleEventDropped, .invalidTransition:
      return nil
    }
  }

  private func schedule(turnID: VoiceTurnID, deadline: VoiceTurnDeadline, interval: TimeInterval) {
    let key = DeadlineKey(turnID: turnID, deadline: deadline)
    deadlineCancellations.removeValue(forKey: key)?.cancel()
    deadlineCancellations[key] = scheduler.schedule(deadline: deadline, after: interval) {
      [weak self] in
      guard let self else { return }
      self.deadlineCancellations.removeValue(forKey: key)
      let phase = self.activeTurn.map { Self.phaseLabel($0.phase) } ?? "idle"
      log(
        "VoiceTurnCoordinator: deadline fired turn=\(turnID.description) "
          + "deadline=\(deadline.rawValue) phase=\(phase)")
      self.send(.deadlineFired(turnID: turnID, deadline: deadline))
    }
  }

  private func cancel(turnID: VoiceTurnID, deadline: VoiceTurnDeadline) {
    deadlineCancellations.removeValue(forKey: DeadlineKey(turnID: turnID, deadline: deadline))?
      .cancel()
  }

  private func cancelAll(turnID: VoiceTurnID) {
    let keys = deadlineCancellations.keys.filter { $0.turnID == turnID }
    for key in keys {
      deadlineCancellations.removeValue(forKey: key)?.cancel()
    }
  }

  private func appendTimeline(
    event: VoiceTurnEvent,
    before: VoiceTurnModel,
    after: VoiceTurnModel
  ) {
    timelineSequence &+= 1
    timeline.append(
      VoiceTurnTimelineEntry(
        sequence: timelineSequence,
        turnID: event.turnID ?? after.turn?.id ?? before.turn?.id,
        event: Self.eventLabel(event),
        phaseBefore: before.turn?.phase,
        phaseAfter: after.turn?.phase,
        route: after.turn?.route,
        terminalReason: after.lastTerminal?.turnID == (event.turnID ?? after.turn?.id)
          ? after.lastTerminal?.reason : nil,
        staleEventCount: after.staleEventCount,
        invalidTransitionCount: after.invalidTransitionCount))
    if timeline.count > timelineLimit {
      timeline.removeFirst(timeline.count - timelineLimit)
    }
  }

  private static func eventLabel(_ event: VoiceTurnEvent) -> String {
    event.diagnosticLabel
  }

  static func phaseLabel(_ phase: VoiceTurnPhase) -> String {
    switch phase {
    case .idle: return "idle"
    case .pendingLockDecision: return "pending_lock_decision"
    case .recording: return "recording"
    case .lockedRecording: return "locked_recording"
    case .finalizing: return "finalizing"
    case .awaitingResponse: return "awaiting_response"
    case .awaitingTools: return "awaiting_tools"
    case .awaitingJournal: return "awaiting_journal"
    case .playing(let lane): return "playing_\(lane.rawValue)"
    case .terminal(let reason): return "terminal_\(reason.rawValue)"
    }
  }

  static func routeLabel(_ route: VoiceTurnRoute) -> String {
    switch route {
    case .undecided: return "undecided"
    case .hubWarmWait: return "hub_warm_wait"
    case .hub: return "hub"
    case .omniSTT: return "omni_stt"
    case .deepgramBatch: return "deepgram_batch"
    case .deepgramLive: return "deepgram_live"
    }
  }

  private static func isHubRoute(_ route: VoiceTurnRoute) -> Bool {
    if case .hub = route { return true }
    return route == .hubWarmWait
  }
}
