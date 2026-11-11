import AppKit
import XCTest

/// **Which of two things it was when a window under test is not key** — a machine that cannot route
/// the keyboard at all, or the defect these suites exist to catch.
///
/// Two suites press keys the way a key press really travels: `NSApp.sendEvent`, which routes to *the
/// key window*. That makes key status a precondition of the measurement, and key status is ambient
/// machine state — a contended GUI session, a locked screen, a headless runner, two `swift test`
/// processes competing for the window server. Observed on 2026-08-15: `TimelineKeyStatusTests` failed
/// three assertions mid-run with `app active: false` and was green on every re-run before and after,
/// while a person was driving a live session on the same Mac. A suite that reddens according to
/// whether somebody is using the machine teaches people to re-run it, and then to ignore it.
///
/// **Asked only after the window under test has already failed, and that ordering is the design.**
/// The obvious shape — probe up front, skip if the machine looks unable — was written first and
/// measured worse: a control window ordered front *before* the real one deterministically failed to
/// take key status in the third test of a suite whose other three were handed a key window seconds
/// apart in the same process. A gate that flaky silently deletes coverage, which is worse than the
/// flaky failure it replaces, because nobody reads a skip.
///
/// So on a healthy machine this file never runs at all: the window is key, the assertions pass, and
/// no control window is ever created. It runs only on the branch that was about to fail, and then it
/// answers the one question that branch cannot answer for itself.
///
/// **The control window is what keeps the skip honest.** It carries none of the app's presentation
/// logic — a plain `.nonactivatingPanel`, whose key-ability costs nothing but a working window
/// server. Asking the window *under test* whether it is key and skipping when it says no would skip
/// precisely when the 1.0.4 defect is present: a timeline that came up visible, with grey traffic
/// lights, and never became key.
///
/// - If the control can become key and the window under test could not, that is not the environment.
///   The caller's assertion runs and fails, as it did before this file existed.
/// - If the control cannot become key either, nothing about routing is measurable here. That is a
///   skip, and it names what went unverified.
@MainActor
enum KeyWindowPrecondition {

    /// - Parameter notVerified: what this run therefore did **not** measure, in the caller's own
    ///   words. A green run must never be mistaken for full coverage, so the skip has to name the
    ///   hole. Returns normally — leaving the caller to fail its own assertion — whenever the machine
    ///   is demonstrably able to route the keyboard.
    static func skipIfNoWindowCanBecomeKey(notVerified: String) throws {
        guard !aControlWindowCanBecomeKey() else { return }
        throw XCTSkip(
            """
            This process cannot give any window key status right now (app active: \(NSApp.isActive)): \
            a control `.nonactivatingPanel`, carrying none of this app's presentation logic, was \
            ordered front and did not become key either. AppKit therefore has no key window to route \
            `NSApp.sendEvent` to, and `isKeyWindow` cannot answer anything here.

            NOT VERIFIED BY THIS RUN: \(notVerified)

            This is a limit of the environment — a contended, locked or headless GUI session — and \
            not a passing result. Every assertion in this file that does not need a routable keyboard \
            still ran; the ones that do did not. Re-run on an uncontended login session to measure \
            them.
            """)
    }

    /// Ordered front, asked, and taken straight back off screen.
    private static func aControlWindowCanBecomeKey() -> Bool {
        let control = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 120, height: 40),
            // `.nonactivatingPanel` for the same reason the timeline is one: it takes key status
            // without waiting on `NSApp.activate`, which is deprecated and does not reliably activate
            // this process. A control that needed activation would report "cannot" on a perfectly
            // healthy machine and turn every real failure into a skip.
            styleMask: [.titled, .closable, .nonactivatingPanel],
            backing: .buffered, defer: false)
        control.isReleasedWhenClosed = false
        control.hidesOnDeactivate = false
        control.makeKeyAndOrderFront(nil)

        // **Patient, and only in the direction that costs nothing.** Key status is granted through the
        // window server and is not always held by the time the next statement runs. Erring towards
        // "yes" is the safe error: it lets the caller's assertion run and fail loudly, which is where
        // this file started. Erring towards "no" would hide a real regression behind a skip.
        var couldBeKey = control.isKeyWindow
        var attempts = 0
        while !couldBeKey, attempts < 25 {
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
            control.makeKey()
            couldBeKey = control.isKeyWindow
            attempts += 1
        }

        control.orderOut(nil)
        return couldBeKey
    }
}
