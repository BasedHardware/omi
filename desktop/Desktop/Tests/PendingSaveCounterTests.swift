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

    /// Defensive: stray `end()` calls without a matching `begin()` must
    /// not drive the counter negative. A negative count would
    /// misreport `isActive == false` when a subsequent `begin()` is
    /// pending, silently re-opening the race window.
    func testEndIsBoundedAtZero() {
        let counter = PendingSaveCounter()
        counter.end()
        counter.end()
        counter.end()
        XCTAssertEqual(counter.currentCount, 0)
        XCTAssertFalse(counter.isActive)
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
