import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

final class RealtimeResponseGlowGateTests: XCTestCase {
  @MainActor
  func testIdleClearIsCancelledByNextAudioChunk() {
    var states: [Bool] = []
    let scheduler = ManualDelayedActionScheduler()
    let lease = makeLease(effectID: 1)
    let gate = RealtimeResponseGlowGate(scheduler: scheduler) { active, _ in
      states.append(active)
    }

    gate.markPlaybackActive(lease: lease)
    gate.scheduleIdleClear()
    gate.markPlaybackActive(lease: lease)

    XCTAssertFalse(scheduler.fireNext())
    XCTAssertEqual(states, [true])
    XCTAssertTrue(gate.isActive)
  }

  @MainActor
  func testIdleClearEventuallyTurnsGlowOff() {
    var states: [Bool] = []
    let scheduler = ManualDelayedActionScheduler()
    let lease = makeLease(effectID: 1)
    let gate = RealtimeResponseGlowGate(scheduler: scheduler) { active, _ in
      states.append(active)
    }

    gate.markPlaybackActive(lease: lease)
    gate.scheduleIdleClear()

    XCTAssertTrue(scheduler.fireNext())
    XCTAssertEqual(states, [true, false])
    XCTAssertFalse(gate.isActive)
  }

  @MainActor
  func testUncancellableOldTimerCannotClearReplacementLease() {
    var updates: [(Bool, VoiceOutputLease?)] = []
    let scheduler = AdversarialDelayedActionScheduler()
    let oldLease = makeLease(effectID: 1)
    let replacementLease = makeLease(effectID: 2)
    let gate = RealtimeResponseGlowGate(scheduler: scheduler) { active, lease in
      updates.append((active, lease))
    }

    gate.markPlaybackActive(lease: oldLease)
    gate.scheduleIdleClear()
    gate.markPlaybackActive(lease: replacementLease)

    XCTAssertTrue(scheduler.fireNextIgnoringCancellation())
    XCTAssertTrue(gate.isActive)
    XCTAssertEqual(updates.count, 1)
    XCTAssertEqual(updates.first?.0, true)
    XCTAssertEqual(updates.first?.1, oldLease)

    gate.scheduleIdleClear()
    XCTAssertTrue(scheduler.fireNextIgnoringCancellation())
    XCTAssertFalse(gate.isActive)
    XCTAssertEqual(updates.last?.0, false)
    XCTAssertEqual(updates.last?.1, replacementLease)
  }

  private func makeLease(effectID: UInt64) -> VoiceOutputLease {
    let turnID = VoiceTurnID()
    return VoiceOutputLease(
      id: VoiceLeaseID(),
      turnID: turnID,
      lane: .nativeRealtime,
      identity: VoiceEffectIdentity(turnID: turnID, effectID: effectID))
  }
}

@MainActor
private final class AdversarialDelayedActionScheduler: DelayedActionScheduling {
  private final class Cancellation: DelayedActionCancellation {
    func cancel() {}
  }

  private var actions: [@MainActor () -> Void] = []

  func schedule(
    after interval: TimeInterval,
    action: @escaping @MainActor () -> Void
  ) -> DelayedActionCancellation {
    _ = interval
    actions.append(action)
    return Cancellation()
  }

  func fireNextIgnoringCancellation() -> Bool {
    guard !actions.isEmpty else { return false }
    actions.removeFirst()()
    return true
  }
}
