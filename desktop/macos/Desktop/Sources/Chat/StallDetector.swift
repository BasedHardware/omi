import Foundation

/// Tracks whether the active chat turn is making forward progress and
/// surfaces transitions to `.slow` / `.stalled` so the UI can render
/// progress affordances and a Cancel banner.
///
/// Two timers track independently:
///   - **Inter-event gap** — ms since the last event of any kind.
///     Captures "the bridge stopped streaming."
///   - **Per-tool no-progress gap** — ms since each in-flight tool last
///     reported progress. Captures "this specific tool stopped moving."
///
/// The detector is pure logic: time is passed in as a parameter on
/// every operation, so tests can drive it instantly without wall-clock
/// waits and production wraps it in a periodic `tick(atMs:)` task.
///
/// Wiring:
///   - On every bridge callback, `ChatProvider` calls
///     `await detector.step(kind: .other, atMs: now)` (or
///     `.toolStarted(id:)` / `.toolCompleted(id:)` for tool events).
///   - A background task running while the turn is active calls
///     `await detector.tick(atMs: now)` every ~500ms so promotions
///     surface even when no new events arrive.
///   - Returned transitions drive `ToolCallStatus` updates and the
///     message-level Cancel banner.
actor StallDetector {

  // MARK: - Public types

  enum State: Equatable, Sendable {
    case running
    case slow
    case stalled
  }

  /// What kind of event observation is being recorded.
  enum EventKind: Equatable, Sendable {
    /// Any non-tool event (text_delta, thinking_delta, init, heartbeat).
    /// Resets the inter-event gap timer.
    case other

    /// A `tool_use` was emitted; the tool is now in flight. Starts the
    /// per-tool timer for `id` (typically the `toolUseId`).
    case toolStarted(id: String)

    /// A `tool_activity` progress update for an in-flight tool. This refreshes
    /// only the tool's no-progress clock; it never changes the tool's original
    /// start time used by duration diagnostics.
    case toolProgress(id: String)

    /// A `tool_activity` with status `completed` (or `failed` /
    /// `cancelled`) arrived. Clears the per-tool timer for `id` and
    /// emits a transition back to `.running` if the tool was promoted.
    case toolCompleted(id: String)
  }

  /// A state change emitted by `step` or `tick`. Consumers translate
  /// these into `ToolCallStatus` updates and banner state.
  enum Transition: Equatable, Sendable {
    /// The whole-turn inter-event timer changed state.
    case interEvent(from: State, to: State)

    /// A specific in-flight tool's per-tool timer changed state.
    /// `id` matches the `toolUseId` from the bridge.
    case tool(id: String, from: State, to: State)
  }

  // MARK: - Configuration

  let thresholds: StallThresholds

  // MARK: - State (actor-isolated)

  private(set) var interEventState: State = .running
  private var lastEventAtMs: Int

  /// In-flight tools keyed by `toolUseId`. Removed on completion.
  private var toolStartedAtMs: [String: Int] = [:]
  private var toolLastProgressAtMs: [String: Int] = [:]
  private var toolStates: [String: State] = [:]

  // MARK: - Init

  /// `startedAtMs` is the simulated/wall-clock time of turn start. The
  /// inter-event gap clock counts from this until the first event.
  init(thresholds: StallThresholds = .v1Defaults, startedAtMs: Int) {
    self.thresholds = thresholds
    self.lastEventAtMs = startedAtMs
  }

  // MARK: - Read-only state queries

  /// Current promoted state for a specific tool, or `.running` if the
  /// tool isn't currently tracked (either never started or already
  /// completed).
  func currentToolState(id: String) -> State {
    toolStates[id] ?? .running
  }

  /// Snapshot of all in-flight tool states. Useful for the UI's "any
  /// tool stalled?" check that gates the message-level banner.
  func snapshotToolStates() -> [String: State] {
    toolStates
  }

  /// IDs of tools that have gone too long without a progress update. The caller
  /// owns the recovery action (for example, interrupting the bridge); the
  /// detector remains pure and does not perform side effects itself.
  func toolIdsWithoutProgress(durationMs: Int, atMs: Int) -> [String] {
    toolLastProgressAtMs.compactMap { id, lastProgressAt in
      atMs - lastProgressAt >= durationMs ? id : nil
    }
  }

  /// A generic bridge timeout may fire only after a full quiet interval with
  /// no tool in flight. Active tools have their own no-progress watchdog.
  func isSilentWithoutActiveTools(durationMs: Int, atMs: Int) -> Bool {
    toolStartedAtMs.isEmpty && atMs - lastEventAtMs >= durationMs
  }

  // MARK: - Observation

  /// Record an event at simulated time `atMs` and return any state
  /// transitions caused by both the observation itself (e.g. a new
  /// event arriving while the detector was `.stalled` flips it back to
  /// `.running`) and by elapsed time up to `atMs`.
  ///
  /// `step` is the entry point production wiring uses on every bridge
  /// callback. Tests may use `step` and `tick` interchangeably; `step`
  /// = observe + tick in a single actor hop.
  func step(kind: EventKind, atMs: Int) -> [Transition] {
    var transitions = observe(kind: kind, atMs: atMs)
    transitions.append(contentsOf: evaluate(atMs: atMs))
    return transitions
  }

  /// Advance to `atMs` without recording a new event. Returns any
  /// transitions caused by elapsed time crossing a threshold. Idempotent
  /// — calling `tick` repeatedly with the same `atMs` returns each
  /// transition exactly once (subsequent calls with the same `atMs`
  /// return an empty array).
  ///
  /// Production wraps this in a periodic background task while a turn
  /// is active so promotions surface even when no new events arrive.
  func tick(atMs: Int) -> [Transition] {
    evaluate(atMs: atMs)
  }

  // MARK: - Internal

  private func observe(kind: EventKind, atMs: Int) -> [Transition] {
    var transitions: [Transition] = []

    // Any event resets the inter-event gap to .running.
    if interEventState != .running {
      transitions.append(.interEvent(from: interEventState, to: .running))
      interEventState = .running
    }
    lastEventAtMs = atMs

    switch kind {
    case .other:
      break

    case .toolStarted(let id):
      if toolStartedAtMs[id] == nil {
        toolStartedAtMs[id] = atMs
        toolLastProgressAtMs[id] = atMs
        toolStates[id] = .running
      }

    case .toolProgress(let id):
      if toolStartedAtMs[id] != nil {
        toolLastProgressAtMs[id] = atMs
      }

    case .toolCompleted(let id):
      toolStartedAtMs.removeValue(forKey: id)
      toolLastProgressAtMs.removeValue(forKey: id)
      let old = toolStates.removeValue(forKey: id) ?? .running
      if old != .running {
        // Tool completed while promoted (slow/stalled → done) — UI
        // should clear the slow/stalled annotation.
        transitions.append(.tool(id: id, from: old, to: .running))
      }
    }

    return transitions
  }

  private func evaluate(atMs: Int) -> [Transition] {
    var transitions: [Transition] = []

    // Inter-event timer.
    let interGap = atMs - lastEventAtMs
    let newInter = promotedState(forElapsedMs: interGap)
    if newInter != interEventState {
      transitions.append(.interEvent(from: interEventState, to: newInter))
      interEventState = newInter
    }

    // Per-tool timers.
    for (toolId, lastProgressAt) in toolLastProgressAtMs {
      let noProgressGap = atMs - lastProgressAt
      let newToolState = promotedState(forElapsedMs: noProgressGap)
      let oldToolState = toolStates[toolId] ?? .running
      if newToolState != oldToolState {
        transitions.append(.tool(id: toolId, from: oldToolState, to: newToolState))
        toolStates[toolId] = newToolState
      }
    }

    return transitions
  }

  private func promotedState(forElapsedMs elapsed: Int) -> State {
    if elapsed >= thresholds.stalledGapMs { return .stalled }
    if elapsed >= thresholds.slowGapMs { return .slow }
    return .running
  }
}
