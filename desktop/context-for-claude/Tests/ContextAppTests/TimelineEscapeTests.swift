import AppKit
import XCTest

@testable import ContextApp

/// **Escape closes the timeline**, which is the window in the report.
///
/// *"Every window that gets launched by a hotkey should also be dismissed by the same hotkey, right now
/// I have no way to exit this without clicking X."* The screenshot was this window — "Remembering", the
/// filmstrip, the date pill — filling the display. It has a title bar, so the X and ⌘W were both there;
/// Escape, which is the key a person reaches for on a surface that size, did nothing at all. The panel
/// this window opens *from* has taken Escape since it shipped, so the key was taught on one surface and
/// dead on the next.
///
/// Behavioural, in the shape `KeyboardReachTests` established for the tutorial card: a real
/// `RewindWindowFrame`, a real `NSEvent`, and the application's own dispatch. None of these claims can
/// be made by reading the source, which is why the gap shipped.
///
/// **Every press here goes through `NSApp.sendEvent`, not `window.sendEvent`.** That is the whole
/// difference between this file and the version that shipped green over a broken window: handing an
/// event straight to the window proves a handler, and what was broken was the *routing* — first because
/// the window was never key (`TimelineKeyStatusTests`), then because a guard declined the key before the
/// responder chain could carry it. Both are invisible to a direct call.
@MainActor
final class TimelineEscapeTests: XCTestCase {

    func testEscapeClosesTheTimeline() throws {
        var closes = 0
        let window = presentWindow { closes += 1 }

        NSApp.sendEvent(try key(53))
        XCTAssertEqual(closes, 1, "Escape is the way out the user went looking for and did not find")

        // Every other key still belongs to the window. The timeline's own bindings are arrows, ⌘±, `/`
        // and Return, and a window that swallowed keys wholesale would take the scrubber with it.
        NSApp.sendEvent(try key(36))
        NSApp.sendEvent(try key(124))
        XCTAssertEqual(closes, 1, "Return and the arrow keys are not exits")
    }

    /// **A focused field the user never touched does not take the only way out.**
    ///
    /// This replaces a test that asserted the opposite, and the reversal is the bug rather than a change
    /// of mind. AppKit installs a field editor and makes it first responder as soon as anything editable
    /// takes focus — nothing typed, nothing to abandon — so the old `sendEvent` guard, which declined
    /// Escape whenever `firstResponder` was a field editor, was true from the moment such a control
    /// appeared and stayed true for the life of the window. The window then had no keyboard exit at all,
    /// which is precisely the report this whole file exists to answer, reintroduced by its own guard.
    ///
    /// The expected value is not reasoned from the source: it is what AppKit does, measured on this
    /// class — `NSTextView` claims `cancelOperation:` only when it has something of its own to cancel,
    /// so an idle field editor passes the key up the responder chain to the window.
    func testAFocusedButIdleFieldEditorStillLetsEscapeOut() throws {
        var closes = 0
        let window = presentWindow { closes += 1 }

        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 80, height: 22))
        window.contentView?.addSubview(field)
        // The field editor, not the field: `NSTextField` edits through a shared `NSTextView` that
        // becomes first responder, and that is the object the old guard recognised.
        XCTAssertTrue(window.makeFirstResponder(field), "the field has to be focused for this to mean anything")
        XCTAssertTrue(
            (window.firstResponder as? NSTextView)?.isFieldEditor == true,
            "AppKit did not install a field editor, so this case is not being exercised")

        NSApp.sendEvent(try key(53))
        XCTAssertEqual(
            closes, 1,
            "a control the user never touched disabled the timeline's only keyboard exit")
    }

    /// **…and a field the user *is* typing in cannot produce a dead end either.**
    ///
    /// Whatever claims Escape has ended its own state by claiming it, so the next press reaches the
    /// window. Asserted as "at most two presses", not as a particular first-press behaviour, because
    /// which of the two consumes it is AppKit's to decide and this window must be correct either way.
    func testATimelineIsNeverMoreThanTwoEscapesFromClosing() throws {
        var closes = 0
        let window = presentWindow { closes += 1 }

        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 80, height: 22))
        window.contentView?.addSubview(field)
        XCTAssertTrue(window.makeFirstResponder(field))
        let editor = try XCTUnwrap(window.firstResponder as? NSTextView)
        editor.insertText("half typed", replacementRange: NSRange(location: 0, length: 0))
        XCTAssertEqual(editor.string, "half typed", "the edit did not land, so this case is not exercised")

        NSApp.sendEvent(try key(53))
        NSApp.sendEvent(try key(53))
        XCTAssertGreaterThanOrEqual(
            closes, 1, "no number of Escapes left the timeline — the dead end in the report")
    }

    /// There is deliberately no case for a window with no Escape route: `onEscape` is an init parameter,
    /// so "a timeline the user cannot leave" is not a state this test could construct even to assert
    /// against. That is the guard — the compiler holds it, not an assertion in here.
    ///
    /// Ordered front and made key, because `NSApp.sendEvent` routes a key event to the *key window* and
    /// a window that is merely constructed receives nothing.
    private func presentWindow(onEscape: @escaping () -> Void) -> RewindWindowFrame {
        let window = RewindWindowFrame(
            contentRect: NSRect(x: 100, y: 100, width: 200, height: 200),
            styleMask: [.titled, .closable, .resizable],
            onEscape: onEscape)
        window.isReleasedWhenClosed = false
        window.makeKeyAndOrderFront(nil)
        addTeardownBlock { MainActor.assumeIsolated { window.orderOut(nil) } }
        return window
    }

    /// **The characters matter, not just the key code.** AppKit translates a key event into a
    /// `doCommandBySelector:` — `cancelOperation:` among them — from what the key *typed*, so an event
    /// carrying key code 53 and an empty string is not an Escape as far as the responder chain is
    /// concerned. Measured while writing this file: an event built with the right code and no
    /// characters reached nothing, and one built with Return's code and Escape's character closed the
    /// window. A real key event always carries both, so a test that omits them is testing a key that
    /// cannot be pressed.
    private func key(_ code: UInt16) throws -> NSEvent {
        let characters: String
        switch code {
        case 53: characters = "\u{1b}"
        case 36: characters = "\r"
        case 124: characters = String(UnicodeScalar(NSRightArrowFunctionKey)!)
        default: characters = ""
        }
        return try XCTUnwrap(
            NSEvent.keyEvent(
                with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0,
                windowNumber: 0, context: nil, characters: characters,
                charactersIgnoringModifiers: characters, isARepeat: false, keyCode: code))
    }
}
