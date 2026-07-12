import XCTest
@testable import Omi_Computer

final class RealtimeResponseGlowGateTests: XCTestCase {
  @MainActor
  func testIdleClearIsCancelledByNextAudioChunk() {
    var states: [Bool] = []
    let scheduler = ManualDelayedActionScheduler()
    let gate = RealtimeResponseGlowGate(scheduler: scheduler) { active in
      states.append(active)
    }

    gate.markPlaybackActive()
    gate.scheduleIdleClear()
    gate.markPlaybackActive()

    XCTAssertFalse(scheduler.fireNext())
    XCTAssertEqual(states, [true])
    XCTAssertTrue(gate.isActive)
  }

  @MainActor
  func testIdleClearEventuallyTurnsGlowOff() {
    var states: [Bool] = []
    let scheduler = ManualDelayedActionScheduler()
    let gate = RealtimeResponseGlowGate(scheduler: scheduler) { active in
      states.append(active)
    }

    gate.markPlaybackActive()
    gate.scheduleIdleClear()

    XCTAssertTrue(scheduler.fireNext())
    XCTAssertEqual(states, [true, false])
    XCTAssertFalse(gate.isActive)
  }
}
