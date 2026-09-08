import AppKit

// MARK: - What a second press of the same chord means

/// What a hotkey press actually did to the window that chord summons.
///
/// Returned rather than only logged, because the three outcomes *are* the feature and not one of them
/// is reachable by clicking around in a headless process: a window cannot be made key, lose key, or
/// sit behind another application in a test runner. Handing the decision back is what lets the rule be
/// executed instead of read.
enum HotkeyPress: Equatable {
    /// Nothing was on screen, so the window was opened.
    case opened
    /// The window was on screen but something else held the keyboard, so it came forward.
    ///
    /// **Deliberately not a dismissal.** Someone who cannot see the window pressed the chord to get
    /// *to* it; closing a window the user is not looking at is a worse answer than the one they
    /// complained about, and it is the mistake `isVisible ? dismiss() : open()` makes.
    case raised
    /// The window was on screen and had the keyboard, so it went away. The behaviour that was missing.
    case dismissed
}

/// **The chord that opened a window is the chord that closes it**, as one value every hotkey shares.
///
/// One report: *"Every window that gets launched by a hotkey should also be dismissed by the same
/// hotkey, right now I have no way to exit this without clicking X."* The obvious reading of that is a
/// two-state toggle, and a two-state toggle is wrong in a way the report cannot mention — see
/// `HotkeyPress.raised`. So there are three outcomes, ordered, in one place, because a second copy of
/// this ordering is how one surface ends up dismissing a window the user cannot see.
///
/// **The presence is asked for, never remembered.** A boolean kept here would drift the first time the
/// user closed the window by its own X — the exact gesture the report is about — and the next press
/// would then "dismiss" a window that was already gone, doing nothing at all. `presence` is a closure
/// so it is read at the moment the chord fires, and the app's implementations of it read `NSWindow`
/// directly.
@MainActor
struct HotkeyToggle {

    /// The window's real state, as AppKit reports it at the moment of the press.
    struct Presence: Equatable {
        /// `NSWindow.isVisible`, and nothing derived from it.
        var isOnScreen: Bool

        /// `NSWindow.isKeyWindow` — this window has the keyboard.
        ///
        /// Deliberately not `NSApp.isActive`. The Activity panel is a `.nonactivatingPanel`: it holds
        /// the keyboard *while this app is not the active application*, by design, so an
        /// application-level reading would call the panel in front of the user's face unfocused and
        /// raise something that is already there — turning the reported dead end into a chord that
        /// still cannot close anything.
        var hasKeyboardFocus: Bool

        /// Nothing is up. The only `Presence` a window that was never built can honestly report, and
        /// the answer every `current == nil` read collapses to.
        static let closed = Presence(isOnScreen: false, hasKeyboardFocus: false)
    }

    /// Read on every press. See the type note for why this is a closure.
    let presence: () -> Presence

    /// Opens the window, or brings an existing one forward and gives it the keyboard.
    ///
    /// One closure for both `opened` and `raised` because every window in this app already has exactly
    /// one idempotent entry point that does both (`present`), and a second spelling of "put this
    /// window in front" is a second thing to keep in agreement with the first.
    let show: () -> Void

    let dismiss: () -> Void

    @discardableResult
    func press() -> HotkeyPress {
        let now = presence()
        guard now.isOnScreen else {
            show()
            return .opened
        }
        guard now.hasKeyboardFocus else {
            show()
            return .raised
        }
        dismiss()
        return .dismissed
    }
}
