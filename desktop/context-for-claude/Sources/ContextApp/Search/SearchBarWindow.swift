import AppKit
import SwiftUI

/// The floating prompt bar. One borderless window, on the display the pointer is on.
///
/// AppKit-owned rather than a SwiftUI scene, for the same reason `OnboardingWindow` is: the app is
/// `LSUIElement` with no `WindowGroup`, so a scene here would be a window the user could summon by
/// accident. This follows that file's structure deliberately — same `static current`, same
/// pointer-screen rule, same `isReleasedWhenClosed = false` so the window survives being closed.
@MainActor
final class SearchBarWindow {
    /// Wide enough for a real sentence, and short enough to read as a bar rather than a panel. The
    /// height is the content's: a 40 pt field, one status line, and the page padding — plus room for
    /// that line to wrap to two, which it does when a route explains itself.
    static let barSize = NSSize(width: 660, height: 112)

    private static var current: NSWindow?

    /// Opens the bar, or brings it forward and re-focuses the field if it is already up.
    ///
    /// - Parameter prefill: a question to start from. This is the seam the timeline's "Search All"
    ///   pill plugs into — `RewindWindow.present(onSearch:)` hands its query straight through, so the
    ///   two surfaces share one bar rather than each growing their own.
    static func present(prefill: String = "") {
        if let window = current {
            window.alphaValue = 1
            window.makeKeyAndOrderFront(nil)
            NotificationCenter.default.post(
                name: refocusNotification, object: nil,
                userInfo: prefill.isEmpty ? nil : [prefillKey: prefill])
            return
        }

        // The screen the pointer is on, not `NSScreen.main`: on a menu-bar-only app `main` is
        // whichever screen holds the key window, which is routinely the one the user is not looking
        // at — and a search bar that opens on the other monitor may as well not have opened.
        let pointer = NSEvent.mouseLocation
        guard let screen = NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
            ?? NSScreen.main
        else {
            ContextLog.error("no screen available to present the search bar", "search")
            return
        }

        let frame = barFrame(on: screen)
        // `.nonactivatingPanel`, and this is the whole reason the bar is an `NSPanel` rather than an
        // `NSWindow` like the onboarding card.
        //
        // A plain borderless window belonging to an `.accessory` app orders in but does **not** become
        // key: `NSApp.activate` is asynchronous and unreliable for an app that owns no regular
        // windows, so every keystroke went to whatever was already in front — measured, with the field
        // still showing its placeholder while the text landed in another app. A non-activating panel
        // takes key status *without* activating the app, which is exactly the Spotlight-style
        // behaviour this surface needs.
        let window = SearchPanel(
            contentRect: frame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        window.isFloatingPanel = true
        window.becomesKeyOnlyIfNeeded = false
        window.isOpaque = false
        window.backgroundColor = .clear
        // Unlike the onboarding sheet this surface *is* a rectangle, so a shadow traces the shape it
        // actually has and is what lifts it off whatever is behind.
        window.hasShadow = true
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.isReleasedWhenClosed = false
        window.hidesOnDeactivate = false
        window.animationBehavior = .utilityWindow

        // A plain container, with the hosting view *inside* it.
        //
        // Making an `NSHostingView` the `contentView` of a borderless window crashes on macOS 26
        // inside `_postWindowNeedsUpdateConstraints`. Hosting it as a subview of an ordinary `NSView`
        // is the same layout and does not.
        let root = FirstMouseView(frame: NSRect(origin: .zero, size: frame.size))
        root.autoresizingMask = [.width, .height]

        let hosting = FirstMouseHostingView(
            rootView: SearchBarView(initialQuery: prefill, onDismiss: { dismiss() }))
        hosting.frame = root.bounds
        hosting.autoresizingMask = [.width, .height]
        root.addSubview(hosting)

        window.contentView = root
        window.setFrame(frame, display: true)

        current = window
        observeKey(window)
        // No `NSApp.activate`. The panel takes key status on its own, and activating the app as well
        // would pull the user out of whatever they were doing for no gain.
        window.makeKeyAndOrderFront(nil)
        // Key status is not focus. SwiftUI's `@FocusState` only reaches the field once the hosting
        // view is the window's first responder, and AppKit does not hand it over on its own for a
        // borderless panel — measured: `isKeyWindow` was true while the field still showed its
        // placeholder and the keystrokes went to the app behind. The async pass is the one that
        // sticks, because SwiftUI installs the field's responder on the next runloop turn.
        window.makeFirstResponder(hosting)
        DispatchQueue.main.async {
            MainActor.assumeIsolated {
                guard current === window else { return }
                window.makeFirstResponder(hosting)
                NotificationCenter.default.post(name: SearchBarWindow.refocusNotification, object: nil)
            }
        }
        // The shared chrome cue, which already honours the system UI-sound setting on its own.
        Sound.effect(.swoosh)
        ContextLog.info("search bar presented (key: \(window.isKeyWindow))", "search")
    }

    /// `userInfo` key carrying a prefill through `refocusNotification`.
    static let prefillKey = "prefill"

    /// SwiftUI can only take focus once the window is key, and for an accessory app that happens
    /// *after* `present()` returns. Re-asserting focus on `didBecomeKey` is what makes the field
    /// typeable on the first open rather than the second.
    private static func observeKey(_ window: NSWindow) {
        keyObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.didBecomeKeyNotification, object: window, queue: .main
        ) { _ in
            MainActor.assumeIsolated {
                NotificationCenter.default.post(name: SearchBarWindow.refocusNotification, object: nil)
            }
        }
    }

