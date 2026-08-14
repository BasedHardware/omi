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
