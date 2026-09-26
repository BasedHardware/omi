import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the hub classification inject. A refused send must
/// stay pending and retry; finalize must not drop it before the input window;
/// a connect signal mid-send must rerun. These drive
/// `InterjectClassificationDelivery` by interleaving scheduled work — not by
/// grepping source and not by running the inject to completion synchronously
/// on the calling turn (that hid the races this suite exists to pin).
@MainActor
final class InterjectClassificationDeliveryTests: XCTestCase {
  @MainActor
  private final class Harness {
    var sessionLive = true
    var acceptSends = true
    var suspendInjects = false
    private(set) var injected: [String] = []
    var injectCount: Int { injected.count }
    private(set) var abandoned = 0
    private(set) var scheduled: [@MainActor () async -> Void] = []
    private(set) var suspendedInjects: [(String, CheckedContinuation<Bool, Never>)] = []

    func makeSubject() -> InterjectClassificationDelivery {
      InterjectClassificationDelivery(
        isVoiceSessionLive: { [unowned self] in self.sessionLive },
        injectInstruction: { [unowned self] text in
          if self.suspendInjects {
            return await withCheckedContinuation { continuation in
              self.suspendedInjects.append((text, continuation))
            }
          }
          guard self.acceptSends else { return false }
          self.injected.append(text)
          return true
        },
        abandonInstruction: { [unowned self] in
          self.abandoned += 1
        },
        scheduleWork: { [unowned self] work in
          self.scheduled.append(work)
        }
      )
    }

    func drainScheduledWork() async {
      while !scheduled.isEmpty {
        let work = scheduled.removeFirst()
        await work()
      }
    }

    func resumeSuspendedInjects(accept: Bool) {
      let waiting = suspendedInjects
      suspendedInjects.removeAll()
      for (text, continuation) in waiting {
        if accept {
          injected.append(text)
        }
        continuation.resume(returning: accept)
      }
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

  func testRefusedInjectStaysPendingAndRetriesWhenTheSessionOpens() async {
    harness.acceptSends = false
    subject.pttDidStart(shouldAttach: true, instruction: "TURN INSTRUCTION")
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.injectCount, 0)
    XCTAssertNotNil(subject.pendingInstruction, "a refused inject must be retried, not dropped")

    harness.acceptSends = true
    subject.voiceSessionDidOpenInputWindow()
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.injectCount, 1)
    XCTAssertEqual(harness.injected[0], "TURN INSTRUCTION")
    XCTAssertNil(subject.pendingInstruction)
  }

  func testRefusedInjectRetriesOnConnect() async {
    harness.sessionLive = false
    subject.pttDidStart(shouldAttach: true, instruction: "waiting")
    await harness.drainScheduledWork()
    XCTAssertEqual(harness.injectCount, 0)
    XCTAssertNotNil(subject.pendingInstruction)

    harness.sessionLive = true
    subject.voiceSessionDidConnect()
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.injectCount, 1)
    XCTAssertNil(subject.pendingInstruction)
  }

  func testTapToLockProducesExactlyOneInject() async {
    subject.pttDidStart(shouldAttach: true, instruction: "once")
    await harness.drainScheduledWork()
    subject.pttDidStart(shouldAttach: true, instruction: "once")
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.injectCount, 1, "lock must not enqueue a second classification inject")
    XCTAssertNil(subject.pendingInstruction)
  }

  func testPTTCancelDropsAnUnconfirmedInject() async {
    harness.acceptSends = false
    subject.pttDidStart(shouldAttach: true, instruction: "late")
    await harness.drainScheduledWork()
    XCTAssertNotNil(subject.pendingInstruction)

    subject.pttDidCancel()
    XCTAssertNil(subject.pendingInstruction)
    XCTAssertNil(subject.activeGeneration)
    XCTAssertEqual(harness.abandoned, 1)

    harness.acceptSends = true
    subject.voiceSessionDidOpenInputWindow()
    await harness.drainScheduledWork()
    XCTAssertEqual(harness.injectCount, 0, "a cancelled inject must not land after PTT ends")
  }

  func testFinalizeKeepsPendingInjectUntilTheInputWindow() async {
    harness.acceptSends = false
    subject.pttDidStart(shouldAttach: true, instruction: "TURN INSTRUCTION")
    await harness.drainScheduledWork()
    XCTAssertNotNil(subject.pendingInstruction)

    subject.pttDidRelease()
    XCTAssertFalse(subject.isHoldOpen)
    XCTAssertNotNil(
      subject.pendingInstruction,
      "finalize must not drop the inject before hubDidOpenInputWindow")

    harness.acceptSends = true
    subject.voiceSessionDidOpenInputWindow()
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.injectCount, 1)
    XCTAssertEqual(harness.injected[0], "TURN INSTRUCTION")
    XCTAssertNil(subject.pendingInstruction)
    XCTAssertEqual(harness.abandoned, 0)
  }

  func testConnectDuringRefusedSendRerunsDelivery() async {
    harness.suspendInjects = true
    subject.pttDidStart(shouldAttach: true, instruction: "TURN INSTRUCTION")

    let inFlight = Task { await harness.drainScheduledWork() }
    for _ in 0..<200 {
      if !harness.suspendedInjects.isEmpty { break }
      await Task.yield()
    }
    XCTAssertFalse(harness.suspendedInjects.isEmpty, "delivery must be awaiting the inject")

    subject.voiceSessionDidConnect()
    harness.suspendInjects = false
    harness.acceptSends = true
    harness.resumeSuspendedInjects(accept: false)
    await inFlight.value
    await harness.drainScheduledWork()

    XCTAssertEqual(
      harness.injectCount, 1,
      "a connect signal during a refused send must rerun delivery afterwards")
    XCTAssertEqual(harness.injected[0], "TURN INSTRUCTION")
    XCTAssertNil(subject.pendingInstruction)
  }

  func testShouldAttachFalseDoesNotEnqueue() async {
    subject.pttDidStart(shouldAttach: false, instruction: "no")
    await harness.drainScheduledWork()
    XCTAssertEqual(harness.injectCount, 0)
    XCTAssertNil(subject.pendingInstruction)
    XCTAssertNil(subject.activeGeneration)
  }
}
