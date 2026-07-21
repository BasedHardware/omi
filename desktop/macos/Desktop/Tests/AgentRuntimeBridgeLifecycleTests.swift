import XCTest

@testable import Omi_Computer

final class AgentRuntimeBridgeLifecycleTests: XCTestCase {
  func testFailedStartIsTypedTerminalStateWithRestartRecovery() {
    var lifecycle = AgentRuntimeBridgeLifecycle()

    XCTAssertEqual(lifecycle.reduce(.spawn), [.launchBridge])
    XCTAssertEqual(lifecycle.state, .starting)
    XCTAssertEqual(
      lifecycle.reduce(.spawnFailure(.handshakeTimedOut)),
      [.surfaceFailedStart(.handshakeTimedOut)])
    XCTAssertEqual(lifecycle.state, .failedStart)
    XCTAssertEqual(lifecycle.startFailure, .handshakeTimedOut)
    XCTAssertFalse(lifecycle.state.hasLiveBridge)

    XCTAssertEqual(lifecycle.reduce(.restart), [.restartBridge])
    XCTAssertEqual(lifecycle.state, .restarting)
    XCTAssertEqual(lifecycle.reduce(.spawn), [.launchBridge])
    XCTAssertEqual(lifecycle.reduce(.handshakeSucceeded), [.bridgeReady])
    XCTAssertEqual(lifecycle.state, .running)
  }

  func testRestartNeverReplaysSettledTurnsOrFramesAfterWALStop() {
    var lifecycle = AgentRuntimeBridgeLifecycle()
    _ = lifecycle.reduce(.spawn)
    _ = lifecycle.reduce(.handshakeSucceeded)
    _ = lifecycle.reduce(.kernelJournalWrite(turnID: "turn-settled", terminal: true))

    XCTAssertEqual(
      lifecycle.reduce(.walFrame(turnID: "turn-settled")),
      [.rejectWALFrame(turnID: "turn-settled")])
    XCTAssertEqual(lifecycle.reduce(.walStopFrame), [.closeWAL])
    XCTAssertEqual(
      lifecycle.reduce(.walFrame(turnID: "turn-open")),
      [.rejectWALFrame(turnID: "turn-open")])

    _ = lifecycle.reduce(.crash)
    _ = lifecycle.reduce(.restart)
    _ = lifecycle.reduce(.spawn)
    _ = lifecycle.reduce(.handshakeSucceeded)
    XCTAssertEqual(
      lifecycle.reduce(.walFrame(turnID: "turn-settled")),
      [.rejectWALFrame(turnID: "turn-settled")],
      "a restart may restore unresolved work but must never replay a settled turn")
  }

  func testSeededLifecycleSequenceFuzzerPreservesBridgeAndReplayInvariants() {
    for seed in 0..<256 {
      var generator = LifecycleSequenceGenerator(seed: UInt64(seed + 1))
      var lifecycle = AgentRuntimeBridgeLifecycle()
      var walClosedForProcess = false

      for _ in 0..<160 {
        let event = generator.nextEvent()
        if case .spawn = event { walClosedForProcess = false }
        let effects = lifecycle.reduce(event)

        XCTAssertLessThanOrEqual(
          lifecycle.state.hasLiveBridge ? 1 : 0,
          1,
          "seed \(seed) produced more than one live bridge mode")
        for effect in effects {
          if case .closeWAL = effect { walClosedForProcess = true }
          if case .applyWALFrame(let turnID) = effect {
            XCTAssertFalse(walClosedForProcess, "seed \(seed) applied WAL after its stop frame")
            XCTAssertFalse(
              lifecycle.settledTurnIDs.contains(turnID),
              "seed \(seed) replayed a terminal journal turn after restart")
          }
        }
      }
    }
  }
}

private struct LifecycleSequenceGenerator {
  private var state: UInt64

  init(seed: UInt64) {
    state = seed
  }

  mutating func nextEvent() -> AgentRuntimeBridgeLifecycle.Event {
    state = state &* 6_364_136_223_846_793_005 &+ 1
    let turnID = "turn-\(state % 7)"
    switch state % 13 {
    case 0: return .spawn
    case 1: return .spawnFailure(.launchFailed)
    case 2: return .spawnFailure(.exitedDuringStartup)
    case 3: return .handshakeSucceeded
    case 4: return .crash
    case 5: return .restart
    case 6: return .modeSwitchRequested
    case 7: return .drainRequested
    case 8: return .walFrame(turnID: turnID)
    case 9: return .walStopFrame
    case 10: return .timeout
    case 11: return .kill
    default: return .kernelJournalWrite(turnID: turnID, terminal: state & 1 == 0)
    }
  }
}
