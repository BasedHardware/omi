import AppKit
import SwiftUI

/// The onboarding surface: one small, centred pane of frosted glass, floating over the desktop.
///
/// No title bar, no traffic lights, no second window. It shipped once as an edgeless oval — a paper
/// floor and a nine-blob wash, both masked by the same radial falloff — and the wash was reported as
/// an ugly hue behind the copy. The mask and the wash are both gone. What replaces them is the app's
/// shared glass — `InkGlassView`, the same component the timeline, settings, the popover, the search
/// bar and the coach marks are built on — pinned to a light appearance and scrimmed just enough to
/// read type on.
///
/// The whole card is legible area — there is no falloff to keep content out of — so the margins in
/// `InkLayout` are real margins rather than the inner third of a dissolve. The *window* is larger
/// than the card by `InkGlassStyle.floating.inset`, which is the room the ambient shadow needs; see
/// `windowSize`.
@MainActor
final class OnboardingWindow {
    /// The glass panel's size. Fixed, so the surface never resizes under the user mid-flow.
    ///
    /// **The height is the permissions card's, and every other card is a guest on it.** 520 pt was
    /// the height of the *short* cards — a headline, a sentence and a button — and the permissions
    /// step is the one screen whose content varies: a preamble that changes length with the gate's
    /// phase, four first-person sentences that wrap or do not, and either a 44 pt escape panel or a
    /// 125 pt replica of the row the user is about to flip by hand. At 520 the tallest of those
    /// states wanted ~40 pt more than the card had, and SwiftUI paid for it by compressing the rows
    /// until three of the four sentences truncated mid-word ("…so I can hear what you talk…"). A
    /// card that silently eats its own copy is worse than a slightly larger card, and a resize
    /// mid-flow would be worse than both — so the pane is sized once, for its tallest state, and
    /// `PermissionsCardTests` is what keeps that true.
    static let cardSize = NSSize(width: 720, height: 640)

    /// The height a card's content is actually laid out in: the pane, less the page's own top and
    /// bottom margins, less the strip reserved for the progress dots.
    ///
    /// **The layout budget, stated once**, so the card, the dots and the tests cannot each hold a
    /// different opinion about how much room there is.
    static var cardContentHeight: CGFloat {
        cardSize.height - 2 * InkLayout.pagePaddingVertical - InkLayout.progressBandHeight
    }

    /// The window's size, which is the panel plus the margin its ambient shadow casts into.
    ///
    /// A borderless window clips at its own bounds, so a panel drawn edge to edge has nowhere to put
    /// a shadow. The window is bigger than the card and transparent everywhere the card is not; the
    /// user sees the card and the light under it, which is the whole point of the extra room.
    static var windowSize: NSSize {
        let pad = InkGlassStyle.floating.inset
        return NSSize(width: cardSize.width + pad * 2, height: cardSize.height + pad * 2)
    }

    private static var current: NSWindow?
    /// The cinematic's own layer, held only while it plays so it can be torn out afterwards.
    private static var cinematicHosting: NSView?
    private static var cinematicDirector: CinematicDirector?
    /// Esc, at the AppKit level. See `installEscapeMonitor`.
    private static var escapeMonitor: Any?

