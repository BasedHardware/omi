import XCTest

@testable import Omi_Computer

private actor OnboardingAnswerWriteTestLatch {
  private var continuation: CheckedContinuation<Void, Never>?
  private var isOpen = false

  func wait() async {
    guard !isOpen else { return }
    await withCheckedContinuation { continuation in
      if isOpen {
        continuation.resume()
      } else {
        self.continuation = continuation
      }
    }
  }

  func open() {
    isOpen = true
    continuation?.resume()
    continuation = nil
  }
}

@MainActor
final class OnboardingAnswerWriteGateTests: XCTestCase {
  func testRevisionWaitsForEarlierWriteBeforeItCanReachTheBackend() async {
    let gate = OnboardingAnswerWriteGate()
    let firstWriteStarted = expectation(description: "first write started")
    let latch = OnboardingAnswerWriteTestLatch()
    var writes: [String] = []

    gate.enqueue(.name) {
      writes.append("first started")
      firstWriteStarted.fulfill()
      await latch.wait()
      writes.append("first finished")
    }
    await fulfillment(of: [firstWriteStarted], timeout: 1)

    gate.enqueue(.name) {
      writes.append("revision")
    }
    await latch.open()
    await gate.waitForIdle(.name)

    XCTAssertEqual(writes, ["first started", "first finished", "revision"])
  }
}
