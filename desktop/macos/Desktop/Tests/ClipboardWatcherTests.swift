import XCTest
@testable import Omi_Computer
import AppKit

/// Tests for ClipboardWatcher.
///
/// Uses an injected `Source` closure (a fake pasteboard that bumps
/// changeCount on write) rather than NSPasteboard.general. Reason:
/// xctest runs in a sandbox that does NOT have access to the user's
/// system pasteboard — changeCount is pinned at startup and never
/// bumps in the test runner. The injected Source simulates the real
/// NSPasteboard.general behavior (changeCount increments per write).
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

        func snapshot() -> ClipboardWatcher.Snapshot {
            ClipboardWatcher.Snapshot(changeCount: changeCount, string: string)
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

    func test_emits_handler_when_clipboard_string_changes() {
        let exp = expectation(description: "handler called")
        var received: String?
        let watcher = ClipboardWatcher(
            source: { [weak fake] in fake?.snapshot() ?? .init(changeCount: 0, string: nil) },
            pollInterval: 999.0,  // never fires naturally
            handler: { content in
                received = content
                exp.fulfill()
            }
        )

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
        let watcher = ClipboardWatcher(
            source: { [weak fake] in fake?.snapshot() ?? .init(changeCount: 0, string: nil) },
            handler: { _ in callCount += 1 }
        )
        watcher.checkClipboard()  // no change since init
        XCTAssertEqual(callCount, 0)
    }

    func test_emits_for_each_new_clipboard_content() {
        // Drive the watcher synchronously via checkClipboard() to avoid
        // Timer / RunLoop timing flakiness. The watcher must emit for
        // every fresh content change — that's the property the
        // production ConnectSheet relies on (each copy from @BotFather
        // fires the auto-detect handler).
        var received: [String] = []
        let watcher = ClipboardWatcher(
            source: { [weak fake] in fake?.snapshot() ?? .init(changeCount: 0, string: nil) },
            handler: { content in received.append(content) }
        )

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
        // should suppress the emit because snapshot.string is nil.
        var callCount = 0
        let watcher = ClipboardWatcher(
            source: { [weak fake] in fake?.snapshot() ?? .init(changeCount: 0, string: nil) },
            handler: { _ in callCount += 1 }
        )
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
        let watcher = ClipboardWatcher(
            source: { [weak fake] in fake?.snapshot() ?? .init(changeCount: 0, string: nil) },
            handler: { content in received.append(content) }
        )
        fake.setString("previous")
        watcher.checkClipboard()
        XCTAssertEqual(received, ["previous"])

        fake.clearContents()
        watcher.checkClipboard()
        XCTAssertEqual(received, ["previous"], "clearContents should NOT trigger an emit (string is nil)")
    }

    func test_stop_prevents_further_emits() {
        var callCount = 0
        let watcher = ClipboardWatcher(
            source: { [weak fake] in fake?.snapshot() ?? .init(changeCount: 0, string: nil) },
            pollInterval: 0.01,
            handler: { _ in callCount += 1 }
        )
        fake.setString("v1")
        watcher.start()
        // Give the timer a chance to fire (pollInterval is 0.01s).
        let waitWindow = expectation(description: "wait for first emit")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { waitWindow.fulfill() }
        wait(for: [waitWindow], timeout: 1.0)
        let beforeStop = callCount

        watcher.stop()
        fake.setString("v2")
        let postStop = expectation(description: "post-stop wait")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { postStop.fulfill() }
        wait(for: [postStop], timeout: 1.0)
        XCTAssertEqual(callCount, beforeStop, "watcher must not emit after stop()")
    }

    func test_checkClipboard_is_idempotent() {
        // checkClipboard() is public + idempotent so unit tests can drive
        // it synchronously. Calling it twice with no clipboard change
        // between should not emit twice.

        // Establish baseline BEFORE creating the watcher so its seed
        // matches the current changeCount. (The watcher's init reads
        // source().changeCount — if we created the watcher first and
        // then bumped changeCount, the FIRST checkClipboard would emit.)
        fake.setString("baseline")
        let watcher = ClipboardWatcher(
            source: { [weak fake] in fake?.snapshot() ?? .init(changeCount: 0, string: nil) },
            handler: { _ in XCTFail("handler should not fire on idempotent checks") }
        )
        // No further fake changes. Multiple checks must all be silent.
        watcher.checkClipboard()
        watcher.checkClipboard()
        watcher.checkClipboard()
    }
}