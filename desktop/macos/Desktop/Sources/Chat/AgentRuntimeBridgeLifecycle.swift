import Foundation

/// Pure lifecycle policy for the local JSONL bridge. Process/pipe I/O stays in
/// `AgentRuntimeProcess`; this type owns only legal state transitions and the
/// replay safety facts that must survive a crash/restart sequence.
///
/// A bridge-start failure is terminal for the attempted launch, but is
/// deliberately recoverable: the caller can request a restart and surface a
/// retry action instead of leaving chat in an ambiguous non-running state.
struct AgentRuntimeBridgeLifecycle: Equatable, Sendable {
  enum State: String, CaseIterable, Sendable {
    case stopped
    case starting
    case running
    case modeSwitching
    case draining
    case crashed
    case restarting
    case failedStart

    var hasLiveBridge: Bool {
      switch self {
      case .starting, .running, .modeSwitching, .draining:
        return true
      case .stopped, .crashed, .restarting, .failedStart:
        return false
      }
    }
  }

  enum StartFailure: String, Equatable, Sendable {
    case launchFailed
    case handshakeTimedOut
    case incompatibleHandshake
    case exitedDuringStartup
  }

  enum Event: Equatable, Sendable {
    case spawn
    case spawnFailure(StartFailure)
    case handshakeSucceeded
    case crash
    case restart
    case modeSwitchRequested
    case drainRequested
    case walFrame(turnID: String)
    case walStopFrame
    case timeout
    case kill
    case kernelJournalWrite(turnID: String, terminal: Bool)
  }

  enum Effect: Equatable, Sendable {
    case launchBridge
    case bridgeReady
    case beginDrain
    case closeWAL
    case applyWALFrame(turnID: String)
    case rejectWALFrame(turnID: String)
    case recordJournalWrite(turnID: String, terminal: Bool)
    case surfaceFailedStart(StartFailure)
    case restartBridge
  }

  private(set) var state: State = .stopped
  private(set) var startFailure: StartFailure?
  private(set) var acceptsWALFrames = false
  private(set) var settledTurnIDs: Set<String> = []

  /// Reduces one lifecycle event. Invalid/redundant events are harmless no-ops;
  /// callers cannot make a second bridge live or replay a settled turn by
  /// sending an event out of order.
  @discardableResult
  mutating func reduce(_ event: Event) -> [Effect] {
    switch event {
    case .spawn:
      guard [.stopped, .crashed, .restarting, .failedStart].contains(state) else { return [] }
      state = .starting
      startFailure = nil
      acceptsWALFrames = true
      return [.launchBridge]

    case .spawnFailure(let failure):
      guard state == .starting else { return [] }
      state = .failedStart
      startFailure = failure
      acceptsWALFrames = false
      return [.surfaceFailedStart(failure)]

    case .handshakeSucceeded:
      guard state == .starting else { return [] }
      state = .running
      return [.bridgeReady]

    case .crash:
      guard state != .stopped else { return [] }
      state = .crashed
      acceptsWALFrames = false
      return [.closeWAL]

    case .restart:
      guard [.stopped, .crashed, .failedStart].contains(state) else { return [] }
      state = .restarting
      acceptsWALFrames = false
      return [.restartBridge]

    case .modeSwitchRequested:
      guard state == .running else { return [] }
      state = .modeSwitching
      return [.beginDrain]

    case .drainRequested:
      guard [.running, .modeSwitching].contains(state) else { return [] }
      state = .draining
      return [.beginDrain]

    case .walFrame(let turnID):
      guard acceptsWALFrames, !settledTurnIDs.contains(turnID) else {
        return [.rejectWALFrame(turnID: turnID)]
      }
      return [.applyWALFrame(turnID: turnID)]

    case .walStopFrame:
      guard acceptsWALFrames else { return [] }
      acceptsWALFrames = false
      return [.closeWAL]

    case .timeout:
      switch state {
      case .starting:
        return reduce(.spawnFailure(.handshakeTimedOut))
      case .modeSwitching:
        return reduce(.drainRequested)
      case .draining:
        state = .stopped
        acceptsWALFrames = false
        return [.closeWAL]
      case .stopped, .running, .crashed, .restarting, .failedStart:
        return []
      }

    case .kill:
      guard state != .stopped else { return [] }
      state = .stopped
      acceptsWALFrames = false
      return [.closeWAL]

    case .kernelJournalWrite(let turnID, let terminal):
      if terminal {
        settledTurnIDs.insert(turnID)
      }
      return [.recordJournalWrite(turnID: turnID, terminal: terminal)]
    }
  }
}
