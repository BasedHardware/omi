import Foundation
import OmiSupport
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
    let winnerCount = LockedCounter()
    let group = DispatchGroup()
    let queue = DispatchQueue(label: "resume-once-racers", attributes: .concurrent)

    for _ in 0..<32 {
      group.enter()
      queue.async {
        if gate.first() {
          winnerCount.increment()
        }
        group.leave()
      }
    }

    group.wait()
    XCTAssertEqual(winnerCount.count, 1)
  }
}
