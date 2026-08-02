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
        // Whether or not there is a window yet: this is what makes a timeline that has been opened
        // once know to stand aside the next time the search panel comes up.
        observeTheSearchPanel()

        if let window = current {
            // A present is a show, and it outranks any yield in progress. Without this the window
            // that is standing aside for the search panel would be ordered front at alpha 0 by the
            // line below — on screen, invisible, and in the way.
            setHidden(false)
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
        // A brand-new window is not standing aside for anything, whatever the last one was doing.
        isHiddenIntent = false
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
        // go looking for — and a timeline *standing aside* for that surface is one they cannot find
        // at all, which is the ordinary case here: the search panel hides it, and then hands it a
        // moment. Bringing it back is the same statement as bringing it forward.
        setHidden(false)
        current?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        return true
    }

    /// Hides the window without discarding the loaded day.
    ///
    /// Clears the yield as well, and that is the half that is easy to forget: a close is a stronger
    /// statement than "stand aside for a moment", so a `setHidden(false)` arriving afterwards — the
    /// search panel finally closing, say — must not put the window back on screen. With the intent
    /// cleared here that call is a no-op, because `setHidden` is idempotent on intent.
    static func dismiss() {
        isHiddenIntent = false
        current?.orderOut(nil)
    }

    static var isVisible: Bool { current?.isVisible ?? false }

    // MARK: - Standing aside

    /// Whether the timeline is currently out of the way of another of this app's floating surfaces.
    ///
    /// The *intent*, not `isVisible`: a window that is mid-fade is still visible while hiding and
    /// already visible while showing, so the two answer differently at exactly the moment it matters.
    /// Readable from outside so a test can assert the yield without putting a window on screen.
    private(set) static var isHiddenIntent = false

    /// Gets out of the way while the search panel is up, and comes back when it goes.
    ///
    /// **Why the timeline hides at all.** The search bar is opened *from* the timeline — the pill is
    /// in its own header — and it is a 760 pt floating slab that lands over the upper half of the
    /// display. Two big floating surfaces stacked is the panel covering the thing that opened it, and
    /// it is what "the rewind tab is hidden" asks for: the timeline steps back for the one surface
    /// that is answering the same question, and returns the moment that surface is done.
    ///
    /// **The asymmetry is deliberate: the hide is immediate, the show fades.** `OnboardingWindow`
    /// documents the trap this design sidesteps — an `orderOut` that lands *after* a show request
    /// strands a window off screen on an `LSUIElement` app, so its version needs a generation counter
    /// to make "a show that arrived mid-fade always wins". There is nothing to win here: hiding
    /// happens on the calling turn, so there is no completion handler to arrive late and no race to
    /// arbitrate. What is left is the part worth animating — a window *returning* is a step back into
    /// the room, and it reads better fading in than popping. Reduce Motion collapses it to nothing.
    ///
    /// Idempotent on intent, so the unconditional restore in `SearchBarWindow.dismiss` costs nothing
    /// on the second call, and a timeline the user never opened is a no-op both ways.
    static func setHidden(_ hidden: Bool) {
        guard hidden != isHiddenIntent else { return }
        // Recorded before the window is looked for, so the flag is honest on a machine where no
        // timeline has ever been opened — and so a `present` that happens next knows what to clear.
        isHiddenIntent = hidden
        guard let window = current else { return }

        guard !hidden else {
            window.orderOut(nil)
            return
        }
        // Ordered in *before* the fade and from zero, so the window never flashes at full opacity for
        // a frame. `orderFrontRegardless` rather than `makeKeyAndOrderFront`: coming back must not
        // take focus off whatever the user moved on to.
        window.alphaValue = 0
        window.orderFrontRegardless()
        NSAnimationContext.runAnimationGroup(
            { context in
                context.duration = InkReduceMotion.duration(InkMotion.stepTransition)
                context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                window.animator().alphaValue = 1
            },
            completionHandler: {
                MainActor.assumeIsolated {
                    // Pinned however the animation ended, so the window can never be left at a
                    // partial alpha — but only while it is still meant to be on screen.
                    guard current === window, !isHiddenIntent else { return }
                    window.alphaValue = 1
                }
            })
    }

    /// Starts listening to the real search surface, once.
    ///
    /// Called from `present` rather than at launch, and the reason is the same one that makes the
    /// yield safe: a timeline that has never been opened has nothing to stand aside, and a
    /// registration that only exists once there is a window to move cannot move one that was never
    /// asked for. Idempotent — a second `present` re-uses the first registration rather than stacking
    /// a second observer that would hide the window twice.
    static func observeTheSearchPanel() {
        guard searchPanelToken == nil else { return }
        searchPanelToken = SearchPanelWatch.addObserver { event in
            switch event {
            case .opened: setHidden(true)
            case .closed: setHidden(false)
            // Not this window's business. What was asked and what was pressed belong to whoever is
            // coaching the panel; all this window has to know is whether it is in the way.
            case .answered, .openedMoment: break
            }
        }
    }

    private static var searchPanelToken: UUID?

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
