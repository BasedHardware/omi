import AppKit
import SwiftUI

/// The onboarding surface: one small, centred oval of paper that dissolves into the desktop.
///
/// No title bar, no traffic lights, no second window — and deliberately **no edge**. The paper
/// floor and the warm wash over it are masked by the same radial falloff, so the surface has no
/// border to notice and no rectangle to read as a dialog. It is a sheet lying on the desktop that
/// happens to have words on it.
///
/// The window is larger than the legible area on purpose: the outer third is falloff, and cropping
/// it would put back the hard edge the mask exists to remove.
@MainActor
final class OnboardingWindow {
    /// Fixed size, so the surface never resizes under the user mid-flow. Roughly a third of this is
    /// falloff; `InkLayout.contentMaxWidth` is what actually holds type.
    static let cardSize = NSSize(width: 720, height: 520)

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
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = duration
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            root.animator().alphaValue = 1
        }, completionHandler: {
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
        // A shadow would trace the window's rectangle around an oval that has no edge — the one
        // thing that gives the illusion away.
        window.hasShadow = false
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.isMovableByWindowBackground = true
        window.isReleasedWhenClosed = false
        window.hidesOnDeactivate = false
        return window
    }

    /// Not layer-backed with a colour: the root has to stay clear, or it paints the rectangle the
    /// mask is there to dissolve.
    ///
    /// Deliberately no NSVisualEffectView. Its material is a rectangle, and every way of masking one
    /// down to an ellipse leaves a faint straight edge somewhere. The surface is painted entirely in
    /// SwiftUI instead, where a single elliptical mask is exact.
    private static func makeRoot<Content: View>(size: NSSize, hosting content: Content) -> NSView {
        let root = FirstMouseView(frame: NSRect(origin: .zero, size: size))
        root.autoresizingMask = [.width, .height]

        let hosting = FirstMouseHostingView(rootView: content)
        hosting.frame = root.bounds
        hosting.autoresizingMask = [.width, .height]
        root.addSubview(hosting)
        return root
    }

    /// Centred horizontally, and sitting slightly above true centre — optical centre reads as
    /// centred where geometric centre reads as low.
    private static func centredFrame(on screen: NSScreen) -> NSRect {
        let visible = screen.visibleFrame
        let x = visible.midX - cardSize.width / 2
        let y = visible.midY - cardSize.height / 2 + visible.height * 0.05
        return NSRect(x: x.rounded(), y: y.rounded(), width: cardSize.width, height: cardSize.height)
    }

    /// Gets out of the way while the user is dealing with something else on screen — the browser
    /// during sign-in, a TCC prompt, the Screen Recording pane in System Settings.
    ///
    /// The card floats above everything, which is right when it is the thing being read and wrong
    /// the moment it is not: an always-on-top window over the account chooser is something to click
    /// around. Hiding is `orderOut`, not a close, so the step machine underneath keeps running and
    /// the same window comes back with its state intact.
    static func setHidden(_ hidden: Bool) {
        guard let window = current else { return }
        if hidden {
            guard window.isVisible else { return }
            window.orderOut(nil)
        } else {
            guard !window.isVisible else { return }
            // `orderFrontRegardless`, not `makeKeyAndOrderFront` + activate: coming back should not
            // yank focus off whatever the user just finished doing.
            window.alphaValue = 1
            window.orderFrontRegardless()
        }
    }

    /// Dissolves the surface. The finale's glow is drawn by `OnboardingView`; this is the fade it
    /// burns out through.
    static func dismiss() {
        guard let window = current else { return }
        current = nil
        // Belt and braces: onboarding cannot finish while the cinematic is still on screen, but if
        // it somehow did, the key monitor must not outlive the window that owns it.
        removeEscapeMonitor()
        cinematicHosting = nil
        cinematicDirector = nil

        let duration: TimeInterval = InkReduceMotion.isEnabled ? 0 : 0.55
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = duration
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            window.animator().alphaValue = 0
        }, completionHandler: {
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
