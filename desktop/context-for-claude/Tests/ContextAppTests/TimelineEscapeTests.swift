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
/// `RewindWindowFrame`, a real `NSEvent`, and the production `sendEvent`. None of these three claims
/// can be made by reading the source, which is why the gap shipped.
final class TimelineEscapeTests: XCTestCase {

    @MainActor
    func testEscapeClosesTheTimeline() throws {
        var closes = 0
        let window = makeWindow { closes += 1 }

        window.sendEvent(try key(53, in: window))
        XCTAssertEqual(closes, 1, "Escape is the way out the user went looking for and did not find")

        // Every other key still belongs to the window. The timeline's own bindings are arrows, ⌘±, `/`
        // and Return, and a window that swallowed keys wholesale would take the scrubber with it.
        window.sendEvent(try key(36, in: window))
        window.sendEvent(try key(124, in: window))
        XCTAssertEqual(closes, 1, "Return and the arrow keys are not exits")
    }

    /// **A field editor keeps Escape.** `sendEvent` runs before the responder chain, so without this the
    /// first editable control added to this window would silently lose the key that abandons an edit —
    /// and closing the whole window is not what Escape means mid-value.
    @MainActor
    func testAnActiveFieldEditorKeepsEscape() throws {
        var closes = 0
        let window = makeWindow { closes += 1 }

        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 80, height: 22))
        window.contentView?.addSubview(field)
        // The field editor, not the field: `NSTextField` edits through a shared `NSTextView` that
        // becomes first responder, and that is the object `sendEvent` has to recognise.
        XCTAssertTrue(window.makeFirstResponder(field), "the field has to be editing for this to mean anything")
        XCTAssertTrue(
            (window.firstResponder as? NSTextView)?.isFieldEditor == true,
            "AppKit did not install a field editor, so this case is not being exercised")

        window.sendEvent(try key(53, in: window))
        XCTAssertEqual(closes, 0, "Escape abandoned an edit before it closes a window — macOS's ordering")
    }

    /// There is deliberately no case for a window with no Escape route: `onEscape` is an init parameter,
    /// so "a timeline the user cannot leave" is not a state this test could construct even to assert
    /// against. That is the guard — the compiler holds it, not an assertion in here.
    @MainActor
    private func makeWindow(onEscape: @escaping () -> Void) -> RewindWindowFrame {
        RewindWindowFrame(
            contentRect: NSRect(x: 0, y: 0, width: 200, height: 200),
            styleMask: [.titled, .closable, .resizable],
            onEscape: onEscape)
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
