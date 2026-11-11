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
        let window = try presentWindow { closes += 1 }

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
        let window = try presentWindow { closes += 1 }

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

    /// **No text state owns Escape for good — including the one the guard deliberately steps aside for.**
    ///
    /// The rule the report is actually about, asserted over every text state this window can be in: an
    /// untouched focused field, a half-typed value, and an input-method composition, which is the single
    /// case `RewindWindowFrame.midEditText` declines to take the key for. Two presses is the budget.
    ///
    /// **What this cannot exercise, stated rather than implied.** The composition case's *other* half —
    /// the text view consuming the first Escape to cancel its own marked text — needs a live input
    /// method, and a test process has none: `setMarkedText` sets the flag but there is no composition
    /// session for AppKit to cancel, so the key travels on and the window closes on the first press here.
    /// Measured, not assumed. So this asserts the property that survives either outcome — the window is
    /// always gone within two Escapes — and deliberately does not assert which press did it.
    func testNoTextStateCanHoldEscapeForever() throws {
        for state in TextState.allCases {
            var closes = 0
            let window = try presentWindow { closes += 1 }
            let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 80, height: 22))
            window.contentView?.addSubview(field)
            XCTAssertTrue(window.makeFirstResponder(field), "\(state): the field never took focus")
            let editor = try XCTUnwrap(window.firstResponder as? NSTextView, "\(state): no field editor")

            switch state {
            case .idle:
                break
            case .typed:
                editor.insertText("half typed", replacementRange: NSRange(location: 0, length: 0))
            case .composing:
                editor.setMarkedText(
                    "にほ", selectedRange: NSRange(location: 2, length: 0),
                    replacementRange: NSRange(location: 0, length: 0))
                XCTAssertTrue(editor.hasMarkedText(), "\(state): no composition, so this case is not exercised")
            }

            NSApp.sendEvent(try key(53))
            NSApp.sendEvent(try key(53))
            XCTAssertGreaterThanOrEqual(
                closes, 1,
                "\(state): no number of Escapes left the timeline — the dead end in the report")
        }
    }

    /// **Content that swallows Escape does not take the window's exit with it.**
    ///
    /// This is the 1.0.5 failure, modelled — and it is a *model*, which has to be said out loud because
    /// the previous two rounds both shipped green tests over a broken app. On the live 1.0.5 the timeline
    /// was key (traffic lights full colour) and **⌘W closed it while Escape did nothing**, which places
    /// the loss inside the window: ⌘W arrives as a main-menu key equivalent, Escape as a responder-chain
    /// command. The suspect is the SwiftUI hosting view claiming the key first.
    ///
    /// **What could not be reproduced.** Presented for real, with the shipped `RewindView` installed and
    /// laid out, `NSHostingView<RewindView>.performKeyEquivalent(esc)` returns `false` in this process and
    /// Escape reaches the window — so the live consumption does not happen here and this test cannot
    /// summon it. What it can do is pin the *property* the fix depends on: a content view that does claim
    /// Escape, exactly as the hypothesis says SwiftUI's does, must not be able to keep it. `sendEvent` is
    /// the only layer above `performKeyEquivalent:`, so this passes there and fails on any route below it.
    func testContentThatClaimsEscapeCannotKeepTheWindowsExit() throws {
        var closes = 0
        let window = try presentWindow { closes += 1 }
        let greedy = EscapeEatingView(frame: NSRect(x: 0, y: 0, width: 200, height: 200))
        window.contentView = greedy

        NSApp.sendEvent(try key(53))

        XCTAssertTrue(
            greedy.wasOffered || closes == 1,
            "neither the content nor the window saw Escape, so this case is not being exercised")
        XCTAssertEqual(
            closes, 1,
            """
            content that claims Escape kept the window's only keyboard exit — the 1.0.5 report, where \
            ⌘W closed the timeline and Escape did nothing. The route must sit above performKeyEquivalent:.
            """)
    }

    /// Stands in for whatever claims Escape inside the hosting view. `performKeyEquivalent:` is the hook
    /// AppKit offers content *before* the responder chain runs, which is precisely the gap a window-level
    /// `cancelOperation` sits below.
    private final class EscapeEatingView: NSView {
        var wasOffered = false
        override func performKeyEquivalent(with event: NSEvent) -> Bool {
            if event.type == .keyDown, event.keyCode == 53 {
                wasOffered = true
                return true
            }
            return super.performKeyEquivalent(with: event)
        }
    }

    private enum TextState: CaseIterable, CustomStringConvertible {
        case idle, typed, composing
        var description: String {
            switch self {
            case .idle: return "an untouched focused field"
            case .typed: return "a half-typed value"
            case .composing: return "an input-method composition"
            }
        }
    }

    /// There is deliberately no case for a window with no Escape route: `onEscape` is an init parameter,
    /// so "a timeline the user cannot leave" is not a state this test could construct even to assert
    /// against. That is the guard — the compiler holds it, not an assertion in here.
    ///
    /// Ordered front and made key, because `NSApp.sendEvent` routes a key event to the *key window* and
    /// a window that is merely constructed receives nothing.
    private func presentWindow(onEscape: @escaping () -> Void) throws -> RewindWindowFrame {
        let window = RewindWindowFrame(
            contentRect: NSRect(x: 100, y: 100, width: 200, height: 200),
            styleMask: [.titled, .closable, .resizable],
            onEscape: onEscape)
        window.isReleasedWhenClosed = false
        window.makeKeyAndOrderFront(nil)
        addTeardownBlock { MainActor.assumeIsolated { window.orderOut(nil) } }

        // **Key status is a precondition here, not the claim** — that the timeline becomes key is
        // `TimelineKeyStatusTests`' assertion, guarded there against a control window so a real
        // regression fails rather than skips. What this must not do is press a key at a window that
        // cannot receive one and report the silence as a broken handler, which is how every press
        // below would read: `closes == 0`, indistinguishable from the bug.
        //
        // Nothing is softened. On a machine that can key a window at all, the `XCTAssertTrue` runs and
        // a timeline that is not key fails exactly as loudly as before.
        if !window.isKeyWindow {
            try KeyWindowPrecondition.skipIfNoWindowCanBecomeKey(
                notVerified: """
                    that Escape closes the timeline, that no text state can hold the key forever, and \
                    that content claiming Escape cannot keep the window's exit. The window was built \
                    and ordered front; no press was delivered, because `NSApp.sendEvent` routes to the \
                    key window and this process has none.
                    """)
        }
        XCTAssertTrue(
            window.isKeyWindow,
            """
            the window under test is not key while a plain control panel in this same process took key \
            status without trouble, so `NSApp.sendEvent` routes nowhere — that is the 1.0.4 defect \
            (`TimelineKeyStatusTests`) and not a limit of this environment.
            """)
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
