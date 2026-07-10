import Foundation

@MainActor
protocol VoiceTurnDeadlineCancellation: AnyObject {
  func cancel()
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
private final class TaskVoiceTurnDeadlineCancellation: VoiceTurnDeadlineCancellation {
  private var task: Task<Void, Never>?

  init(task: Task<Void, Never>) {
    self.task = task
  }

  func cancel() {
    task?.cancel()
    task = nil
  }
}

@MainActor
final class TaskVoiceTurnDeadlineScheduler: VoiceTurnDeadlineScheduling {
  func schedule(
    deadline: VoiceTurnDeadline,
    after interval: TimeInterval,
    action: @escaping @MainActor () -> Void
  )
    -> VoiceTurnDeadlineCancellation
  {
    _ = deadline
    let task = Task { @MainActor in
      do {
        try await Task.sleep(nanoseconds: UInt64(max(0, interval) * 1_000_000_000))
      } catch {
        return
      }
      guard !Task.isCancelled else { return }
      action()
    }
    return TaskVoiceTurnDeadlineCancellation(task: task)
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

@MainActor
final class PTTBarPresenter {
  private weak var barState: FloatingControlBarState?
  private var previousProjection = VoiceTurnUIProjection.idle

  init(barState: FloatingControlBarState) {
    self.barState = barState
  }

  func apply(_ projection: VoiceTurnUIProjection) {
    guard let barState else { return }
    let wasExpandedForVoice = previousProjection.isListening || !previousProjection.hint.isEmpty
    let shouldExpandForVoice = projection.isListening || !projection.hint.isEmpty

    barState.isVoiceListening = shouldExpandForVoice
    barState.isVoiceLocked = projection.isLocked
    barState.isVoiceFollowUp = projection.isFollowUp && shouldExpandForVoice
    barState.voiceTranscript = projection.transcript
    if !projection.isFollowUp {
      barState.voiceFollowUpTranscript = ""
    }
    barState.pttHintText = projection.hint
    barState.isThinking = projection.isThinking
    if projection.isResponseActive {
      barState.isVoiceResponseActive = true
    } else if projection.isResponseWaiting {
      barState.beginVoiceResponseWaiting()
    } else if previousProjection.isResponseActive || previousProjection.isResponseWaiting {
      barState.clearVoiceResponseState()
    }

    if shouldExpandForVoice != wasExpandedForVoice,
      !barState.isVoiceFollowUp,
      !barState.showingAIConversation,
      UserDefaults.standard.bool(forKey: .hasCompletedOnboarding)
    {
      FloatingControlBarManager.shared.resizeForPTT(expanded: shouldExpandForVoice)
    }
    previousProjection = projection
  }
}

@MainActor
final class VoiceTurnCoordinator {
  static let shared = VoiceTurnCoordinator()

  typealias EffectHandler = @MainActor (VoiceTurnEffect) -> Void
  typealias SnapshotHandler = @MainActor (VoiceTurnModel) -> Void

  private struct DeadlineKey: Hashable {
    let turnID: VoiceTurnID
    let deadline: VoiceTurnDeadline
  }

  private let reducer: VoiceTurnReducer
  private let scheduler: VoiceTurnDeadlineScheduling
  private var deadlineCancellations: [DeadlineKey: VoiceTurnDeadlineCancellation] = [:]
  private var presenter: PTTBarPresenter?
  private var effectHandler: EffectHandler?
  private var snapshotHandler: SnapshotHandler?
  private var timeline: [VoiceTurnTimelineEntry] = []
  private let timelineLimit: Int
  private var timelineSequence: UInt64 = 0

  private(set) var model: VoiceTurnModel

  init(
    model: VoiceTurnModel = .idle,
    reducer: VoiceTurnReducer = VoiceTurnReducer(),
    scheduler: VoiceTurnDeadlineScheduling? = nil,
    timelineLimit: Int = 256
  ) {
    self.model = model
    self.reducer = reducer
    self.scheduler = scheduler ?? TaskVoiceTurnDeadlineScheduler()
    self.timelineLimit = max(1, timelineLimit)
  }

  var activeTurnID: VoiceTurnID? { model.turn?.phase.isTerminal == false ? model.turn?.id : nil }
  var activeTurn: VoiceTurn? { model.turn?.phase.isTerminal == false ? model.turn : nil }
  var projection: VoiceTurnUIProjection { model.turn?.projection ?? .idle }

  func configure(barState: FloatingControlBarState) {
    presenter = PTTBarPresenter(barState: barState)
    presenter?.apply(projection)
  }

  func setEffectHandler(_ handler: EffectHandler?) {
    effectHandler = handler
  }

  func setSnapshotHandler(_ handler: SnapshotHandler?) {
    snapshotHandler = handler
    handler?(model)
  }

  @discardableResult
  func begin(intent: VoiceTurnIntent, id: VoiceTurnID = VoiceTurnID()) -> VoiceTurnID {
    if model.turn?.phase.isTerminal == true {
      send(.reset)
    }
    send(.start(turnID: id, intent: intent))
    return id
  }

  func send(_ event: VoiceTurnEvent) {
    let before = model
    let reduction = reducer.reduce(model, event)
    model = reduction.model
    appendTimeline(event: event, before: before, after: model)
    process(reduction.effects)
    presenter?.apply(projection)
    snapshotHandler?(model)
  }

  func timelineSnapshot() -> [VoiceTurnTimelineEntry] {
    timeline
  }

  func refreshPresentation() {
    presenter?.apply(projection)
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

  private func schedule(turnID: VoiceTurnID, deadline: VoiceTurnDeadline, interval: TimeInterval) {
    let key = DeadlineKey(turnID: turnID, deadline: deadline)
    deadlineCancellations.removeValue(forKey: key)?.cancel()
    deadlineCancellations[key] = scheduler.schedule(deadline: deadline, after: interval) {
      [weak self] in
      guard let self else { return }
      self.deadlineCancellations.removeValue(forKey: key)
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
    case .agentFollowUp: return "agent_follow_up"
    }
  }
}
