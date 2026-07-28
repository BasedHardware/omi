import AppKit
import SwiftUI

/// The onboarding surface: one small, centred oval of glass that dissolves into the desktop.
///
/// No title bar, no traffic lights, no second window — and deliberately **no edge**. The material,
/// the darkness and the colour field are all masked by the same radial falloff, so the surface has
/// no border to notice and no rectangle to read as a dialog. It is a warm spot on the desktop that
/// happens to have words in it.
///
/// The window is larger than the legible area on purpose: the outer third is falloff, and cropping
/// it would put back the hard edge the mask exists to remove.
@MainActor
final class OnboardingWindow {
    /// Fixed size, so the surface never resizes under the user mid-flow. Roughly a third of this is
    /// falloff; `InkLayout.contentMaxWidth` is what actually holds type.
    static let cardSize = NSSize(width: 720, height: 520)

    private static var current: NSWindow?

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
            EarshotLog.error("no screen available to present onboarding", "onboarding")
            return
        }

        let frame = centredFrame(on: screen)

        let window = KeyableWindow(
            contentRect: frame,
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

        // Not layer-backed with a colour: the root has to stay clear, or it paints the rectangle
        // the mask is there to dissolve.
        let root = FirstMouseView(frame: NSRect(origin: .zero, size: frame.size))
        root.autoresizingMask = [.width, .height]

        // Deliberately no NSVisualEffectView. Its material is a rectangle, and every way of
        // masking one down to an ellipse leaves a faint straight edge somewhere. The surface is
        // painted entirely in SwiftUI instead, where a single elliptical mask is exact.

        let hosting = FirstMouseHostingView(rootView: OnboardingView())
        hosting.frame = root.bounds
        hosting.autoresizingMask = [.width, .height]
        root.addSubview(hosting)

        window.contentView = root
        window.setFrame(frame, display: true)

        current = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    /// Centred horizontally, and sitting slightly above true centre — optical centre reads as
    /// centred where geometric centre reads as low.
    private static func centredFrame(on screen: NSScreen) -> NSRect {
        let visible = screen.visibleFrame
        let x = visible.midX - cardSize.width / 2
        let y = visible.midY - cardSize.height / 2 + visible.height * 0.05
        return NSRect(x: x.rounded(), y: y.rounded(), width: cardSize.width, height: cardSize.height)
    }

    /// Dissolves the surface. The finale's glow is drawn by `OnboardingView`; this is the fade it
    /// burns out through.
    static func dismiss() {
        guard let window = current else { return }
        current = nil

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
