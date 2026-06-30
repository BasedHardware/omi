import XCTest
@testable import Omi_Computer
import AppKit

/// Tests for ClipboardWatcher.
///
/// Uses injected `changeCountSource` + `stringSource` closures (a
/// fake pasteboard that bumps changeCount on write) rather than
/// NSPasteboard.general. Reason: xctest runs in a sandbox that does
/// NOT have access to the user's system pasteboard — changeCount is
/// pinned at startup and never bumps in the test runner. The
/// injected sources simulate the real NSPasteboard.general behavior
/// (changeCount increments per write).
///
/// P1 (cubic follow-up): the previous design used a single Source
/// closure that read BOTH changeCount AND string. The fix splits
/// into two closures so the watcher's main loop only reads the
/// string when the change count has actually moved.
@MainActor
final class ClipboardWatcherTests: XCTestCase {

    /// In-memory pasteboard fake for tests. Mirrors NSPasteboard.general's
    /// real-world behavior: changeCount increments on every clear / set.
    /// String content is held separately.
    final class FakeClipboard {
        private(set) var changeCount: Int = 0
        private(set) var string: String?

        func clearContents() {
            string = nil
            changeCount += 1
        }

        func setString(_ value: String) {
            string = value
            changeCount += 1
        }
    }

    private var fake: FakeClipboard!

    override func setUp() {
        super.setUp()
        fake = FakeClipboard()
    }

    override func tearDown() {
        fake = nil
        super.tearDown()
    }

    private func makeWatcher(
        pollInterval: TimeInterval = 999.0,
        handler: @escaping ClipboardWatcher.ChangeHandler
    ) -> ClipboardWatcher {
        ClipboardWatcher(
            changeCountSource: { [weak fake] in fake?.changeCount ?? 0 },
            stringSource: { [weak fake] in fake?.string },
            pollInterval: pollInterval,
            handler: handler
        )
    }

    func test_emits_handler_when_clipboard_string_changes() {
        let exp = expectation(description: "handler called")
        var received: String?
        let watcher = makeWatcher { content in
            received = content
            exp.fulfill()
        }

        fake.setString("123456789:AAEhBP7fWqu7vK3HbZGE-vJRq4YH9k5m7XQ")
        watcher.checkClipboard()
        wait(for: [exp], timeout: 2.0)
        XCTAssertEqual(received, "123456789:AAEhBP7fWqu7vK3HbZGE-vJRq4YH9k5m7XQ")
    }

    func test_does_not_emit_when_changeCount_unchanged() {
        // Establish a baseline (write once, then start watching). The
        // watcher's seed should match changeCount at init time, so a
        // check with no further changes must not emit.
        var callCount = 0
        fake.setString("baseline")
        let watcher = makeWatcher { _ in callCount += 1 }
        watcher.checkClipboard()
        XCTAssertEqual(callCount, 0)
    }

    func test_emits_for_each_new_clipboard_content() {
        // Drive the watcher synchronously via checkClipboard() to avoid
        // Timer / RunLoop timing flakiness. The watcher must emit for
        // every fresh content change — that's the property the
        // production ConnectSheet relies on (each copy from @BotFather
        // fires the auto-detect handler).
        var received: [String] = []
        let watcher = makeWatcher { content in received.append(content) }

        watcher.checkClipboard()
        XCTAssertTrue(received.isEmpty, "no emit on initial check")

        fake.setString("first-value")
        watcher.checkClipboard()
        XCTAssertEqual(received, ["first-value"])

        fake.setString("second-value")
        watcher.checkClipboard()
        XCTAssertEqual(received, ["first-value", "second-value"])

        // Same string content again — changeCount still bumps on the
        // fake, so the watcher still notifies. The VALIDATOR (in
        // ConnectSheet) decides whether to actually overwrite the
        // field; the watcher's job is just "tell me when changeCount
        // changes."
        fake.setString("second-value")
        watcher.checkClipboard()
        XCTAssertEqual(received, ["first-value", "second-value", "second-value"])
    }

