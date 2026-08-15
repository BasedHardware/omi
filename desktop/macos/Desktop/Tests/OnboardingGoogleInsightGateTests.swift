import XCTest

@testable import Omi_Computer

final class OnboardingGoogleInsightGateTests: XCTestCase {
  private actor Signal {
    private var isOpen = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
      if isOpen { return }
      await withCheckedContinuation { waiters.append($0) }
    }

    func open() {
      guard !isOpen else { return }
      isOpen = true
      let pending = waiters
      waiters.removeAll()
      for waiter in pending {
        waiter.resume()
      }
    }
  }

  private actor Trace {
    private var values: [String] = []

    func append(_ value: String) { values.append(value) }
    func snapshot() -> [String] { values }
  }

  func testGmailWaitsForCalendarThenContinuesAfterCalendarFailure() async {
    let gate = OnboardingGoogleInsightGate()
    let gmailStarted = Signal()
    let gmailFinished = Signal()
    let trace = Trace()

    let gmail = Task {
      await gmailStarted.open()
      await gate.waitForCalendar()
      // This models Gmail's own terminal failure. It still must run after a
      // separate Calendar failure released the shared-auth gate.
      await trace.append("gmail_attempted")
      await gmailFinished.open()
      return false
    }

    await gmailStarted.wait()
    let beforeCalendarCompletes = await trace.snapshot()
    XCTAssertEqual(beforeCalendarCompletes, [])

    await trace.append("calendar_failed")
    await gate.markCalendarFinished()
    await gmailFinished.wait()

    let gmailSucceeded = await gmail.value
    let completedTrace = await trace.snapshot()
    XCTAssertFalse(gmailSucceeded)
    XCTAssertEqual(completedTrace, ["calendar_failed", "gmail_attempted"])
  }
}
