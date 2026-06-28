import XCTest
@testable import Omi_Computer

/// Tests for `ReentrancyGate`, the single-entry gate that prevents overlapping
/// `ChatProvider.pollForNewMessages()` fetches when `didBecomeActive` and
/// `.refreshAllData` fire back-to-back.
@MainActor
final class ReentrancyGateTests: XCTestCase {

    func testFirstEnterSucceeds() {
        let gate = ReentrancyGate()
        XCTAssertTrue(gate.tryEnter(), "First enter on a fresh gate must succeed")
    }

    func testSecondEnterWithoutExitIsBlocked() {
        let gate = ReentrancyGate()
        XCTAssertTrue(gate.tryEnter())
        XCTAssertFalse(
            gate.tryEnter(),
            "Second enter without matching exit must be blocked (in-flight)"
        )
    }

    func testEnterAfterExitSucceeds() {
        let gate = ReentrancyGate()
        XCTAssertTrue(gate.tryEnter())
        gate.exit()
        XCTAssertTrue(
            gate.tryEnter(),
            "Enter after exit must succeed — gate should be reopened"
        )
    }

    func testRepeatedEnterExitCyclesAllSucceed() {
        // Simulates activation + Cmd+R firing sequentially (not overlapping) —
        // every cycle should complete cleanly.
        let gate = ReentrancyGate()
        for cycle in 0..<5 {
            XCTAssertTrue(
                gate.tryEnter(),
                "Cycle \(cycle): enter should succeed after prior exit"
            )
            gate.exit()
        }
    }

    func testOverlappingTriggersResultInOneEntry() {
        // Simulates the exact race `ChatProvider.pollGate` guards against:
        // activation + Cmd+R fire while a fetch is in flight — only one caller
        // may enter, the rest must bail out until the in-flight caller exits.
        let gate = ReentrancyGate()
        var enteredCount = 0

        // Caller A starts the fetch
        if gate.tryEnter() { enteredCount += 1 }
        // Caller B (overlapping) tries while A is still in flight
        if gate.tryEnter() { enteredCount += 1 }
        // Caller C (overlapping) tries while A is still in flight
        if gate.tryEnter() { enteredCount += 1 }

        XCTAssertEqual(enteredCount, 1, "Only one of 3 overlapping callers may enter")

        // Caller A completes
        gate.exit()

        // Caller D arrives after A exited — should be allowed
        XCTAssertTrue(gate.tryEnter(), "New caller after exit must be allowed")
        gate.exit()
    }

    func testGuardDeferPatternNonOwnerDoesNotCallExit() {
        // Models the canonical ChatProvider.pollForNewMessages() usage:
        //   guard gate.tryEnter() else { return }
        //   defer { gate.exit() }
        //
        // Regression guard: if a future edit swapped `defer` above `guard`, a
        // non-owning caller would still fire `exit()` and reopen the gate while
        // the owner was still inside the critical section. This test forces an
        // overlap — caller A holds the gate, caller B invokes the critical
        // section while A is still in-flight — and asserts B neither enters
        // nor reopens the gate.
        let gate = ReentrancyGate()
        var exitCalls = 0

        func criticalSection() {
            guard gate.tryEnter() else { return }
            defer {
                gate.exit()
                exitCalls += 1
            }
        }

        // Caller A (the test itself) acquires the gate directly.
        XCTAssertTrue(gate.tryEnter(), "Precondition: caller A must acquire the gate")

        // Caller B invokes the critical section while A is still in-flight.
        // Under guard/defer, B's guard short-circuits and no `defer` is registered,
        // so exit() must not fire.
        criticalSection()
        XCTAssertEqual(exitCalls, 0, "Non-owner caller B must not register an exit")

        // Gate must still be owned by A — B must not have reopened it.
        XCTAssertFalse(
            gate.tryEnter(),
            "Gate must still be held by A; a regressed guard/defer order would have reopened it"
        )

        // A releases; caller C can now run through the critical section normally.
        gate.exit()
        criticalSection()
        XCTAssertEqual(exitCalls, 1, "Owner caller C must register exactly one exit")
    }
}
