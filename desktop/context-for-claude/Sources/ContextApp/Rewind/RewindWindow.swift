import AppKit
import ContextCore
import SwiftUI

/// The timeline window, owned by AppKit rather than by SwiftUI.
///
/// The app is `LSUIElement` with no `WindowGroup` — there is no SwiftUI scene graph to add a window
/// to — so this follows `OnboardingWindow`'s structure exactly: a `@MainActor final class` holding a
/// `static current`, the screen chosen from the pointer rather than `NSScreen.main`, and
/// `isReleasedWhenClosed = false` so closing the window keeps the instance and its loaded day alive
/// for the next open.
@MainActor
enum RewindWindow {

    /// Large enough that a 1600 px frame is not the limiting factor, and small enough to open
    /// comfortably on a 13" display.
    static let defaultSize = NSSize(width: 1180, height: 760)
    static let minimumSize = NSSize(width: 820, height: 560)

    private static var current: NSWindow?
    private static var model: RewindModel?

    /// Opens the window, or brings the existing one forward with its state intact.
    ///
    /// - Parameters:
    ///   - store: the capture database. Injected rather than opened here so the app's single store
    ///     is reused; opening a second writer would be a second migration racing the first.
    static func present(
        store: ContextStore,
        onOpenSettings: @escaping () -> Void = {},
        onSearch: @escaping (String) -> Void = { _ in }
    ) {
        if let window = current {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        // The screen the pointer is on, not `NSScreen.main`. With two displays `main` is whichever
        // holds the key window, which on a menu-bar-only app is routinely the one the user is not
        // looking at.
        let pointer = NSEvent.mouseLocation
        guard let screen = NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
            ?? NSScreen.main
        else {
            ContextLog.error("no screen available to present the timeline", "rewind")
            return
        }

        let model = RewindModel(store: store)
        Self.model = model

        let window = NSWindow(
            contentRect: centredFrame(on: screen),
            // Titled and resizable: unlike onboarding, this is a document-ish window the user keeps
            // open, moves, and resizes. The title bar is transparent and the title hidden so the
            // spec's centred mode title is the only thing that reads as one.
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false)
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.minSize = minimumSize
        window.isReleasedWhenClosed = false
        window.title = RewindView.modeTitle
        // Deliberately not `.floating`: this window is worked *in*, and something always on top of
        // every other window is something to fight rather than something to read.
        window.level = .normal

        // Glass, and pinned light like every other surface in the app. On a titled window the pin has
        // to be on the *window* rather than on the content view: pinning only the content leaves the
        // title bar and the traffic lights in the system's appearance, which on a Dark machine is a
        // dark bar sitting on a white sheet. `.fullSizeContentView` plus a transparent title bar
        // means the glass runs edge to edge under it.
        InkGlass.pin(window)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.titlebarSeparatorStyle = .none

        // CRITICAL: Use a container view instead of making NSHostingView the contentView directly.
        // When NSHostingView IS the contentView of a borderless window, it tries to negotiate
        // window sizing through updateWindowContentSizeExtremaIfNecessary and updateAnimatedWindowSize,
        // causing re-entrant constraint updates that crash in _postWindowNeedsUpdateConstraints.
        // Wrapping in a container breaks that "I own this window" relationship.
        //
        // sizingOptions: Remove .intrinsicContentSize so the hosting view can expand beyond
        // its SwiftUI ideal size. Keep .minSize and .maxSize for proper min/max constraints.
        // Setting [] removes ALL sizing info (broken). Default includes .intrinsicContentSize
        // which pins the view to its ideal size (prevents expansion). [.minSize, .maxSize] is correct.
        // The shared glass, full-bleed: no corner and no shadow of its own, because the window frame
        // already owns both. Everything the app draws on glass goes through this one component.
        let container = InkGlassView(
            frame: NSRect(origin: .zero, size: window.frame.size), style: .fullBleed)
        container.autoresizingMask = [.width, .height]
        window.contentView = container
        container.layoutSubtreeIfNeeded()

        let hosting = NSHostingView(
            rootView: RewindView(model: model, onOpenSettings: onOpenSettings, onSearch: onSearch))
        hosting.sizingOptions = [.minSize, .maxSize]
        hosting.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(hosting)
        NSLayoutConstraint.activate([
            hosting.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            hosting.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            hosting.topAnchor.constraint(equalTo: container.topAnchor),
            hosting.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])

        current = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    /// Opens the timeline **at a moment**, or moves an already-open one to it.
    ///
    /// The seam a search result travels through, and the reason it exists: `present(store:…)` opens
    /// whatever day the model last had — today, on a first open — so a card for last Tuesday could
    /// only ever open the wrong day. There was no way to say *when* from outside this file at all,
    /// which is why the search surface's result cards shipped inert.
    ///
    /// Correct whether or not the window is already up, and that is the whole of its contract:
    ///
    /// - **Closed.** `present` builds the model and the window; the instant is held by the model
    ///   (`pendingFocus`) and consumed by the opening read, so the day that opens *is* the moment's
    ///   day rather than the newest one being replaced a frame later.
    /// - **Open on another day.** The model loads that day and parks the playhead on the nearest
    ///   capture to the instant.
    /// - **Open on the same day.** No re-read; the playhead moves and the window comes forward.
    ///
    /// - Parameter instant: Unix epoch seconds — a `SearchMoment.capturedAt`, which is the frame's
    ///   capture time for a screen hit and the line's start for a spoken one.
    static func present(
        store: ContextStore,
        at instant: Double,
        onOpenSettings: @escaping () -> Void = {},
        onSearch: @escaping (String) -> Void = { _ in }
    ) {
        // Present first, then aim. The other order would ask a model that does not exist yet.
        present(store: store, onOpenSettings: onOpenSettings, onSearch: onSearch)
        focus(instant)
    }

    /// Moves an already-open timeline to `instant` and brings it forward.
    ///
    /// Returns false when there is no timeline to move — which is a state a caller may legitimately
    /// want to know about rather than a failure, so it is reported rather than logged. Callers that
    /// simply want the moment on screen should use `present(store:at:)`, which cannot fail this way.
    @discardableResult
    static func focus(_ instant: Double) -> Bool {
        guard let model else { return false }
        model.focus(on: instant)
        // A timeline behind the surface that just handed it a moment is a timeline the user has to
        // go looking for.
        current?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        return true
    }

    /// Hides the window without discarding the loaded day.
    static func dismiss() {
        current?.orderOut(nil)
    }

    static var isVisible: Bool { current?.isVisible ?? false }

    private static func centredFrame(on screen: NSScreen) -> NSRect {
        let visible = screen.visibleFrame
        let size = NSSize(
            width: min(defaultSize.width, visible.width - 40),
            height: min(defaultSize.height, visible.height - 40))
        return NSRect(
            x: (visible.midX - size.width / 2).rounded(),
            y: (visible.midY - size.height / 2).rounded(),
            width: size.width,
            height: size.height)
    }
}
