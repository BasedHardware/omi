import Foundation
import XCTest
@testable import Omi_Computer

final class RealtimeHubResumeOnceGateTests: XCTestCase {
  func testOnlyTheFirstContinuationCanResume() {
    let gate = RealtimeHubResumeOnceGate()

    XCTAssertTrue(gate.first())
    XCTAssertFalse(gate.first())
  }

  func testConcurrentContinuationRacersHaveOneWinner() {
    let gate = RealtimeHubResumeOnceGate()
    let winners = NSLock()
    let group = DispatchGroup()
    let queue = DispatchQueue(label: "resume-once-racers", attributes: .concurrent)
    var winnerCount = 0

    for _ in 0..<32 {
      group.enter()
      queue.async {
        if gate.first() {
          winners.lock()
          winnerCount += 1
          winners.unlock()
        }
        group.leave()
      }
    }

    group.wait()
    XCTAssertEqual(winnerCount, 1)
  }
}