    func test_does_not_emit_when_clipboard_contains_non_string_content() {
        // changeCount goes up when content is cleared too. The watcher
        // should suppress the emit because stringSource() returns nil.
        var callCount = 0
        let watcher = makeWatcher { _ in callCount += 1 }
        fake.clearContents()
        watcher.checkClipboard()
        XCTAssertEqual(callCount, 0, "watcher should skip when string content is nil")
    }

    func test_does_not_emit_when_empty_string_clears_previous_content() {
        // Edge case: clearContents() puts the string to nil AND bumps
        // changeCount. After this, a checkClipboard() must NOT emit an
        // empty string to the handler (would be confusing for the
        // validator).
        var received: [String] = []
        let watcher = makeWatcher { content in received.append(content) }
        fake.setString("previous")
        watcher.checkClipboard()
        XCTAssertEqual(received, ["previous"])

        fake.clearContents()
        watcher.checkClipboard()
        XCTAssertEqual(received, ["previous"], "clearContents should NOT trigger an emit (string is nil)")
    }

    func test_stop_prevents_further_emits() {
        // P2 (cubic, PR #8682): the previous version used a real Timer
        // with pollInterval=0.01s + DispatchQueue.main.asyncAfter to
        // wait for the timer to fire, which races against the
        // dispatch-to-MainActor Task the timer creates and produced
        // intermittent CI failures. The watcher's `isRunning` getter
        // lets us assert start()/stop() lifecycle synchronously
        // without spinning a real timer.
        var callCount = 0
        let watcher = makeWatcher { _ in callCount += 1 }
        XCTAssertFalse(watcher.isRunning, "watcher must not be running before start()")

        watcher.start()
        XCTAssertTrue(watcher.isRunning, "start() must schedule the timer")

        // Drive one tick to confirm the watcher works when running.
        fake.setString("v1")
        watcher.checkClipboard()
        XCTAssertEqual(callCount, 1, "watcher must emit v1 while running")

        watcher.stop()
        XCTAssertFalse(watcher.isRunning, "stop() must invalidate the timer")
        XCTAssertTrue(callCount == 1, "stop() must not retroactively roll back emissions")

        // stop() is safe to call repeatedly.
        watcher.stop()
        XCTAssertFalse(watcher.isRunning)
    }

    func test_checkClipboard_is_idempotent() {
        // checkClipboard() is public + idempotent so unit tests can drive
        // it synchronously. Calling it twice with no clipboard change
        // between should not emit twice.

        // Establish baseline BEFORE creating the watcher so its seed
        // matches the current changeCount.
        fake.setString("baseline")
        let watcher = makeWatcher { _ in
            XCTFail("handler should not fire on idempotent checks")
        }
        // No further fake changes. Multiple checks must all be silent.
        watcher.checkClipboard()
        watcher.checkClipboard()
        watcher.checkClipboard()
    }

    // P1 (cubic follow-up): verifies the LAZY string read. The fake
    // stringSource counts how many times it's invoked; it should ONLY
    // be called when changeCount has actually moved. A steady-state
    // watch (no clipboard changes) must NOT touch the string at all.
    func test_does_not_read_string_when_changeCount_unchanged() {
        var stringReadCount = 0
        var changeCountReadCount = 0
        let fake = self.fake  // explicit capture for closure
        let watcher = ClipboardWatcher(
            changeCountSource: {
                changeCountReadCount += 1
                return fake?.changeCount ?? 0
            },
            stringSource: {
                stringReadCount += 1
                return fake?.string
            },
            handler: { _ in XCTFail("handler should not fire") }
        )
        // Seed the watcher
        let initialCount = changeCountReadCount
        // Multiple checks with no changeCount change
        for _ in 0..<5 {
            watcher.checkClipboard()
        }
        XCTAssertEqual(stringReadCount, 0, "stringSource must NOT be called when changeCount is unchanged")
        XCTAssertGreaterThan(changeCountReadCount, initialCount, "changeCountSource IS called every tick")
    }
}