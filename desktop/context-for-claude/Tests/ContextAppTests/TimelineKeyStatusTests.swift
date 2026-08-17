import AppKit
import ContextCore
import XCTest

@testable import ContextApp

/// **The timeline is the key window, which is what makes its Escape route exist at all.**
///
/// `TimelineEscapeTests` proved the handler and shipped a window that never ran it. It built a
/// `RewindWindowFrame` by hand, handed a synthetic `NSEvent` straight to `sendEvent`, and went green —
/// while the real window, presented the real way, was never key, so AppKit had no reason to deliver it
/// a `keyDown` at all. On the shipped 1.0.4 the timeline came up with grey traffic lights and Escape did
/// nothing, repeatedly, with the app frontmost.
///
/// The property that was actually false is the one asserted here, and it is asserted **through
/// `RewindWindow.present`** rather than against a window this file assembled: the whole failure was a
/// gap between what the test built and what the app builds, so a second hand-built window would be the
/// same test again with a different assertion on it.
///
/// The test process is never activated, which is not a limitation — it is the condition.
/// `makeKeyWindow` is documented as a no-op while the application is inactive, and
/// `NSApp.activate(ignoringOtherApps:)` is deprecated as of macOS 14 and does not reliably activate; in
/// this process it does not activate at all. A window that is key here is a window whose key status
/// does not depend on activation having landed, which is precisely the guarantee 1.0.4 lacked.
///
/// **The activation policy is the app's own, installed on purpose, and it used to arrive by
/// accident.** `setUp` set `.accessory` and said so in this paragraph — and then `RewindWindow.present`
/// built a `RewindView`, which held an `@ObservedObject` on `SettingsStore.shared`, whose `init`
/// calls `applyDockIcon()` and therefore `NSApp.setActivationPolicy(.regular)`. So every measurement
/// in this file was taken on a `.regular` process while the file documented an `.accessory` one. That
/// was invisible until the timeline stopped reading `SettingsStore` at all (the Appearance pane's
/// timeline-control toggles went, and with them the view's only reason to hold the store): the
/// process stayed `.accessory`, no window in it could take key status, and three of these four tests
/// went from measuring to skipping — coverage deleted by a change nowhere near them.
///
/// So it is stated, and stated **without reading the machine**. `DockPresence.launchPolicy()` was
/// the obvious spelling and is the wrong one here: it resolves through `UserDefaults.standard`, so a
/// developer who had run the real app with Show Dock Icon *off* would put this process back to
/// `.accessory` and silently lose the same three measurements to skips — the identical failure, now
/// caused by ambient state instead of by a diff. The mapping is still production's
/// (`DockPresence.activationPolicy`); only the input is pinned.
@MainActor
final class TimelineKeyStatusTests: XCTestCase {

    private var root: URL!

    override func setUpWithError() throws {
        try super.setUpWithError()
        NSApplication.shared.setActivationPolicy(
            DockPresence.activationPolicy(showsDockIcon: true))
        root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("timeline-key-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDown() {
        RewindWindow.dismiss()
        if let root { try? FileManager.default.removeItem(at: root) }
        super.tearDown()
    }

    /// **The timeline becomes key when it is presented.** The shipped failure, stated as a claim.
    ///
    /// The two halves are separated on purpose. `canBecomeKey`/`canBecomeMain` are facts about the
    /// window this app builds and are measurable anywhere; `isKeyWindow`/`isMainWindow` need a process
    /// that can route the keyboard at all. Only the second pair is gated, and it is gated on a
    /// *control* window rather than on this one — see `KeyWindowPrecondition` for why asking the
    /// window under test would skip exactly when the 1.0.4 defect is present.
    func testPresentingTheTimelineMakesItTheKeyWindow() throws {
        let window = try presentTheTimeline()

        XCTAssertTrue(
            window.canBecomeKey,
            "the timeline refuses key status outright, so nothing typed at it can ever reach it")
        XCTAssertTrue(
            window.canBecomeMain,
            "the timeline refuses main status, which is a titled window with grey traffic lights")

        // Only on the branch that was about to fail, and it decides which failure it is. On a machine
        // that can key a window at all this is not reached and nothing below is softened.
        if !window.isKeyWindow {
            try KeyWindowPrecondition.skipIfNoWindowCanBecomeKey(
                notVerified: """
                    that `RewindWindow.present` produces a window which is actually key and main. The \
                    window's own claims about itself were checked and hold; whether AppKit granted \
                    them was not — that is the 1.0.4 report, with the traffic lights drawn grey.
                    """)
        }

        XCTAssertTrue(
            window.isKeyWindow,
            """
            the timeline is on screen and is not the key window (app active: \(NSApp.isActive)), \
            while a plain control panel in this same process took key status without trouble. \
            AppKit delivers key events to the key window, so `RewindWindowFrame.sendEvent` is never \
            called and Escape does nothing — the 1.0.4 report, with the traffic lights drawn grey.
            """)
        XCTAssertTrue(
            window.isMainWindow,
            "a titled window that is key but not main draws its traffic lights grey")
    }

    /// **Escape closes the timeline when it travels the way a keystroke really travels.**
    ///
    /// `NSApp.sendEvent` rather than `window.sendEvent`, which is the whole difference between this and
    /// the test that shipped green: `NSApplication` routes a key event to *the key window*, so this
    /// exercises the delivery that was missing as well as the handling that was not.
    func testEscapeClosesTheTimelineThroughTheApplicationsOwnDispatch() throws {
        let window = try presentTheTimeline()

        if !window.isKeyWindow {
            try KeyWindowPrecondition.skipIfNoWindowCanBecomeKey(
                notVerified: """
                    that Escape reaches the timeline through `NSApp.sendEvent` and closes it. The \
                    window came up; whether a real key press can arrive at it was not measured.
                    """)
        }
        XCTAssertTrue(window.isKeyWindow, "nothing below is measured unless the timeline is key")

        NSApp.sendEvent(try escape(in: window))

        XCTAssertFalse(
            RewindWindow.isVisible,
            "Escape did not reach the timeline through the application's own event dispatch")
    }

    /// **The panel defaults that would be wrong for this window are not left at their defaults.**
    ///
    /// Key status without waiting on activation costs `.nonactivatingPanel`, and `NSPanel` brings
    /// defaults with it that this window must not keep. `hidesOnDeactivate` is the dangerous one: left
    /// alone it would order the timeline off screen every time the user looked at another app, which is
    /// a worse dead end than the one being repaired. The chrome is asserted beside it because a titled
    /// panel that quietly lost its traffic lights would take the X — the only exit the report credited
    /// the window with having — with it.
    func testTheTimelineKeepsItsWindowChromeAndSurvivesDeactivation() throws {
        let window = try presentTheTimeline()

        XCTAssertFalse(
            window.hidesOnDeactivate,
            "the timeline would vanish whenever the user switched apps")
        XCTAssertTrue(window.styleMask.contains(.titled), "the timeline lost its title bar")
        XCTAssertTrue(window.styleMask.contains(.resizable), "the timeline stopped being resizable")
        XCTAssertEqual(window.level, .normal, "the timeline is worked in, not floated over everything")
        for button in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] {
            XCTAssertNotNil(
                window.standardWindowButton(button),
                "the timeline lost a standard window button (\(button)) — the X is an exit the report counted on")
        }
    }

