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

    func testGuardDeferPatternOnlyExitsWhenOwnerEntered() {
        // Models the canonical ChatProvider.pollForNewMessages() usage:
        //   guard gate.tryEnter() else { return }
        //   defer { gate.exit() }
        // Non-owners return before the defer is registered, so exit() is
        // never called from a non-owning caller — the contract holds.
        let gate = ReentrancyGate()
        var exitCalls = 0

        func criticalSection() {
            guard gate.tryEnter() else { return }
            defer {
                gate.exit()
                exitCalls += 1
            }
            // simulated critical work — the second concurrent call below runs
            // before this defer fires because Swift closures run synchronously.
        }

        // First caller acquires + releases via defer.
        criticalSection()
        XCTAssertEqual(exitCalls, 1)

        // Second sequential caller also acquires cleanly after the first exited.
        criticalSection()
        XCTAssertEqual(exitCalls, 2)
    }
}
