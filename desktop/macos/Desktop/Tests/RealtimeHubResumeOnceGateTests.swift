import Foundation
import XCTest

@testable import Omi_Computer

private final class LockedCounter: @unchecked Sendable {
  private let lock = NSLock()
  private var value = 0

  func increment() {
    lock.lock()
    value += 1
    lock.unlock()
  }

  var currentValue: Int {
    lock.lock()
    defer { lock.unlock() }
    return value
  }
}

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
    XCTAssertEqual(winnerCount.currentValue, 1)
  }
}
