import XCTest
@testable import Omi_Computer

final class RealtimeResponseGlowGateTests: XCTestCase {
  func testIdleClearIsCancelledByNextAudioChunk() {
    var states: [Bool] = []
    let gate = RealtimeResponseGlowGate(idleClearDelay: 0.05) { active in
      states.append(active)
    }

    gate.markPlaybackActive()
    gate.scheduleIdleClear()
    gate.markPlaybackActive()

    let expectation = expectation(description: "idle clear would have fired")
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.08) {
      expectation.fulfill()
    }
    wait(for: [expectation], timeout: 0.2)

    XCTAssertEqual(states, [true])
    XCTAssertTrue(gate.isActive)
  }

  func testIdleClearEventuallyTurnsGlowOff() {
    var states: [Bool] = []
    let gate = RealtimeResponseGlowGate(idleClearDelay: 0.02) { active in
      states.append(active)
    }

    gate.markPlaybackActive()
    gate.scheduleIdleClear()

    let expectation = expectation(description: "idle clear fired")
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
      expectation.fulfill()
    }
    wait(for: [expectation], timeout: 0.2)

    XCTAssertEqual(states, [true, false])
    XCTAssertFalse(gate.isActive)
  }
}
