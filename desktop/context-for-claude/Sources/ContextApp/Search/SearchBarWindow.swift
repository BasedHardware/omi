import AppKit
import ContextCore
import SwiftUI

/// The floating prompt bar. One borderless window, on the display the pointer is on.
///
/// AppKit-owned rather than a SwiftUI scene, for the same reason `OnboardingWindow` is: the app is
/// `LSUIElement` with no `WindowGroup`, so a scene here would be a window the user could summon by
/// accident. This follows that file's structure deliberately — same `static current`, same
/// pointer-screen rule, same `isReleasedWhenClosed = false` so the window survives being closed.
@MainActor
final class SearchBarWindow {
    /// The window is the whole surface — both panels, the gap between them, and the clear margin the
    /// shadows fall into. Every number comes from `SearchLayout`, so the window and the view can
    /// never disagree about how tall the content is.
    ///
    /// `showingNote` is the taller state: the bar grows one line when it has something to say about
    /// where the question went.
    static func surfaceSize(showingNote: Bool = false) -> NSSize {
        NSSize(
            width: SearchLayout.surfaceWidth,
            height: SearchLayout.surfaceHeight(showingNote: showingNote))
    }

    private static var current: NSWindow?

    /// The panel's own rectangle, in AppKit screen coordinates, or nil when it is not up.
    ///
    /// Read by anything that has to stand *beside* this surface rather than on it — today the
    /// tutorial's coach mark, which coaches the real panel and must not sit over the field the user
    /// is being asked to type in. Nil is an ordinary answer and every caller has to live with it: the
    /// panel is closed far more often than it is open.
    ///
    /// The window includes `SearchLayout.shadowMargin` of clear margin on every side, which is
    /// deliberate — a card placed against this rectangle clears the shadow too.
    static var panelFrame: NSRect? {
        guard let window = current, window.isVisible else { return nil }
        return window.frame
    }

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
            // Announced on this branch too. "The panel is up" is the fact observers care about, and a
            // second press of the pill on an already-open bar leaves them holding it either way.
            SearchPanelWatch.report(.opened)
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
        // The window-side half of the glass: transparent ground, the light pin, and no window shadow.
        //
        // `.floating` is right for this surface twice over. Once for the ordinary reason — the panels
        // draw the broad ambient shadow themselves, inside the window, which is the only shadow that
        // can follow their rounded corners. And once for a reason peculiar to this window: the
        // surface is not one rectangle but *two* panels with a gap between them, and AppKit's window
        // shadow traces the frame, so leaving it on would draw a shadow straight across the gap and
        // weld them back into the single slab this design exists to stop being.
        //
        // The pin is not cosmetic either. `InkGlass` is light in both system appearances, and the
        // bar's field is an `NSTextField` whose `Ink.nsPrimary` resolves against its *view's*
        // appearance rather than SwiftUI's environment — so on a Dark Mac an unpinned window puts
        // near-white type on a near-white panel. Pinning the window is what makes the AppKit half of
        // this surface agree with the SwiftUI half.
        WindowGlass.wear(window, as: .floating)
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
            rootView: SearchBarView(
                initialQuery: prefill,
                // The app's single store, not a second connection: a second writer would be a second
                // migration racing the first. Nil when capture has not opened one yet, which the
                // panel renders as its empty state rather than as an error.
                store: Engine.shared.contextStore,
                onDismiss: { dismiss() },
                onHeightChange: { height in resize(to: height) },
                onOpenMoment: { moment in open(moment) }))
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
        // Last, once the window is genuinely on screen. Anything listening for this — the timeline
        // standing aside, the tutorial's search beat — is being told a fact about the display, so it
        // is announced after the display has it and not before.
        SearchPanelWatch.report(.opened)
    }

    /// **Activating a result: open the timeline there, then get out of the way.**
    ///
    /// The one place a found moment becomes a window operation. `capturedAt` is the instant for both
    /// kinds of result — a screen hit carries its frame's capture time, a conversation hit carries
    /// the moment the line was spoken — so a single call covers both and neither kind can drift into
    /// a different meaning of "when".
    ///
    /// The order is load-bearing in both directions:
    ///
    /// - **Present first.** `RewindWindow.present(store:at:)` is what activates the app and takes key
    ///   status; doing it after the panel closed would leave a moment on screen behind whatever the
    ///   user was in.
    /// - **Then dismiss.** A floating search panel sitting over the timeline is covering the exact
    ///   thing the user just asked to see. It closes rather than hides, which is what this surface
    ///   has always done — the next open rebuilds it, empty, ready for the next question.
    ///
    /// Declining when the store is not open yet is the same rule the menu bar and the global
    /// shortcut already follow: a timeline over nothing is worse than no timeline.
    private static func open(_ moment: SearchMoment) {
        guard let store = Engine.shared.contextStore else {
            ContextLog.error("cannot open a moment before the capture database is open", "search")
            return
        }
        RewindWindow.present(
            store: store,
            at: moment.capturedAt,
            // The same two handlers the menu bar and the global shortcut hand it, because the window
            // this opens is the same window: one that could not reach Settings, or whose "Search All"
            // pill did nothing, would be a second-class timeline reachable only from here.
            onOpenSettings: { SettingsWindow.present() },
            onSearch: { query in SearchBarWindow.present(prefill: query) })
        // Announced before the panel goes, so an observer sees "a result was activated" followed by
        // "the panel closed" rather than the other way round — the close is a *consequence* of the
        // activation here, and an observer that saw it first would read the beat as abandoned.
        //
        // `frame != nil` and not `kind == .screen`: what the fact is about is whether there is a
        // picture of that instant to travel back to, and a screen whose file retention already
        // unlinked has no more of one than a spoken line does.
        SearchPanelWatch.report(
            .openedMoment(at: moment.capturedAt, hasPicture: moment.frame != nil))
        dismiss()
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

    /// Closes the bar and tells everyone who stood aside for it that they can come back.
    ///
    /// **The announcement is before the guard, not after it, and that is load-bearing.** The one
    /// thing a surface that hides another surface must never do is leave the other one hidden — this
    /// app is `LSUIElement`, so a window ordered out with nothing to bring it back is a dead end. A
    /// `dismiss()` of an already-closed bar is exactly the shape that reaches here after some *other*
    /// path already closed the window (a result being opened, a second dismissal racing the first),
    /// and it is precisely the call that has to still restore the timeline. Reporting `.closed`
    /// unconditionally makes "the panel is not up" and "nothing is standing aside for it" the same
    /// statement; every observer of this event is idempotent for the same reason.
    static func dismiss() {
        SearchPanelWatch.report(.closed)
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
    ///
    /// Clamped to the screen: the surface is a tall two-panel object now, and on a 13" display the
    /// naive upper-third placement puts its bottom edge past the dock.
    static func barFrame(on screen: NSScreen, showingNote: Bool = false) -> NSRect {
        let size = surfaceSize(showingNote: showingNote)
        let visible = screen.visibleFrame
        let x = visible.midX - size.width / 2
        let wanted = visible.maxY - size.height - visible.height * 0.10
        let y = max(visible.minY, wanted)
        return NSRect(x: x.rounded(), y: y.rounded(), width: size.width, height: size.height)
    }

    /// Grows or shrinks the window around its **top** edge.
    ///
    /// Around the top and not the centre because the bar is the thing the user is looking at and
    /// typing into: a window that re-centres itself when a status line appears moves the field out
    /// from under the cursor mid-sentence.
    static func resize(to height: CGFloat) {
        guard let window = current else { return }
        let frame = window.frame
        guard abs(frame.height - height) > 0.5 else { return }
        window.setFrame(
            NSRect(x: frame.minX, y: frame.maxY - height, width: frame.width, height: height),
            display: true,
            animate: false)
    }

}

// MARK: - What the real search surface just did

/// One thing that really happened on the real search surface.
///
/// Every case is a fact about the *shipped* panel — the window that came up, the read that finished,
/// the card somebody pressed — and nothing here can be produced by asking. That is the whole reason
/// it exists: two things outside this surface need to react to it, and neither of them may do so by
/// growing a copy of it.
///
/// - **The timeline stands aside.** Two floating slabs stacked on one display is the search panel
///   covering the very thing it was opened from, so `RewindWindow` yields on `.opened` and comes
///   back on `.closed`.
/// - **The tutorial coaches it.** Its search beats used to draw their own field and their own grid of
///   results on a coach card — a tutorial teaching a surface that does not exist. They now watch
///   these events instead, so what the user learns to press is the real pill and what answers them is
///   the real panel.
enum SearchPanelEvent: Equatable, Sendable {
    /// The panel is on screen. Sent on a fresh open *and* on a press that re-focused one already up,
    /// because the fact is about the display and not about how it got there.
    case opened
    /// The panel is gone, whichever route closed it. Always sent, even for a dismissal that found
    /// nothing to close — see `SearchBarWindow.dismiss`.
    case closed
    /// A real read finished.
    ///
    /// - Parameters:
    ///   - query: what was asked, trimmed. **Empty is a real value and means something specific**:
    ///     the panel opens by reading the newest captures with nothing typed, so an observer waiting
    ///     for somebody to genuinely search for something has to be able to tell that read apart from
    ///     a question. Folding the two together would let the search beat's gate be satisfied by the
    ///     bar merely opening.
    ///   - results: how many moments came back. Zero for a read that failed as well as for one that
    ///     genuinely found nothing — the panel says which in its own copy, and nothing downstream may
    ///     treat "could not look" as an answer.
    case answered(query: String, results: Int)
    /// One of those results was activated, and the timeline has travelled to it.
    ///
    /// - Parameters:
    ///   - at: the moment, in Unix epoch seconds.
    ///   - hasPicture: whether a captured frame survives for that instant. False for a spoken line
    ///     and for a screen whose file retention has already unlinked.
    case openedMoment(at: Double, hasPicture: Bool)
}

/// Who is listening to the real search surface.
///
/// A registry of closures rather than `NotificationCenter`, for the same reason
/// `GlobalShortcuts.addObserver` is one: the token makes a second `start` impossible to leak, the
/// payload is a typed value rather than a `userInfo` dictionary every reader has to re-parse, and
/// nothing here is discoverable by an observer that was never handed the type.
///
/// Observers are told, never asked. Nothing in here can make the panel do anything.
@MainActor
enum SearchPanelWatch {
    private static var observers: [UUID: (SearchPanelEvent) -> Void] = [:]

    /// - Returns: a token to hand back to `removeObserver`. Observers are additive; registering a
    ///   second one never replaces the first.
    @discardableResult
    static func addObserver(_ observe: @escaping (SearchPanelEvent) -> Void) -> UUID {
        let token = UUID()
        observers[token] = observe
        return token
    }

    static func removeObserver(_ token: UUID) {
        observers[token] = nil
    }

    /// Tells every observer. Copied first so an observer that removes itself — or registers another —
    /// while being told cannot mutate the collection being iterated.
    static func report(_ event: SearchPanelEvent) {
        for observe in Array(observers.values) { observe(event) }
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