    private static var keyObserver: NSObjectProtocol?

    /// Fires when `present()` is called on an already-open bar, so the field takes focus again.
    static let refocusNotification = Notification.Name("context.search.refocus")

    static var isVisible: Bool { current?.isVisible ?? false }

    static func toggle(prefill: String = "") {
        if isVisible {
            dismiss()
        } else {
            present(prefill: prefill)
        }
    }

    static func dismiss() {
        guard let window = current else { return }
        current = nil
        if let keyObserver {
            NotificationCenter.default.removeObserver(keyObserver)
            self.keyObserver = nil
        }
        window.orderOut(nil)
        window.close()
    }

    /// Upper third, horizontally centred. A prompt bar belongs where the eye already is, not at the
    /// optical centre of the display.
    private static func barFrame(on screen: NSScreen) -> NSRect {
        let visible = screen.visibleFrame
        let x = visible.midX - barSize.width / 2
        let y = visible.maxY - barSize.height - visible.height * 0.18
        return NSRect(x: x.rounded(), y: y.rounded(), width: barSize.width, height: barSize.height)
    }

}

// MARK: - Window

/// Borderless panels refuse key status by default, which would leave the field untypeable.
///
/// `canBecomeMain` stays false on purpose: a non-activating panel that claims main status drags the
/// app forward, which is the thing `.nonactivatingPanel` exists to avoid.
private final class SearchPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }

    /// Escape, intercepted where interception is guaranteed.
    ///
    /// Belt to the field's own braces. `SearchField`'s delegate already reports Escape as
    /// `cancelOperation:`, but only while the field editor holds focus — this catches it when focus has
    /// moved to the target pill, where a bar that would not close is the worst possible state. Return
    /// is deliberately **not** handled here: the field owns submitting, and intercepting it in two
    /// places is how it ends up handled in neither.
    ///
    /// `sendEvent` rather than a local `NSEvent` monitor because a monitor does not see these events at
    /// all — measured: the field took Escape and dropped its focus while the monitor was never called.
    /// For a non-activating panel in an app that was never activated, key events do not go through
    /// `NSApplication`'s dispatch.
    override func sendEvent(_ event: NSEvent) {
        if event.type == .keyDown {
            switch event.keyCode {
            case 53:  // Escape
                MainActor.assumeIsolated { SearchBarWindow.dismiss() }
                return
            default:
                break
            }
        }
        super.sendEvent(event)
    }
}

// MARK: - First mouse
//
// The app is an `.accessory`, so it is never the active application when the bar appears. By default
// AppKit spends the first click activating the window and never delivers it to the control
// underneath — the user's first click into the field would do nothing at all. This codebase has been
// bitten by exactly that before; accepting first mouse is what makes the first click count.

private final class FirstMouseView: NSView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

private final class FirstMouseHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}