    /// **Escape leaves the real timeline even with a field editor focused in it.**
    ///
    /// The same claim `TimelineEscapeTests` makes against a bare window, made here against the window
    /// `present()` builds — because the two failures this file records were both *routing*, and routing
    /// is the thing a hand-built window cannot vouch for. The field is installed rather than hoped for:
    /// AppKit focuses a field editor the moment anything editable appears, and the guard this replaced
    /// treated that as an edit in progress and declined the only keyboard exit for good.
    func testEscapeLeavesTheRealTimelineWithAFieldEditorFocused() throws {
        let window = try presentTheTimeline()

        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 80, height: 22))
        window.contentView?.addSubview(field)
        // Removed again by hand: the timeline is a singleton that outlives this test
        // (`isReleasedWhenClosed = false`), and a focused field left in it would follow the window into
        // every later test in the process — which is exactly how a probe can confirm its own hypothesis.
        addTeardownBlock { MainActor.assumeIsolated { field.removeFromSuperview() } }

        XCTAssertTrue(window.makeFirstResponder(field))
        XCTAssertTrue(
            (window.firstResponder as? NSTextView)?.isFieldEditor == true,
            "AppKit did not install a field editor, so this case is not being exercised")

        // **Which route put it away, not merely that it went away.** `NSPanel` closes a closable panel
        // on Escape by itself, so "the window is gone" is satisfied by AppKit stepping over this app's
        // own dismissal — and it did, while the guard this replaced believed it had declined the key.
        // `RewindWindow.dismiss` orders the window out precisely so the loaded day survives the way the
        // X leaves it; a `close()` behind its back sends `willClose` and is a different contract.
        var closed = 0
        let token = NotificationCenter.default.addObserver(
            forName: NSWindow.willCloseNotification, object: window, queue: .main
        ) { _ in closed += 1 }
        addTeardownBlock { NotificationCenter.default.removeObserver(token) }

        // The field-editor half above is a fact about AppKit and holds anywhere; only the press needs
        // a routable keyboard.
        if !window.isKeyWindow {
            try KeyWindowPrecondition.skipIfNoWindowCanBecomeKey(
                notVerified: """
                    that Escape leaves the real timeline with a field editor focused, and that it is \
                    this app's `dismiss()` rather than AppKit's `close()` that puts the window away. \
                    The field editor was installed and confirmed; the press was not delivered.
                    """)
        }

        NSApp.sendEvent(try escape(in: window))

        XCTAssertFalse(
            RewindWindow.isVisible,
            "a focused field the user never touched left the real timeline with no way out")
        XCTAssertEqual(
            closed, 0,
            "the timeline was closed by AppKit rather than dismissed by the app — the loaded day is gone")
    }

    // MARK: - Harness

    /// The real presentation path, over an empty capture database. What is asserted is the window the
    /// app builds, so nothing here may build one.
    private func presentTheTimeline() throws -> RewindWindowFrame {
        let store = try ContextStore(url: root.appendingPathComponent("context.db"))
        RewindWindow.present(store: store)
        return try XCTUnwrap(
            NSApp.windows.compactMap { $0 as? RewindWindowFrame }.first { $0.isVisible },
            "the timeline never came up, so nothing here is measured")
    }

    /// Carrying `U+001B`, because AppKit turns a key event into `cancelOperation:` from the character it
    /// typed rather than from its key code — see `TimelineEscapeTests.key(_:)`, where that is measured.
    private func escape(in window: NSWindow) throws -> NSEvent {
        try XCTUnwrap(
            NSEvent.keyEvent(
                with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0,
                windowNumber: window.windowNumber, context: nil, characters: "\u{1b}",
                charactersIgnoringModifiers: "\u{1b}", isARepeat: false, keyCode: 53))
    }
}
