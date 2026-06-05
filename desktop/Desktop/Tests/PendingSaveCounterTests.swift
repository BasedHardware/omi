import XCTest

@testable import Omi_Computer

/// Contract tests for `PendingSaveCounter` — the synchronization
/// primitive that gates `pollForNewMessages` against in-flight
/// `saveMessage(...)` calls.
@MainActor
final class PendingSaveCounterTests: XCTestCase {

    func testFreshCounterIsInactive() {
        let counter = PendingSaveCounter()
        XCTAssertFalse(counter.isActive)
        XCTAssertEqual(counter.currentCount, 0)
    }

    func testBeginActivatesCounter() {
        let counter = PendingSaveCounter()
        counter.begin()
        XCTAssertTrue(counter.isActive)
        XCTAssertEqual(counter.currentCount, 1)
    }

    func testEndDecrementsCounter() {
        let counter = PendingSaveCounter()
        counter.begin()
        counter.end()
        XCTAssertFalse(counter.isActive)
        XCTAssertEqual(counter.currentCount, 0)
    }

    /// Multiple sites can hold the counter simultaneously. This mirrors
    /// production: `sendMessage` saves both the user message and the AI
    /// response, plus a partial-save path on error. Concurrent saves
    /// must all suppress the poll until the last one completes.
    func testMultipleHoldersStack() {
        let counter = PendingSaveCounter()
        counter.begin()
        counter.begin()
        counter.begin()
        XCTAssertEqual(counter.currentCount, 3)
        XCTAssertTrue(counter.isActive)

        counter.end()
        XCTAssertEqual(counter.currentCount, 2)
        XCTAssertTrue(counter.isActive, "still active until all holders release")

        counter.end()
        counter.end()
        XCTAssertEqual(counter.currentCount, 0)
        XCTAssertFalse(counter.isActive)
    }

    /// The counter must not get "stuck" or go negative across balanced
    /// use — after equal begins and ends it returns cleanly to zero and
    /// a fresh round still activates it. (Calling `end()` without a
    /// matching `begin()` is a programmer error caught by an `assert` in
    /// debug builds; the release-build guard still bounds it at zero.)
    func testCounterReturnsToZeroAndStaysUsableAcrossRounds() {
        let counter = PendingSaveCounter()
        counter.begin()
        counter.begin()
        counter.end()
        counter.end()
        XCTAssertEqual(counter.currentCount, 0)
        XCTAssertFalse(counter.isActive)

        // A subsequent round must still activate — no stuck state.
        counter.begin()
        XCTAssertTrue(counter.isActive)
        counter.end()
        XCTAssertFalse(counter.isActive)
    }

    /// `onDrained` fires exactly when the last holder releases (count
    /// returns to 0), not on intermediate `end()` calls. This is what
    /// lets the owner re-run a poll cycle that was deferred while saves
    /// were in flight.
    func testOnDrainedFiresOnlyWhenCountReturnsToZero() {
        let counter = PendingSaveCounter()
        var drains = 0
        counter.onDrained = { drains += 1 }

        counter.begin()
        counter.begin()
        counter.end()
        XCTAssertEqual(drains, 0, "still one holder — must not fire yet")
        counter.end()
        XCTAssertEqual(drains, 1, "last holder released — fires once")

        // A fresh round fires again.
        counter.begin()
        counter.end()
        XCTAssertEqual(drains, 2)
    }

    /// Production usage interleaves begin/end across overlapping save
    /// Tasks. Verify the counter behaves correctly when begins and
    /// ends arrive out of original order.
    func testInterleavedBeginAndEnd() {
        let counter = PendingSaveCounter()
        // Site A starts
        counter.begin()
        XCTAssertTrue(counter.isActive)
        // Site B starts before A finishes
        counter.begin()
        XCTAssertEqual(counter.currentCount, 2)
        // Site A finishes first
        counter.end()
        XCTAssertTrue(counter.isActive, "B is still in flight")
        // Site B finishes
        counter.end()
        XCTAssertFalse(counter.isActive)
    }
}
