import AppKit
import XCTest

@testable import ContextApp

/// **How far a key press is allowed to reach**, for the two surfaces that were getting it wrong in
/// opposite directions: one consumed keystrokes belonging to every other window in the app, and one
/// consumed none at all and left the user with no way off it.
///
/// Both are behavioural: a real `NSWindow`, a real `NSEvent`, and the production `sendEvent` /
/// monitor predicate. Neither claim can be made by reading the source, which is exactly why both
/// shipped.
final class KeyboardReachTests: XCTestCase {

    // MARK: - The shortcut recorder only hears its own window

    /// `NSEvent.addLocalMonitorForEvents` is a **process** monitor, and every branch of the
    /// recorder's returns `nil`. So while a shortcut field said "…", it swallowed every key press in
    /// every window of this app: ⌘W would not close the timeline, and **⌘Q would not quit** — Quit
    /// was captured as a candidate chord, rejected as reserved, and the user was shown a rejection
    /// message for a key they had aimed at the application.
    @MainActor
    func testAnArmedShortcutRecorderOnlyConsumesItsOwnWindowsKeys() {
        let settings = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 10, height: 10), styleMask: [.borderless],
            backing: .buffered, defer: true)
        let somewhereElse = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 10, height: 10), styleMask: [.borderless],
            backing: .buffered, defer: true)

        XCTAssertTrue(
            ShortcutRecorderScope.belongsToTheRecorder(settings, settingsWindow: settings))
        XCTAssertFalse(
            ShortcutRecorderScope.belongsToTheRecorder(somewhereElse, settingsWindow: settings),
            "the timeline's ⌘W and the app's ⌘Q are not the recorder's to eat")
        XCTAssertFalse(
            ShortcutRecorderScope.belongsToTheRecorder(nil, settingsWindow: settings),
            "an event with no window was not delivered to a window of ours at all")
        XCTAssertFalse(
            ShortcutRecorderScope.belongsToTheRecorder(somewhereElse, settingsWindow: nil),
            "no Settings window means no recorder, whatever a stale monitor thinks")
    }

    // MARK: - An abandoned recorder is not a keyboard outage

    /// **A recorder monitor cannot outlive the window that armed it.**
    ///
    /// The predicate above is a *value*: it says which window a key press belongs to, and it can only
    /// be consulted by a monitor that is still installed. Nothing in it stops a monitor being left
    /// installed forever, and the only route to `NSEvent.removeMonitor` used to be SwiftUI's
    /// `onDisappear` on the field, with the token held in that view's `@State`. Ordering the Settings
    /// window out does not remove its hosting view from any hierarchy — `isReleasedWhenClosed` is
    /// false and the window is merely hidden — so that callback has no reason to run, and a monitor
    /// orphaned that way can never be removed again for the life of the process.
    ///
    /// Behavioural, through the seam the type exists to have: the real `deliver` decision, real
    /// `NSWindow`s and a real `NSEvent`, with only the AppKit registration stubbed — a test process
    /// can neither install a local monitor nor make a window key.
    @MainActor
    func testAnAbandonedRecorderRemovesItselfRatherThanEatingAnotherWindowsEscape() throws {
        let settings = offscreenWindow()
        let timeline = offscreenWindow()
        var installed = 0
        var removed = 0
        // The recorder's window as the *world* sees it, which is what the monitor asks: a window a
        // recorder could be drawn in right now, or nothing. It becomes nothing without anybody
        // telling the field, which is the abandonment.
        var recorderWindow: NSWindow? = settings

        let monitor = ShortcutRecorderMonitor(
            install: { _ in
                installed += 1
                return installed as NSNumber
            },
            remove: { _ in removed += 1 },
            recorderWindow: { recorderWindow })

        var swallowed = 0
        monitor.arm { _ in
            swallowed += 1
            return nil
        }
        XCTAssertEqual(installed, 1, "arming installs exactly one monitor")
        XCTAssertNil(
            monitor.deliver(try key(53, in: settings), in: settings),
            "while the recorder is really on screen, its own window's Escape is still its own")
        XCTAssertEqual(swallowed, 1)

        // The pane goes away without disarming — the window ordered out, the view never told.
        recorderWindow = nil

        let escape = try key(53, in: timeline)
        XCTAssertEqual(
            monitor.deliver(escape, in: timeline), escape,
            "the timeline's Escape is not an abandoned recorder's to eat")
        XCTAssertEqual(swallowed, 1, "an abandoned recorder consumes nothing")
        XCTAssertEqual(removed, 1, "it removes itself rather than waiting for a callback that never came")
        XCTAssertFalse(monitor.isArmed, "and it is gone, so it cannot swallow anything later either")
    }

    /// One process, one recorder monitor — and a `disarm` from a view that has already been replaced
    /// is a no-op rather than a teardown of its successor's.
    ///
    /// SwiftUI rebuilds this pane on every record, clear and app activation, and the replacement's
    /// `onAppear` arms before the old view's `onDisappear` runs. Without the token that ordering
    /// leaves the field showing "…" over no monitor at all.
    @MainActor
    func testRearmingReplacesTheMonitorAndAStaleDisarmDoesNotTearDownItsSuccessor() throws {
        let settings = offscreenWindow()
        var installed = 0
        var removed = 0
        let monitor = ShortcutRecorderMonitor(
            install: { _ in
                installed += 1
                return installed as NSNumber
            },
            remove: { _ in removed += 1 },
            recorderWindow: { settings })

        let first = monitor.arm { _ in nil }
        var swallowed = 0
        monitor.arm { _ in
            swallowed += 1
            return nil
        }
        XCTAssertEqual(installed, 2)
        XCTAssertEqual(removed, 1, "the second arming replaces the first rather than stacking on it")

        monitor.disarm(first)
        XCTAssertTrue(monitor.isArmed, "a superseded token names a monitor that is already gone")
        XCTAssertNil(monitor.deliver(try key(53, in: settings), in: settings))
        XCTAssertEqual(swallowed, 1, "the live recorder is still the one hearing its window")
    }

    @MainActor
    private func offscreenWindow() -> NSWindow {
        NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 10, height: 10), styleMask: [.borderless],
            backing: .buffered, defer: true)
    }

    // MARK: - The tutorial card can be left with the keyboard

    /// The tutorial's card is borderless — so `performClose:` and ⌘W do nothing to it — floats above
    /// everything the user owns, and carried no keyboard shortcut anywhere in `Tutorial/`. `Skip`
    /// was reachable by pointer only. The onboarding cinematic immediately before it *does* take
    /// Escape, so the key was taught and then silently stopped working.
    @MainActor
    func testEscapeLeavesTheTutorialCard() throws {
        let window = TutorialOverlayWindow(
            contentRect: NSRect(x: 0, y: 0, width: 100, height: 100), styleMask: [.borderless],
            backing: .buffered, defer: true)
        var skips = 0
        window.onEscape = { skips += 1 }

        window.sendEvent(try key(53, in: window))
        XCTAssertEqual(skips, 1, "Escape is the way off a card with no title bar and no ⌘W")

        // Everything else still belongs to the card. A window that swallowed keys wholesale would be
        // the recorder's bug in a second place.
        window.sendEvent(try key(36, in: window))
        XCTAssertEqual(skips, 1, "Return is not an exit")
    }

    /// A card with no route out of it must not be silently reachable again: a window built without
    /// an Escape route swallows nothing and passes the key on, rather than eating it.
    @MainActor
    func testAnUnwiredCardDoesNotSwallowEscape() throws {
        let window = TutorialOverlayWindow(
            contentRect: NSRect(x: 0, y: 0, width: 100, height: 100), styleMask: [.borderless],
            backing: .buffered, defer: true)
        // No `onEscape`. `sendEvent` must fall through to `super` rather than consuming the key —
        // the failure mode where a half-wired overlay eats Escape and leaves *nothing* able to
        // answer it.
        window.sendEvent(try key(53, in: window))
    }

    @MainActor
    private func key(_ code: UInt16, in window: NSWindow) throws -> NSEvent {
        try XCTUnwrap(
            NSEvent.keyEvent(
                with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0,
                windowNumber: window.windowNumber, context: nil, characters: "",
                charactersIgnoringModifiers: "", isARepeat: false, keyCode: code))
    }
}
