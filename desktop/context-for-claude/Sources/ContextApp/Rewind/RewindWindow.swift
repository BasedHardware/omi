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
        let container = NSView(frame: NSRect(origin: .zero, size: window.frame.size))
        container.autoresizingMask = [.width, .height]
        window.contentView = container

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