    /// The first-run entry point.
    ///
    /// Plays the Phase 3 cinematic on the display under the pointer and then shrinks into the
    /// welcome card. Once `context.onboarded` is set — the same flag `ContextApp` gates this call on
    /// — `CinematicGate` turns the intro off and this is the card alone, so the sequence runs
    /// exactly once per install and the entry point never has to change.
    static func present() {
        if let window = current {
            window.alphaValue = 1
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        // The screen the pointer is on, not `NSScreen.main`. With two displays `main` is whichever
        // holds the key window, which on a menu-bar-only app is routinely the one the user is not
        // looking at — and a first-run card that opens on the other monitor may as well not exist.
        let pointer = NSEvent.mouseLocation
        guard let screen = NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
            ?? NSScreen.main
        else {
            ContextLog.error("no screen available to present onboarding", "onboarding")
            return
        }

        guard CinematicGate().shouldPlay else {
            presentCard(on: screen)
            return
        }
        presentCinematic(on: screen)
    }

    /// The tutorial hand-off, shared by both entry points.
    ///
    /// `OnboardingView` has taken an `onTutorial` closure since the flow gained its final step, but
    /// both call sites here constructed `OnboardingView()` without it — so "Show me" fell through to
    /// `.done` and the entire tutorial was unreachable. Same shape of defect as the timeline window
    /// having no call site: built, tested, and impossible to get to.
    ///
    /// The card is dismissed first. The tutorial drives real windows and real coach marks anchored to
    /// them, and a floating onboarding card left on top would sit over the very UI it is pointing at.
    private static let startTutorial: () -> Void = {
        dismiss()
        Tutorial.start()
    }

    /// The welcome card, with no intro. The state onboarding actually runs in, and where the
    /// cinematic lands.
    static func presentCard(on screen: NSScreen) {
        let frame = centredFrame(on: screen)
        let window = makeWindow(contentRect: frame)
        window.contentView = makeRoot(size: frame.size, hosting: OnboardingView(onTutorial: startTutorial))
        window.setFrame(frame, display: true)

        current = window
        isHiddenIntent = false
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    // MARK: - The cinematic

    /// Beat 1 needs the whole display, so the window opens at `screen.frame` and above the menu bar
    /// — a dim with a bright strip along the top is not a dim. It is the *same window* that becomes
    /// the card, so beat 6 is a resize rather than a second window appearing over the first.
    private static func presentCinematic(on screen: NSScreen) {
        let full = screen.frame
        let window = makeWindow(contentRect: full)
        // Above `.mainMenu` (24), so the scrim covers the menu bar and the Dock. Dropped back to
        // `.floating` the moment the card takes over — an always-on-top-of-everything window is
        // right for eight seconds and wrong for a flow the user has to click through.
        window.level = .statusBar

        let director = CinematicDirector()
        let root = FirstMouseView(frame: NSRect(origin: .zero, size: full.size))
        root.autoresizingMask = [.width, .height]

        let hosting = FirstMouseHostingView(rootView: CinematicView(director: director))
        hosting.frame = root.bounds
        hosting.autoresizingMask = [.width, .height]
        root.addSubview(hosting)

        // CRITICAL: the hosting view goes *inside* a plain container and is never the window's
        // `contentView`. As `RewindWindow` documents, an `NSHostingView` that is the contentView of
        // a borderless window negotiates the window's size and crashes in
        // `_postWindowNeedsUpdateConstraints` on macOS 26.
        window.contentView = root
        window.setFrame(full, display: true)

        current = window
        cinematicHosting = hosting
        cinematicDirector = director

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        installEscapeMonitor(director)

        director.start { end in
            MainActor.assumeIsolated { landOnCard(on: screen, after: end) }
        }
    }

    /// Beat 6's landing: the window shrinks to the card's frame and the card fades in where the
    /// composition receded to.
    ///
    /// The order matters. The cinematic layer is already at zero opacity by the time beat 6 ends, so
    /// the resize itself is invisible and can happen instantly — animating an empty transparent
    /// window would only add a pause. On an abort the layer is *not* faded out, so it is dropped in
    /// the same turn as the resize.
    private static func landOnCard(on screen: NSScreen, after end: CinematicEnd) {
        removeEscapeMonitor()
        cinematicDirector = nil

        guard let window = current else {
            // The window went away under us (a `dismiss()` racing the last beat). Onboarding still
            // has to happen, so open the card fresh.
            presentCard(on: screen)
            return
        }

        cinematicHosting?.removeFromSuperview()
        cinematicHosting = nil

        let frame = centredFrame(on: screen)
        window.level = .floating
        window.setFrame(frame, display: true)

        let root = makeRoot(size: frame.size, hosting: OnboardingView(onTutorial: startTutorial))
        // `NSView.alphaValue` is only honoured on a layer-backed view, and `animator()` can only
        // animate it through Core Animation. Without this the card either never fades or — worse —
        // is left sitting at the alpha it started from, which is a first run with no visible
        // onboarding at all. The completion handler pins it to 1 regardless, so the one thing that
        // cannot happen is an invisible card.
        root.wantsLayer = true
        root.alphaValue = 0
        window.contentView = root
        window.makeKeyAndOrderFront(nil)

        let duration = InkReduceMotion.isEnabled ? 0 : InkMotion.finaleGlow
        NSAnimationContext.runAnimationGroup(
            { context in
                context.duration = duration
                context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                root.animator().alphaValue = 1
            },
            completionHandler: {
                MainActor.assumeIsolated { root.alphaValue = 1 }
            })

        ContextLog.info("cinematic handed off to the welcome card (\(end))", "onboarding")
    }

    /// Esc, at the AppKit level.
    ///
    /// The Skip button already carries `.keyboardShortcut(.cancelAction)`, but this app is an
    /// `.accessory` presenting a borderless window, and whether AppKit routes Esc to a SwiftUI
    /// cancel action there depends on what currently holds first responder. A local monitor does
    /// not: it sees the key event before anything else in this process, which is what "Esc aborts
    /// at any point" has to mean. Removed the instant the cinematic ends, so it can never eat an
    /// Esc that belongs to the onboarding card.
    private static func installEscapeMonitor(_ director: CinematicDirector) {
        removeEscapeMonitor()
        escapeMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            guard event.keyCode == 53 else { return event }
            MainActor.assumeIsolated { director.skip() }
            return nil
        }
    }

    private static func removeEscapeMonitor() {
        if let escapeMonitor { NSEvent.removeMonitor(escapeMonitor) }
        escapeMonitor = nil
    }

    // MARK: - Window construction

    private static func makeWindow(contentRect: NSRect) -> NSWindow {
        let window = KeyableWindow(
            contentRect: contentRect,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.isOpaque = false
        window.backgroundColor = .clear
        // The card draws its own ambient shadow — a broad, diffuse one that AppKit's window shadow
        // cannot express — so the window must not draw a second, tighter one around the transparent
        // margin the card floats in. See `InkGlassShadow`.
        window.hasShadow = false
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.isMovableByWindowBackground = true
        window.isReleasedWhenClosed = false
        window.hidesOnDeactivate = false
        return window
    }

    /// The card's root: the app's shared glass panel, with the SwiftUI card hosted inside it.
    ///
    /// The ground is AppKit's and not SwiftUI's, all of it — material, scrim, corner, edge and
    /// shadow — so there is exactly one owner of "what is under the type" and the SwiftUI side stays
    /// entirely transparent. Two grounds is how a translucent surface ends up opaque in one
    /// appearance and muddy in the other. It is `InkGlassView` and not a pane built here, so this
    /// window cannot drift from the five other surfaces wearing the same glass.
    private static func makeRoot<Content: View>(size: NSSize, hosting content: Content) -> NSView {
        let root = InkGlassView(frame: NSRect(origin: .zero, size: size), style: .floating)
        root.autoresizingMask = [.width, .height]
        root.layoutSubtreeIfNeeded()
        root.setContent(FirstMouseHostingView(rootView: content))
        return root
    }

    /// Centred horizontally, and sitting slightly above true centre — optical centre reads as
    /// centred where geometric centre reads as low. Sized to the *window*, which is the card plus
    /// the margin its shadow needs; the card itself still lands where it always did.
    private static func centredFrame(on screen: NSScreen) -> NSRect {
        placement(of: windowSize, in: screen.visibleFrame)
    }

    /// **Where a card of any size goes inside any usable area, always wholly on screen.**
    ///
    /// Pure, and separated from `NSScreen`, because the failure it prevents is invisible on the
    /// machine it is written on and obvious on somebody else's. The optical-centre nudge is
    /// unconditional arithmetic — `visible.midY - height / 2 + visible.height * 0.05` — and it is
    /// only *safe* while the card is comfortably shorter than the display. It was: at 520 pt the card
    /// needed 702 pt of usable height. Then the card grew to 640 to stop the permissions copy
    /// truncating, which took the requirement to 836 pt — past what a 13-inch display with a Dock
    /// actually has — and the card started hanging off the bottom edge, taking the "I'll do this
    /// later" button with it. That button is the *only* escape from an unanswered permission, so
    /// clipping it strands the run.
    ///
    /// The clamp is last and applies to both axes, so the nudge is a preference that yields rather
    /// than an offset that wins. When the card is genuinely taller than the usable area there is no
    /// right answer left, and it is pinned to the top — losing the foot of a card is survivable,
    /// losing its head means the user cannot tell what they are looking at.
    ///
    /// `OnboardingWindowPlacementTests` sweeps every display this app could plausibly open on, at
    /// every card height, which is the only way the arithmetic above gets exercised at all.
    nonisolated static func placement(of size: NSSize, in visible: NSRect) -> NSRect {
        /// Clamps one axis. `whenTooBig` is the origin to keep when the card is larger than the area
        /// and the two bounds cross — the edge whose content matters most, which is not the same edge
        /// on both axes: the **top** vertically (a card missing its headline cannot be identified)
        /// and the **left** horizontally (that is where every line of it starts).
        func clamp(_ value: CGFloat, low: CGFloat, high: CGFloat, whenTooBig: CGFloat) -> CGFloat {
            guard high >= low else { return whenTooBig }
            return min(max(value, low), high)
        }
        let x = clamp(
            visible.midX - size.width / 2,
            low: visible.minX, high: visible.maxX - size.width, whenTooBig: visible.minX)
        let y = clamp(
            visible.midY - size.height / 2 + visible.height * 0.05,
            low: visible.minY, high: visible.maxY - size.height,
            whenTooBig: visible.maxY - size.height)
        return NSRect(x: x.rounded(), y: y.rounded(), width: size.width, height: size.height)
    }

    /// **A frame that has ended up off screen, put back.** Returns `frame` untouched when it is
    /// already wholly inside `visible`.
    ///
    /// Placing the card once, at creation, is not enough, and assuming it is was the other half of
    /// the clipped-card defect. Three things move a card that was placed correctly:
    ///
    /// - the window is `isMovableByWindowBackground`, so a drag anywhere on the glass moves it, and
    ///   a borderless window is **not** constrained by AppKit the way a titled one is — there is
    ///   nothing to stop it being dragged half off the bottom and nothing to bring it back;
    /// - `visibleFrame` changes underneath it — the Dock shown, hidden, resized or moved, the menu
    ///   bar auto-hiding, a display added or removed — all while the card is faded out mid-yield;
    /// - the card's own height changed in this app's lifetime (520 → 640), which shrank the slack
    ///   every one of the above eats into.
    ///
    /// So it is re-checked on every return from a yield, which is the instant before the user looks
    /// at it again. Only a card that is genuinely outside is moved: one the user dragged somewhere
    /// they wanted it stays where they put it.
    nonisolated static func reclaimed(_ frame: NSRect, into visible: NSRect) -> NSRect {
        visible.contains(frame) ? frame : placement(of: frame.size, in: visible)
    }

    /// `reclaimed`, against whichever screen the card is on — or the pointer's, when it is so far off
    /// screen that AppKit no longer associates it with one.
    private static func reclaimOnScreen(_ window: NSWindow) {
        let pointer = NSEvent.mouseLocation
        let screen =
            window.screen
            ?? NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
            ?? NSScreen.main ?? NSScreen.screens.first
        guard let screen else { return }
        let reclaimed = reclaimed(window.frame, into: screen.visibleFrame)
        guard reclaimed != window.frame else { return }
        ContextLog.info(
            "onboarding card was off the usable area at \(window.frame); moved to \(reclaimed)",
            "onboarding")
        window.setFrame(reclaimed, display: false)
    }

    /// Gets out of the way while the user is dealing with something else on screen — the browser
    /// during sign-in, a TCC prompt, the Screen Recording pane in System Settings.
    ///
    /// The card floats above everything, which is right when it is the thing being read and wrong
    /// the moment it is not: an always-on-top window over the account chooser is something to click
    /// around. Hiding is `orderOut`, not a close, so the step machine underneath keeps running and
    /// the same window comes back with its state intact.
    ///
    /// **It fades.** It used to be a bare `orderOut`, and on the permissions card that is three
    /// vanish-and-reappear pops per grant — the card blinking out of existence and back while the
    /// user is reading it, which is what "it glitches a lot" was. A yield is a step aside, not a
    /// disappearance, so it is a 240 ms fade in both directions; Reduce Motion collapses that to
    /// zero and it is a show/hide again.
    static func setHidden(_ hidden: Bool) {
        guard let window = current else { return }
        // Idempotent on *intent*, not on `isVisible`: mid-fade the window is still visible while
        // hiding and already visible while showing, so `isVisible` would re-arm a transition that is
        // already running and stutter exactly the way this exists to stop.
        guard hidden != isHiddenIntent else { return }
        isHiddenIntent = hidden
        hideGeneration &+= 1
        let generation = hideGeneration
        let duration = InkReduceMotion.duration(InkMotion.stepTransition)

        if hidden {
            NSAnimationContext.runAnimationGroup(
                { context in
                    context.duration = duration
                    context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                    window.animator().alphaValue = 0
                },
                completionHandler: {
                    MainActor.assumeIsolated {
                        // The one rule that cannot be got wrong. This app is `LSUIElement` — no Dock
                        // icon, nothing for a user to click to get the window back — so an `orderOut`
                        // that lands *after* a show request would strand first-run onboarding off
                        // screen with no way back to it. A show that arrived mid-fade always wins.
                        guard
                            hideMayComplete(
                                startedAt: generation, current: hideGeneration, stillHidden: isHiddenIntent),
                            current === window
                        else { return }
                        window.orderOut(nil)
                    }
                })
        } else {
            // Ordered in *before* the fade, and from wherever the alpha currently is: a show that
            // interrupts a half-faded hide picks the card back up rather than restarting it, and a
            // show of an already-ordered-out window starts from zero instead of flashing at full
            // opacity for a frame.
            if !window.isVisible { window.alphaValue = 0 }
            // Before it is looked at again. A yield is exactly when the usable area is most likely to
            // have changed under the card — the user has been in another application, resizing the
            // Dock, plugging in a display, answering a dialog — and a card that comes back with its
            // escape button off the bottom edge is the defect this guards.
            reclaimOnScreen(window)
            // `orderFrontRegardless`, not `makeKeyAndOrderFront` + activate: coming back should not
            // yank focus off whatever the user just finished doing.
            window.orderFrontRegardless()
            NSAnimationContext.runAnimationGroup(
                { context in
                    context.duration = duration
                    context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                    window.animator().alphaValue = 1
                },
                completionHandler: {
                    MainActor.assumeIsolated {
                        guard generation == hideGeneration, current === window else { return }
                        // Pinned regardless of how the animation ended, so the card can never be left
                        // sitting at a partial alpha.
                        window.alphaValue = 1
                    }
                })
        }
    }

    /// Whether a hide that began at `startedAt` is still the current intent by the time its fade
    /// finishes — which is to say, whether it is allowed to take the window off screen.
    ///
    /// A free function on three values rather than two `if`s inside a completion handler, because the
    /// failure it guards against is unobservable after the fact: the window is simply gone, on a
    /// Dock-less app, during first run. The generation is what makes a *second* hide arriving while
    /// the first is still fading not count as the first one completing.
    /// `nonisolated` because it is a function of its three arguments and nothing else — which is the
    /// property that makes it worth extracting at all.
    nonisolated static func hideMayComplete(startedAt: Int, current: Int, stillHidden: Bool) -> Bool {
        startedAt == current && stillHidden
    }

    /// The last thing `setHidden` was asked for, and a token identifying that request.
    private static var isHiddenIntent = false
    private static var hideGeneration = 0

    /// Dissolves the surface. The finale's glow is drawn by `OnboardingView`; this is the fade it
    /// burns out through.
    static func dismiss() {
        guard let window = current else { return }
        current = nil
        isHiddenIntent = false
        // Belt and braces: onboarding cannot finish while the cinematic is still on screen, but if
        // it somehow did, the key monitor must not outlive the window that owns it.
        removeEscapeMonitor()
        cinematicHosting = nil
        cinematicDirector = nil

        let duration: TimeInterval = InkReduceMotion.isEnabled ? 0 : 0.55
        NSAnimationContext.runAnimationGroup(
            { context in
                context.duration = duration
                context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                window.animator().alphaValue = 0
            },
            completionHandler: {
                MainActor.assumeIsolated {
                    window.orderOut(nil)
                    window.close()
                }
            })
    }
}

// MARK: - Window

/// Borderless windows refuse key status by default, which would leave every button unreachable by
/// keyboard and swallow Return on the primary action.
private final class KeyableWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

// MARK: - First mouse
//
// This app is an `.accessory` — it is never the active application when onboarding appears. By
// default AppKit spends the first click activating the window and never delivers it to the control
// underneath, so the user's first press on "Hi Omi!" does nothing at all. Accepting first mouse is
// what makes the very first click count.

private final class FirstMouseView: NSView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

private final class FirstMouseHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}
