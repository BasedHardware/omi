import AppKit
import XCTest

@testable import ContextApp

/// **The chord that opened a window has to close it**, and the two ways of getting that wrong.
///
/// The report this pins: *"Every window that gets launched by a hotkey should also be dismissed by the
/// same hotkey, right now I have no way to exit this without clicking X."* `openActivity` called
/// `SearchBarWindow.present()`, which is idempotent — so the second press of the app's advertised
/// gesture re-focused a panel already in front of the user and there was no way off the keyboard.
///
/// Exercised through `HotkeyToggle`'s own presence closure rather than by making windows, because none
/// of the three states can be produced in a headless runner: a test process has no display to put a
/// window on and cannot make one key. The probe is what a real `NSWindow` answers with
/// (`SearchBarWindow.presence` reads exactly these two properties), and the recorders below are the
/// real `present`/`dismiss` closures the app passes in.
@MainActor
final class HotkeyToggleTests: XCTestCase {

    /// What the window claims to be doing, and what the toggle did about it.
    private struct Probe {
        var presence: HotkeyToggle.Presence = .closed
        var shown = 0
        var dismissed = 0
    }

    /// A toggle over `probe`, wired the way `SearchBarWindow.hotkeyToggle()` wires the real one.
    private func toggle(over probe: Box<Probe>) -> HotkeyToggle {
        HotkeyToggle(
            presence: { probe.value.presence },
            show: { probe.value.shown += 1 },
            dismiss: { probe.value.dismissed += 1 })
    }

    /// A reference cell, so the closures above share one probe with the assertions.
    private final class Box<Wrapped> {
        var value: Wrapped
        init(_ value: Wrapped) { self.value = value }
    }

    // MARK: - The three transitions

    func testPressingTheChordWithNothingUpOpensTheWindow() {
        let probe = Box(Probe())
        XCTAssertEqual(toggle(over: probe).press(), .opened)
        XCTAssertEqual(probe.value.shown, 1)
        XCTAssertEqual(probe.value.dismissed, 0)
    }

    /// **The bug.** The window is on screen and has the keyboard, so the chord that put it there takes
    /// it away — rather than re-presenting it and leaving the X as the only exit.
    func testPressingTheChordOnTheFocusedWindowDismissesIt() {
        let probe = Box(Probe())
        probe.value.presence = HotkeyToggle.Presence(isOnScreen: true, hasKeyboardFocus: true)
        XCTAssertEqual(toggle(over: probe).press(), .dismissed)
        XCTAssertEqual(probe.value.dismissed, 1)
        XCTAssertEqual(probe.value.shown, 0, "a focused window must not be re-presented as well")
    }

    /// **The bug the obvious fix introduces.** `isVisible ? dismiss() : open()` closes a window the
    /// user cannot see: they pressed the chord to get *to* it, from whatever application is in front.
    func testPressingTheChordOnAWindowBehindAnotherAppRaisesItInsteadOfClosingIt() {
        let probe = Box(Probe())
        probe.value.presence = HotkeyToggle.Presence(isOnScreen: true, hasKeyboardFocus: false)
        XCTAssertEqual(toggle(over: probe).press(), .raised)
        XCTAssertEqual(probe.value.shown, 1)
        XCTAssertEqual(
            probe.value.dismissed, 0,
            "the chord dismissed a window the user could not see — they pressed it to reach the window")
    }

    /// Open, close, open: the state comes from the window on every press, so the sequence cannot drift
    /// out of step with reality the way a boolean kept here would.
    func testTheStateIsReadOnEveryPressRatherThanRemembered() {
        let probe = Box(Probe())
        let hotkey = toggle(over: probe)

        XCTAssertEqual(hotkey.press(), .opened)
        probe.value.presence = HotkeyToggle.Presence(isOnScreen: true, hasKeyboardFocus: true)
        XCTAssertEqual(hotkey.press(), .dismissed)
        // The user closed it by its own X between presses, and nothing told us. The next press opens.
        probe.value.presence = .closed
        XCTAssertEqual(hotkey.press(), .opened)
    }

    // MARK: - Every chord, not just the one that already worked

    /// **The assertion the shipped bug fails**, and the reason `ContextAppDelegate.shortcutFired` is a
    /// named function rather than a closure inside `applicationDidFinishLaunching`.
    ///
    /// `openSearch` toggled from the day it shipped; `openActivity` — the gesture the product teaches,
    /// the one on the menu row and in onboarding — called `present()`, so its second press re-focused a
    /// panel already in front of the user and the X was the only way out. Exhaustive over
    /// `Action.allCases` so a third shortcut cannot be added with the old behaviour.
    func testEveryGlobalShortcutTogglesTheWindowItOpens() {
        for action in GlobalShortcuts.Action.allCases {
            let probe = Box(Probe())

            XCTAssertEqual(
                ContextAppDelegate.shortcutFired(action, on: toggle(over: probe)), .opened,
                "\(action.rawValue) did not open its window")

            probe.value.presence = HotkeyToggle.Presence(isOnScreen: true, hasKeyboardFocus: true)
            XCTAssertEqual(
                ContextAppDelegate.shortcutFired(action, on: toggle(over: probe)), .dismissed,
                "\(action.rawValue) cannot close the window it opened — the user is left clicking the X")

            probe.value.presence = HotkeyToggle.Presence(isOnScreen: true, hasKeyboardFocus: false)
            XCTAssertEqual(
                ContextAppDelegate.shortcutFired(action, on: toggle(over: probe)), .raised,
                "\(action.rawValue) closed a window the user could not see instead of reaching it")
        }
    }

    // MARK: - The real panel

    /// The real read, on a process with no panel up: closed, and therefore unfocused.
    ///
    /// The one thing tying the rule above to the shipped window. `SearchBarWindow.presence` reads
    /// `NSWindow.isVisible` and `isKeyWindow` — a retained-but-closed panel is the state this app
    /// produces constantly (`isReleasedWhenClosed = false` everywhere), and reporting it as on screen
    /// would make the chord dismiss nothing forever.
    func testTheRealPanelReportsItselfClosedWhenItIsNotUp() {
        SearchBarWindow.dismiss()
        XCTAssertEqual(SearchBarWindow.presence, .closed)
    }

    /// The real dismissal, reached through the real toggle, with only the presence injected.
    ///
    /// Asserted on the announcement rather than on the window, because `.closed` is what every observer
    /// of this surface acts on — and because it is the half of `dismiss()` a headless process can see.
    func testTheRealToggleDismissesThePanelWhenItHasTheKeyboard() {
        var heard: [SearchPanelEvent] = []
        let token = SearchPanelWatch.addObserver { heard.append($0) }
        defer { SearchPanelWatch.removeObserver(token) }

        let press = SearchBarWindow.hotkeyToggle(
            presence: { HotkeyToggle.Presence(isOnScreen: true, hasKeyboardFocus: true) }
        ).press()

        XCTAssertEqual(press, .dismissed)
        XCTAssertEqual(heard, [.closed])
    }
}
