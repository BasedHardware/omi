import AppKit
import ContextCore
import SwiftUI

/// The timeline window, owned by AppKit rather than by SwiftUI.
///
/// There is no `WindowGroup` anywhere in this app — every window is owned by its own type — so this
/// follows `OnboardingWindow`'s structure exactly: a `@MainActor` enum holding a `static current`,
/// the screen chosen from the pointer rather than `NSScreen.main`, and `isReleasedWhenClosed = false`
/// so closing the window keeps the instance and its loaded day alive for the next open.
///
/// **This is the app's second window now, not its first.** Activity is what the app opens on
/// (`SearchBarWindow`), and the timeline is what a *moment* opens into: a result card, an activity
/// tile, the panel's own Timeline pill, or the menu bar's row.
///
/// **It used to stand aside whenever the search panel came up, and that is deliberately not coming
/// back.** `SearchPanelEvent.opened` never meant "a window appeared" — it meant "present() was
/// called", including on a panel already on screen — and a window ordered out on that fact had no
/// `.closed` coming to bring it back. The panel dismisses itself on Escape and dismisses itself the
/// moment it opens this window, so there is nothing left for a yield to solve.
@MainActor
enum RewindWindow {

    /// Large enough that a 1600 px frame is not the limiting factor, and small enough to open
    /// comfortably on a 13" display.
    static let defaultSize = NSSize(width: 1180, height: 760)
    static let minimumSize = NSSize(width: 820, height: 560)

    /// How often an open timeline looks for captures made since it read its day.
    ///
    /// Deliberately slow. The capture tick is three seconds and nobody sits watching a timeline for
    /// the next frame to appear, so this exists so a window left open all afternoon is not still
    /// claiming the day ended at the hour it was opened — not so the track animates. Each tick costs
    /// one `COUNT(*)` over an indexed range (`RewindModel.hasUnreadCaptures`) and reads nothing
    /// further unless that count moved.
    static let liveRefreshInterval: TimeInterval = 30

    private static var current: NSWindow?
    private static var model: RewindModel?
    private static var liveRefreshTimer: Timer?

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
            // The day this window holds was read when it was last opened, and capture has gone on
            // writing since. Opening the timeline again is exactly the moment to catch up — without
            // it the track stops at whatever hour the first open happened to fall on, for the rest
            // of the process. Nothing the user left in place moves; see `RewindModel.refresh`.
            model?.refresh()
            window.makeKeyAndOrderFront(nil)
            // Activation stays, on this branch and the two below. The timeline is secondary now, but
            // every route into it is an explicit ask — a result card, a menu row, the chord — and an
            // app that answers one by ordering a window in behind whatever is frontmost has not
            // answered it.
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        // The screen the pointer is on, not `NSScreen.main`. With two displays `main` is whichever
        // holds the key window, which is routinely the one the user is not looking at.
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
        window.isMovableByWindowBackground = true
        window.minSize = minimumSize
        window.isReleasedWhenClosed = false
        window.title = RewindView.modeTitle
        // Deliberately not `.floating`: this window is worked *in*, and something always on top of
        // every other window is something to fight rather than something to read.
        window.level = .normal

        // The window-side half of the glass, which for a titled window is four properties that have
        // to agree: the light pin on the *window* (pinning only the content leaves the title bar and
        // the traffic lights in the system's appearance — a dark bar on a white sheet), a transparent
        // ground so the material blurs the desktop rather than a sheet AppKit painted, AppKit's own
        // shadow kept because the frame is the panel's edge here, and a title bar the glass runs edge
        // to edge underneath. All of it is `WindowGlass`, so this window and settings cannot drift.
        WindowGlass.wear(window, as: .titled)

        // CRITICAL: Use a container view instead of making NSHostingView the contentView directly.
        // When NSHostingView IS the contentView of a borderless window, it tries to negotiate
        // window sizing through updateWindowContentSizeExtremaIfNecessary and updateAnimatedWindowSize,
        // causing re-entrant constraint updates that crash in _postWindowNeedsUpdateConstraints.
        // Wrapping in a container breaks that "I own this window" relationship.
        //
        // The hosting view is constrained to the glass *host* rather than handed to
        // `InkGlassView.setContent`, which is the seam a floating panel uses: `setContent` is
        // frame-and-autoresizing, and this window is resizable with a minimum size that only Auto
        // Layout expresses. It is the same rectangle either way — `.fullBleed` is inset 0, so the
        // panel fills its host exactly — and every part of the ground stays AppKit's, which is the
        // property that matters. `RewindView` therefore paints no background of its own.
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
        startLiveRefresh()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    /// Keeps an open timeline level with what capture is writing.
    ///
    /// Only while the window is actually on screen, and never in the middle of a settle: `refresh()`
    /// moves nothing by construction, but a re-span behind a gesture that is still landing is a risk
    /// worth not taking for a catch-up nobody is waiting on. A hidden window catches up on its next
    /// `present`, which is the moment it matters.
    ///
    /// The tick itself is a `Task` because both halves of the catch-up — the count and the day —
    /// happen off the main actor now. What the timer does here is decide whether to ask; the model
    /// owns the asking, so this window never has to know which read is safe to run where.
    private static func startLiveRefresh() {
        liveRefreshTimer?.invalidate()
        let timer = Timer(timeInterval: liveRefreshInterval, repeats: true) { _ in
            MainActor.assumeIsolated {
                guard current?.isVisible == true, let model else { return }
                Task { @MainActor in await model.refreshIfCapturesLanded() }
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        liveRefreshTimer = timer
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
        // go looking for, so bringing it forward is part of aiming it.
        current?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        return true
    }

    /// Hides the window without discarding the loaded day.
    ///
    /// A close is the user's statement about this window and nothing else may undo it: nothing in the
    /// app orders the timeline back in on its own, and the only routes back on screen are the ones a
    /// person takes on purpose — `present`, `focus`, the menu row, the chord.
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
