import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the hub classification inject. A refused send must
/// stay pending and retry; tap-to-lock must not enqueue a second copy. These
/// drive `InterjectClassificationDelivery` the same way
/// `NotchCardVoiceDeliveryTests` drive card delivery — not by grepping source.
@MainActor
final class InterjectClassificationDeliveryTests: XCTestCase {
  @MainActor
  private final class Harness {
    var sessionLive = true
    var acceptSends = true
    private(set) var injected: [String] = []
    var injectCount: Int { injected.count }

    func makeSubject() -> InterjectClassificationDelivery {
      InterjectClassificationDelivery(
        isVoiceSessionLive: { [unowned self] in self.sessionLive },
        injectInstruction: { [unowned self] text in
          guard self.acceptSends else { return false }
          self.injected.append(text)
          return true
        },
        scheduleWork: { work in
          let semaphore = DispatchSemaphore(value: 0)
          Task { @MainActor in
            await work()
            semaphore.signal()
          }
          while semaphore.wait(timeout: .now()) == .timedOut {
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.005))
          }
        }
      )
    }
  }

  private var harness = Harness()
  private var subjectStorage: InterjectClassificationDelivery?
  private var subject: InterjectClassificationDelivery {
    guard let subjectStorage else {
      preconditionFailure("subject accessed before setUp")
    }
    return subjectStorage
  }

  override func setUp() async throws {
    harness = Harness()
    subjectStorage = harness.makeSubject()
  }

  func testRefusedInjectStaysPendingAndRetriesWhenTheSessionOpens() {
    harness.acceptSends = false
    subject.pttDidStart(shouldAttach: true, instruction: "TURN INSTRUCTION")

    XCTAssertEqual(harness.injectCount, 0)
    XCTAssertNotNil(subject.pendingInstruction, "a refused inject must be retried, not dropped")

    harness.acceptSends = true
    subject.voiceSessionDidOpenInputWindow()

    XCTAssertEqual(harness.injectCount, 1)
    XCTAssertEqual(harness.injected[0], "TURN INSTRUCTION")
    XCTAssertNil(subject.pendingInstruction)
  }

  func testRefusedInjectRetriesOnConnect() {
    harness.sessionLive = false
    subject.pttDidStart(shouldAttach: true, instruction: "waiting")
    XCTAssertEqual(harness.injectCount, 0)
    XCTAssertNotNil(subject.pendingInstruction)

    harness.sessionLive = true
    subject.voiceSessionDidConnect()

    XCTAssertEqual(harness.injectCount, 1)
    XCTAssertNil(subject.pendingInstruction)
  }

  func testTapToLockProducesExactlyOneInject() {
    subject.pttDidStart(shouldAttach: true, instruction: "once")
    subject.pttDidStart(shouldAttach: true, instruction: "once")

    XCTAssertEqual(harness.injectCount, 1, "lock must not enqueue a second classification inject")
    XCTAssertNil(subject.pendingInstruction)
  }

  func testPTTEndCancelsAnUnconfirmedInject() {
    harness.acceptSends = false
    subject.pttDidStart(shouldAttach: true, instruction: "late")
    XCTAssertNotNil(subject.pendingInstruction)

    subject.pttDidEnd()
    XCTAssertNil(subject.pendingInstruction)
    XCTAssertNil(subject.activeGeneration)

    harness.acceptSends = true
    subject.voiceSessionDidOpenInputWindow()
    XCTAssertEqual(harness.injectCount, 0, "a cancelled inject must not land after PTT ends")
  }

  func testShouldAttachFalseDoesNotEnqueue() {
    subject.pttDidStart(shouldAttach: false, instruction: "no")
    XCTAssertEqual(harness.injectCount, 0)
    XCTAssertNil(subject.pendingInstruction)
    XCTAssertNil(subject.activeGeneration)
  }
}
